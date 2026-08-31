"""Verify noncanonical Observatory v2 foundation schemas and synthetic fixtures.

This verifier intentionally checks only deterministic structural and cross-record
invariants available in the repository. Passing it does not establish substantive
truth, canonical publication authority, or complete JSON Schema conformance.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_ASSERTION_SCHEMA = ROOT / "schemas" / "observatory-v2-assertion.schema.json"
DEFAULT_OBSERVATION_SCHEMA = ROOT / "schemas" / "observatory-v1-observation.schema.json"
DEFAULT_ASSERTION_EXAMPLE = ROOT / "fixtures" / "v2-foundation" / "assertion.example.json"
DEFAULT_OBSERVATION_EXAMPLE = ROOT / "fixtures" / "v2-foundation" / "observation.example.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TEMPORAL_PRECISIONS = {"TIMESTAMP", "DATE", "MONTH", "YEAR", "INTERVAL", "UNRESOLVED"}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _require_keys(record: dict[str, Any], keys: list[str], *, label: str) -> None:
    missing = [key for key in keys if key not in record]
    if missing:
        raise ValueError(f"{label} missing required keys: {missing}")


def _verify_temporal(value: Any, *, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"value", "precision"}:
        raise ValueError(f"{label} must be an explicit temporal value object")
    raw = value["value"]
    precision = value["precision"]
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{label}.value must be a non-empty string")
    if precision not in TEMPORAL_PRECISIONS:
        raise ValueError(f"{label}.precision is invalid: {precision!r}")
    if precision == "TIMESTAMP":
        candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError(f"{label} is not an ISO/RFC3339 timestamp: {raw!r}") from exc
    elif precision == "DATE":
        try:
            date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"{label} is not an ISO date: {raw!r}") from exc
    elif precision == "YEAR" and not re.fullmatch(r"\d{4}", raw):
        raise ValueError(f"{label} YEAR precision must preserve a four-digit year")
    elif precision == "MONTH" and not re.fullmatch(r"\d{4}-\d{2}", raw):
        raise ValueError(f"{label} MONTH precision must use YYYY-MM")


def verify(
    assertion_schema_path: Path = DEFAULT_ASSERTION_SCHEMA,
    observation_schema_path: Path = DEFAULT_OBSERVATION_SCHEMA,
    assertion_example_path: Path = DEFAULT_ASSERTION_EXAMPLE,
    observation_example_path: Path = DEFAULT_OBSERVATION_EXAMPLE,
) -> dict[str, Any]:
    assertion_schema = _load(assertion_schema_path)
    observation_schema = _load(observation_schema_path)
    assertion = _load(assertion_example_path)
    observation = _load(observation_example_path)

    for schema, expected_id in (
        (assertion_schema, "observatory-v2-assertion.schema.json"),
        (observation_schema, "observatory-v1-observation.schema.json"),
    ):
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValueError(f"{expected_id} must use JSON Schema 2020-12")
        if schema.get("$id") != expected_id:
            raise ValueError(f"Schema ID mismatch for {expected_id}")
        if schema.get("additionalProperties") is not False:
            raise ValueError(f"{expected_id} must fail closed on undeclared top-level fields")

    _require_keys(
        assertion,
        [
            "schema_version",
            "assertion_id",
            "subject_id",
            "predicate",
            "observed_at",
            "knowledge_time_state",
            "source_ids",
            "observation_ids",
            "source_linkage_state",
            "evidence_state",
            "verification_state",
            "review_state",
            "claim_boundary",
            "record_state",
            "authority_boundary",
        ],
        label="assertion example",
    )
    _require_keys(
        observation,
        [
            "schema_version",
            "observation_id",
            "source_id",
            "observed_at",
            "retrieval_method",
            "retrieval_outcome",
            "capture_state",
            "redistribution_state",
            "protected_bytes_in_record",
            "authority_boundary",
        ],
        label="observation example",
    )

    if assertion["schema_version"] != "2.0.0-draft":
        raise ValueError("Assertion example must remain on the draft v2 schema")
    if observation["schema_version"] != "1.0.0-draft":
        raise ValueError("Observation example must remain on the draft observation schema")
    if assertion.get("record_state") != "NONCANONICAL_CANDIDATE":
        raise ValueError("Foundation assertion fixture must remain explicitly noncanonical")
    if observation.get("protected_bytes_in_record") is not False:
        raise ValueError("Public observation fixture must not contain protected evidence bytes")

    has_object = "object_id" in assertion
    has_value = "value" in assertion
    if has_object == has_value:
        raise ValueError("Assertion must contain exactly one of object_id or value")

    if not re.fullmatch(r"AST-[A-Za-z0-9._:-]+", str(assertion["assertion_id"])):
        raise ValueError("Invalid assertion_id")
    if not re.fullmatch(r"OBS-[A-Za-z0-9._:-]+", str(observation["observation_id"])):
        raise ValueError("Invalid observation_id")
    if not re.fullmatch(r"[A-Z][A-Z0-9_:-]*", str(assertion["predicate"])):
        raise ValueError("Invalid assertion predicate")

    if assertion["knowledge_time_state"] not in {
        "OBSERVED_AT_CAPTURE",
        "EXACT_PREDECESSOR_TIME",
        "PREDECESSOR_TIME_UNRESOLVED",
    }:
        raise ValueError("Invalid assertion knowledge_time_state")
    if assertion["source_linkage_state"] not in {
        "SOURCE_LINKED",
        "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED",
    }:
        raise ValueError("Invalid assertion source_linkage_state")

    if assertion["knowledge_time_state"] == "PREDECESSOR_TIME_UNRESOLVED":
        if assertion["observed_at"] is not None:
            raise ValueError("Unresolved predecessor knowledge time must not fabricate observed_at")
    else:
        _verify_temporal(assertion["observed_at"], label="assertion observed_at")

    if assertion["source_linkage_state"] == "SOURCE_LINKED":
        if not assertion["source_ids"]:
            raise ValueError("SOURCE_LINKED assertion must carry at least one source_id")
    else:
        if assertion["source_ids"]:
            raise ValueError("Unresolved predecessor source linkage must not invent source_ids")
        if assertion["review_state"] != "MIGRATED_PREDECESSOR_STATE":
            raise ValueError("Source-unresolved assertion is permitted only for migrated predecessor state")
        if assertion["record_state"] != "NONCANONICAL_CANDIDATE":
            raise ValueError("Source-unresolved assertion must remain noncanonical")

    _verify_temporal(observation["observed_at"], label="observation observed_at")
    for label, temporal in (
        ("assertion valid_from", assertion.get("valid_from")),
        ("assertion valid_until", assertion.get("valid_until")),
        ("assertion adjudicated_at", assertion.get("adjudicated_at")),
        ("observation source_published_at", observation.get("source_published_at")),
        ("observation source_effective_at", observation.get("source_effective_at")),
    ):
        if temporal is not None:
            _verify_temporal(temporal, label=label)

    content_sha = observation.get("content_sha256")
    if content_sha is not None and not SHA256_RE.fullmatch(str(content_sha)):
        raise ValueError("Invalid content_sha256")
    normalized_sha = observation.get("normalized_content_sha256")
    if normalized_sha is not None and not SHA256_RE.fullmatch(str(normalized_sha)):
        raise ValueError("Invalid normalized_content_sha256")

    if observation["source_id"] not in assertion["source_ids"]:
        raise ValueError("Assertion source_ids must include the linked observation source")
    if observation["observation_id"] not in assertion["observation_ids"]:
        raise ValueError("Assertion observation_ids must include the linked observation")

    forbidden_capture_tokens = ("/home/", "/Users/", "C:\\", "token=", "secret=", "password=")
    capture_reference = str(observation.get("capture_reference_class") or "")
    if any(token in capture_reference for token in forbidden_capture_tokens):
        raise ValueError("Public observation capture reference appears to contain a local path or secret")

    return {
        "assertion_schema": assertion_schema["$id"],
        "observation_schema": observation_schema["$id"],
        "assertion_id": assertion["assertion_id"],
        "observation_id": observation["observation_id"],
        "source_id": observation["source_id"],
        "record_state": assertion["record_state"],
        "protected_bytes_in_record": observation["protected_bytes_in_record"],
        "authority_boundary": "STRUCTURAL_TEST_ONLY_NO_SUBSTANTIVE_OR_PUBLICATION_AUTHORITY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assertion-schema", type=Path, default=DEFAULT_ASSERTION_SCHEMA)
    parser.add_argument("--observation-schema", type=Path, default=DEFAULT_OBSERVATION_SCHEMA)
    parser.add_argument("--assertion-example", type=Path, default=DEFAULT_ASSERTION_EXAMPLE)
    parser.add_argument("--observation-example", type=Path, default=DEFAULT_OBSERVATION_EXAMPLE)
    args = parser.parse_args()
    result = verify(
        args.assertion_schema,
        args.observation_schema,
        args.assertion_example,
        args.observation_example,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
