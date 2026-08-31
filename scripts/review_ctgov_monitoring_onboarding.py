#!/usr/bin/env python3
"""Review CT.gov monitoring recommendations and create non-executable onboarding plans.

This gate consumes one deterministic discovery-Source materialization package and one explicit
local monitor-review packet. APPROVE_RECOMMENDATION creates a draft monitor identity, exact NCT
route-resilience plan, and first-capture request template. It performs no network I/O, quarantine
approval, monitor-registry succession, Source publication, graph mutation, assessment mutation,
or canonical publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode

PROGRAMME_ID = "SU-TRIALS-CTGOV-v0.1"
EXPECTED_MATERIALIZATION_FILES = {
    "discovery-sources.jsonl",
    "monitoring-eligibility-proposals.json",
    "reconciliation.json",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NCT = re.compile(r"^NCT[0-9]{8}$")
_SMEP = re.compile(r"^SMEP-[0-9a-f]{32}$")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_no}: JSONL row must be an object")
        rows.append(value)
    return rows


def verify_materialization(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Source materialization manifest.json missing")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("Source materialization manifest must be an object")
    if manifest.get("schema_version") != "0.1.0" or manifest.get("status") != "NONCANONICAL_DISCOVERY_SOURCE_MATERIALIZATION":
        raise ValueError("Source materialization manifest contract/status mismatch")
    successor_id = manifest.get("source_namespace_successor_proposal_id")
    if not isinstance(successor_id, str) or not re.fullmatch(r"SNSP-[0-9a-f]{32}", successor_id):
        raise ValueError("Source materialization successor identity invalid")
    for key in (
        "source_namespace_publication_performed",
        "monitor_creation_performed",
        "trial_entity_creation_performed",
        "trial_site_relationship_creation_performed",
        "assessment_mutation_performed",
        "canonical_successor_ready",
    ):
        if manifest.get(key) is not False:
            raise ValueError(f"Source materialization authority boundary weakened: {key}")

    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("file_count") != len(entries):
        raise ValueError("Source materialization manifest file list/count invalid")
    paths = [row.get("path") for row in entries if isinstance(row, dict)]
    if len(paths) != len(entries) or set(paths) != EXPECTED_MATERIALIZATION_FILES or len(paths) != len(set(paths)):
        raise ValueError("Source materialization manifest file set mismatch")
    for entry in entries:
        relative = entry.get("path")
        if not isinstance(relative, str) or Path(relative).name != relative:
            raise ValueError(f"Unsafe materialization manifest path {relative!r}")
        path = root / relative
        if not path.is_file():
            raise ValueError(f"Materialization file missing: {relative}")
        payload = path.read_bytes()
        expected_sha = entry.get("sha256")
        if not isinstance(expected_sha, str) or not _HEX64.fullmatch(expected_sha):
            raise ValueError(f"Materialization digest invalid: {relative}")
        if _sha256_bytes(payload) != expected_sha or entry.get("bytes") != len(payload):
            raise ValueError(f"Materialization manifest mismatch: {relative}")

    sources = _load_jsonl(root / "discovery-sources.jsonl")
    monitoring = _load_json(root / "monitoring-eligibility-proposals.json")
    reconciliation = _load_json(root / "reconciliation.json")
    if not sources or not isinstance(monitoring, dict) or not isinstance(reconciliation, dict):
        raise ValueError("Materialization source/monitoring/reconciliation content invalid")
    if monitoring.get("status") != "NONCANONICAL_PENDING_MONITOR_REVIEW":
        raise ValueError("Monitoring package is not pending monitor review")
    if monitoring.get("source_namespace_successor_proposal_id") != successor_id:
        raise ValueError("Monitoring package successor binding mismatch")
    if monitoring.get("source_candidate_count") != len(sources):
        raise ValueError("Monitoring package source count mismatch")
    for key in (
        "automatic_registry_mutation",
        "monitor_creation_performed",
        "source_namespace_publication_performed",
        "trial_entity_creation_performed",
        "trial_site_relationship_creation_performed",
        "assessment_mutation_performed",
        "canonical_successor_ready",
    ):
        if monitoring.get(key) is not False:
            raise ValueError(f"Monitoring package authority boundary weakened: {key}")
    proposals = monitoring.get("proposals")
    if not isinstance(proposals, list) or len(proposals) != len(sources) or not all(isinstance(row, dict) for row in proposals):
        raise ValueError("Monitoring proposals have invalid shape/count")

    source_by_id: dict[str, dict[str, Any]] = {}
    nct_seen: set[str] = set()
    for source in sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in source_by_id:
            raise ValueError("Discovery Source identities must be unique/non-empty")
        if source.get("source_origin") != "DISCOVERY_HUMAN_ACCEPTED_SOURCE_NAMESPACE_PROPOSAL":
            raise ValueError(f"{source_id}: source is not discovery-origin")
        if source.get("record_state") != "NONCANONICAL_DISCOVERY_ADMITTED_CANDIDATE":
            raise ValueError(f"{source_id}: source record state mismatch")
        if source.get("source_class") != "OFFICIAL_TRIAL_REGISTRY":
            raise ValueError(f"{source_id}: CT.gov onboarding requires OFFICIAL_TRIAL_REGISTRY")
        provenance = source.get("discovery_provenance")
        if not isinstance(provenance, dict):
            raise ValueError(f"{source_id}: discovery provenance missing")
        nct_id = provenance.get("nct_id")
        if not isinstance(nct_id, str) or not _NCT.fullmatch(nct_id) or nct_id in nct_seen:
            raise ValueError(f"{source_id}: NCT identity invalid/duplicate")
        nct_seen.add(nct_id)
        source_by_id[source_id] = source

    proposal_by_id: dict[str, dict[str, Any]] = {}
    proposal_source_ids: set[str] = set()
    for proposal in proposals:
        proposal_id = proposal.get("proposal_id")
        source_id = proposal.get("source_id")
        if not isinstance(proposal_id, str) or not _SMEP.fullmatch(proposal_id) or proposal_id in proposal_by_id:
            raise ValueError("Monitoring proposal identity invalid/duplicate")
        if not isinstance(source_id, str) or source_id not in source_by_id or source_id in proposal_source_ids:
            raise ValueError(f"{proposal_id}: monitoring Source identity invalid/duplicate")
        proposal_source_ids.add(source_id)
        source = source_by_id[source_id]
        if proposal.get("nct_id") != source["discovery_provenance"]["nct_id"] or proposal.get("source_class") != source["source_class"]:
            raise ValueError(f"{proposal_id}: Source/NCT/class binding mismatch")
        if proposal.get("review_state") != "PENDING_MONITOR_REVIEW" or proposal.get("monitor_present") is not False or proposal.get("monitor_creation_performed") is not False:
            raise ValueError(f"{proposal_id}: proposal is not pending/non-mutating")
        proposal_by_id[proposal_id] = proposal
    if proposal_source_ids != set(source_by_id):
        raise ValueError("Monitoring proposal/Source identity sets differ")

    return {
        "root": root,
        "manifest": manifest,
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "successor_id": successor_id,
        "sources": source_by_id,
        "proposals": proposal_by_id,
        "reconciliation": reconciliation,
    }


def load_decisions(path: Path, materialization: Mapping[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("Monitor-review decision packet missing")
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Monitor-review decision packet must be an object")
    if value.get("schema_version") != "0.1.0" or value.get("artifact") != "monitor_review_decision_packet" or value.get("status") != "EXPLICIT_LOCAL_MONITOR_REVIEW":
        raise ValueError("Monitor-review packet contract/status mismatch")
    if value.get("source_materialization_manifest_sha256") != materialization["manifest_sha256"]:
        raise ValueError("Monitor-review packet manifest binding mismatch")
    if value.get("source_namespace_successor_proposal_id") != materialization["successor_id"]:
        raise ValueError("Monitor-review packet Source-successor binding mismatch")
    if value.get("identity_boundary") != "LOCAL_UNAUTHENTICATED_ATTRIBUTION":
        raise ValueError("Monitor-review identity boundary mismatch")
    for key in ("reviewed_by", "reviewed_at", "authority_boundary"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"Monitor-review packet field {key} must be non-empty")
    authority = {
        "onboarding_plan_authorized_only": True,
        "network_execution_authorized": False,
        "quarantine_approval_authorized": False,
        "monitor_registry_successor_authorized": False,
        "source_namespace_publication_authorized": False,
        "trial_entity_creation_authorized": False,
        "trial_site_relationship_creation_authorized": False,
        "assessment_mutation_authorized": False,
        "canonical_publication_authorized": False,
    }
    for key, expected in authority.items():
        if value.get(key) is not expected:
            raise ValueError(f"Monitor-review authority boundary weakened: {key}")

    rows = value.get("decisions")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Monitor-review decisions must be a non-empty object array")
    decisions: dict[str, dict[str, Any]] = {}
    for row in rows:
        proposal_id = row.get("monitoring_proposal_id")
        source_id = row.get("source_id")
        decision = row.get("decision")
        rationale = row.get("rationale")
        if proposal_id not in materialization["proposals"]:
            raise ValueError(f"Monitor-review packet contains unknown proposal {proposal_id!r}")
        if proposal_id in decisions:
            raise ValueError(f"Duplicate monitor-review decision for {proposal_id}")
        if source_id != materialization["proposals"][proposal_id]["source_id"]:
            raise ValueError(f"{proposal_id}: decision Source identity mismatch")
        if decision not in {"APPROVE_RECOMMENDATION", "DEFER", "REJECT"}:
            raise ValueError(f"{proposal_id}: unsupported monitor-review decision")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"{proposal_id}: monitor-review rationale must be non-empty")
        decisions[proposal_id] = row
    if set(decisions) != set(materialization["proposals"]):
        missing = sorted(set(materialization["proposals"]) - set(decisions))
        raise ValueError(f"Monitor-review packet must dispose every proposal; missing={missing}")
    return {"record": value, "sha256": _sha256_bytes(payload), "decisions": decisions}


def _routes(source_id: str, nct_id: str) -> list[dict[str, Any]]:
    query = urlencode({"query.id": nct_id, "pageSize": "1", "format": "json"})
    return [
        {
            "route_id": f"{source_id}:api-v2-single",
            "url": f"https://clinicaltrials.gov/api/v2/studies/{nct_id}",
            "priority": 0,
            "role": "PRIMARY",
            "route_class": "PRIMARY",
            "accept": "application/json",
            "identity_check": {"kind": "JSON_NCT_ID", "expected": nct_id},
            "corroboration_check": None,
        },
        {
            "route_id": f"{source_id}:api-v2-id-query",
            "url": f"https://clinicaltrials.gov/api/v2/studies?{query}",
            "priority": 1,
            "role": "FALLBACK",
            "route_class": "IDENTITY_EQUIVALENT",
            "accept": "application/json",
            "identity_check": {"kind": "JSON_NCT_ID", "expected": nct_id},
            "corroboration_check": None,
        },
        {
            "route_id": f"{source_id}:official-study-page",
            "url": f"https://clinicaltrials.gov/study/{nct_id}",
            "priority": 2,
            "role": "FALLBACK",
            "route_class": "LIVENESS_CORROBORATION",
            "accept": "text/html,application/xhtml+xml;q=0.9",
            "identity_check": None,
            "corroboration_check": {"kind": "TEXT_CONTAINS", "expected": nct_id},
        },
    ]


def build_onboarding(materialization_dir: Path, decision_packet: Path) -> dict[str, Any]:
    materialization = verify_materialization(materialization_dir)
    decisions = load_decisions(decision_packet, materialization)
    dispositions: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []

    for proposal_id in sorted(materialization["proposals"]):
        proposal = materialization["proposals"][proposal_id]
        decision = decisions["decisions"][proposal_id]
        source = materialization["sources"][proposal["source_id"]]
        dispositions.append({
            "monitoring_proposal_id": proposal_id,
            "source_id": proposal["source_id"],
            "nct_id": proposal["nct_id"],
            "decision": decision["decision"],
            "rationale": decision["rationale"],
        })
        if decision["decision"] != "APPROVE_RECOMMENDATION":
            continue
        expected = {"recommended_mode": "RECURRING", "recommended_cadence": "MONTHLY", "priority": "HIGH"}
        for key, value in expected.items():
            if proposal.get(key) != value:
                raise ValueError(f"{proposal_id}: RECOMMENDATION_DRIFT_REVIEW_REQUIRED: {key}={proposal.get(key)!r}")
        nct_id = proposal["nct_id"]
        routes = _routes(proposal["source_id"], nct_id)
        draft_basis = {
            "materialization_manifest_sha256": materialization["manifest_sha256"],
            "monitoring_proposal_id": proposal_id,
            "source_id": proposal["source_id"],
            "nct_id": nct_id,
            "decision_packet_sha256": decisions["sha256"],
        }
        draft_monitor_id = f"DMON-{_digest(draft_basis)[:32]}"
        request_basis = {
            "draft_monitor_id": draft_monitor_id,
            "source_id": proposal["source_id"],
            "requested_url": routes[0]["url"],
            "materialization_manifest_sha256": materialization["manifest_sha256"],
        }
        request_id = f"CREQ-{_digest(request_basis)[:32]}"
        plans.append({
            "draft_monitor_id": draft_monitor_id,
            "monitoring_proposal_id": proposal_id,
            "source_id": proposal["source_id"],
            "source_candidate_sha256": _digest(source),
            "nct_id": nct_id,
            "source_class": source["source_class"],
            "approved_mode": proposal["recommended_mode"],
            "approved_cadence": proposal["recommended_cadence"],
            "priority": proposal["priority"],
            "network_access_required": True,
            "adapter_id": "clinicaltrials_gov",
            "routes": routes,
            "initial_capture_route_id": routes[0]["route_id"],
            "first_capture_request_template": {
                "request_id": request_id,
                "source_id": proposal["source_id"],
                "monitor_id": draft_monitor_id,
                "requested_url": routes[0]["url"],
                "required_execution_fields": [
                    "requested_at",
                    "onboarding_manifest_sha256",
                    "collector_version",
                    "configuration_hash",
                    "boundary",
                ],
                "execution_state": "TEMPLATE_NOT_EXECUTED",
            },
            "first_capture_requirement": (
                "Execute the primary ClinicalTrials.gov API route through the controlled Workbench collector, verify exact "
                f"JSON NCT identity {nct_id}, retain bytes in quarantine, and require separate quarantine approval before "
                "any monitor-registry successor may be drafted. The pre-registry request must bind to the exact onboarding "
                "manifest, because no monitor-registry digest exists yet."
            ),
            "monitor_registry_state": "NOT_CREATED",
        })

    summary = {
        "schema_version": "0.1.0",
        "artifact": "monitor_review_disposition_summary",
        "status": "COMPLETED_LOCAL_MONITOR_REVIEW",
        "source_materialization_manifest_sha256": materialization["manifest_sha256"],
        "monitor_review_decision_packet_sha256": decisions["sha256"],
        "source_namespace_successor_proposal_id": materialization["successor_id"],
        "reviewed_by": decisions["record"]["reviewed_by"],
        "reviewed_at": decisions["record"]["reviewed_at"],
        "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
        "proposal_count": len(dispositions),
        "approved_count": len(plans),
        "dispositions": dispositions,
        "network_execution_performed": False,
        "quarantine_approval_performed": False,
        "monitor_registry_successor_created": False,
        "monitor_creation_performed": False,
        "source_namespace_publication_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": "Explicit local monitoring recommendation disposition only; approved items advance to non-executable onboarding plans.",
    }
    package = None
    if plans:
        package = {
            "schema_version": "0.1.0",
            "artifact": "ctgov_monitor_onboarding_package",
            "status": "DRAFT_NONCANONICAL_MONITOR_ONBOARDING",
            "source_materialization_manifest_sha256": materialization["manifest_sha256"],
            "monitor_review_decision_packet_sha256": decisions["sha256"],
            "source_namespace_successor_proposal_id": materialization["successor_id"],
            "approved_plan_count": len(plans),
            "plans": plans,
            "network_execution_performed": False,
            "quarantine_approval_performed": False,
            "monitor_registry_successor_created": False,
            "monitor_creation_performed": False,
            "source_namespace_publication_performed": False,
            "trial_entity_creation_performed": False,
            "trial_site_relationship_creation_performed": False,
            "assessment_mutation_performed": False,
            "canonical_successor_ready": False,
            "authority_boundary": (
                "Draft monitor identities, route-resilience policy and first-capture templates only. Network execution, "
                "quarantine approval and monitor-registry succession require later explicit gates."
            ),
        }
    return {"summary": summary, "onboarding": package}


def write_outputs(result: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, bytes] = {
        "monitor-review-summary.json": (json.dumps(result["summary"], indent=2, sort_keys=True) + "\n").encode("utf-8")
    }
    if result["onboarding"] is not None:
        payloads["ctgov-monitor-onboarding.json"] = (
            json.dumps(result["onboarding"], indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    for name, payload in payloads.items():
        path = output_dir / name
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f"OUTPUT_COLLISION_REFUSED: {path}")
        path.write_bytes(payload)
    manifest = {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_CT_GOV_MONITOR_ONBOARDING",
        "file_count": len(payloads),
        "files": [
            {"path": name, "sha256": _sha256_bytes(payload), "bytes": len(payload)}
            for name, payload in sorted(payloads.items())
        ],
        "network_execution_performed": False,
        "quarantine_approval_performed": False,
        "monitor_registry_successor_created": False,
        "monitor_creation_performed": False,
        "source_namespace_publication_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": "Noncanonical monitor-review/onboarding manifest only; no collection or registry authority.",
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists() and manifest_path.read_bytes() != manifest_bytes:
        raise ValueError(f"OUTPUT_COLLISION_REFUSED: {manifest_path}")
    manifest_path.write_bytes(manifest_bytes)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-materialization-dir", type=Path, required=True)
    parser.add_argument("--monitor-review-packet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_onboarding(args.source_materialization_dir, args.monitor_review_packet)
    manifest = write_outputs(result, args.output_dir)
    print(json.dumps({
        "approved_count": result["summary"]["approved_count"],
        "onboarding_created": result["onboarding"] is not None,
        "manifest": manifest,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())