#!/usr/bin/env python3
"""Project recorded ClinicalTrials.gov search pages into a deterministic SU-TRIALS package.

Raw API pages are ephemeral input only. This runner emits selected normalized study state,
exact known/new NCT classification, query coverage and provenance digests. It does not emit
raw pages, create canonical Sources/entities/relationships/monitors/assessments, or make human
adjudication decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

import project_v14_sources_to_v2
import project_v16_sources_observations_to_v2
import project_v17_prima_sources_to_v2

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation" / "clinicaltrials_discovery_programme_v0.1.json"
_NCT_RE = re.compile(r"\bNCT\d{8}\b", re.I)

Projector = Callable[..., dict[str, Any]]


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_workbench_capability() -> tuple[Any, Projector]:
    try:
        from neuroai_workbench.collector.adapters.clinicaltrials import ClinicalTrialsGovAdapter
        from neuroai_workbench.discovery import project_clinicaltrials_search_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench capability project_clinicaltrials_search_pages is unavailable; "
            "SU-TRIALS integration remains PENDING_S1_MERGE"
        ) from exc
    return ClinicalTrialsGovAdapter.__new__(ClinicalTrialsGovAdapter), project_clinicaltrials_search_pages


def build_known_nct_source_index() -> dict[str, Any]:
    """Derive exact CT.gov NCT→Source identity from the actual 248-source migrated namespace."""
    modules = (
        ("V1_4_BASELINE", project_v14_sources_to_v2),
        ("V1_6_REFRESH", project_v16_sources_observations_to_v2),
        ("V1_7_PRIMA_SUPPLEMENTAL", project_v17_prima_sources_to_v2),
    )
    all_source_ids: set[str] = set()
    source_id_duplicates: list[str] = []
    nct_to_source: dict[str, str] = {}
    nct_lineage: dict[str, dict[str, str]] = {}

    for family, module in modules:
        result = module.project()
        sources = result.get("sources")
        if not isinstance(sources, list):
            raise ValueError(f"{family}: source projector returned no sources list")
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError(f"{family}: projected source must be object")
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                raise ValueError(f"{family}: projected source missing source_id")
            if source_id in all_source_ids:
                source_id_duplicates.append(source_id)
            all_source_ids.add(source_id)

            locator = source.get("canonical_locator")
            if not isinstance(locator, str) or "clinicaltrials.gov" not in locator.lower():
                continue
            ncts = sorted(set(match.upper() for match in _NCT_RE.findall(locator)))
            if len(ncts) > 1:
                raise ValueError(f"{source_id}: ClinicalTrials.gov locator contains multiple NCT identifiers")
            if not ncts:
                continue
            nct_id = ncts[0]
            prior = nct_to_source.get(nct_id)
            if prior is not None and prior != source_id:
                raise ValueError(
                    f"Controlled source namespace maps {nct_id} to conflicting source IDs {prior} and {source_id}"
                )
            nct_to_source[nct_id] = source_id
            nct_lineage[nct_id] = {"source_id": source_id, "lineage_family": family}

    if source_id_duplicates:
        raise ValueError(f"Duplicate Source identities in effective namespace: {sorted(set(source_id_duplicates))}")
    if len(all_source_ids) != 248:
        raise ValueError(f"Expected materialized 248-source namespace, found {len(all_source_ids)}")

    return {
        "materialized_source_count": len(all_source_ids),
        "known_ctgov_nct_count": len(nct_to_source),
        "nct_to_source": dict(sorted(nct_to_source.items())),
        "nct_lineage": {key: nct_lineage[key] for key in sorted(nct_lineage)},
        "global_completeness_claim": False,
    }


def _programme() -> dict[str, Any]:
    value = _load(PROGRAMME)
    if not isinstance(value, dict) or value.get("programme_id") != "SU-TRIALS-CTGOV-v0.1":
        raise ValueError("Invalid SU-TRIALS programme control")
    return value


def _validate_bundle(bundle: Any, programme: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(bundle, dict):
        raise ValueError("Replay input bundle must be an object")
    if bundle.get("schema_version") != "0.1.0":
        raise ValueError("Replay input schema_version must be 0.1.0")
    if bundle.get("programme_id") != programme["programme_id"]:
        raise ValueError("Replay input programme_id mismatch")
    scope = bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME", "PARTIAL_VALIDATION"}:
        raise ValueError("capture_scope must be FULL_PROGRAMME or PARTIAL_VALIDATION")
    captured_at = bundle.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise ValueError("captured_at must be non-empty")
    captures = bundle.get("query_captures")
    if not isinstance(captures, list) or not captures or not all(isinstance(row, dict) for row in captures):
        raise ValueError("query_captures must be a non-empty array of objects")

    configured = {row["query_id"]: row for row in programme["query_streams"] if row.get("status") == "ACTIVE"}
    seen: set[str] = set()
    for capture in captures:
        query_id = capture.get("query_id")
        if query_id not in configured:
            raise ValueError(f"Unconfigured or inactive query capture {query_id!r}")
        if query_id in seen:
            raise ValueError(f"Duplicate query capture {query_id}")
        seen.add(query_id)
        if capture.get("query_term") != configured[query_id]["query_term"]:
            raise ValueError(f"{query_id}: captured query term does not match programme control")
        pages = capture.get("pages")
        if not isinstance(pages, list) or not pages or not all(isinstance(page, dict) for page in pages):
            raise ValueError(f"{query_id}: pages must be a non-empty object array")
        for key in ("count_total_first_page_requested", "count_total_later_pages_requested"):
            if not isinstance(capture.get(key), bool):
                raise ValueError(f"{query_id}: {key} must be boolean")

    if scope == "FULL_PROGRAMME" and seen != set(configured):
        raise ValueError(
            f"FULL_PROGRAMME replay requires all active query streams; missing={sorted(set(configured) - seen)}"
        )
    return str(scope), captures


def _mechanical_query_blockers(
    *,
    capture: Mapping[str, Any],
    coverage: Mapping[str, Any],
    programme: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    request_policy = programme["request_policy"]
    if capture.get("count_total_first_page_requested") is not request_policy["count_total_first_page"]:
        blockers.append("COUNT_TOTAL_FIRST_PAGE_POLICY_MISMATCH")
    if capture.get("count_total_later_pages_requested") is not request_policy["count_total_later_pages"]:
        blockers.append("COUNT_TOTAL_LATER_PAGE_POLICY_MISMATCH")

    required_metrics = set(programme["coverage_contract"]["required_metrics"])
    missing_metrics = sorted(required_metrics - set(coverage))
    if missing_metrics:
        blockers.append(f"MISSING_COVERAGE_METRICS:{','.join(missing_metrics)}")
    for key, expected in programme["coverage_contract"]["mechanical_completion_requires"].items():
        if coverage.get(key) != expected:
            blockers.append(f"COVERAGE_GATE:{key}:{coverage.get(key)!r}!={expected!r}")
    return blockers


def build_replay(
    bundle: Mapping[str, Any],
    *,
    adapter: Any | None = None,
    projector: Projector | None = None,
) -> dict[str, Any]:
    programme = _programme()
    scope, captures = _validate_bundle(bundle, programme)
    if adapter is None or projector is None:
        loaded_adapter, loaded_projector = _load_workbench_capability()
        adapter = adapter if adapter is not None else loaded_adapter
        projector = projector if projector is not None else loaded_projector

    known = build_known_nct_source_index()
    known_map = known["nct_to_source"]
    for anchor in programme["known_identifier_anchors"]:
        nct_id = anchor["nct_id"]
        expected_source = anchor["existing_source_id"]
        if known_map.get(nct_id) != expected_source:
            raise ValueError(
                f"Configured known anchor {nct_id}->{expected_source} does not match materialized source namespace"
            )

    configured = {row["query_id"]: row for row in programme["query_streams"] if row.get("status") == "ACTIVE"}
    query_reports: list[dict[str, Any]] = []
    union: dict[str, dict[str, Any]] = {}
    query_blocker_count = 0
    raw_page_count = 0

    for capture in sorted(captures, key=lambda row: str(row["query_id"])):
        query_id = str(capture["query_id"])
        config = configured[query_id]
        pages = capture["pages"]
        raw_page_count += len(pages)
        projection = projector(
            adapter,
            query_id=query_id,
            query_text=config["query_term"],
            pages=pages,
            required_study_types=config["post_retrieval_required_study_types"],
            known_nct_sources=known_map,
        )
        coverage = projection.get("coverage")
        records = projection.get("result_records")
        normalized = projection.get("normalized_records")
        if not isinstance(coverage, dict) or not isinstance(records, list) or not isinstance(normalized, list):
            raise ValueError(f"{query_id}: Workbench projector returned invalid shape")
        normalized_by_nct = {
            row.get("nct_id"): row for row in normalized if isinstance(row, dict) and isinstance(row.get("nct_id"), str)
        }
        if len(normalized_by_nct) != len(normalized):
            raise ValueError(f"{query_id}: normalized study identities are missing or duplicated")

        blockers = _mechanical_query_blockers(capture=capture, coverage=coverage, programme=programme)
        query_blocker_count += len(blockers)
        query_reports.append(
            {
                "query_id": query_id,
                "query_term": config["query_term"],
                "capture_sha256": _digest(capture),
                "coverage": coverage,
                "mechanical_blockers": blockers,
            }
        )

        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{query_id}: discovery result record must be object")
            nct_id = record.get("record_key")
            if not isinstance(nct_id, str) or nct_id not in normalized_by_nct:
                raise ValueError(f"{query_id}: candidate record has no matching normalized study")
            normalized_row = normalized_by_nct[nct_id]
            aggregate_digest = normalized_row.get("aggregate_digest")
            if not isinstance(aggregate_digest, str) or len(aggregate_digest) != 64:
                raise ValueError(f"{query_id}/{nct_id}: normalized aggregate_digest missing/invalid")
            classification = str(record.get("classification_hint", "NEW"))
            duplicate_of = record.get("duplicate_of_source_id")
            candidate_core = {
                "record_key": nct_id,
                "title": record.get("title"),
                "url": record.get("url"),
                "publisher": record.get("publisher"),
                "source_class": record.get("source_class"),
                "suggested_source_id": record.get("suggested_source_id"),
                "classification_hint": classification,
                "duplicate_of_source_id": duplicate_of,
            }
            prior = union.get(nct_id)
            if prior is None:
                union[nct_id] = {
                    "nct_id": nct_id,
                    "normalized_study": normalized_row,
                    "normalized_aggregate_digest": aggregate_digest,
                    "candidate_input": candidate_core,
                    "query_ids": {query_id},
                }
                continue
            if prior["normalized_aggregate_digest"] != aggregate_digest or prior["candidate_input"] != candidate_core:
                raise ValueError(f"Cross-query conflict for {nct_id}")
            prior["query_ids"].add(query_id)

    active_ids = set(configured)
    executed_ids = {str(row["query_id"]) for row in captures}
    all_active_executed = executed_ids == active_ids

    normalized_studies: list[dict[str, Any]] = []
    known_duplicates: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    cross_query_repeat_count = 0
    for nct_id in sorted(union):
        row = union[nct_id]
        query_ids = sorted(row["query_ids"])
        cross_query_repeat_count += max(0, len(query_ids) - 1)
        normalized_studies.append(
            {
                "nct_id": nct_id,
                "query_ids": query_ids,
                "normalized_study": row["normalized_study"],
            }
        )
        classified = {
            **row["candidate_input"],
            "query_ids": query_ids,
            "normalized_aggregate_digest": row["normalized_aggregate_digest"],
        }
        if classified["classification_hint"] == "DUPLICATE":
            known_duplicates.append(classified)
        elif classified["classification_hint"] == "NEW":
            new_candidates.append(classified)
        else:
            raise ValueError(f"Unexpected union discovery classification for {nct_id}")

    mechanically_complete = scope == "FULL_PROGRAMME" and all_active_executed and query_blocker_count == 0
    reconciliation = {
        "scope": scope,
        "configured_active_query_count": len(active_ids),
        "executed_query_count": len(executed_ids),
        "all_active_queries_executed": all_active_executed,
        "query_mechanical_blocker_count": query_blocker_count,
        "union_unique_nct_count": len(union),
        "known_controlled_duplicate_count": len(known_duplicates),
        "new_candidate_input_count": len(new_candidates),
        "cross_query_repeat_membership_count": cross_query_repeat_count,
        "materialized_source_namespace_count": known["materialized_source_count"],
        "known_ctgov_nct_count_before_run": known["known_ctgov_nct_count"],
        "raw_input_page_count": raw_page_count,
        "raw_api_page_payloads_emitted": False,
        "participant_level_data_emitted": False,
        "automatic_source_admission": False,
        "automatic_trial_entity_creation": False,
        "automatic_trial_site_relationship_creation": False,
        "automatic_monitor_creation": False,
        "automatic_assessment_mutation": False,
        "human_adjudication_performed": False,
        "mechanically_complete": mechanically_complete,
        "global_neuroai_trial_recall_claim": False,
        "registry_completeness_claim": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Mechanical completion applies only to this exact configured query traversal and known-source namespace. "
            "It does not establish global NeuroAI trial recall, ClinicalTrials.gov completeness, substantive clinical truth, "
            "source admission, relationship validity, assessment effect or canonical publication authority."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_SU_TRIALS_RECORDED_REPLAY_PROJECTION",
        "programme_id": programme["programme_id"],
        "input_provenance": {
            "bundle_sha256": _digest(bundle),
            "captured_at": bundle["captured_at"],
            "capture_scope": scope,
            "api_data_timestamp": bundle.get("api_data_timestamp"),
            "raw_pages_retained_in_output": False,
            "known_nct_index_sha256": _digest(known_map),
        },
        "known_source_index_summary": {
            "materialized_source_count": known["materialized_source_count"],
            "known_ctgov_nct_count": known["known_ctgov_nct_count"],
            "global_completeness_claim": False,
        },
        "query_reports": query_reports,
        "normalized_studies": normalized_studies,
        "known_duplicates": known_duplicates,
        "new_candidate_inputs": new_candidates,
        "reconciliation": reconciliation,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload = b"".join(_canonical_bytes(row) for row in rows)
    path.write_bytes(payload)
    return {"path": path.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "records": len(rows)}


def write_projection(result: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for key, filename in (
        ("normalized_studies", "normalized-studies.jsonl"),
        ("known_duplicates", "known-duplicates.jsonl"),
        ("new_candidate_inputs", "new-candidate-inputs.jsonl"),
    ):
        files.append(_write_jsonl(output_dir / filename, result[key]))

    for key, filename in (
        ("input_provenance", "input-provenance.json"),
        ("known_source_index_summary", "known-source-index-summary.json"),
        ("query_reports", "query-reports.json"),
        ("reconciliation", "reconciliation.json"),
    ):
        payload = _canonical_bytes(result[key])
        path = output_dir / filename
        path.write_bytes(payload)
        files.append({"path": filename, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "records": 1})

    manifest = {
        "programme_id": result["programme_id"],
        "status": result["status"],
        "files": sorted(files, key=lambda row: row["path"]),
        "file_count": len(files),
        "raw_api_page_payloads_emitted": False,
        "canonical_successor_ready": False,
    }
    manifest_payload = _canonical_bytes(manifest)
    (output_dir / "manifest.json").write_bytes(manifest_payload)
    return {**manifest, "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    bundle = _load(args.input_bundle.resolve())
    result = build_replay(bundle)
    manifest = write_projection(result, args.output_dir.resolve())
    print(json.dumps({"reconciliation": result["reconciliation"], "manifest": manifest}, indent=2, sort_keys=True))
    return 0 if result["reconciliation"]["mechanically_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
