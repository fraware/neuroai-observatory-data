"""Project v1.4 public source records into the draft Observatory v2 source model.

This is a deliberately narrow, noncanonical migration vertical slice. It projects
only `canonical_observatory_release_v1.4.json:sources`, preserves every predecessor
source payload byte-semantically through canonical JSON and digest binding, and
creates observation metadata only when the predecessor actually records a
retrieval time. It does not migrate organizations or authorize a v2 successor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_BASELINE = (
    ROOT
    / "releases"
    / "data-v0.1.0-public-governing"
    / "records"
    / "canonical_observatory_release_v1.4.json"
)


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _temporal_value(raw: str) -> dict[str, str]:
    """Preserve the predecessor value exactly while classifying known precision."""
    if re.fullmatch(r"\d{4}", raw):
        precision = "YEAR"
    elif re.fullmatch(r"\d{4}-\d{2}", raw):
        precision = "MONTH"
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        precision = "DATE"
    elif "T" in raw:
        precision = "TIMESTAMP"
    else:
        precision = "UNRESOLVED"
    return {"value": raw, "precision": precision}


def _require_text(record: dict[str, Any], key: str, *, source_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source_id}: required predecessor field {key!r} is missing/empty")
    return value


def _observation_id(source_id: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._:-]", "-", source_id)
    return f"OBS-MIG-V14-{token}"


def project_source(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    source_id = _require_text(record, "source_id", source_id="<unknown-source>")
    title = _require_text(record, "title", source_id=source_id)
    publisher = _require_text(record, "publisher", source_id=source_id)
    locator = _require_text(record, "url", source_id=source_id)
    source_class = _require_text(record, "source_class", source_id=source_id)

    legacy_ids = record.get("legacy_source_ids")
    if legacy_ids is None:
        normalized_legacy_ids: list[str] = []
    elif isinstance(legacy_ids, list) and all(isinstance(item, str) for item in legacy_ids):
        normalized_legacy_ids = list(legacy_ids)
    else:
        raise ValueError(f"{source_id}: legacy_source_ids must be a string array when present")

    claim_boundary = record.get("claim_boundary")
    if claim_boundary is not None and not isinstance(claim_boundary, str):
        raise ValueError(f"{source_id}: claim_boundary must be string/null")

    predecessor_payload = json.loads(json.dumps(record, ensure_ascii=False))
    source = {
        "schema_version": "2.0.0-draft",
        "source_id": source_id,
        "title": title,
        "publisher": publisher,
        "canonical_locator": locator,
        "source_class": source_class,
        "legacy_source_ids": normalized_legacy_ids,
        "source_claim_boundary": claim_boundary,
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_observatory_release_v1.4.json",
            "section": "sources",
            "record_id": source_id,
            "record_sha256": _digest(predecessor_payload),
            "payload": predecessor_payload,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": (
            "This migrated source preserves a v1.4 public predecessor record and normalized "
            "logical source identity only. It does not establish source authenticity, "
            "substantive truth, currentness beyond the predecessor evidence, or canonical v2 publication authority."
        ),
    }

    retrieved = record.get("retrieved")
    if retrieved is None:
        return source, None
    if not isinstance(retrieved, str) or not retrieved:
        raise ValueError(f"{source_id}: retrieved must be a non-empty string when present")

    observation = {
        "schema_version": "1.0.0-draft",
        "observation_id": _observation_id(source_id),
        "source_id": source_id,
        "observed_at": _temporal_value(retrieved),
        "retrieval_method": "MIGRATED_PREDECESSOR_RETRIEVAL_RECORD",
        "retrieval_outcome": "PREDECESSOR_RECORDED_OBSERVATION",
        "requested_locator": None,
        "resolved_locator": None,
        "http_status": None,
        "content_type": None,
        "content_sha256": None,
        "normalized_content_sha256": None,
        "capture_state": "CAPTURE_STATE_UNRESOLVED",
        "capture_reference_class": None,
        "redistribution_state": "RIGHTS_UNRESOLVED",
        "collector_or_operator_version": None,
        "source_published_at": None,
        "source_effective_at": None,
        "protected_bytes_in_record": False,
        "authority_boundary": (
            "The predecessor records a retrieval/verification date but this migration does not "
            "invent transport metadata, capture custody, content hashes, redistribution rights, "
            "or source authenticity that the predecessor source record did not encode."
        ),
    }
    return source, observation


def project(baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    predecessor_sources = payload.get("sources")
    if not isinstance(predecessor_sources, list):
        raise ValueError("v1.4 baseline must contain a sources array")

    seen_ids: set[str] = set()
    sources: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    core_mismatches = 0
    payload_roundtrip_failures = 0
    claim_boundary_losses = 0
    source_reference_losses = 0
    temporal_precision_fabrications = 0

    for predecessor in predecessor_sources:
        if not isinstance(predecessor, dict):
            raise ValueError("Every v1.4 source must be an object")
        source, observation = project_source(predecessor)
        source_id = source["source_id"]
        if source_id in seen_ids:
            raise ValueError(f"Duplicate predecessor source_id: {source_id}")
        seen_ids.add(source_id)

        expected_core = {
            "source_id": predecessor.get("source_id"),
            "title": predecessor.get("title"),
            "publisher": predecessor.get("publisher"),
            "canonical_locator": predecessor.get("url"),
            "source_class": predecessor.get("source_class"),
        }
        actual_core = {key: source[key] for key in expected_core}
        if actual_core != expected_core:
            core_mismatches += 1

        if source["predecessor"]["payload"] != predecessor:
            payload_roundtrip_failures += 1
        if source["predecessor"]["record_sha256"] != _digest(predecessor):
            payload_roundtrip_failures += 1
        if source["source_claim_boundary"] != predecessor.get("claim_boundary"):
            claim_boundary_losses += 1
        if source["source_id"] != predecessor.get("source_id"):
            source_reference_losses += 1

        retrieved = predecessor.get("retrieved")
        if observation is not None:
            if observation["source_id"] != source_id:
                source_reference_losses += 1
            if observation["observed_at"]["value"] != retrieved:
                temporal_precision_fabrications += 1
            observations.append(observation)
        elif retrieved is not None:
            temporal_precision_fabrications += 1

        sources.append(source)

    source_ids = [row["source_id"] for row in sources]
    observation_ids = [row["observation_id"] for row in observations]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Projected source IDs are not unique")
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("Projected observation IDs are not unique")

    reconciliation = {
        "scope": "V1.4_SOURCES_ONLY",
        "semantic_reconciliation_state": "EXECUTED_FOR_SOURCE_VERTICAL_SLICE_ONLY",
        "input_source_count": len(predecessor_sources),
        "projected_source_count": len(sources),
        "projected_observation_count": len(observations),
        "normalized_core_mismatch_count": core_mismatches,
        "predecessor_payload_roundtrip_failure_count": payload_roundtrip_failures,
        "source_field_loss_count": payload_roundtrip_failures,
        "claim_boundary_loss_count": claim_boundary_losses,
        "source_reference_loss_count": source_reference_losses,
        "temporal_precision_fabrication_count": temporal_precision_fabrications,
        "invented_predecessor_field_value_count": 0,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Zero reconciliation counts, if achieved, apply only to the v1.4 public source-record "
            "vertical slice and rely on exact predecessor-payload preservation. They do not prove "
            "organization/event/relationship/assertion migration, scientific truth, global completeness, "
            "or canonical v2 publication readiness."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_SOURCE_MIGRATION_VERTICAL_SLICE",
        "input_release": "data-v0.1.0-public-governing",
        "input_file": "canonical_observatory_release_v1.4.json",
        "sources": sources,
        "observations": observations,
        "reconciliation": reconciliation,
    }


def write_projection(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources_path = output_dir / "sources.jsonl"
    observations_path = output_dir / "observations.jsonl"
    reconciliation_path = output_dir / "reconciliation.json"
    sources_path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["sources"]),
        encoding="utf-8",
    )
    observations_path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["observations"]),
        encoding="utf-8",
    )
    reconciliation_path.write_text(
        json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "sources": str(sources_path),
        "observations": str(observations_path),
        "reconciliation": str(reconciliation_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = project(args.baseline.resolve())
    if args.output_dir:
        outputs = write_projection(result, args.output_dir.resolve())
        print(json.dumps({"reconciliation": result["reconciliation"], "outputs": outputs}, indent=2, sort_keys=True))
    else:
        print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
