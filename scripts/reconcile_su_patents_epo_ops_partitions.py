#!/usr/bin/env python3
"""Reconcile date-partitioned EPO OPS patent replay leaves against bounded parent probes.

This proof is deliberately narrower than the unbounded provider query. It establishes only that,
for the dated universe from 1800-01-01 through the replay capture date, declared child intervals
are contiguous/disjoint and their exact OPS denominators reconcile to the exact bounded parent
denominator. It does not establish recall for records without a usable publication date or any
substantive patent, system, legal, scientific, ethical, regulatory or canonical conclusion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation" / "epo_ops_patent_discovery_programme_v0.1.json"
LOWER_BOUND = "18000101"

Projector = Callable[..., dict[str, Any]]


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}: JSONL row must be object")
            rows.append(value)
    return rows


def _load_workbench_capability() -> Projector:
    try:
        from neuroai_workbench.discovery import project_epo_ops_search_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("Required Workbench capability project_epo_ops_search_pages is unavailable") from exc
    return project_epo_ops_search_pages


def _programme() -> dict[str, Any]:
    value = _load(PROGRAMME)
    if not isinstance(value, dict) or value.get("programme_id") != "SU-PATENTS-EPO-OPS-v0.1":
        raise ValueError("Invalid SU-PATENTS EPO OPS programme control")
    return value


def _capture_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("captured_at must be ISO-8601 timestamp") from exc
    return parsed.date().strftime("%Y%m%d")


def _parse_date(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must be valid YYYYMMDD date") from exc


def _root_cql(config: Mapping[str, Any], applicant_term: Any) -> str:
    if config.get("query_mode") == "APPLICANT_WATCH_SET":
        terms = config.get("applicant_terms") or []
        if applicant_term not in terms:
            raise ValueError("Invalid applicant_term for patent applicant watch")
        return str(config["cql_template"]).format(applicant_term=applicant_term)
    if applicant_term is not None:
        raise ValueError("applicant_term is only valid for applicant-watch root")
    return str(config["cql"])


def _bounded_cql(root_cql: str, lower: str, upper: str) -> str:
    return f'({root_cql}) and pd within "{lower} {upper}"'


def _replay_manifest_sha256(replay_output_dir: Path) -> str:
    manifest = replay_output_dir / "manifest.json"
    if not manifest.is_file():
        raise ValueError("Replay output directory has no manifest.json")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def load_replay_output(replay_output_dir: Path) -> dict[str, Any]:
    return {
        "manifest_sha256": _replay_manifest_sha256(replay_output_dir),
        "input_provenance": _load(replay_output_dir / "input-provenance.json"),
        "query_reports": _load(replay_output_dir / "query-reports.json"),
        "reconciliation": _load(replay_output_dir / "reconciliation.json"),
        "normalized_patents": _load_jsonl(replay_output_dir / "normalized-patents.jsonl"),
    }


def _validate_proof_bundle(proof: Mapping[str, Any], replay: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], str]:
    if proof.get("schema_version") != "0.1.0":
        raise ValueError("Partition proof schema_version must be 0.1.0")
    if proof.get("programme_id") != "SU-PATENTS-EPO-OPS-v0.1":
        raise ValueError("Partition proof programme_id mismatch")
    proof_id = proof.get("proof_id")
    if not isinstance(proof_id, str) or not proof_id.startswith("OPS-PARTITION-PROOF-"):
        raise ValueError("Invalid proof_id")
    if proof.get("replay_manifest_sha256") != replay.get("manifest_sha256"):
        raise ValueError("Partition proof replay manifest binding mismatch")
    provenance = replay.get("input_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("Replay input provenance missing")
    captured_at = provenance.get("captured_at")
    if proof.get("captured_at") != captured_at:
        raise ValueError("Partition proof captured_at does not match replay")
    if proof.get("dated_universe_lower_bound") != LOWER_BOUND:
        raise ValueError("Dated universe lower bound must remain 18000101")
    upper = _capture_date(str(captured_at))

    reports = replay.get("query_reports")
    if not isinstance(reports, list) or not all(isinstance(row, dict) for row in reports):
        raise ValueError("Replay query reports missing/invalid")
    by_leaf: dict[str, dict[str, Any]] = {}
    for row in reports:
        leaf = row.get("leaf_query_id")
        if not isinstance(leaf, str) or not leaf:
            raise ValueError("Replay query report missing leaf_query_id")
        if leaf in by_leaf:
            raise ValueError(f"Duplicate replay leaf_query_id {leaf}")
        by_leaf[leaf] = row
    return by_leaf, upper


def _interval_proof(
    *,
    root: Mapping[str, Any],
    root_cql: str,
    upper_bound: str,
    by_leaf: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    intervals = root.get("leaf_intervals")
    if not isinstance(intervals, list) or len(intervals) < 2:
        raise ValueError("Partition root requires at least two leaf intervals")
    parsed: list[tuple[date, date, dict[str, Any]]] = []
    leaf_ids: set[str] = set()
    for row in intervals:
        if not isinstance(row, dict):
            raise ValueError("leaf interval must be object")
        leaf_id = row.get("leaf_query_id")
        if not isinstance(leaf_id, str) or not leaf_id:
            raise ValueError("leaf interval missing leaf_query_id")
        if leaf_id in leaf_ids:
            raise ValueError(f"Duplicate leaf interval {leaf_id}")
        leaf_ids.add(leaf_id)
        lower = str(row.get("lower_date") or "")
        upper = str(row.get("upper_date") or "")
        lower_date = _parse_date(lower, f"{leaf_id}.lower_date")
        upper_date = _parse_date(upper, f"{leaf_id}.upper_date")
        if upper_date < lower_date:
            raise ValueError(f"{leaf_id}: reversed partition interval")
        parsed.append((lower_date, upper_date, row))

    parsed.sort(key=lambda item: item[0])
    blockers: list[str] = []
    if parsed[0][0].strftime("%Y%m%d") != LOWER_BOUND:
        blockers.append("DATED_UNIVERSE_LOWER_BOUND_GAP")
    if parsed[-1][1].strftime("%Y%m%d") != upper_bound:
        blockers.append("DATED_UNIVERSE_UPPER_BOUND_GAP")
    for previous, current in zip(parsed, parsed[1:]):
        expected = previous[1] + timedelta(days=1)
        if current[0] != expected:
            if current[0] <= previous[1]:
                blockers.append("PARTITION_INTERVAL_OVERLAP")
            else:
                blockers.append("PARTITION_INTERVAL_GAP")

    interval_reports: list[dict[str, Any]] = []
    for lower_date, upper_date, row in parsed:
        leaf_id = str(row["leaf_query_id"])
        replay_report = by_leaf.get(leaf_id)
        if replay_report is None:
            blockers.append(f"MISSING_REPLAY_LEAF:{leaf_id}")
            continue
        expected_cql = _bounded_cql(root_cql, lower_date.strftime("%Y%m%d"), upper_date.strftime("%Y%m%d"))
        if replay_report.get("effective_cql") != expected_cql:
            blockers.append(f"LEAF_CQL_MISMATCH:{leaf_id}")
        mechanical = replay_report.get("mechanical_blockers")
        if mechanical != []:
            blockers.append(f"LEAF_NOT_MECHANICALLY_CLEAN:{leaf_id}")
        coverage = replay_report.get("coverage")
        if not isinstance(coverage, Mapping):
            blockers.append(f"LEAF_COVERAGE_MISSING:{leaf_id}")
            continue
        total = coverage.get("reported_total_result_count")
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            blockers.append(f"LEAF_DENOMINATOR_INVALID:{leaf_id}")
            total = None
        interval_reports.append({
            "leaf_query_id": leaf_id,
            "lower_date": lower_date.strftime("%Y%m%d"),
            "upper_date": upper_date.strftime("%Y%m%d"),
            "reported_total_result_count": total,
            "capture_sha256": replay_report.get("capture_sha256"),
        })
    return interval_reports, blockers


def _cross_partition_duplicates(
    normalized_patents: Any,
    leaf_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(normalized_patents, list):
        raise ValueError("Replay normalized_patents missing/invalid")
    duplicates: list[dict[str, Any]] = []
    for row in normalized_patents:
        if not isinstance(row, Mapping):
            raise ValueError("Replay normalized patent row must be object")
        memberships = row.get("leaf_query_ids")
        if not isinstance(memberships, list):
            raise ValueError("Replay normalized patent missing leaf_query_ids")
        overlap = sorted(set(str(item) for item in memberships) & leaf_ids)
        if len(overlap) > 1:
            duplicates.append({
                "docdb_publication_reference": row.get("docdb_publication_reference"),
                "leaf_query_ids": overlap,
            })
    return duplicates


def build_partition_proof(
    replay: Mapping[str, Any],
    proof: Mapping[str, Any],
    *,
    projector: Projector | None = None,
) -> dict[str, Any]:
    programme = _programme()
    if projector is None:
        projector = _load_workbench_capability()
    by_leaf, upper_bound = _validate_proof_bundle(proof, replay)

    reconciliation = replay.get("reconciliation")
    if not isinstance(reconciliation, Mapping):
        raise ValueError("Replay reconciliation missing")
    replay_blockers: list[str] = []
    if reconciliation.get("scope") != "FULL_PROGRAMME":
        replay_blockers.append("REPLAY_SCOPE_NOT_FULL_PROGRAMME")
    if reconciliation.get("all_logical_queries_represented") is not True:
        replay_blockers.append("REPLAY_LOGICAL_QUERY_COVERAGE_INCOMPLETE")
    if reconciliation.get("leaf_mechanical_blocker_count") != 0:
        replay_blockers.append("REPLAY_HAS_LEAF_MECHANICAL_BLOCKERS")
    if reconciliation.get("partition_reconciliation_required") is not True:
        replay_blockers.append("REPLAY_HAS_NO_PARTITIONED_LEAVES")

    configured = {
        str(row["query_id"]): row
        for row in programme["query_streams"]
        if row.get("status") == "ACTIVE"
    }
    roots = proof.get("partition_roots")
    if not isinstance(roots, list) or not roots:
        raise ValueError("partition_roots must be non-empty array")

    used_leaf_ids: set[str] = set()
    root_reports: list[dict[str, Any]] = []
    total_root_blockers = 0
    normalized_patents = replay.get("normalized_patents")

    for root in roots:
        if not isinstance(root, Mapping):
            raise ValueError("partition root must be object")
        query_id = root.get("query_id")
        if query_id not in configured:
            raise ValueError(f"Unknown partition root query_id {query_id!r}")
        applicant_term = root.get("applicant_term")
        root_cql = _root_cql(configured[str(query_id)], applicant_term)
        expected_parent_cql = _bounded_cql(root_cql, LOWER_BOUND, upper_bound)
        if root.get("bounded_parent_cql") != expected_parent_cql:
            raise ValueError(f"{query_id}: bounded_parent_cql mismatch")
        pages = root.get("parent_probe_pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError(f"{query_id}: parent_probe_pages required")

        parent = projector(
            query_id=str(query_id),
            query_text=expected_parent_cql,
            pages=pages,
            known_docdb_sources={},
        )
        parent_coverage = parent.get("coverage")
        if not isinstance(parent_coverage, Mapping):
            raise ValueError(f"{query_id}: parent projector coverage missing")
        blockers: list[str] = []
        if parent_coverage.get("reported_total_result_count_state") != "CONSISTENT":
            blockers.append("PARENT_DENOMINATOR_NOT_CONSISTENT")
        parent_total = parent_coverage.get("reported_total_result_count")
        if not isinstance(parent_total, int) or isinstance(parent_total, bool) or parent_total <= 2000:
            blockers.append("PARENT_NOT_OVER_RETRIEVAL_LIMIT")
        if parent_coverage.get("over_2000_limit") is not True or parent_coverage.get("partition_required") is not True:
            blockers.append("PARENT_DID_NOT_REQUIRE_PARTITION")
        if parent.get("result_records") != [] or parent.get("normalized_records") != []:
            blockers.append("PARENT_OVERLIMIT_CANDIDATE_EMISSION_OCCURRED")

        intervals, interval_blockers = _interval_proof(
            root=root,
            root_cql=root_cql,
            upper_bound=upper_bound,
            by_leaf=by_leaf,
        )
        blockers.extend(interval_blockers)
        root_leaf_ids = {row["leaf_query_id"] for row in intervals}
        collision = root_leaf_ids & used_leaf_ids
        if collision:
            blockers.append(f"LEAF_ASSIGNED_TO_MULTIPLE_ROOTS:{','.join(sorted(collision))}")
        used_leaf_ids.update(root_leaf_ids)

        child_totals = [row["reported_total_result_count"] for row in intervals]
        if any(value is None for value in child_totals):
            child_sum = None
            blockers.append("CHILD_DENOMINATOR_SUM_UNAVAILABLE")
        else:
            child_sum = sum(int(value) for value in child_totals)
            if isinstance(parent_total, int) and child_sum != parent_total:
                blockers.append("CHILD_DENOMINATOR_SUM_MISMATCH")

        duplicates = _cross_partition_duplicates(normalized_patents, root_leaf_ids)
        if duplicates:
            blockers.append("CROSS_PARTITION_DOCDB_DUPLICATE")

        total_root_blockers += len(blockers)
        root_reports.append({
            "query_id": query_id,
            "applicant_term": applicant_term,
            "bounded_parent_cql": expected_parent_cql,
            "parent_probe_sha256": _digest(pages),
            "parent_reported_total_result_count": parent_total,
            "parent_over_2000_limit": parent_coverage.get("over_2000_limit"),
            "dated_universe_lower_bound": LOWER_BOUND,
            "dated_universe_upper_bound": upper_bound,
            "leaf_intervals": intervals,
            "child_reported_total_sum": child_sum,
            "cross_partition_duplicate_count": len(duplicates),
            "cross_partition_duplicates": duplicates,
            "blockers": blockers,
            "dated_partition_reconciled": not blockers,
        })

    replay_partitioned_leaf_ids = {
        str(row["leaf_query_id"])
        for row in by_leaf.values()
        if row.get("partition_path")
    }
    missing_proof_leaf_ids = sorted(replay_partitioned_leaf_ids - used_leaf_ids)
    extraneous_proof_leaf_ids = sorted(used_leaf_ids - replay_partitioned_leaf_ids)
    if missing_proof_leaf_ids:
        replay_blockers.append("PARTITIONED_REPLAY_LEAVES_MISSING_FROM_PROOF")
    if extraneous_proof_leaf_ids:
        replay_blockers.append("PROOF_REFERENCES_UNPARTITIONED_REPLAY_LEAVES")

    proof_complete = not replay_blockers and total_root_blockers == 0
    final = {
        "proof_id": proof["proof_id"],
        "programme_id": proof["programme_id"],
        "replay_manifest_sha256": proof["replay_manifest_sha256"],
        "captured_at": proof["captured_at"],
        "dated_universe_lower_bound": LOWER_BOUND,
        "dated_universe_upper_bound": upper_bound,
        "root_reports": root_reports,
        "replay_level_blockers": replay_blockers,
        "missing_partitioned_replay_leaf_ids": missing_proof_leaf_ids,
        "extraneous_proof_leaf_ids": extraneous_proof_leaf_ids,
        "root_blocker_count": total_root_blockers,
        "dated_partition_reconciliation_complete": proof_complete,
        "unbounded_query_completeness_claim": False,
        "global_neuroai_patent_recall_claim": False,
        "patent_family_completeness_claim": False,
        "automatic_source_admission": False,
        "automatic_patent_family_creation": False,
        "automatic_entity_creation": False,
        "automatic_product_or_system_relationship_creation": False,
        "automatic_capability_claim_creation": False,
        "automatic_assessment_mutation": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "A complete proof establishes only exact denominator reconciliation for explicitly dated OPS search "
            "universes from 1800-01-01 through the replay capture date. It excludes records without usable "
            "publication-date indexing and does not establish unbounded provider-query completeness, global "
            "NeuroAI patent recall, family identity, ownership, implementation, validity/enforceability, freedom "
            "to operate, system capability, safety/effectiveness, assessment effect or canonical authority."
        ),
    }
    return final


def write_proof(result: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(result)
    proof_path = output_dir / "partition-reconciliation.json"
    proof_path.write_bytes(payload)
    manifest = {
        "programme_id": result["programme_id"],
        "proof_id": result["proof_id"],
        "files": [{
            "path": proof_path.name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "records": 1,
        }],
        "file_count": 1,
        "raw_parent_probe_xml_emitted": False,
        "dated_partition_reconciliation_complete": result["dated_partition_reconciliation_complete"],
        "canonical_successor_ready": False,
    }
    manifest_payload = _canonical_bytes(manifest)
    (output_dir / "manifest.json").write_bytes(manifest_payload)
    return {**manifest, "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-output-dir", type=Path, required=True)
    parser.add_argument("--proof-bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    replay = load_replay_output(args.replay_output_dir.resolve())
    proof = _load(args.proof_bundle.resolve())
    result = build_partition_proof(replay, proof)
    manifest = write_proof(result, args.output_dir.resolve())
    print(json.dumps({"proof": result, "manifest": manifest}, indent=2, sort_keys=True))
    return 0 if result["dated_partition_reconciliation_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
