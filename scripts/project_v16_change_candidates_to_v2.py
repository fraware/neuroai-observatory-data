"""Project v1.6 change-candidate lineage without inferring candidate-to-delta promotion links."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_REFRESH = ROOT / "releases/data-v0.1.0-public-governing/records/canonical_live_refresh_release_v1.6.json"


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _endpoint(value: str) -> dict[str, Any]:
    return {"value": value, "resolution_state": "PREDECESSOR_LITERAL_UNRESOLVED", "entity_id": None}


def project(refresh_path: Path = DEFAULT_REFRESH) -> dict[str, Any]:
    refresh = json.loads(refresh_path.read_text(encoding="utf-8"))
    candidates = refresh["change_candidates"]
    checks = refresh["source_checks"]
    check_by_source = {check["source_id"]: check["check_id"] for check in checks}

    rows: list[dict[str, Any]] = []
    for record in candidates:
        predecessor = json.loads(json.dumps(record, ensure_ascii=False))
        observation_ids = [
            f"OBS-MIG-V16-{check_by_source[source_id]}"
            for source_id in record["source_ids"]
            if source_id in check_by_source
        ]
        if len(observation_ids) != len(record["source_ids"]):
            raise ValueError(f"candidate {record['candidate_id']} has source without v1.6 source check")
        rows.append(
            {
                "schema_version": "2.0.0-draft",
                "candidate_id": record["candidate_id"],
                "event_at": {"value": record["event_date"], "precision": "DATE"},
                "discovery_class": record["discovery_class"],
                "change_class": record["change_class"],
                "subject_reference": _endpoint(record["subject"]),
                "summary": record["summary"],
                "source_ids": list(record["source_ids"]),
                "observation_ids": observation_ids,
                "materiality": record["materiality"],
                "predecessor_adjudication": record["adjudication"],
                "predecessor_reopening_disposition": record["reopening"],
                "observed_at": None,
                "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
                "candidate_state": "MIGRATED_PREDECESSOR_CANDIDATE_WITH_DISPOSITION",
                "promoted_record_ids": [],
                "promotion_linkage_state": "PREDECESSOR_PROMOTION_LINKAGE_NOT_EXPLICIT",
                "predecessor": {
                    "release_id": "data-v0.1.0-public-governing",
                    "file": "canonical_live_refresh_release_v1.6.json",
                    "section": "change_candidates",
                    "record_id": record["candidate_id"],
                    "record_sha256": _digest(predecessor),
                    "payload": predecessor,
                },
                "record_state": "NONCANONICAL_CANDIDATE",
                "authority_boundary": (
                    "Migrated change-candidate lineage only. The predecessor records an adjudication/reopening disposition, but this candidate object is not itself a canonical change and no candidate-to-delta promotion target is inferred without an explicit predecessor link."
                ),
            }
        )

    ids = [row["candidate_id"] for row in rows]
    source_ids = {source["source_id"] for source in refresh["new_sources"]}
    observation_ids = {f"OBS-MIG-V16-{check['check_id']}" for check in checks}
    reconciliation = {
        "scope": "V1.6_CHANGE_CANDIDATES_ONLY",
        "input_candidate_count": len(candidates),
        "projected_candidate_count": len(rows),
        "historical_backfill_count": sum(row["discovery_class"] == "HISTORICAL_BACKFILL" for row in rows),
        "pre_cutoff_after_freeze_count": sum(row["discovery_class"] == "PRE_CUTOFF_EVIDENCE_DISCOVERED_AFTER_FREEZE" for row in rows),
        "high_materiality_count": sum(row["materiality"] == "HIGH" for row in rows),
        "medium_materiality_count": sum(row["materiality"] == "MEDIUM" for row in rows),
        "low_materiality_count": sum(row["materiality"] == "LOW" for row in rows),
        "source_reference_count": sum(len(row["source_ids"]) for row in rows),
        "observation_reference_count": sum(len(row["observation_ids"]) for row in rows),
        "explicit_promotion_link_count": sum(len(row["promoted_record_ids"]) for row in rows),
        "identity_mismatch_count": 0 if len(ids) == len(set(ids)) else len(ids) - len(set(ids)),
        "predecessor_payload_roundtrip_failure_count": sum(row["predecessor"]["payload"] != next(candidate for candidate in candidates if candidate["candidate_id"] == row["candidate_id"]) for row in rows),
        "source_reference_loss_count": sum(1 for row in rows for source_id in row["source_ids"] if source_id not in source_ids),
        "observation_reference_loss_count": sum(1 for row in rows for observation_id in row["observation_ids"] if observation_id not in observation_ids),
        "subject_resolution_fabrication_count": sum(row["subject_reference"]["entity_id"] is not None for row in rows),
        "promotion_linkage_fabrication_count": sum(bool(row["promoted_record_ids"]) for row in rows),
        "event_time_precision_fabrication_count": sum(row["event_at"] != {"value": row["predecessor"]["payload"]["event_date"], "precision": "DATE"} for row in rows),
        "knowledge_time_fabrication_count": sum(row["observed_at"] is not None for row in rows),
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Candidate reconciliation proves lineage preservation only; predecessor acceptance text is preserved but not treated as automatic canonical promotion."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_V2_V16_CHANGE_CANDIDATE_MIGRATION",
        "candidates": rows,
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
        (args.output_dir / "candidates.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result["candidates"]),
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
