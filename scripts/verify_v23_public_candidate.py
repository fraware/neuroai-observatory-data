#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = ROOT / "releases" / "data-v0.2.0-v2.3.0-dev-candidate"
EXPECTED_REPORT_SHA = "323bccc3c7ff0a2cb911b4668ada24d3693ea6c705cf0a32ce7c33f856f6d6dc"
EXPECTED_DELTA_SHA = "86d7a2ce102765b165ceda704622da686a0ef872e74d3663fefe676a8f917c99"
EXPECTED_SUCCESSOR_SHA = "0ca19a25c118f2d25406d9b4694dbd1e3e80afa092446860f0fd311c4cfb718f"
EXPECTED_PREDECESSOR_SHA = "9cc36aacb4c791c9830990b58e144f223925f3ad492016abaea44727b48a0b70"
EXPECTED_WORKBENCH_COMMIT = "e01b56f96b494f40f026181fa9f01f2c91926f30"
FAILURES = {
    ("SRC-0041", "HTTP_ERROR_UNCLASSIFIED", "HTTP_ERROR"),
    ("SRC-0115", "HTTP_ERROR_UNCLASSIFIED", "HTTP_ERROR"),
    ("SRC-0124", "TIMEOUT", "TIMEOUT"),
    ("SRC-14-007", "HTTP_ERROR_UNCLASSIFIED", "HTTP_ERROR"),
}
PROHIBITED_PATH_PATTERNS = (
    re.compile(r"/home/runner/"),
    re.compile(r"/mnt/"),
    re.compile(r"/tmp/"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\"),
)


class VerificationError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def verify_manifest(release: Path) -> None:
    manifest = release / "SHA256SUMS.txt"
    rows: list[tuple[str, str]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        rows.append((rel, digest))
    expected = sorted(
        p.relative_to(release).as_posix()
        for root in (release / "records", release / "verification")
        for p in root.rglob("*")
        if p.is_file()
    )
    if [rel for rel, _ in rows] != expected:
        raise VerificationError("Manifest file population drift")
    for rel, digest in rows:
        observed = hashlib.sha256((release / rel).read_bytes()).hexdigest()
        if observed != digest:
            raise VerificationError(f"Manifest digest mismatch: {rel}")
    descriptor = load(release / "release-descriptor.json")
    observed_manifest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if descriptor.get("manifest_sha256") != observed_manifest:
        raise VerificationError("Descriptor manifest digest mismatch")


def verify_schema_contract(release: Path) -> None:
    paths = [
        release / "release-descriptor.json",
        *sorted((release / "records").rglob("*.json")),
        *sorted((release / "verification").rglob("*.json")),
    ]
    for path in paths:
        value = load(path)
        for key in ("schema_version", "artifact", "status", "authority_boundary"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise VerificationError(f"{path}: missing generic schema field {key}")
        if value["schema_version"] != "1.0.0":
            raise VerificationError(f"{path}: unsupported schema version")


def verify_semantics(release: Path) -> None:
    descriptor = load(release / "release-descriptor.json")
    if descriptor["status"] != "CANDIDATE_PUBLIC_PROJECTION_NOT_CANONICAL":
        raise VerificationError("Bad release status")
    if descriptor["workbench"]["merged_main_commit"] != EXPECTED_WORKBENCH_COMMIT:
        raise VerificationError("Workbench commit drift")
    if descriptor["predecessor"]["v1_7_snapshot_sha256"] != EXPECTED_PREDECESSOR_SHA:
        raise VerificationError("Predecessor drift")
    if descriptor["comparative_refresh"]["comparative_refresh_report_sha256"] != EXPECTED_REPORT_SHA:
        raise VerificationError("Report digest drift")
    if descriptor["comparative_refresh"]["accepted_development_delta_sha256"] != EXPECTED_DELTA_SHA:
        raise VerificationError("Delta digest drift")
    if descriptor["comparative_refresh"]["candidate_successor_sha256"] != EXPECTED_SUCCESSOR_SHA:
        raise VerificationError("Successor digest drift")
    if descriptor["governance_state"] != "DEFERRED" or descriptor["governance_layer_applied"] is not False:
        raise VerificationError("Governance authority crossed")
    if descriptor["canonical_publication_state"] != "NOT_AUTHORIZED" or descriptor["canonical_successor_written"] is not False:
        raise VerificationError("Publication authority crossed")
    if descriptor["assessment_mutation_performed"] is not False or descriptor["current_pointer_updated"] is not False:
        raise VerificationError("Forbidden mutation declared")

    outcomes = load(release / "records/comparisons/source-outcomes.json")["records"]
    if len(outcomes) != 25 or len({row["source_id"] for row in outcomes}) != 25:
        raise VerificationError("Source outcome population drift")
    if Counter(row["outcome_type"] for row in outcomes) != Counter(
        {"CONTENT_CHANGED": 14, "NO_CHANGE": 7, "HTTP_ERROR_UNCLASSIFIED": 3, "TIMEOUT": 1}
    ):
        raise VerificationError("Source outcome count drift")
    if any(row.get("finding_effect") != "NONE" for row in outcomes):
        raise VerificationError("Retrieval outcome promoted into finding effect")
    failures = {
        (row["source_id"], row["outcome_type"], row["failure_class"])
        for row in outcomes
        if row["outcome_type"] not in {"CONTENT_CHANGED", "NO_CHANGE"}
    }
    if failures != FAILURES:
        raise VerificationError(f"Typed failure drift: {failures}")

    comparisons = load(release / "records/comparisons/comparison-index.json")["records"]
    if len(comparisons) != 21 or len({row["source_id"] for row in comparisons}) != 21:
        raise VerificationError("Comparison population drift")
    if Counter(row["classification"] for row in comparisons) != Counter(
        {"STRUCTURED_RECORD_FIELD_CHANGE": 1, "SUBSTANTIVE_NORMALIZED_TEXT_CHANGE": 13, "BYTE_IDENTICAL": 7}
    ):
        raise VerificationError("Comparison classification drift")
    fda = next(row for row in comparisons if row["source_id"] == "SRC-0004")
    if fda.get("changed_structured_paths") != ["meta.last_updated"]:
        raise VerificationError("Structured FDA change-path drift")

    delta = load(release / "records/delta/development-delta-reference.json")
    if delta["operation_count"] != 14 or delta["delta_sha256"] != EXPECTED_DELTA_SHA:
        raise VerificationError("Delta reference drift")
    if delta["operation_bodies_in_this_repository"] is not False or delta["substantive_authority"] is not False:
        raise VerificationError("Delta body/authority boundary crossed")
    reopening = load(release / "records/reopening/reopening-analysis-reference.json")
    if reopening["recommendation_count"] != 112 or reopening["assessment_mutation_performed"] is not False:
        raise VerificationError("Reopening boundary drift")


def verify_no_protected_paths(release: Path) -> None:
    paths = [
        release / "release-descriptor.json",
        release / "SHA256SUMS.txt",
        *sorted((release / "records").rglob("*")),
        *sorted((release / "verification").rglob("*")),
    ]
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PROHIBITED_PATH_PATTERNS:
            if pattern.search(text):
                raise VerificationError(f"Protected/local path pattern in {path}")
    scan = load(release / "verification/protected-data-scan.json")
    if scan["result"] != "PASS" or scan["prohibited_content_found"] is not False:
        raise VerificationError("Protected-data scan record is not fail-closed PASS")


def verify_all(release: Path = DEFAULT_RELEASE) -> None:
    verify_manifest(release)
    verify_schema_contract(release)
    verify_semantics(release)
    verify_no_protected_paths(release)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    args = parser.parse_args(argv)
    verify_all(args.release.resolve())
    print("v2.3 public candidate verification: PASS")
    print("source outcomes: 25 | comparisons: 21 | candidates: 14 | delta ops referenced: 14 | reopening recommendations referenced: 112")
    print("governance: DEFERRED | canonical publication: NOT_AUTHORIZED | assessment mutation: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
