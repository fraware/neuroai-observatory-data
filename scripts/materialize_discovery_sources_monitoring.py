#!/usr/bin/env python3
"""Materialize human-accepted discovery Source candidates and monitoring proposals.

Input is one draft Source-namespace successor proposal produced by the SU-TRIALS adjudication
boundary. Output remains noncanonical: v2 Source candidate records plus separate monitoring
eligibility proposals. No monitor-registry, Trial/site graph, assessment or canonical release is
mutated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

import adjudicate_su_trials_source_namespace as adjudication
import build_monitoring_eligibility as monitoring

PROGRAMME_ID = "SU-TRIALS-CTGOV-v0.1"
_SUCCESSOR_ID = re.compile(r"^SNSP-[0-9a-f]{32}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_successor(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("Source-namespace successor proposal file does not exist")
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Source-namespace successor proposal must be an object")
    if value.get("schema_version") != "0.1.0":
        raise ValueError("Source-namespace successor schema_version mismatch")
    if value.get("artifact") != "source_namespace_successor_proposal":
        raise ValueError("Source-namespace successor artifact mismatch")
    if value.get("status") != "DRAFT_NONCANONICAL_SOURCE_NAMESPACE_SUCCESSOR":
        raise ValueError("Source-namespace successor status mismatch")
    if value.get("programme_id") != PROGRAMME_ID:
        raise ValueError("Source-namespace successor programme mismatch")
    proposal_id = value.get("proposal_id")
    if not isinstance(proposal_id, str) or not _SUCCESSOR_ID.fullmatch(proposal_id):
        raise ValueError("Source-namespace successor proposal_id invalid")
    boundary_flags = {
        "overwrite_refused": True,
        "source_namespace_publication_performed": False,
        "monitor_creation_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
    }
    for key, expected in boundary_flags.items():
        if value.get(key) is not expected:
            raise ValueError(f"Source-namespace successor authority boundary weakened: {key}")
    base = value.get("base_source_namespace")
    provenance = value.get("decision_provenance")
    accepted_ids = value.get("accepted_proposal_ids")
    accepted = value.get("accepted_sources")
    if not isinstance(base, dict) or not isinstance(provenance, dict):
        raise ValueError("Source-namespace successor base/provenance missing")
    if not isinstance(accepted_ids, list) or not accepted_ids or accepted_ids != sorted(set(accepted_ids)):
        raise ValueError("accepted_proposal_ids must be sorted unique non-empty")
    if not isinstance(accepted, list) or not accepted or not all(isinstance(row, dict) for row in accepted):
        raise ValueError("accepted_sources must be a non-empty object array")
    if len(accepted_ids) != len(accepted):
        raise ValueError("accepted proposal/source count mismatch")
    for key in ("source_ids_sha256", "known_nct_index_sha256"):
        digest = base.get(key)
        if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
            raise ValueError(f"Invalid base digest: {key}")
    for key in ("projection_manifest_sha256", "review_index_sha256", "decision_packet_sha256"):
        digest = provenance.get(key)
        if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
            raise ValueError(f"Invalid decision provenance digest: {key}")
    source_ids: set[str] = set()
    nct_ids: set[str] = set()
    from_proposals: set[str] = set()
    for row in accepted:
        source_id = row.get("source_id")
        nct_id = row.get("nct_id")
        from_proposal = row.get("from_proposal_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("Accepted source_id missing")
        if not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id):
            raise ValueError(f"{source_id}: accepted NCT identity invalid")
        if source_id in source_ids or nct_id in nct_ids or from_proposal in from_proposals:
            raise ValueError("Accepted Source successor contains duplicate source/NCT/proposal identity")
        source_ids.add(source_id)
        nct_ids.add(nct_id)
        from_proposals.add(str(from_proposal))
        if from_proposal not in accepted_ids:
            raise ValueError(f"{source_id}: accepted source references proposal outside accepted_proposal_ids")
        if row.get("source_origin") != "DISCOVERY_CTGOV_RECORDED_REPLAY_HUMAN_ACCEPTED":
            raise ValueError(f"{source_id}: source_origin mismatch")
        if row.get("namespace_admission_state") != "PROPOSED_NOT_CANONICAL":
            raise ValueError(f"{source_id}: namespace admission state mismatch")
        if row.get("source_class") != "OFFICIAL_TRIAL_REGISTRY":
            raise ValueError(f"{source_id}: SU-TRIALS discovery source class must be OFFICIAL_TRIAL_REGISTRY")
        query_ids = row.get("query_ids")
        if not isinstance(query_ids, list) or not query_ids or query_ids != sorted(set(query_ids)):
            raise ValueError(f"{source_id}: query provenance invalid")
        for key in ("normalized_aggregate_digest", "candidate_input_sha256"):
            digest = row.get(key)
            if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
                raise ValueError(f"{source_id}: accepted-source provenance digest invalid: {key}")
    if from_proposals != set(accepted_ids):
        raise ValueError("Accepted source/proposal identity sets differ")
    return {
        "path": path.resolve(),
        "file_sha256": _sha256_bytes(payload),
        "record": value,
    }


def _require_unchanged_base(successor: Mapping[str, Any]) -> dict[str, Any]:
    current = adjudication._current_source_namespace()
    base = successor["base_source_namespace"]
    checks = {
        "materialized_source_count": current["materialized_source_count"],
        "source_ids_sha256": current["source_ids_sha256"],
        "known_ctgov_nct_count": current["known_ctgov_nct_count"],
        "known_nct_index_sha256": current["known_nct_index_sha256"],
    }
    for key, current_value in checks.items():
        if base.get(key) != current_value:
            raise ValueError(
                f"SOURCE_NAMESPACE_BASE_DRIFT_REBASE_REQUIRED: {key} successor={base.get(key)!r} current={current_value!r}"
            )
    return current


def _source_candidate(successor: Mapping[str, Any], accepted: Mapping[str, Any]) -> dict[str, Any]:
    decision = successor["decision_provenance"]
    return {
        "schema_version": "2.0.0-draft",
        "source_id": accepted["source_id"],
        "title": accepted["title"],
        "publisher": accepted["publisher"],
        "canonical_locator": accepted["canonical_locator"],
        "source_class": accepted["source_class"],
        "legacy_source_ids": [],
        "source_claim_boundary": accepted["claim_boundary"],
        "source_origin": "DISCOVERY_HUMAN_ACCEPTED_SOURCE_NAMESPACE_PROPOSAL",
        "discovery_provenance": {
            "source_namespace_successor_proposal_id": successor["proposal_id"],
            "programme_id": PROGRAMME_ID,
            "projection_manifest_sha256": decision["projection_manifest_sha256"],
            "review_index_sha256": decision["review_index_sha256"],
            "decision_packet_sha256": decision["decision_packet_sha256"],
            "workbench_query_id": decision["workbench_query_id"],
            "workbench_run_id": decision["workbench_run_id"],
            "workbench_proposal_id": accepted["from_proposal_id"],
            "workbench_adjudication_id": accepted["workbench_adjudication_id"],
            "nct_id": accepted["nct_id"],
            "query_ids": accepted["query_ids"],
            "normalized_aggregate_digest": accepted["normalized_aggregate_digest"],
            "candidate_input_sha256": accepted["candidate_input_sha256"],
        },
        "record_state": "NONCANONICAL_DISCOVERY_ADMITTED_CANDIDATE",
        "authority_boundary": (
            "Human-accepted discovery source identity materialized as a noncanonical v2 Source candidate. "
            "This record is not governing Source publication and does not establish substantive truth, monitoring, "
            "Trial/site relationships, assessment effect, regulatory status or institutional endorsement."
        ),
    }


def _monitoring_proposal(successor_id: str, source: Mapping[str, Any]) -> dict[str, Any]:
    mode, cadence, priority, reason = monitoring._rule_for(source["source_class"], source["title"])
    basis = {
        "source_namespace_successor_proposal_id": successor_id,
        "source_id": source["source_id"],
        "nct_id": source["discovery_provenance"]["nct_id"],
        "recommended_mode": mode,
        "recommended_cadence": cadence,
        "priority": priority,
        "reason": reason,
    }
    return {
        "proposal_id": f"SMEP-{_digest(basis)[:32]}",
        "source_id": source["source_id"],
        "nct_id": source["discovery_provenance"]["nct_id"],
        "source_class": source["source_class"],
        "recommended_mode": mode,
        "recommended_cadence": cadence,
        "priority": priority,
        "reason": reason,
        "review_state": "PENDING_MONITOR_REVIEW",
        "monitor_present": False,
        "monitor_creation_performed": False,
    }


def materialize(successor_path: Path) -> dict[str, Any]:
    loaded = _load_successor(successor_path)
    successor = loaded["record"]
    current = _require_unchanged_base(successor)
    sources = sorted(
        (_source_candidate(successor, row) for row in successor["accepted_sources"]),
        key=lambda row: row["source_id"],
    )
    source_ids = [row["source_id"] for row in sources]
    nct_ids = [row["discovery_provenance"]["nct_id"] for row in sources]
    if len(source_ids) != len(set(source_ids)) or len(nct_ids) != len(set(nct_ids)):
        raise ValueError("Materialized discovery Source identities are not unique")
    for source in sources:
        if source["source_id"] in current["source_ids"]:
            raise ValueError(f"SOURCE_NAMESPACE_BASE_COLLISION: {source['source_id']} already exists")
        if source["discovery_provenance"]["nct_id"] in current["nct_to_source"]:
            raise ValueError(
                f"SOURCE_NAMESPACE_NCT_COLLISION: {source['discovery_provenance']['nct_id']} already exists"
            )

    proposals = [_monitoring_proposal(successor["proposal_id"], source) for source in sources]
    proposal_ids = [row["proposal_id"] for row in proposals]
    if len(proposal_ids) != len(set(proposal_ids)):
        raise ValueError("Monitoring proposal IDs are not unique")
    monitoring_package = {
        "schema_version": "0.1.0",
        "artifact": "source_monitoring_eligibility_proposal",
        "status": "NONCANONICAL_PENDING_MONITOR_REVIEW",
        "source_namespace_successor_proposal_id": successor["proposal_id"],
        "source_candidate_count": len(sources),
        "proposals": proposals,
        "automatic_registry_mutation": False,
        "monitor_creation_performed": False,
        "source_namespace_publication_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Monitoring recommendations only. A recommendation does not create a monitor-registry entry, apply cadence, "
            "authorize collection, or establish Source/Trial/assessment/canonical state."
        ),
    }
    reconciliation = {
        "schema_version": "0.1.0",
        "scope": "DISCOVERY_ORIGIN_SOURCE_MATERIALIZATION_AND_MONITORING_PROPOSAL_ONLY",
        "source_namespace_successor_proposal_id": successor["proposal_id"],
        "source_namespace_successor_file_sha256": loaded["file_sha256"],
        "base_materialized_source_count": current["materialized_source_count"],
        "base_source_ids_sha256": current["source_ids_sha256"],
        "base_known_ctgov_nct_count": current["known_ctgov_nct_count"],
        "base_known_nct_index_sha256": current["known_nct_index_sha256"],
        "accepted_source_count": len(successor["accepted_sources"]),
        "materialized_source_candidate_count": len(sources),
        "monitoring_proposal_count": len(proposals),
        "all_source_ids_unique": True,
        "all_nct_ids_unique": True,
        "monitoring_classifier": "build_monitoring_eligibility._rule_for",
        "automatic_registry_mutation": False,
        "source_namespace_publication_performed": False,
        "monitor_creation_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Reconciliation covers only deterministic Source-candidate materialization and monitoring recommendation. "
            "It does not publish a successor namespace or authorize monitoring/graph/assessment changes."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_DISCOVERY_SOURCE_MATERIALIZATION",
        "source_namespace_successor_proposal_id": successor["proposal_id"],
        "source_namespace_successor_file_sha256": loaded["file_sha256"],
        "sources": sources,
        "monitoring": monitoring_package,
        "reconciliation": reconciliation,
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _jsonl_bytes(rows: list[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        for row in rows
    )


def _write_exact(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != payload:
            raise ValueError(f"OUTPUT_COLLISION_REFUSED: {path}")
        return
    path.write_bytes(payload)


def write_projection(result: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    payloads = {
        "discovery-sources.jsonl": _jsonl_bytes(list(result["sources"])),
        "monitoring-eligibility-proposals.json": _json_bytes(result["monitoring"]),
        "reconciliation.json": _json_bytes(result["reconciliation"]),
    }
    for name, payload in payloads.items():
        _write_exact(output_dir / name, payload)
    files = [
        {"path": name, "sha256": _sha256_bytes(payload), "bytes": len(payload)}
        for name, payload in sorted(payloads.items())
    ]
    manifest = {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_DISCOVERY_SOURCE_MATERIALIZATION",
        "source_namespace_successor_proposal_id": result["source_namespace_successor_proposal_id"],
        "source_namespace_successor_file_sha256": result["source_namespace_successor_file_sha256"],
        "file_count": len(files),
        "files": files,
        "source_namespace_publication_performed": False,
        "monitor_creation_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Checksum manifest for noncanonical Source candidates and monitoring proposals only; not a governing release manifest."
        ),
    }
    _write_exact(output_dir / "manifest.json", _json_bytes(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-namespace-successor", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.source_namespace_successor)
    manifest = write_projection(result, args.output_dir)
    print(json.dumps({
        "status": result["status"],
        "source_candidate_count": len(result["sources"]),
        "monitoring_proposal_count": len(result["monitoring"]["proposals"]),
        "manifest": manifest,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
