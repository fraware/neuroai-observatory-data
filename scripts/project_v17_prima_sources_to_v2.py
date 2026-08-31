#!/usr/bin/env python3
"""Project the 12 actual PRIMA supplemental source records into draft v2 Source/Observation objects.

Missing numeric IDs are not inferred. Retrieval time remains DATE precision. Explicit local hashes are
preserved as local-copy content digests while capture custody remains unresolved. This slice is noncanonical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DEFAULT_REGISTER = ROOT / "supplemental_records/PRIMA_NEW_UNIQUE_SOURCE_REGISTER_v1.7.json"
EXPECTED_IDS = [
    "SRC-PR-001", "SRC-PR-002", "SRC-PR-005", "SRC-PR-006", "SRC-PR-007", "SRC-PR-008",
    "SRC-PR-009", "SRC-PR-010", "SRC-PR-012", "SRC-PR-013", "SRC-PR-014", "SRC-PR-015",
]


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _source(row: dict[str, Any]) -> dict[str, Any]:
    sid = row["source_id"]
    payload = json.loads(json.dumps(row, ensure_ascii=False))
    return {
        "schema_version": "2.0.0-draft",
        "source_id": sid,
        "title": row["title"],
        "publisher": row["publisher"],
        "canonical_locator": row["url"],
        "source_class": row["source_class"],
        "legacy_source_ids": [],
        "source_claim_boundary": row.get("claim_boundary"),
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "PRIMA_NEW_UNIQUE_SOURCE_REGISTER_v1.7.json",
            "section": "supplemental_records",
            "record_id": sid,
            "record_sha256": _digest(payload),
            "payload": payload,
        },
        "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
        "authority_boundary": "Preserves the exact supplemental source identity and claim boundary. Source registration does not establish substantive truth, current applicability, authorization, effectiveness or conformance.",
    }


def _observation(row: dict[str, Any]) -> dict[str, Any]:
    sid = row["source_id"]
    local_hash = row.get("local_sha256")
    redistribution = row.get("redistribution")
    if local_hash is not None and (not isinstance(local_hash, str) or len(local_hash) != 64):
        raise ValueError(f"{sid}: invalid local_sha256")
    if redistribution is not None and redistribution not in {"NOT_PACKAGED_COPYRIGHTED_SOURCE", "NOT_PACKAGED_SOURCE_COPY"}:
        raise ValueError(f"{sid}: unsupported explicit redistribution state {redistribution!r}")
    payload = json.loads(json.dumps(row, ensure_ascii=False))
    published = row.get("published")
    return {
        "schema_version": "1.0.0-draft",
        "observation_id": f"OBS-V17-{sid}",
        "source_id": sid,
        "observed_at": {"value": row["retrieved"], "precision": "DATE"},
        "retrieval_method": "PREDECESSOR_SUPPLEMENTAL_RECORD",
        "retrieval_outcome": "PREDECESSOR_RECORDED_OBSERVATION",
        "requested_locator": None,
        "resolved_locator": None,
        "http_status": None,
        "content_type": None,
        "content_sha256": local_hash,
        "normalized_content_sha256": None,
        "content_hash_state": "AVAILABLE" if local_hash else "UNRESOLVED",
        "comparison_state": None,
        "metadata_digest_sha256": None,
        "capture_state": "CAPTURE_STATE_UNRESOLVED",
        "capture_reference_class": None,
        "redistribution_state": redistribution if redistribution else "RIGHTS_UNRESOLVED",
        "collector_or_operator_version": None,
        "source_published_at": {"value": published, "precision": "DATE"} if isinstance(published, str) and published else None,
        "source_effective_at": None,
        "predecessor": {
            "release_id": "data-v0.1.0-public-governing",
            "file": "PRIMA_NEW_UNIQUE_SOURCE_REGISTER_v1.7.json",
            "section": "supplemental_records",
            "record_id": sid,
            "record_sha256": _digest(payload),
            "payload": payload,
        },
        "protected_bytes_in_record": False,
        "authority_boundary": "The observation preserves predecessor retrieval date and any explicit local-copy hash/redistribution metadata. A local hash does not establish capture custody, source authenticity, redistribution rights beyond the recorded state, or substantive truth.",
    }


def project(register_path: Path = DEFAULT_REGISTER) -> dict[str, Any]:
    rows = json.loads(register_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("PRIMA supplemental register must be a JSON array of objects")
    ids = [r.get("source_id") for r in rows]
    if ids != EXPECTED_IDS:
        raise ValueError(f"Unexpected supplemental source ID set/order: {ids}")
    sources = [_source(r) for r in rows]
    observations = [_observation(r) for r in rows]
    hash_count = sum(1 for r in rows if r.get("local_sha256"))
    redistribution_count = sum(1 for r in rows if r.get("redistribution"))
    payload_failures = sum(1 for s, r in zip(sources, rows) if s["predecessor"]["payload"] != r or s["predecessor"]["record_sha256"] != _digest(r))
    source_id_loss = sum(1 for s, r in zip(sources, rows) if s["source_id"] != r["source_id"])
    claim_boundary_loss = sum(1 for s, r in zip(sources, rows) if s["source_claim_boundary"] != r.get("claim_boundary"))
    time_fabrication = sum(1 for o, r in zip(observations, rows) if o["observed_at"] != {"value": r["retrieved"], "precision": "DATE"})
    hash_loss = sum(1 for o, r in zip(observations, rows) if o["content_sha256"] != r.get("local_sha256"))
    custody_fabrication = sum(1 for o in observations if o["capture_state"] != "CAPTURE_STATE_UNRESOLVED" or o["capture_reference_class"] is not None)
    redistribution_loss = sum(1 for o, r in zip(observations, rows) if o["redistribution_state"] != (r.get("redistribution") or "RIGHTS_UNRESOLVED"))
    protected_byte_violation = sum(1 for o in observations if o["protected_bytes_in_record"] is not False)

    reconciliation = {
        "scope": "V1.7_PRIMA_SUPPLEMENTAL_SOURCES_ONLY",
        "input_source_count": len(rows),
        "projected_source_count": len(sources),
        "projected_observation_count": len(observations),
        "actual_source_ids": ids,
        "inferred_missing_source_id_count": 0,
        "date_precision_observation_count": sum(1 for o in observations if o["observed_at"]["precision"] == "DATE"),
        "explicit_local_hash_count": hash_count,
        "available_content_hash_count": sum(1 for o in observations if o["content_hash_state"] == "AVAILABLE"),
        "explicit_redistribution_state_count": redistribution_count,
        "rights_unresolved_count": sum(1 for o in observations if o["redistribution_state"] == "RIGHTS_UNRESOLVED"),
        "source_id_loss_count": source_id_loss,
        "predecessor_payload_roundtrip_failure_count": payload_failures,
        "claim_boundary_loss_count": claim_boundary_loss,
        "temporal_precision_fabrication_count": time_fabrication,
        "local_hash_loss_or_fabrication_count": hash_loss,
        "capture_custody_fabrication_count": custody_fabrication,
        "redistribution_state_loss_or_fabrication_count": redistribution_loss,
        "protected_byte_violation_count": protected_byte_violation,
        "canonical_successor_ready": False,
        "authority_boundary": "Zero counters apply only to the 12 actual supplemental records. Missing numeric IDs are not inferred, and local hashes do not establish custody or substantive validity.",
    }
    return {"sources": sources, "observations": observations, "reconciliation": reconciliation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = project(args.register)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name in ("sources", "observations"):
            (args.output_dir / f"{name}.jsonl").write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in result[name]), encoding="utf-8")
        (args.output_dir / "reconciliation.json").write_text(json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
