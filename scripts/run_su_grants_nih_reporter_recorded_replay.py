#!/usr/bin/env python3
"""Project recorded NIH RePORTER search pages into a deterministic SU-GRANTS package.

Raw RePORTER response pages are ephemeral input only. This runner emits normalized award metadata,
exact controlled-source duplicate/new classification, leaf-query coverage and provenance digests.
It does not emit raw provider pages, resolve PI/organization identities, create grant/project/system
relationships, admit Sources, create monitors, mutate assessments, make relevance decisions, or
authorize canonical state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

import project_v14_sources_to_v2
import project_v16_sources_observations_to_v2
import project_v17_prima_sources_to_v2

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation" / "nih_reporter_grants_discovery_programme_v0.1.json"
_REPORTER_APPL_RE = re.compile(r"reporter\.nih\.gov/project-details/(\d+)", re.I)

Projector = Callable[..., dict[str, Any]]


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_workbench_capability() -> Projector:
    try:
        from neuroai_workbench.discovery import project_nih_reporter_search_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench capability project_nih_reporter_search_pages is unavailable; "
            "SU-GRANTS NIH RePORTER integration remains PENDING_S1_MERGE"
        ) from exc
    return project_nih_reporter_search_pages


def _programme() -> dict[str, Any]:
    value = _load(PROGRAMME)
    if not isinstance(value, dict) or value.get("programme_id") != "SU-GRANTS-NIH-REPORTER-v0.1":
        raise ValueError("Invalid SU-GRANTS NIH RePORTER programme control")
    return value


def _eligible_grant_source(source: Mapping[str, Any]) -> bool:
    token = str(source.get("source_class") or "").upper()
    return any(part in token for part in ("GRANT", "FUNDER", "FUNDING", "AWARD"))


def build_known_appl_source_index() -> dict[str, Any]:
    """Derive exact RePORTER appl_id aliases only from controlled grant-typed Sources."""
    modules = (
        ("V1_4_BASELINE", project_v14_sources_to_v2),
        ("V1_6_REFRESH", project_v16_sources_observations_to_v2),
        ("V1_7_PRIMA_SUPPLEMENTAL", project_v17_prima_sources_to_v2),
    )
    all_source_ids: set[str] = set()
    eligible_source_ids: set[str] = set()
    appl_to_source: dict[int, str] = {}
    lineage: dict[int, dict[str, str]] = {}

    for family, module in modules:
        projected = module.project()
        sources = projected.get("sources")
        if not isinstance(sources, list):
            raise ValueError(f"{family}: source projector returned no sources list")
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError(f"{family}: projected source must be object")
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                raise ValueError(f"{family}: projected source missing source_id")
            if source_id in all_source_ids:
                raise ValueError(f"Duplicate Source identity in effective namespace: {source_id}")
            all_source_ids.add(source_id)
            if not _eligible_grant_source(source):
                continue
            eligible_source_ids.add(source_id)
            locator = source.get("canonical_locator")
            if not isinstance(locator, str):
                continue
            match = _REPORTER_APPL_RE.search(locator)
            if not match:
                continue
            appl_id = int(match.group(1))
            prior = appl_to_source.get(appl_id)
            if prior is not None and prior != source_id:
                raise ValueError(
                    f"Controlled grant namespace maps RePORTER appl_id {appl_id} to conflicting Sources {prior} and {source_id}"
                )
            appl_to_source[appl_id] = source_id
            lineage[appl_id] = {"source_id": source_id, "lineage_family": family}

    if len(all_source_ids) != 248:
        raise ValueError(f"Expected materialized 248-source namespace, found {len(all_source_ids)}")
    return {
        "materialized_source_count": len(all_source_ids),
        "grant_typed_source_count": len(eligible_source_ids),
        "known_reporter_appl_id_count": len(appl_to_source),
        "appl_to_source": {str(key): appl_to_source[key] for key in sorted(appl_to_source)},
        "appl_lineage": {str(key): lineage[key] for key in sorted(lineage)},
        "global_grant_completeness_claim": False,
    }


def _active_queries(programme: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["query_id"]): dict(row)
        for row in programme["query_streams"]
        if row.get("status") == "ACTIVE"
    }


def _validate_bundle(bundle: Any, programme: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(bundle, dict):
        raise ValueError("Replay input bundle must be an object")
    if bundle.get("schema_version") != "0.1.0":
        raise ValueError("Replay input schema_version must be 0.1.0")
    if bundle.get("programme_id") != programme["programme_id"]:
        raise ValueError("Replay input programme_id mismatch")
    if bundle.get("provider") != programme["provider_contract"]["provider"]:
        raise ValueError("Replay input provider mismatch")
    scope = bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME", "PARTIAL_VALIDATION"}:
        raise ValueError("capture_scope must be FULL_PROGRAMME or PARTIAL_VALIDATION")
    captured_at = bundle.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise ValueError("captured_at must be non-empty")
    captures = bundle.get("leaf_query_captures")
    if not isinstance(captures, list) or not captures or not all(isinstance(row, dict) for row in captures):
        raise ValueError("leaf_query_captures must be a non-empty array of objects")

    configured = _active_queries(programme)
    seen_leaf_ids: set[str] = set()
    for capture in captures:
        query_id = capture.get("query_id")
        if query_id not in configured:
            raise ValueError(f"Unconfigured or inactive RePORTER query capture {query_id!r}")
        leaf_id = capture.get("leaf_query_id")
        if not isinstance(leaf_id, str) or not leaf_id.strip():
            raise ValueError(f"{query_id}: leaf_query_id must be non-empty")
        if leaf_id in seen_leaf_ids:
            raise ValueError(f"Duplicate leaf_query_id {leaf_id}")
        seen_leaf_ids.add(leaf_id)
        query_payload = capture.get("query_payload")
        if not isinstance(query_payload, dict):
            raise ValueError(f"{leaf_id}: query_payload must be an object")
        criteria = query_payload.get("criteria")
        if not isinstance(criteria, dict):
            raise ValueError(f"{leaf_id}: query_payload.criteria must be an object")
        if criteria.get("advanced_text_search") != configured[str(query_id)]["advanced_text_search"]:
            raise ValueError(f"{leaf_id}: advanced_text_search must exactly match programme control")
        if query_payload.get("offset") != 0:
            raise ValueError(f"{leaf_id}: initial query payload offset must be 0")
        if query_payload.get("limit") != programme["pagination_partition_policy"]["page_limit"]:
            raise ValueError(f"{leaf_id}: initial query payload limit must match programme page limit")
        partition_path = capture.get("partition_path")
        if not isinstance(partition_path, list):
            raise ValueError(f"{leaf_id}: partition_path must be an array")
        for part in partition_path:
            if not isinstance(part, dict) or part.get("dimension") not in {"FISCAL_YEAR", "AWARD_NOTICE_DATE"} or "value" not in part:
                raise ValueError(f"{leaf_id}: invalid partition_path entry")
        pages = capture.get("pages")
        if not isinstance(pages, list) or not pages or not all(isinstance(page, dict) for page in pages):
            raise ValueError(f"{leaf_id}: pages must be a non-empty object array")

    return str(scope), captures, configured


def _logical_coverage(*, captures: list[dict[str, Any]], configured: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    represented = {str(row["query_id"]) for row in captures}
    missing = sorted(set(configured) - represented)
    partitioned = [row for row in captures if row.get("partition_path")]
    return {
        "configured_active_query_count": len(configured),
        "represented_query_count": len(represented),
        "missing_query_ids": missing,
        "partitioned_leaf_count": len(partitioned),
        "partition_reconciliation_required": bool(partitioned),
        "all_logical_queries_represented": not missing,
    }


def _leaf_blockers(coverage: Mapping[str, Any], programme: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    required = set(programme["coverage_contract"]["required_metrics_per_leaf_query"])
    missing = sorted(required - set(coverage))
    if missing:
        blockers.append(f"MISSING_COVERAGE_METRICS:{','.join(missing)}")
    for key, expected in programme["coverage_contract"]["mechanical_completion_requires"].items():
        if coverage.get(key) != expected:
            blockers.append(f"COVERAGE_GATE:{key}:{coverage.get(key)!r}!={expected!r}")
    if coverage.get("candidate_emission_refused_due_to_over_limit") is True:
        blockers.append("OVER_LIMIT_CANDIDATE_EMISSION_REFUSED")
    return blockers


def build_replay(
    bundle: Mapping[str, Any],
    *,
    projector: Projector | None = None,
    known_index: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    programme = _programme()
    scope, captures, configured = _validate_bundle(bundle, programme)
    if projector is None:
        projector = _load_workbench_capability()
    known = dict(known_index) if known_index is not None else build_known_appl_source_index()
    known_map = known.get("appl_to_source") or {}

    logical = _logical_coverage(captures=captures, configured=configured)
    query_reports: list[dict[str, Any]] = []
    union: dict[int, dict[str, Any]] = {}
    total_blockers = 0
    raw_page_count = 0

    for capture in sorted(captures, key=lambda row: str(row["leaf_query_id"])):
        query_id = str(capture["query_id"])
        leaf_id = str(capture["leaf_query_id"])
        pages = capture["pages"]
        raw_page_count += len(pages)
        projection = projector(
            query_id=query_id,
            query_payload=capture["query_payload"],
            pages=pages,
            known_appl_sources=known_map,
        )
        coverage = projection.get("coverage")
        records = projection.get("result_records")
        normalized = projection.get("normalized_records")
        if not isinstance(coverage, dict) or not isinstance(records, list) or not isinstance(normalized, list):
            raise ValueError(f"{leaf_id}: Workbench projector returned invalid shape")
        blockers = _leaf_blockers(coverage, programme)
        total_blockers += len(blockers)
        query_reports.append({
            "query_id": query_id,
            "leaf_query_id": leaf_id,
            "partition_path": capture.get("partition_path"),
            "query_payload_sha256": _digest(capture["query_payload"]),
            "capture_sha256": _digest(capture),
            "coverage": coverage,
            "mechanical_blockers": blockers,
        })

        normalized_by_appl: dict[int, dict[str, Any]] = {}
        for row in normalized:
            if not isinstance(row, dict) or not isinstance(row.get("appl_id"), int):
                raise ValueError(f"{leaf_id}: normalized grant identity is missing")
            appl_id = row["appl_id"]
            if appl_id in normalized_by_appl:
                raise ValueError(f"{leaf_id}: duplicated normalized appl_id {appl_id}")
            normalized_by_appl[appl_id] = row

        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{leaf_id}: candidate record must be object")
            key = record.get("record_key")
            if not isinstance(key, str) or not key.startswith("REPORTER:APPL:"):
                raise ValueError(f"{leaf_id}: candidate record has invalid record_key")
            try:
                appl_id = int(key.rsplit(":", 1)[1])
            except ValueError as exc:
                raise ValueError(f"{leaf_id}: candidate record has invalid appl_id key") from exc
            normalized_row = normalized_by_appl.get(appl_id)
            if normalized_row is None:
                raise ValueError(f"{leaf_id}: candidate record has no normalized grant")
            digest = normalized_row.get("normalized_record_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"{leaf_id}/{appl_id}: normalized_record_sha256 missing/invalid")
            classification = record.get("classification_hint")
            duplicate_of = record.get("duplicate_of_source_id")
            candidate_core = {
                "appl_id": appl_id,
                "record_key": key,
                "title": record.get("title"),
                "url": record.get("url"),
                "publisher": record.get("publisher"),
                "source_class": record.get("source_class"),
                "suggested_source_id": record.get("suggested_source_id"),
                "classification_hint": classification,
                "duplicate_of_source_id": duplicate_of,
                "normalized_record_sha256": digest,
            }
            prior = union.get(appl_id)
            if prior is None:
                union[appl_id] = {
                    "candidate": candidate_core,
                    "normalized": dict(normalized_row),
                    "query_memberships": {query_id},
                    "leaf_memberships": {leaf_id},
                }
            else:
                if prior["candidate"] != candidate_core:
                    raise ValueError(f"Cross-leaf candidate conflict for RePORTER appl_id {appl_id}")
                if prior["normalized"].get("normalized_record_sha256") != digest:
                    raise ValueError(f"Cross-leaf content conflict for RePORTER appl_id {appl_id}")
                prior["query_memberships"].add(query_id)
                prior["leaf_memberships"].add(leaf_id)

    normalized_output: list[dict[str, Any]] = []
    known_duplicates: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    for appl_id in sorted(union):
        entry = union[appl_id]
        normalized_row = dict(entry["normalized"])
        normalized_row["query_memberships"] = sorted(entry["query_memberships"])
        normalized_row["leaf_memberships"] = sorted(entry["leaf_memberships"])
        normalized_output.append(normalized_row)
        candidate = dict(entry["candidate"])
        candidate["query_memberships"] = sorted(entry["query_memberships"])
        candidate["leaf_memberships"] = sorted(entry["leaf_memberships"])
        if candidate.get("classification_hint") == "DUPLICATE":
            known_duplicates.append(candidate)
        elif candidate.get("classification_hint") == "NEW":
            new_candidates.append(candidate)
        else:
            raise ValueError(f"Unsupported candidate classification for appl_id {appl_id}")

    mechanically_complete = (
        scope == "FULL_PROGRAMME"
        and logical["all_logical_queries_represented"]
        and not logical["partition_reconciliation_required"]
        and total_blockers == 0
    )
    reconciliation = {
        "programme_id": programme["programme_id"],
        "capture_scope": scope,
        "captured_at": bundle["captured_at"],
        "materialized_source_namespace_count": known.get("materialized_source_count"),
        "known_reporter_appl_id_count": known.get("known_reporter_appl_id_count", len(known_map)),
        **logical,
        "leaf_query_capture_count": len(captures),
        "raw_provider_page_count": raw_page_count,
        "leaf_mechanical_blocker_count": total_blockers,
        "union_unique_appl_id_count": len(union),
        "known_controlled_duplicate_count": len(known_duplicates),
        "new_candidate_input_count": len(new_candidates),
        "mechanically_complete": mechanically_complete,
        "automatic_grant_source_admission": False,
        "automatic_project_entity_creation": False,
        "automatic_pi_or_organization_entity_creation": False,
        "automatic_system_or_model_relationship_creation": False,
        "automatic_funding_success_claim_creation": False,
        "automatic_assessment_mutation": False,
        "global_neuroai_grant_recall_claim": False,
        "funding_success_claim": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Recorded replay establishes deterministic processing of exact supplied RePORTER pages only. "
            "Programme-level mechanical completion additionally requires full unpartitioned configured coverage. "
            "Neither state establishes relevance, research success, entity identity, system relationship, global grant recall or canonical authority."
        ),
    }
    provenance = {
        "programme_id": programme["programme_id"],
        "provider": programme["provider_contract"]["provider"],
        "captured_at": bundle["captured_at"],
        "capture_scope": scope,
        "input_bundle_sha256": _digest(bundle),
        "leaf_query_capture_count": len(captures),
        "raw_provider_pages_retained_in_output": False,
    }
    return {
        "normalized_grants": normalized_output,
        "known_duplicates": known_duplicates,
        "new_candidates": new_candidates,
        "query_reports": query_reports,
        "reconciliation": reconciliation,
        "input_provenance": provenance,
        "known_source_index_summary": {
            key: value for key, value in known.items() if key not in {"appl_to_source", "appl_lineage"}
        },
    }


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) for row in rows)


def write_projection(result: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, bytes] = {
        "normalized-grants.jsonl": _jsonl(list(result["normalized_grants"])),
        "known-grant-duplicates.jsonl": _jsonl(list(result["known_duplicates"])),
        "new-grant-candidate-inputs.jsonl": _jsonl(list(result["new_candidates"])),
        "input-provenance.json": _canonical_bytes(result["input_provenance"]),
        "known-source-index-summary.json": _canonical_bytes(result["known_source_index_summary"]),
        "query-reports.json": _canonical_bytes(result["query_reports"]),
        "reconciliation.json": _canonical_bytes(result["reconciliation"]),
    }
    files: list[dict[str, Any]] = []
    for name in sorted(payloads):
        data = payloads[name]
        (output_dir / name).write_bytes(data)
        files.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    manifest = {
        "schema_version": "0.1.0",
        "programme_id": result["reconciliation"]["programme_id"],
        "files": files,
        "raw_provider_pages_included": False,
        "canonical_successor_ready": False,
    }
    manifest_bytes = _canonical_bytes(manifest)
    (output_dir / "manifest.json").write_bytes(manifest_bytes)
    return {"manifest": manifest, "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    bundle = _load(args.input)
    result = build_replay(bundle)
    written = write_projection(result, args.output_dir)
    print(json.dumps({"reconciliation": result["reconciliation"], **written}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
