#!/usr/bin/env python3
"""Apply explicit SU-TRIALS human decisions and draft a Source-namespace successor.

This operational bridge deliberately separates four states:
1. deterministic recorded-replay candidate projection,
2. Workbench PENDING_HUMAN_ACCEPTANCE proposals,
3. explicit local human adjudication,
4. noncanonical Source-namespace successor proposal for ACCEPTed source identities.

Workbench adjudication is always invoked with create_successor=False. This script never creates a
source-monitor-registry successor, monitor, Trial/site relationship, assessment mutation, or
canonical publication. Runtime actor strings are local attribution only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, NamedTuple

import run_su_trials_recorded_replay as replay
import stage_su_trials_human_review as staging

PROGRAMME_ID = "SU-TRIALS-CTGOV-v0.1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PROPOSAL_ID = re.compile(r"^DSP-[0-9a-f]{32}$")
_RUN_ID = re.compile(r"^DRUN-[0-9a-f]{32}$")
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_EXPECTED_STATUS = {
    "ACCEPT": "ACCEPTED",
    "REJECT": "REJECTED",
    "DEFER": "DEFERRED",
    "EXCLUDE": "EXCLUDED",
}


class WorkbenchAPI(NamedTuple):
    load_proposal: Callable[..., dict[str, Any]]
    load_adjudication: Callable[..., dict[str, Any]]
    adjudicate_candidate_source: Callable[..., dict[str, Any]]


def _load_workbench_api() -> WorkbenchAPI:
    try:
        from neuroai_workbench.discovery import (
            adjudicate_candidate_source,
            load_adjudication,
            load_proposal,
        )
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("Required Workbench adjudication API is unavailable") from exc
    return WorkbenchAPI(
        load_proposal=load_proposal,
        load_adjudication=load_adjudication,
        adjudicate_candidate_source=adjudicate_candidate_source,
    )


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _review_index(workspace: Path, path: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    review_root = (workspace / "programme-review" / PROGRAMME_ID).resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(review_root):
        raise ValueError("Review index must be inside the SU-TRIALS operational review workspace")
    if not resolved.is_file():
        raise ValueError("Review index file does not exist")
    payload = resolved.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Review index must be an object")
    if value.get("schema_version") != "0.1.0" or value.get("status") != "LOCAL_OPERATIONAL_HUMAN_REVIEW_INDEX":
        raise ValueError("Review index contract/status mismatch")
    if value.get("programme_id") != PROGRAMME_ID:
        raise ValueError("Review index programme mismatch")
    if value.get("automatic_mutation_performed") is not False:
        raise ValueError("Review index indicates automatic mutation")
    if value.get("human_adjudication_performed") is not False:
        raise ValueError("Review index already claims human adjudication")
    if value.get("canonical_successor_ready") is not False:
        raise ValueError("Review index improperly claims canonical successor readiness")
    manifest_sha = value.get("projection_manifest_sha256")
    current_index_sha = value.get("current_known_nct_index_sha256")
    run_id = value.get("workbench_run_id")
    query_id = value.get("workbench_query_id")
    if not isinstance(manifest_sha, str) or not _HEX64.fullmatch(manifest_sha):
        raise ValueError("Review index projection manifest digest invalid")
    if not isinstance(current_index_sha, str) or not _HEX64.fullmatch(current_index_sha):
        raise ValueError("Review index staging NCT-index digest invalid")
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("Review index Workbench run ID invalid")
    if not isinstance(query_id, str) or not query_id.startswith("DISCOVERY-"):
        raise ValueError("Review index Workbench query ID invalid")
    rows = value.get("proposals")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Review index proposals must be a non-empty object array")
    if value.get("proposal_count") != len(rows):
        raise ValueError("Review index proposal_count mismatch")
    proposal_ids: set[str] = set()
    nct_ids: set[str] = set()
    for row in rows:
        proposal_id = row.get("proposal_id")
        nct_id = row.get("nct_id")
        if not isinstance(proposal_id, str) or not _PROPOSAL_ID.fullmatch(proposal_id):
            raise ValueError("Review index proposal ID invalid")
        if not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id):
            raise ValueError("Review index NCT ID invalid")
        if proposal_id in proposal_ids or nct_id in nct_ids:
            raise ValueError("Review index contains duplicate proposal/NCT identity")
        proposal_ids.add(proposal_id)
        nct_ids.add(nct_id)
        query_ids = row.get("query_ids")
        if not isinstance(query_ids, list) or not query_ids or query_ids != sorted(set(query_ids)):
            raise ValueError(f"{proposal_id}: review query memberships invalid")
        for key in ("normalized_aggregate_digest", "candidate_input_sha256"):
            digest = row.get(key)
            if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
                raise ValueError(f"{proposal_id}: review provenance digest invalid: {key}")
    return {
        "path": resolved,
        "sha256": _sha256_bytes(payload),
        "record": value,
        "proposal_rows": {row["proposal_id"]: row for row in rows},
    }


def _decision_packet(path: Path, review: Mapping[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("Decision packet file does not exist")
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Decision packet must be an object")
    if value.get("schema_version") != "0.1.0":
        raise ValueError("Decision packet schema_version mismatch")
    if value.get("artifact") != "su_trials_human_decision_packet" or value.get("status") != "EXPLICIT_LOCAL_HUMAN_DECISION_PACKET":
        raise ValueError("Decision packet artifact/status mismatch")
    if value.get("programme_id") != PROGRAMME_ID:
        raise ValueError("Decision packet programme mismatch")
    review_record = review["record"]
    exact_bindings = {
        "projection_manifest_sha256": review_record["projection_manifest_sha256"],
        "review_index_sha256": review["sha256"],
        "workbench_query_id": review_record["workbench_query_id"],
        "workbench_run_id": review_record["workbench_run_id"],
    }
    for key, expected in exact_bindings.items():
        if value.get(key) != expected:
            raise ValueError(f"Decision packet binding mismatch: {key}")
    actor = value.get("adjudicated_by")
    when = value.get("adjudicated_at")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("Decision packet adjudicated_by must be non-empty")
    if not isinstance(when, str) or len(when) < 10:
        raise ValueError("Decision packet adjudicated_at must be non-empty timestamp/date text")
    if value.get("identity_boundary") != "LOCAL_UNAUTHENTICATED_ATTRIBUTION":
        raise ValueError("Decision packet identity boundary mismatch")
    boundaries = {
        "source_namespace_admission_only": True,
        "monitor_creation_authorized": False,
        "trial_entity_creation_authorized": False,
        "trial_site_relationship_creation_authorized": False,
        "assessment_mutation_authorized": False,
        "canonical_publication_authorized": False,
    }
    for key, expected in boundaries.items():
        if value.get(key) is not expected:
            raise ValueError(f"Decision packet authority boundary weakened: {key}")
    if not isinstance(value.get("authority_boundary"), str) or not value["authority_boundary"].strip():
        raise ValueError("Decision packet authority_boundary must be non-empty")

    decisions = value.get("decisions")
    if not isinstance(decisions, list) or not decisions or not all(isinstance(row, dict) for row in decisions):
        raise ValueError("Decision packet decisions must be a non-empty object array")
    review_rows = review["proposal_rows"]
    seen: set[str] = set()
    decision_by_proposal: dict[str, dict[str, Any]] = {}
    for row in decisions:
        proposal_id = row.get("proposal_id")
        nct_id = row.get("nct_id")
        decision = row.get("decision")
        rationale = row.get("rationale")
        if not isinstance(proposal_id, str) or not _PROPOSAL_ID.fullmatch(proposal_id):
            raise ValueError("Decision proposal_id invalid")
        if proposal_id in seen:
            raise ValueError(f"Duplicate decision for proposal {proposal_id}")
        seen.add(proposal_id)
        if proposal_id not in review_rows:
            raise ValueError(f"Decision packet contains extra proposal {proposal_id}")
        if nct_id != review_rows[proposal_id]["nct_id"]:
            raise ValueError(f"{proposal_id}: decision NCT identity mismatch")
        if decision not in _EXPECTED_STATUS:
            raise ValueError(f"{proposal_id}: unsupported decision {decision!r}")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"{proposal_id}: rationale must be non-empty")
        decision_by_proposal[proposal_id] = row
    if set(decision_by_proposal) != set(review_rows):
        missing = sorted(set(review_rows) - set(decision_by_proposal))
        raise ValueError(f"Decision packet must dispose every staged proposal; missing={missing}")
    return {
        "path": path.resolve(),
        "sha256": _sha256_bytes(payload),
        "record": value,
        "decisions": decision_by_proposal,
    }


def _projection_candidates(projection_dir: Path, review: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    verified = staging.verify_projection(projection_dir)
    if verified["manifest_sha256"] != review["record"]["projection_manifest_sha256"]:
        raise ValueError("Projection manifest no longer matches the staged review index")
    candidates = verified["candidates"]
    if not isinstance(candidates, list):
        raise ValueError("Projection candidates unavailable")
    by_nct: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Projection candidate must be an object")
        nct_id = candidate.get("record_key")
        if not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id) or nct_id in by_nct:
            raise ValueError("Projection candidate NCT identity invalid/duplicate")
        by_nct[nct_id] = candidate
    review_ncts = {row["nct_id"] for row in review["proposal_rows"].values()}
    if set(by_nct) != review_ncts:
        raise ValueError("Projection candidate identity set differs from staged review index")
    for review_row in review["proposal_rows"].values():
        candidate = by_nct[review_row["nct_id"]]
        if staging._digest(candidate) != review_row["candidate_input_sha256"]:
            raise ValueError(f"{review_row['proposal_id']}: candidate input digest mismatch")
        if candidate.get("query_ids") != review_row["query_ids"]:
            raise ValueError(f"{review_row['proposal_id']}: query-membership provenance mismatch")
        if candidate.get("normalized_aggregate_digest") != review_row["normalized_aggregate_digest"]:
            raise ValueError(f"{review_row['proposal_id']}: normalized digest provenance mismatch")
    return by_nct


def _current_source_namespace() -> dict[str, Any]:
    modules = (
        replay.project_v14_sources_to_v2,
        replay.project_v16_sources_observations_to_v2,
        replay.project_v17_prima_sources_to_v2,
    )
    source_ids: set[str] = set()
    for module in modules:
        result = module.project()
        sources = result.get("sources")
        if not isinstance(sources, list):
            raise ValueError("Source projector did not return sources")
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("Projected source must be object")
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                raise ValueError("Projected source missing source_id")
            if source_id in source_ids:
                raise ValueError(f"Duplicate controlled Source identity {source_id}")
            source_ids.add(source_id)
    if len(source_ids) != 248:
        raise ValueError(f"Expected current 248-Source namespace, found {len(source_ids)}")
    nct = replay.build_known_nct_source_index()
    if nct.get("materialized_source_count") != 248:
        raise ValueError("NCT identity index source count mismatch")
    mapping = nct.get("nct_to_source")
    if not isinstance(mapping, dict):
        raise ValueError("Current NCT identity map unavailable")
    return {
        "materialized_source_count": len(source_ids),
        "source_ids": source_ids,
        "source_ids_sha256": _digest(sorted(source_ids)),
        "known_ctgov_nct_count": len(mapping),
        "nct_to_source": mapping,
        "known_nct_index_sha256": _digest(dict(sorted(mapping.items()))),
    }


def _registry_successor_files(workspace: Path) -> set[str]:
    root = workspace / "discovery" / "registry_successors"
    if not root.exists():
        return set()
    return {str(path.resolve()) for path in root.glob("*.json") if path.is_file()}


def _validate_workbench_proposal(
    proposal: Mapping[str, Any],
    *,
    review_row: Mapping[str, Any],
    candidate: Mapping[str, Any],
    review_record: Mapping[str, Any],
) -> None:
    proposal_id = review_row["proposal_id"]
    if proposal.get("proposal_id") != proposal_id:
        raise ValueError(f"{proposal_id}: Workbench proposal identity mismatch")
    if proposal.get("run_id") != review_record["workbench_run_id"]:
        raise ValueError(f"{proposal_id}: Workbench run binding mismatch")
    if proposal.get("query_id") != review_record["workbench_query_id"]:
        raise ValueError(f"{proposal_id}: Workbench query binding mismatch")
    if proposal.get("classification") != "NEW":
        raise ValueError(f"{proposal_id}: only NEW staged proposals may be adjudicated here")
    if proposal.get("automatic_mutation_performed") is not False:
        raise ValueError(f"{proposal_id}: proposal indicates automatic mutation")
    proposed = proposal.get("proposed_source")
    if not isinstance(proposed, dict):
        raise ValueError(f"{proposal_id}: proposed_source missing")
    expected = {
        "record_key": candidate["record_key"],
        "title": candidate["title"],
        "url": candidate["url"],
        "publisher": candidate["publisher"],
        "source_class": candidate["source_class"],
        "suggested_source_id": candidate["suggested_source_id"],
    }
    for key, value in expected.items():
        if proposed.get(key) != value:
            raise ValueError(f"{proposal_id}: Workbench proposal source field drift: {key}")


def _matching_existing_adjudication(
    api: WorkbenchAPI,
    workspace: Path,
    *,
    proposal: Mapping[str, Any],
    decision: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> dict[str, Any] | None:
    if proposal.get("status") == "PENDING_HUMAN_ACCEPTANCE":
        if proposal.get("adjudication_id") is not None:
            raise ValueError(f"{proposal['proposal_id']}: pending proposal unexpectedly has adjudication_id")
        return None
    expected_status = _EXPECTED_STATUS[decision["decision"]]
    if proposal.get("status") != expected_status:
        raise ValueError(
            f"{proposal['proposal_id']}: proposal already adjudicated as {proposal.get('status')}, expected {expected_status}"
        )
    adjudication_id = proposal.get("adjudication_id")
    if not isinstance(adjudication_id, str):
        raise ValueError(f"{proposal['proposal_id']}: final proposal missing adjudication_id")
    adjudication = api.load_adjudication(workspace, adjudication_id)
    expected = {
        "proposal_id": proposal["proposal_id"],
        "run_id": proposal["run_id"],
        "decision": decision["decision"],
        "rationale": decision["rationale"],
        "adjudicated_by": packet["record"]["adjudicated_by"],
        "adjudicated_at": packet["record"]["adjudicated_at"],
        "registry_successor_id": None,
        "automatic_mutation_performed": False,
    }
    for key, value in expected.items():
        if adjudication.get(key) != value:
            raise ValueError(f"{proposal['proposal_id']}: existing adjudication does not match decision packet: {key}")
    return adjudication


def _validate_adjudication_result(
    result: Mapping[str, Any],
    *,
    decision: Mapping[str, Any],
    packet: Mapping[str, Any],
    proposal_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    adjudication = result.get("adjudication")
    proposal = result.get("proposal")
    if not isinstance(adjudication, dict) or not isinstance(proposal, dict):
        raise ValueError(f"{proposal_id}: Workbench adjudication result shape invalid")
    expected_adjudication = {
        "proposal_id": proposal_id,
        "decision": decision["decision"],
        "rationale": decision["rationale"],
        "adjudicated_by": packet["record"]["adjudicated_by"],
        "adjudicated_at": packet["record"]["adjudicated_at"],
        "registry_successor_id": None,
        "automatic_mutation_performed": False,
    }
    for key, value in expected_adjudication.items():
        if adjudication.get(key) != value:
            raise ValueError(f"{proposal_id}: Workbench adjudication mismatch: {key}")
    if result.get("successor") is not None:
        raise ValueError(f"{proposal_id}: WORKBENCH_REGISTRY_SUCCESSOR_LEAKAGE")
    if proposal.get("status") != _EXPECTED_STATUS[decision["decision"]]:
        raise ValueError(f"{proposal_id}: Workbench proposal final status mismatch")
    if proposal.get("automatic_mutation_performed") is not False:
        raise ValueError(f"{proposal_id}: Workbench proposal automatic mutation signal")
    return adjudication, proposal


def _output_root(workspace: Path, run_id: str, packet_sha256: str) -> Path:
    return workspace / "programme-adjudication" / PROGRAMME_ID / run_id / packet_sha256[:16]


def _write_failure_summary(
    output_root: Path,
    *,
    review: Mapping[str, Any],
    packet: Mapping[str, Any],
    completed: Mapping[str, Mapping[str, Any]],
    failed_proposal_id: str,
    error: Exception,
) -> None:
    summary = {
        "schema_version": "0.1.0",
        "status": "PARTIAL_WORKBENCH_ADJUDICATION_FAILURE",
        "programme_id": PROGRAMME_ID,
        "projection_manifest_sha256": review["record"]["projection_manifest_sha256"],
        "review_index_sha256": review["sha256"],
        "decision_packet_sha256": packet["sha256"],
        "workbench_run_id": review["record"]["workbench_run_id"],
        "completed_proposal_ids": sorted(completed),
        "failed_proposal_id": failed_proposal_id,
        "remaining_proposal_ids": sorted(set(packet["decisions"]) - set(completed) - {failed_proposal_id}),
        "error": f"{type(error).__name__}: {error}",
        "safe_resume_supported": True,
        "source_namespace_successor_emitted": False,
        "monitor_registry_successor_creation_requested": False,
        "monitor_creation_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Partial operational failure record only. Completed exact matching adjudications may be recognized on retry; "
            "no Source-namespace successor is emitted until every decision is reconciled."
        ),
    }
    _atomic_json(output_root / "adjudication-summary.json", summary)


def adjudicate(
    projection_dir: Path,
    workspace: Path,
    review_index_path: Path,
    decision_packet_path: Path,
    *,
    workbench_api: WorkbenchAPI | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    review = _review_index(workspace, review_index_path)
    packet = _decision_packet(decision_packet_path, review)
    candidates_by_nct = _projection_candidates(projection_dir, review)
    namespace = _current_source_namespace()
    api = workbench_api or _load_workbench_api()
    output_root = _output_root(workspace, review["record"]["workbench_run_id"], packet["sha256"])

    review_rows = review["proposal_rows"]
    proposals: dict[str, dict[str, Any]] = {}
    existing_adjudications: dict[str, dict[str, Any]] = {}
    accepted_source_ids: set[str] = set()
    for proposal_id in sorted(review_rows):
        row = review_rows[proposal_id]
        candidate = candidates_by_nct[row["nct_id"]]
        proposal = api.load_proposal(workspace, proposal_id)
        _validate_workbench_proposal(
            proposal,
            review_row=row,
            candidate=candidate,
            review_record=review["record"],
        )
        proposals[proposal_id] = proposal
        decision = packet["decisions"][proposal_id]
        if decision["decision"] == "ACCEPT":
            nct_id = row["nct_id"]
            source_id = candidate["suggested_source_id"]
            if nct_id in namespace["nct_to_source"]:
                raise ValueError(
                    f"STALE_ACCEPT_RECLASSIFICATION_REQUIRED: {nct_id} is now controlled as {namespace['nct_to_source'][nct_id]}"
                )
            if source_id in namespace["source_ids"]:
                raise ValueError(f"STALE_ACCEPT_SOURCE_ID_COLLISION: {source_id} already exists in current Source namespace")
            if source_id in accepted_source_ids:
                raise ValueError(f"Decision packet proposes duplicate accepted source_id {source_id}")
            accepted_source_ids.add(source_id)
        existing = _matching_existing_adjudication(
            api,
            workspace,
            proposal=proposal,
            decision=decision,
            packet=packet,
        )
        if existing is not None:
            existing_adjudications[proposal_id] = existing

    before_successors = _registry_successor_files(workspace)
    completed: dict[str, dict[str, Any]] = dict(existing_adjudications)
    final_proposals: dict[str, dict[str, Any]] = {}
    for proposal_id in sorted(existing_adjudications):
        final_proposals[proposal_id] = proposals[proposal_id]

    for proposal_id in sorted(review_rows):
        if proposal_id in completed:
            continue
        decision = packet["decisions"][proposal_id]
        try:
            result = api.adjudicate_candidate_source(
                workspace,
                proposal_id,
                decision["decision"],
                rationale=decision["rationale"],
                actor=packet["record"]["adjudicated_by"],
                create_successor=False,
                adjudicated_at=packet["record"]["adjudicated_at"],
            )
            if not isinstance(result, dict):
                raise ValueError("Workbench adjudication result must be an object")
            adjudication_record, final_proposal = _validate_adjudication_result(
                result,
                decision=decision,
                packet=packet,
                proposal_id=proposal_id,
            )
            completed[proposal_id] = adjudication_record
            final_proposals[proposal_id] = final_proposal
            after_step = _registry_successor_files(workspace)
            if after_step != before_successors:
                raise ValueError("WORKBENCH_REGISTRY_SUCCESSOR_LEAKAGE")
        except Exception as exc:
            _write_failure_summary(
                output_root,
                review=review,
                packet=packet,
                completed=completed,
                failed_proposal_id=proposal_id,
                error=exc,
            )
            raise RuntimeError(
                f"PARTIAL_WORKBENCH_ADJUDICATION_FAILURE at {proposal_id}; exact matching completed decisions may be resumed"
            ) from exc

    if set(completed) != set(review_rows):
        raise ValueError("Not every staged proposal has a reconciled Workbench adjudication")
    if _registry_successor_files(workspace) != before_successors:
        raise ValueError("WORKBENCH_REGISTRY_SUCCESSOR_LEAKAGE")

    accepted_ids = sorted(
        proposal_id
        for proposal_id, decision in packet["decisions"].items()
        if decision["decision"] == "ACCEPT"
    )
    successor: dict[str, Any] | None = None
    successor_path: Path | None = None
    if accepted_ids:
        basis = {
            "programme_id": PROGRAMME_ID,
            "projection_manifest_sha256": review["record"]["projection_manifest_sha256"],
            "review_index_sha256": review["sha256"],
            "decision_packet_sha256": packet["sha256"],
            "base_source_ids_sha256": namespace["source_ids_sha256"],
            "base_known_nct_index_sha256": namespace["known_nct_index_sha256"],
            "accepted_proposal_ids": accepted_ids,
            "accepted_source_ids": [candidates_by_nct[review_rows[pid]["nct_id"]]["suggested_source_id"] for pid in accepted_ids],
        }
        successor_id = f"SNSP-{_digest(basis)[:32]}"
        accepted_sources: list[dict[str, Any]] = []
        for proposal_id in accepted_ids:
            review_row = review_rows[proposal_id]
            candidate = candidates_by_nct[review_row["nct_id"]]
            adjudication_record = completed[proposal_id]
            accepted_sources.append(
                {
                    "source_id": candidate["suggested_source_id"],
                    "nct_id": candidate["record_key"],
                    "title": candidate["title"],
                    "publisher": candidate["publisher"],
                    "canonical_locator": candidate["url"],
                    "source_class": candidate["source_class"],
                    "source_origin": "DISCOVERY_CTGOV_RECORDED_REPLAY_HUMAN_ACCEPTED",
                    "namespace_admission_state": "PROPOSED_NOT_CANONICAL",
                    "from_proposal_id": proposal_id,
                    "workbench_adjudication_id": adjudication_record["adjudication_id"],
                    "query_ids": review_row["query_ids"],
                    "normalized_aggregate_digest": review_row["normalized_aggregate_digest"],
                    "candidate_input_sha256": review_row["candidate_input_sha256"],
                    "claim_boundary": (
                        "Human ACCEPT admits only this public source identity into a draft namespace-successor proposal. "
                        "It does not establish clinical truth, trial/site relationships, authorization, safety, effectiveness, "
                        "system conformance, monitoring cadence, assessment effect, or canonical publication."
                    ),
                }
            )
        successor = {
            "schema_version": "0.1.0",
            "artifact": "source_namespace_successor_proposal",
            "status": "DRAFT_NONCANONICAL_SOURCE_NAMESPACE_SUCCESSOR",
            "proposal_id": successor_id,
            "programme_id": PROGRAMME_ID,
            "created_at": packet["record"]["adjudicated_at"],
            "created_by": packet["record"]["adjudicated_by"],
            "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
            "base_source_namespace": {
                "materialized_source_count": namespace["materialized_source_count"],
                "source_ids_sha256": namespace["source_ids_sha256"],
                "known_ctgov_nct_count": namespace["known_ctgov_nct_count"],
                "known_nct_index_sha256": namespace["known_nct_index_sha256"],
            },
            "decision_provenance": {
                "projection_manifest_sha256": review["record"]["projection_manifest_sha256"],
                "review_index_sha256": review["sha256"],
                "decision_packet_sha256": packet["sha256"],
                "workbench_query_id": review["record"]["workbench_query_id"],
                "workbench_run_id": review["record"]["workbench_run_id"],
            },
            "accepted_proposal_ids": accepted_ids,
            "accepted_sources": accepted_sources,
            "overwrite_refused": True,
            "source_namespace_publication_performed": False,
            "monitor_creation_performed": False,
            "trial_entity_creation_performed": False,
            "trial_site_relationship_creation_performed": False,
            "assessment_mutation_performed": False,
            "canonical_successor_ready": False,
            "authority_boundary": (
                "Draft Source-namespace succession only. This proposal is not a canonical Source registry, monitor registry, "
                "Trial/site graph update, assessment update, publication authorization or institutional endorsement."
            ),
        }
        successor_path = output_root / f"{successor_id}.json"
        _atomic_json(successor_path, successor)

    disposition_rows = []
    for proposal_id in sorted(review_rows):
        row = review_rows[proposal_id]
        decision = packet["decisions"][proposal_id]
        adjudication_record = completed[proposal_id]
        disposition_rows.append(
            {
                "proposal_id": proposal_id,
                "nct_id": row["nct_id"],
                "decision": decision["decision"],
                "rationale": decision["rationale"],
                "workbench_adjudication_id": adjudication_record["adjudication_id"],
                "proposal_final_status": _EXPECTED_STATUS[decision["decision"]],
            }
        )

    summary = {
        "schema_version": "0.1.0",
        "status": (
            "COMPLETED_WITH_DRAFT_SOURCE_NAMESPACE_SUCCESSOR"
            if successor is not None
            else "COMPLETED_NO_SOURCE_NAMESPACE_ACCEPTANCES"
        ),
        "programme_id": PROGRAMME_ID,
        "projection_manifest_sha256": review["record"]["projection_manifest_sha256"],
        "review_index_sha256": review["sha256"],
        "decision_packet_sha256": packet["sha256"],
        "workbench_query_id": review["record"]["workbench_query_id"],
        "workbench_run_id": review["record"]["workbench_run_id"],
        "adjudicated_by": packet["record"]["adjudicated_by"],
        "adjudicated_at": packet["record"]["adjudicated_at"],
        "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
        "proposal_count": len(disposition_rows),
        "accept_count": len(accepted_ids),
        "dispositions": disposition_rows,
        "source_namespace_successor_proposal_id": successor["proposal_id"] if successor else None,
        "source_namespace_successor_path": str(successor_path) if successor_path else None,
        "workbench_monitor_registry_successor_created": False,
        "source_namespace_publication_performed": False,
        "monitor_creation_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Records explicit local human disposition and, for ACCEPT decisions, a draft Source-namespace successor proposal. "
            "It does not authenticate the adjudicator or authorize monitoring, graph mutation, assessment effect or publication."
        ),
    }
    summary_path = output_root / "adjudication-summary.json"
    _atomic_json(summary_path, summary)
    return {
        "status": summary["status"],
        "programme_id": PROGRAMME_ID,
        "decision_packet_sha256": packet["sha256"],
        "proposal_count": len(disposition_rows),
        "accept_count": len(accepted_ids),
        "summary_path": str(summary_path),
        "source_namespace_successor_proposal_id": successor["proposal_id"] if successor else None,
        "source_namespace_successor_path": str(successor_path) if successor_path else None,
        "workbench_monitor_registry_successor_created": False,
        "monitor_creation_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--review-index", type=Path, required=True)
    parser.add_argument("--decision-packet", type=Path, required=True)
    args = parser.parse_args()
    result = adjudicate(
        args.projection_dir,
        args.workspace,
        args.review_index,
        args.decision_packet,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
