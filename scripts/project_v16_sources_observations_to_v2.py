"""Project v1.6 new-source identities and source checks into draft v2 Source/Observation records."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_REFRESH = ROOT / "releases/data-v0.1.0-public-governing/records/canonical_live_refresh_release_v1.6.json"


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _temporal(raw: str) -> dict[str, str]:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        precision = "DATE"
    elif re.fullmatch(r"\d{4}-\d{2}", raw):
        precision = "MONTH"
    elif re.fullmatch(r"\d{4}", raw):
        precision = "YEAR"
    elif "T" in raw:
        precision = "TIMESTAMP"
    else:
        precision = "UNRESOLVED"
    return {"value": raw, "precision": precision}


def _observation_id(check_id: str) -> str:
    return f"OBS-MIG-V16-{check_id}"


def project(refresh_path: Path = DEFAULT_REFRESH) -> dict[str, Any]:
    refresh = json.loads(refresh_path.read_text(encoding="utf-8"))
    checks = refresh.get("source_checks")
    new_sources = refresh.get("new_sources")
    if not isinstance(checks, list) or not isinstance(new_sources, list):
        raise ValueError("v1.6 source_checks/new_sources required")

    new_by_id = {row.get("source_id"): row for row in new_sources if isinstance(row, dict)}
    if len(new_by_id) != len(new_sources):
        raise ValueError("duplicate/missing v1.6 new source id")

    sources: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for record in new_sources:
        source_id = record["source_id"]
        predecessor = json.loads(json.dumps(record, ensure_ascii=False))
        sources.append(
            {
                "schema_version": "2.0.0-draft",
                "source_id": source_id,
                "title": record["title"],
                "publisher": record["publisher"],
                "canonical_locator": record["url"],
                "source_class": record["source_class"],
                "legacy_source_ids": [],
                "source_claim_boundary": record.get("claim_boundary"),
                "predecessor": {
                    "release_id": "data-v0.1.0-public-governing",
                    "file": "canonical_live_refresh_release_v1.6.json",
                    "section": "new_sources",
                    "record_id": source_id,
                    "record_sha256": _digest(predecessor),
                    "payload": predecessor,
                },
                "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
                "authority_boundary": (
                    "Migrated v1.6 source identity only. Source registration and successful retrieval do not establish substantive truth, independent verification, regulatory authorization, clinical effectiveness, system conformance or canonical v2 authority."
                ),
            }
        )

    for check in checks:
        source_id = check["source_id"]
        source = new_by_id.get(source_id)
        if source is None:
            raise ValueError(f"v1.6 check has no paired new_source: {source_id}")

        raw_hash = check.get("page_content_hash")
        if raw_hash == "NOT_AVAILABLE_FROM_WEB_RESEARCH_INTERFACE":
            content_hash = None
            hash_state = "NOT_AVAILABLE_FROM_PREDECESSOR_INTERFACE"
        elif isinstance(raw_hash, str) and re.fullmatch(r"[0-9a-f]{64}", raw_hash):
            content_hash = raw_hash
            hash_state = "AVAILABLE"
        else:
            content_hash = None
            hash_state = "UNRESOLVED"

        published = source.get("published")
        published_at = _temporal(published) if isinstance(published, str) and published else None
        predecessor = json.loads(json.dumps(check, ensure_ascii=False))
        observations.append(
            {
                "schema_version": "1.0.0-draft",
                "observation_id": _observation_id(check["check_id"]),
                "source_id": source_id,
                "observed_at": _temporal(check["retrieved"]),
                "retrieval_method": "MIGRATED_V1_6_WEB_RESEARCH_CHECK",
                "retrieval_outcome": "SUCCESS",
                "requested_locator": None,
                "resolved_locator": None,
                "http_status": None,
                "content_type": None,
                "content_sha256": content_hash,
                "normalized_content_sha256": None,
                "content_hash_state": hash_state,
                "comparison_state": check.get("baseline_match"),
                "metadata_digest_sha256": check.get("metadata_digest"),
                "capture_state": "METADATA_ONLY",
                "capture_reference_class": "PREDECESSOR_WEB_RESEARCH_NO_PUBLIC_CAPTURE_BYTES",
                "redistribution_state": "RIGHTS_UNRESOLVED",
                "collector_or_operator_version": None,
                "source_published_at": published_at,
                "source_effective_at": None,
                "predecessor": {
                    "release_id": "data-v0.1.0-public-governing",
                    "file": "canonical_live_refresh_release_v1.6.json",
                    "section": "source_checks",
                    "record_id": check["check_id"],
                    "record_sha256": _digest(predecessor),
                    "payload": predecessor,
                },
                "protected_bytes_in_record": False,
                "authority_boundary": (
                    "This migrated observation records the predecessor web-research check. The predecessor did not provide page-content bytes/hash, HTTP status, exact requested/resolved locator, capture custody or redistribution rights; those fields remain unknown rather than being inferred."
                ),
            }
        )

    source_ids = {row["source_id"] for row in sources}
    observation_source_ids = {row["source_id"] for row in observations}
    reconciliation = {
        "scope": "V1.6_NEW_SOURCES_AND_SOURCE_CHECKS_ONLY",
        "input_source_count": len(new_sources),
        "input_check_count": len(checks),
        "projected_source_count": len(sources),
        "projected_observation_count": len(observations),
        "one_to_one_source_check_pair_count": sum(1 for source_id in source_ids if source_id in observation_source_ids),
        "exact_timestamp_observation_count": sum(row["observed_at"] == {"value": "2026-07-29T12:38:00Z", "precision": "TIMESTAMP"} for row in observations),
        "source_published_date_count": sum(row["source_published_at"] is not None and row["source_published_at"]["precision"] == "DATE" for row in observations),
        "source_published_unresolved_count": sum(row["source_published_at"] is None for row in observations),
        "content_hash_unavailable_count": sum(row["content_hash_state"] == "NOT_AVAILABLE_FROM_PREDECESSOR_INTERFACE" and row["content_sha256"] is None for row in observations),
        "new_or_backfill_comparison_count": sum(row["comparison_state"] == "NEW_SOURCE_OR_BACKFILL" for row in observations),
        "no_material_change_comparison_count": sum(row["comparison_state"] == "NO_MATERIAL_CHANGE" for row in observations),
        "source_identity_loss_count": sum(1 for row in sources if row["source_id"] != row["predecessor"]["payload"].get("source_id")),
        "source_payload_roundtrip_failure_count": sum(1 for row in sources if row["predecessor"]["payload"] != new_by_id[row["source_id"]]),
        "observation_payload_roundtrip_failure_count": sum(1 for row in observations if row["predecessor"]["payload"] != next(check for check in checks if check["check_id"] == row["predecessor"]["record_id"])),
        "claim_boundary_loss_count": sum(1 for row in sources if row["source_claim_boundary"] != row["predecessor"]["payload"].get("claim_boundary")),
        "source_reference_loss_count": sum(1 for row in observations if row["source_id"] not in source_ids),
        "content_hash_fabrication_count": sum(1 for row in observations if row["predecessor"]["payload"].get("page_content_hash") == "NOT_AVAILABLE_FROM_WEB_RESEARCH_INTERFACE" and row["content_sha256"] is not None),
        "locator_fabrication_count": sum(1 for row in observations if row["requested_locator"] is not None or row["resolved_locator"] is not None),
        "http_metadata_fabrication_count": sum(1 for row in observations if row["http_status"] is not None or row["content_type"] is not None),
        "temporal_precision_fabrication_count": sum(1 for row in observations if row["observed_at"]["value"] != row["predecessor"]["payload"].get("retrieved") or row["observed_at"]["precision"] != "TIMESTAMP"),
        "protected_bytes_in_public_record_count": sum(1 for row in observations if row["protected_bytes_in_record"] is not False),
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Zero reconciliation counters establish only faithful v1.6 source/check migration. They do not prove source authenticity, claim truth, completeness, materiality adjudication or canonical v2 authority."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_V16_SOURCE_OBSERVATION_MIGRATION",
        "sources": sources,
        "observations": observations,
        "reconciliation": reconciliation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", type=Path, default=DEFAULT_REFRESH)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = project(args.refresh.resolve())
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "sources.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["sources"]),
            encoding="utf-8",
        )
        (args.output_dir / "observations.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["observations"]),
            encoding="utf-8",
        )
        (args.output_dir / "reconciliation.json").write_text(
            json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
