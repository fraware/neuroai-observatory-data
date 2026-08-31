#!/usr/bin/env python3
"""Project v1.6 reopening decisions and no-change confirmations into draft v2 records.

The migration preserves exact predecessor payloads. Empty reopening bases remain empty.
No-change confirmations are comparison provenance linked to exact v1.6 observations and
are never converted into world-level absence assertions. This slice is noncanonical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
RECORDS = ROOT / "releases" / "data-v0.1.0-public-governing" / "records"
DEFAULT_REFRESH = RECORDS / "canonical_live_refresh_release_v1.6.json"
DEFAULT_DELTA = RECORDS / "adjudicated_delta_v1.6.json"


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _accepted_ids(delta: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for value in delta.values():
        if not isinstance(value, list):
            continue
        for row in value:
            if not isinstance(row, dict):
                continue
            for key in ("event_id", "model_id", "dependency_id", "relationship_id", "governance_id", "id"):
                raw = row.get(key)
                if isinstance(raw, str) and raw:
                    ids.add(raw)
                    break
    return ids


def _check_map(refresh: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = refresh.get("source_checks")
    if not isinstance(checks, list):
        raise ValueError("v1.6 source_checks missing")
    result: dict[str, dict[str, Any]] = {}
    for row in checks:
        if not isinstance(row, dict) or not isinstance(row.get("source_id"), str):
            raise ValueError("invalid v1.6 source check")
        result[row["source_id"]] = row
    return result


def project(refresh_path: Path = DEFAULT_REFRESH, delta_path: Path = DEFAULT_DELTA) -> dict[str, Any]:
    refresh = json.loads(refresh_path.read_text(encoding="utf-8"))
    delta = json.loads(delta_path.read_text(encoding="utf-8"))
    if not isinstance(refresh, dict) or not isinstance(delta, dict):
        raise ValueError("governing v1.6 inputs must be objects")
    decisions = refresh.get("reopening_decisions")
    confirmations = refresh.get("no_change_confirmations")
    if not isinstance(decisions, list) or not isinstance(confirmations, list):
        raise ValueError("v1.6 reopening/no-change sections missing")

    accepted = _accepted_ids(delta)
    checks = _check_map(refresh)
    source_to_observation = {sid: f"OBS-V16-{row['check_id']}" for sid, row in checks.items()}

    projected_decisions: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    empty_basis_count = 0
    basis_reference_count = 0
    unresolved_basis_count = 0
    payload_failures = basis_losses = action_losses = time_fabrications = 0

    for row in decisions:
        if not isinstance(row, dict):
            raise ValueError("reopening decision must be object")
        did = row.get("decision_id")
        target = row.get("object")
        decision = row.get("decision")
        basis = row.get("basis")
        actions = row.get("required_actions")
        if not all(isinstance(v, str) and v for v in (did, target, decision)):
            raise ValueError("invalid reopening decision identity")
        if not isinstance(basis, list) or not all(isinstance(v, str) and v for v in basis):
            raise ValueError(f"{did}: invalid basis")
        if not isinstance(actions, list) or not all(isinstance(v, str) and v for v in actions):
            raise ValueError(f"{did}: invalid required_actions")
        unresolved = [bid for bid in basis if bid not in accepted]
        unresolved_basis_count += len(unresolved)
        basis_reference_count += len(basis)
        if not basis:
            empty_basis_count += 1
        payload = json.loads(json.dumps(row, ensure_ascii=False))
        out = {
            "schema_version": "2.0.0-draft",
            "decision_id": did,
            "target_reference": {"value": target, "resolution_state": "PREDECESSOR_LITERAL_UNRESOLVED", "entity_or_assessment_id": None},
            "decision": decision,
            "basis_record_ids": list(basis),
            "basis_resolution_state": "EMPTY_PREDECESSOR_BASIS" if not basis else "ACCEPTED_DELTA_IDENTITIES_RESOLVED",
            "required_actions": list(actions),
            "decided_at": None,
            "knowledge_time_state": "PREDECESSOR_TIME_UNRESOLVED",
            "predecessor": {
                "release_id": "data-v0.1.0-public-governing",
                "file": "canonical_live_refresh_release_v1.6.json",
                "section": "reopening_decisions",
                "record_id": did,
                "record_sha256": _digest(payload),
                "payload": payload,
            },
            "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
            "authority_boundary": "Preserves the predecessor reopening/update decision only. It does not mutate an assessment finding, establish that no other evidence exists, or authorize publication.",
        }
        if out["predecessor"]["payload"] != row or out["predecessor"]["record_sha256"] != _digest(row):
            payload_failures += 1
        if out["basis_record_ids"] != basis:
            basis_losses += 1
        if out["required_actions"] != actions:
            action_losses += 1
        if out["decided_at"] is not None:
            time_fabrications += 1
        decision_counts[decision] += 1
        projected_decisions.append(out)

    projected_confirmations: list[dict[str, Any]] = []
    nochange_source_refs = nochange_obs_refs = 0
    nochange_source_losses = nochange_obs_losses = nochange_payload_failures = world_absence_fabrications = 0
    for index, row in enumerate(confirmations, start=1):
        if not isinstance(row, dict):
            raise ValueError("no-change confirmation must be object")
        obj = row.get("object")
        source_ids = row.get("source_ids")
        result = row.get("result")
        if not isinstance(obj, str) or not obj or not isinstance(result, str) or not result:
            raise ValueError("invalid no-change confirmation")
        if not isinstance(source_ids, list) or not source_ids or not all(isinstance(s, str) and s for s in source_ids):
            raise ValueError("no-change source_ids must be non-empty")
        observation_ids: list[str] = []
        observed_times: set[str] = set()
        for sid in source_ids:
            check = checks.get(sid)
            if check is None or check.get("baseline_match") != "NO_MATERIAL_CHANGE":
                nochange_obs_losses += 1
                continue
            observation_ids.append(source_to_observation[sid])
            if isinstance(check.get("retrieved"), str):
                observed_times.add(check["retrieved"])
        if len(observed_times) != 1:
            raise ValueError("no-change confirmation sources must resolve to one exact observation time")
        observed_at = next(iter(observed_times))
        cid = f"CMP-16-{index:03d}"
        payload = json.loads(json.dumps(row, ensure_ascii=False))
        out = {
            "schema_version": "2.0.0-draft",
            "comparison_id": cid,
            "object_reference": obj,
            "source_ids": list(source_ids),
            "observation_ids": observation_ids,
            "result": result,
            "comparison_scope": "BOUNDED_PREDECESSOR_SOURCE_COMPARISON",
            "world_absence_claim": False,
            "observed_at": {"value": observed_at, "precision": "TIMESTAMP"},
            "predecessor": {
                "release_id": "data-v0.1.0-public-governing",
                "file": "canonical_live_refresh_release_v1.6.json",
                "section": "no_change_confirmations",
                "record_id": cid,
                "record_sha256": _digest(payload),
                "payload": payload,
            },
            "record_state": "NONCANONICAL_MIGRATED_CANDIDATE",
            "authority_boundary": "This is bounded comparison provenance for the cited source observation(s). It does not establish absence of unannounced, inaccessible, non-indexed, or otherwise unobserved events or text changes.",
        }
        if out["source_ids"] != source_ids:
            nochange_source_losses += 1
        if len(out["observation_ids"]) != len(source_ids):
            nochange_obs_losses += 1
        if out["predecessor"]["payload"] != row or out["predecessor"]["record_sha256"] != _digest(row):
            nochange_payload_failures += 1
        if out["world_absence_claim"] is not False:
            world_absence_fabrications += 1
        nochange_source_refs += len(source_ids)
        nochange_obs_refs += len(observation_ids)
        projected_confirmations.append(out)

    reconciliation = {
        "scope": "V1.6_REOPENING_AND_NO_CHANGE_ONLY",
        "semantic_reconciliation_state": "EXECUTED_FOR_V16_REOPENING_NO_CHANGE_SLICE_ONLY",
        "input_reopening_decision_count": len(decisions),
        "projected_reopening_decision_count": len(projected_decisions),
        "decision_counts": dict(sorted(decision_counts.items())),
        "empty_basis_decision_count": empty_basis_count,
        "basis_reference_count": basis_reference_count,
        "unresolved_accepted_basis_reference_count": unresolved_basis_count,
        "input_no_change_confirmation_count": len(confirmations),
        "projected_no_change_confirmation_count": len(projected_confirmations),
        "no_change_source_reference_count": nochange_source_refs,
        "no_change_observation_reference_count": nochange_obs_refs,
        "predecessor_payload_roundtrip_failure_count": payload_failures + nochange_payload_failures,
        "basis_loss_count": basis_losses,
        "required_action_loss_count": action_losses,
        "decision_time_fabrication_count": time_fabrications,
        "no_change_source_reference_loss_count": nochange_source_losses,
        "no_change_observation_reference_loss_count": nochange_obs_losses,
        "world_absence_claim_fabrication_count": world_absence_fabrications,
        "canonical_successor_ready": False,
        "authority_boundary": "Zero counters apply only to the v1.6 reopening/no-change migration mechanics. Empty basis is preserved as empty, and no-change provenance is not a global absence claim.",
    }
    return {"reopening_decisions": projected_decisions, "comparison_provenance": projected_confirmations, "reconciliation": reconciliation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", type=Path, default=DEFAULT_REFRESH)
    parser.add_argument("--delta", type=Path, default=DEFAULT_DELTA)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = project(args.refresh, args.delta)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for key in ("reopening_decisions", "comparison_provenance"):
            (args.output_dir / f"{key}.jsonl").write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in result[key]), encoding="utf-8")
        (args.output_dir / "reconciliation.json").write_text(json.dumps(result["reconciliation"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["reconciliation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
