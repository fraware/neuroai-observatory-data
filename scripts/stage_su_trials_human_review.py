#!/usr/bin/env python3
"""Stage a verified SU-TRIALS replay projection into Workbench human-gated review.

This is an operational bridge only. It verifies one deterministic replay package, re-checks
current NCT identity against the controlled Source namespace, creates PENDING human-review
proposals through Workbench OFFLINE_REPLAY, and writes a local review-index sidecar. It never
adjudicates proposals or mutates canonical S2 data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, NamedTuple

import run_su_trials_recorded_replay as replay

PROGRAMME_ID = "SU-TRIALS-CTGOV-v0.1"
EXPECTED_FILES = {
    "normalized-studies.jsonl",
    "known-duplicates.jsonl",
    "new-candidate-inputs.jsonl",
    "input-provenance.json",
    "known-source-index-summary.json",
    "query-reports.json",
    "reconciliation.json",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class WorkbenchAPI(NamedTuple):
    store_query: Callable[..., dict[str, Any]]
    execute_discovery_query: Callable[..., dict[str, Any]]


def _load_workbench_api() -> WorkbenchAPI:
    try:
        from neuroai_workbench.discovery import execute_discovery_query, store_query
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench discovery API is unavailable; human-review staging cannot proceed"
        ) from exc
    return WorkbenchAPI(store_query=store_query, execute_discovery_query=execute_discovery_query)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number}: JSONL record must be an object")
        rows.append(value)
    return rows


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


def verify_projection(projection_dir: Path) -> dict[str, Any]:
    root = projection_dir.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Replay projection is missing manifest.json")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("Replay manifest must be an object")
    if manifest.get("programme_id") != PROGRAMME_ID:
        raise ValueError("Replay manifest programme_id mismatch")
    if manifest.get("status") != "NONCANONICAL_SU_TRIALS_RECORDED_REPLAY_PROJECTION":
        raise ValueError("Replay manifest status mismatch")
    if manifest.get("canonical_successor_ready") is not False:
        raise ValueError("Replay manifest cannot claim canonical successor readiness")
    if manifest.get("raw_api_page_payloads_emitted") is not False:
        raise ValueError("Replay manifest indicates raw API page emission")

    entries = manifest.get("files")
    if not isinstance(entries, list) or not all(isinstance(row, dict) for row in entries):
        raise ValueError("Replay manifest files must be an object array")
    if manifest.get("file_count") != len(entries):
        raise ValueError("Replay manifest file_count mismatch")

    paths = [row.get("path") for row in entries]
    if set(paths) != EXPECTED_FILES or len(paths) != len(set(paths)):
        raise ValueError(f"Replay manifest file set mismatch: {sorted(str(value) for value in paths)}")

    for entry in entries:
        relative = entry.get("path")
        if not isinstance(relative, str) or Path(relative).name != relative:
            raise ValueError(f"Unsafe replay manifest path {relative!r}")
        path = root / relative
        if not path.is_file():
            raise ValueError(f"Replay manifest file missing: {relative}")
        payload = path.read_bytes()
        expected_sha = entry.get("sha256")
        if not isinstance(expected_sha, str) or not _HEX64.fullmatch(expected_sha):
            raise ValueError(f"Replay manifest digest invalid: {relative}")
        if _sha256_bytes(payload) != expected_sha:
            raise ValueError(f"Replay manifest checksum mismatch: {relative}")
        if entry.get("bytes") != len(payload):
            raise ValueError(f"Replay manifest byte count mismatch: {relative}")

    reconciliation = _load_json(root / "reconciliation.json")
    if not isinstance(reconciliation, dict):
        raise ValueError("Replay reconciliation must be an object")
    if reconciliation.get("mechanically_complete") is not True:
        raise ValueError("Replay projection is not mechanically complete")
    for key in (
        "raw_api_page_payloads_emitted",
        "participant_level_data_emitted",
        "automatic_source_admission",
        "automatic_trial_entity_creation",
        "automatic_trial_site_relationship_creation",
        "automatic_monitor_creation",
        "automatic_assessment_mutation",
        "human_adjudication_performed",
        "canonical_successor_ready",
    ):
        if reconciliation.get(key) is not False:
            raise ValueError(f"Replay reconciliation boundary weakened: {key}")

    provenance = _load_json(root / "input-provenance.json")
    candidates = _load_jsonl(root / "new-candidate-inputs.jsonl")
    query_reports = _load_json(root / "query-reports.json")
    if not isinstance(provenance, dict) or not isinstance(query_reports, list):
        raise ValueError("Replay provenance/query reports have invalid shape")

    manifest_sha256 = _sha256_bytes(manifest_bytes)
    return {
        "root": root,
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "reconciliation": reconciliation,
        "input_provenance": provenance,
        "candidates": candidates,
        "query_reports": query_reports,
    }


def _validate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    programme = replay._programme()
    configured_query_ids = {
        row["query_id"] for row in programme["query_streams"] if row.get("status") == "ACTIVE"
    }
    current = replay.build_known_nct_source_index()["nct_to_source"]
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []

    for row in sorted(candidates, key=lambda item: str(item.get("record_key", ""))):
        nct_id = row.get("record_key")
        if not isinstance(nct_id, str) or not re.fullmatch(r"NCT\d{8}", nct_id):
            raise ValueError(f"Invalid NEW candidate NCT identity {nct_id!r}")
        if nct_id in seen:
            raise ValueError(f"Duplicate NEW candidate identity {nct_id}")
        seen.add(nct_id)
        if nct_id in current:
            raise ValueError(
                f"STALE_PROJECTION_RECLASSIFICATION_REQUIRED: {nct_id} is now controlled as {current[nct_id]}"
            )
        if row.get("classification_hint") != "NEW" or row.get("duplicate_of_source_id") is not None:
            raise ValueError(f"{nct_id}: replay NEW candidate classification is invalid")
        query_ids = row.get("query_ids")
        if (
            not isinstance(query_ids, list)
            or not query_ids
            or not all(isinstance(value, str) for value in query_ids)
            or query_ids != sorted(set(query_ids))
            or not set(query_ids).issubset(configured_query_ids)
        ):
            raise ValueError(f"{nct_id}: invalid configured query membership")
        aggregate = row.get("normalized_aggregate_digest")
        if not isinstance(aggregate, str) or not _HEX64.fullmatch(aggregate):
            raise ValueError(f"{nct_id}: normalized aggregate digest invalid")
        for field in ("title", "url", "publisher", "source_class", "suggested_source_id"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"{nct_id}: candidate field {field} missing")
        normalized.append(row)
    return normalized


def _union_query(*, manifest_sha256: str, captured_at: str, candidate_count: int) -> dict[str, Any]:
    programme = replay._programme()
    suffix = manifest_sha256[:12].upper()
    query_id = f"DISCOVERY-CTGOV-SU-TRIALS-UNION-{suffix}"
    return {
        "query_id": query_id,
        "object_family": "DISCOVERY_QUERY",
        "query_text": f"Manifest-bound union of {PROGRAMME_ID} configured ClinicalTrials.gov query streams",
        "filters": {
            "programme_id": PROGRAMME_ID,
            "projection_manifest_sha256": manifest_sha256,
            "original_query_ids": sorted(
                row["query_id"] for row in programme["query_streams"] if row.get("status") == "ACTIVE"
            ),
            "candidate_count": candidate_count,
            "execution_semantics": "OFFLINE_REPLAY_SANITIZED_UNION",
        },
        "source_system": "CLINICALTRIALS_GOV",
        "created_at": captured_at,
        "created_by": "SU-TRIALS-RECORDED-REPLAY-STAGER",
        "status": "ACTIVE",
        "network_access_required": False,
        "notes": "Operational union scope only; individual candidate query memberships remain in the local review index.",
        "boundary": (
            "Manifest-bound operational review query. It does not establish discovery completeness, "
            "source admission, trial identity beyond exact NCT registry identity, or canonical authority."
        ),
    }


def stage_projection(
    projection_dir: Path,
    workspace: Path,
    *,
    actor: str = "local-user",
    staged_at: str | None = None,
    workbench_api: WorkbenchAPI | None = None,
) -> dict[str, Any]:
    verified = verify_projection(projection_dir)
    candidates = _validate_candidates(verified["candidates"])
    if not candidates:
        return {
            "status": "NO_NEW_CANDIDATES_TO_STAGE",
            "programme_id": PROGRAMME_ID,
            "projection_manifest_sha256": verified["manifest_sha256"],
            "candidate_count": 0,
            "discovery_run_id": None,
            "review_index_path": None,
            "automatic_mutation_performed": False,
            "human_adjudication_performed": False,
            "canonical_successor_ready": False,
        }

    api = workbench_api or _load_workbench_api()
    captured_at = verified["input_provenance"].get("captured_at")
    if not isinstance(captured_at, str) or not captured_at:
        raise ValueError("Replay captured_at missing from input provenance")
    execution_time = staged_at or captured_at
    query = _union_query(
        manifest_sha256=verified["manifest_sha256"],
        captured_at=captured_at,
        candidate_count=len(candidates),
    )
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    api.store_query(workspace, query)

    workbench_records = [
        {
            "record_key": row["record_key"],
            "title": row["title"],
            "url": row["url"],
            "publisher": row["publisher"],
            "source_class": row["source_class"],
            "suggested_source_id": row["suggested_source_id"],
            "classification_hint": "NEW",
        }
        for row in candidates
    ]
    outcome = api.execute_discovery_query(
        workspace,
        query["query_id"],
        actor=actor,
        execution_mode="OFFLINE_REPLAY",
        result_records=workbench_records,
        executed_at=execution_time,
    )
    if not isinstance(outcome, dict):
        raise ValueError("Workbench discovery outcome must be an object")
    run = outcome.get("run")
    proposals = outcome.get("proposals")
    if not isinstance(run, dict) or not isinstance(proposals, list) or not all(isinstance(row, dict) for row in proposals):
        raise ValueError("Workbench discovery outcome has invalid run/proposal shape")
    if run.get("query_id") != query["query_id"] or run.get("execution_mode") != "OFFLINE_REPLAY":
        raise ValueError("Workbench discovery run scope/provenance mismatch")
    if run.get("automatic_registry_mutation_performed") is not False:
        raise ValueError("Workbench discovery run performed automatic registry mutation")
    expected_counts = {"total": len(candidates), "new": len(candidates), "duplicate": 0, "excluded": 0}
    if run.get("result_counts") != expected_counts:
        raise ValueError(f"Workbench discovery classification count mismatch: {run.get('result_counts')}")
    if len(proposals) != len(candidates):
        raise ValueError("Workbench discovery proposal count mismatch")

    candidate_by_nct = {row["record_key"]: row for row in candidates}
    proposal_by_nct: dict[str, dict[str, Any]] = {}
    for proposal in proposals:
        proposed = proposal.get("proposed_source")
        if not isinstance(proposed, dict):
            raise ValueError("Workbench proposal proposed_source missing")
        nct_id = proposed.get("record_key")
        if not isinstance(nct_id, str) or nct_id not in candidate_by_nct or nct_id in proposal_by_nct:
            raise ValueError(f"Workbench proposal identity mismatch: {nct_id!r}")
        if proposal.get("classification") != "NEW" or proposal.get("status") != "PENDING_HUMAN_ACCEPTANCE":
            raise ValueError(f"Workbench proposal {nct_id} is not NEW/PENDING_HUMAN_ACCEPTANCE")
        if proposal.get("automatic_mutation_performed") is not False:
            raise ValueError(f"Workbench proposal {nct_id} performed automatic mutation")
        proposal_by_nct[nct_id] = proposal

    if set(proposal_by_nct) != set(candidate_by_nct):
        raise ValueError("Workbench proposal identity set differs from replay candidate set")

    index_rows: list[dict[str, Any]] = []
    for nct_id in sorted(candidate_by_nct):
        candidate = candidate_by_nct[nct_id]
        proposal = proposal_by_nct[nct_id]
        proposal_id = proposal.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise ValueError(f"Workbench proposal {nct_id} missing proposal_id")
        index_rows.append(
            {
                "proposal_id": proposal_id,
                "nct_id": nct_id,
                "query_ids": candidate["query_ids"],
                "normalized_aggregate_digest": candidate["normalized_aggregate_digest"],
                "candidate_input_sha256": _digest(candidate),
            }
        )

    run_id = run.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Workbench discovery run missing run_id")
    review_index = {
        "schema_version": "0.1.0",
        "status": "LOCAL_OPERATIONAL_HUMAN_REVIEW_INDEX",
        "programme_id": PROGRAMME_ID,
        "projection_manifest_sha256": verified["manifest_sha256"],
        "workbench_query_id": query["query_id"],
        "workbench_run_id": run_id,
        "staged_at": execution_time,
        "staged_by": actor,
        "identity_boundary": (
            "Runtime actor/reviewer identities are claimed local workflow identities; this record does not authenticate "
            "identity, independence, delegation or institutional authority."
        ),
        "proposal_count": len(index_rows),
        "proposals": index_rows,
        "automatic_mutation_performed": False,
        "human_adjudication_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "This index binds operational proposal IDs to deterministic replay provenance only. "
            "It does not accept proposals, create a registry successor, establish trial/site relationships, "
            "mutate assessments, or authorize canonical publication."
        ),
    }
    review_path = workspace / "programme-review" / PROGRAMME_ID / f"{run_id}.json"
    _atomic_json(review_path, review_index)

    return {
        "status": "STAGED_FOR_HUMAN_ACCEPTANCE",
        "programme_id": PROGRAMME_ID,
        "projection_manifest_sha256": verified["manifest_sha256"],
        "candidate_count": len(candidates),
        "discovery_query_id": query["query_id"],
        "discovery_run_id": run_id,
        "proposal_ids": [row["proposal_id"] for row in index_rows],
        "review_index_path": str(review_path),
        "automatic_mutation_performed": False,
        "human_adjudication_performed": False,
        "canonical_successor_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--actor", default="local-user")
    parser.add_argument("--staged-at")
    args = parser.parse_args()
    result = stage_projection(
        args.projection_dir,
        args.workspace,
        actor=args.actor,
        staged_at=args.staged_at,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
