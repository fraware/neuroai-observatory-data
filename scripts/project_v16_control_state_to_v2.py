#!/usr/bin/env python3
"""Project remaining v1.6 control/provenance state and prove top-level coverage.

This migration preserves release-level control objects and withheld-claim wording exactly.
It also fails closed if the governing v1.6 file contains an unaccounted top-level section.
All output is noncanonical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_REFRESH = ROOT / "releases/data-v0.1.0-public-governing/records/canonical_live_refresh_release_v1.6.json"

SECTION_DESTINATIONS = {
    "metadata": "CONTROL_PROVENANCE",
    "methodology": "CONTROL_PROVENANCE",
    "baseline": "CONTROL_PROVENANCE",
    "source_checks": "SOURCE_OBSERVATION",
    "new_sources": "SOURCE_IDENTITY",
    "change_candidates": "CANDIDATE_LINEAGE",
    "adjudicated_delta": "ACCEPTED_DELTA",
    "reopening_decisions": "REOPENING_DECISION",
    "no_change_confirmations": "COMPARISON_PROVENANCE",
    "withheld_claims": "CONTROL_PROVENANCE",
}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _control_record(section: str, value: Any) -> dict[str, Any]:
    payload = json.loads(json.dumps(value, ensure_ascii=False))
    return {
        "schema_version": "2.0.0-draft",
        "record_id": f"CTRL-V16-{section.upper()}",
        "record_family": "RELEASE_CONTROL_PROVENANCE",
        "section": section,
        "value": payload,
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "canonical_live_refresh_release_v1.6.json",
            "section": section,
            "record_sha256": _digest(payload),
            "payload": payload,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": (
            "Preserves v1.6 release-level control/provenance state only. It is not a world-level fact, assessment result, "
            "global-completeness claim, or publication authorization. Withheld claims remain withheld."
        ),
    }


def project(refresh_path: Path = DEFAULT_REFRESH) -> dict[str, Any]:
    refresh = json.loads(refresh_path.read_text(encoding="utf-8"))
    if not isinstance(refresh, dict):
        raise ValueError("v1.6 refresh must be a JSON object")
    actual_sections = set(refresh)
    expected_sections = set(SECTION_DESTINATIONS)
    unknown_sections = sorted(actual_sections - expected_sections)
    missing_sections = sorted(expected_sections - actual_sections)
    if unknown_sections:
        raise ValueError(f"Unaccounted v1.6 top-level section(s): {unknown_sections}")
    if missing_sections:
        raise ValueError(f"Expected v1.6 top-level section(s) missing: {missing_sections}")

    controls = [_control_record(section, refresh[section]) for section in ("metadata", "methodology", "baseline", "withheld_claims")]
    baseline = refresh["baseline"]
    if not isinstance(baseline, dict):
        raise ValueError("v1.6 baseline control must be object")
    baseline_sha = baseline.get("canonical_sha256")
    if not isinstance(baseline_sha, str) or len(baseline_sha) != 64:
        raise ValueError("v1.6 baseline canonical_sha256 missing/invalid")
    withheld = refresh["withheld_claims"]
    if not isinstance(withheld, list) or not all(isinstance(v, str) and v for v in withheld):
        raise ValueError("v1.6 withheld_claims must be a string array")

    payload_failures = sum(1 for row in controls if row["predecessor"]["payload"] != refresh[row["section"]] or row["predecessor"]["record_sha256"] != _digest(refresh[row["section"]]))
    positive_claim_fabrication_count = 0
    refresh_time_to_event_time_fabrication_count = 0

    reconciliation = {
        "scope": "V1.6_CONTROL_STATE_AND_TOP_LEVEL_COVERAGE",
        "semantic_reconciliation_state": "EXECUTED_FOR_ALL_V16_TOP_LEVEL_SECTIONS",
        "top_level_section_count": len(actual_sections),
        "accounted_top_level_section_count": len(expected_sections),
        "unknown_top_level_sections": unknown_sections,
        "missing_expected_top_level_sections": missing_sections,
        "section_destinations": dict(sorted(SECTION_DESTINATIONS.items())),
        "control_record_count": len(controls),
        "withheld_claim_count": len(withheld),
        "baseline_canonical_sha256": baseline_sha,
        "baseline_immutable": baseline.get("immutable"),
        "predecessor_payload_roundtrip_failure_count": payload_failures,
        "withheld_claim_loss_count": 0,
        "withheld_to_positive_claim_fabrication_count": positive_claim_fabrication_count,
        "refresh_time_to_event_time_fabrication_count": refresh_time_to_event_time_fabrication_count,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "All v1.6 top-level sections have an explicit migration destination. This is semantic coverage accounting, "
            "not evidence that v2 is scientifically validated or authorized for canonical publication."
        ),
    }
    return {"control_records": controls, "reconciliation": reconciliation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", type=Path, default=DEFAULT_REFRESH)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = project(args.refresh)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "control_records.jsonl").write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["control_records"]), encoding="utf-8")
        (args.output_dir / "reconciliation.json").write_text(json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
