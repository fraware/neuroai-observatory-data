#!/usr/bin/env python3
"""Project recorded EPO OPS patent search pages into a deterministic SU-PATENTS package.

Raw OPS XML is ephemeral input only. This runner emits normalized patent-publication metadata,
exact controlled-source duplicate/new classification, leaf-query coverage and provenance digests.
It does not emit raw OPS XML, create patent families/entities/system relationships, admit Sources,
create monitors, mutate assessments, make human relevance decisions, or authorize canonical state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

import project_v14_sources_to_v2
import project_v16_sources_observations_to_v2
import project_v17_prima_sources_to_v2

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation" / "epo_ops_patent_discovery_programme_v0.1.json"
_DOCDB_DOTTED_RE = re.compile(r"\b([A-Z]{2})\.([A-Z0-9./-]+)\.([A-Z][A-Z0-9]*)\b", re.I)
_PUBLICATION_TOKEN_RE = re.compile(r"\b([A-Z]{2})([0-9][A-Z0-9./-]{3,}?)([A-Z][0-9]?)\b", re.I)

Projector = Callable[..., dict[str, Any]]


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_workbench_capability() -> Projector:
    try:
        from neuroai_workbench.discovery import project_epo_ops_search_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench capability project_epo_ops_search_pages is unavailable; "
            "SU-PATENTS EPO OPS integration remains PENDING_S1_MERGE"
        ) from exc
    return project_epo_ops_search_pages


def _programme() -> dict[str, Any]:
    value = _load(PROGRAMME)
    if not isinstance(value, dict) or value.get("programme_id") != "SU-PATENTS-EPO-OPS-v0.1":
        raise ValueError("Invalid SU-PATENTS EPO OPS programme control")
    return value


def _eligible_patent_source(source: Mapping[str, Any]) -> bool:
    source_class = str(source.get("source_class") or "").upper()
    return "PATENT" in source_class


def _docdb_identities_from_locator(locator: str) -> set[str]:
    text = unquote(locator.strip())
    identities: set[str] = set()
    for country, number, kind in _DOCDB_DOTTED_RE.findall(text):
        identities.add(f"DOCDB:{country.upper()}:{number.upper()}:{kind.upper()}")
    lowered = text.lower()
    patent_context = any(token in lowered for token in ("espacenet", "patent", "ops.epo.org", "patentscope"))
    if patent_context:
        for country, number, kind in _PUBLICATION_TOKEN_RE.findall(text):
            identities.add(f"DOCDB:{country.upper()}:{number.upper()}:{kind.upper()}")
    return identities


def build_known_docdb_source_index() -> dict[str, Any]:
    """Derive exact DOCDB publication aliases only from controlled patent-typed Sources."""
    modules = (
        ("V1_4_BASELINE", project_v14_sources_to_v2),
        ("V1_6_REFRESH", project_v16_sources_observations_to_v2),
        ("V1_7_PRIMA_SUPPLEMENTAL", project_v17_prima_sources_to_v2),
    )
    all_source_ids: set[str] = set()
    eligible_source_ids: set[str] = set()
    docdb_to_source: dict[str, str] = {}
    lineage: dict[str, dict[str, str]] = {}

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
            if not _eligible_patent_source(source):
                continue
            eligible_source_ids.add(source_id)
            locator = source.get("canonical_locator")
            if not isinstance(locator, str) or not locator.strip():
                continue
            for identity in sorted(_docdb_identities_from_locator(locator)):
                prior = docdb_to_source.get(identity)
                if prior is not None and prior != source_id:
                    raise ValueError(
                        f"Controlled patent namespace maps exact {identity} to conflicting Sources {prior} and {source_id}"
                    )
                docdb_to_source[identity] = source_id
                lineage[identity] = {"source_id": source_id, "lineage_family": family}

    if len(all_source_ids) != 248:
        raise ValueError(f"Expected materialized 248-source namespace, found {len(all_source_ids)}")
    return {
        "materialized_source_count": len(all_source_ids),
        "patent_typed_source_count": len(eligible_source_ids),
        "known_docdb_publication_count": len(docdb_to_source),
        "docdb_to_source": dict(sorted(docdb_to_source.items())),
        "docdb_lineage": {key: lineage[key] for key in sorted(lineage)},
        "global_patent_completeness_claim": False,
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
            raise ValueError(f"Unconfigured or inactive OPS query capture {query_id!r}")
        leaf_id = capture.get("leaf_query_id")
        if not isinstance(leaf_id, str) or not leaf_id.strip():
            raise ValueError(f"{query_id}: leaf_query_id must be non-empty")
        if leaf_id in seen_leaf_ids:
            raise ValueError(f"Duplicate leaf_query_id {leaf_id}")
        seen_leaf_ids.add(leaf_id)
        effective_cql = capture.get("effective_cql")
        if not isinstance(effective_cql, str) or not effective_cql.strip():
            raise ValueError(f"{leaf_id}: effective_cql must be non-empty")
        config = configured[str(query_id)]
        applicant_term = capture.get("applicant_term")
        if config.get("query_mode") == "APPLICANT_WATCH_SET":
            if applicant_term not in config["applicant_terms"]:
                raise ValueError(f"{leaf_id}: invalid applicant_term")
            expected_root = config["cql_template"].format(applicant_term=applicant_term)
        else:
            if applicant_term is not None:
                raise ValueError(f"{leaf_id}: applicant_term only allowed for applicant watch")
            expected_root = config["cql"]
        partition_path = capture.get("partition_path")
        if not isinstance(partition_path, list):
            raise ValueError(f"{leaf_id}: partition_path must be an array")
        if not partition_path and effective_cql != expected_root:
            raise ValueError(f"{leaf_id}: unpartitioned effective_cql must exactly match programme control")
        if partition_path and expected_root not in effective_cql:
            raise ValueError(f"{leaf_id}: partitioned effective_cql must retain the exact configured root CQL")
        if capture.get("search_constituent") != programme["provider_contract"]["search_constituent"]:
            raise ValueError(f"{leaf_id}: search_constituent mismatch")
        if capture.get("response_media_type") != programme["provider_contract"]["response_media_type"]:
            raise ValueError(f"{leaf_id}: response_media_type mismatch")
        if capture.get("range_transport") != programme["provider_contract"]["range_transport"]:
            raise ValueError(f"{leaf_id}: range_transport mismatch")
        pages = capture.get("pages")
        if not isinstance(pages, list) or not pages or not all(isinstance(page, dict) and isinstance(page.get("xml"), str) and page["xml"].strip() for page in pages):
            raise ValueError(f"{leaf_id}: pages must be non-empty objects with XML")

    return str(scope), captures, configured


def _logical_coverage(
    *,
    captures: list[dict[str, Any]],
    configured: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    by_query: dict[str, list[dict[str, Any]]] = {}
    for capture in captures:
        by_query.setdefault(str(capture["query_id"]), []).append(capture)

    missing_query_ids: list[str] = []
    missing_applicant_terms: list[str] = []
    for query_id, config in configured.items():
        rows = by_query.get(query_id, [])
        if not rows:
            missing_query_ids.append(query_id)
            continue
        if config.get("query_mode") == "APPLICANT_WATCH_SET":
            present = {str(row.get("applicant_term")) for row in rows}
            for term in config["applicant_terms"]:
                if term not in present:
                    missing_applicant_terms.append(term)

    partitioned = [row for row in captures if row.get("partition_path")]
    return {
        "configured_active_query_count": len(configured),
        "represented_query_count": len(set(str(row["query_id"]) for row in captures)),
        "missing_query_ids": sorted(missing_query_ids),
        "missing_applicant_terms": sorted(missing_applicant_terms),
        "partitioned_leaf_count": len(partitioned),
        "partition_reconciliation_required": bool(partitioned),
        "all_logical_queries_represented": not missing_query_ids and not missing_applicant_terms,
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
    known = dict(known_index) if known_index is not None else build_known_docdb_source_index()
    known_map = known["docdb_to_source"]

    logical = _logical_coverage(captures=captures, configured=configured)
    query_reports: list[dict[str, Any]] = []
    union: dict[str, dict[str, Any]] = {}
    total_blockers = 0
    raw_page_count = 0

    for capture in sorted(captures, key=lambda row: str(row["leaf_query_id"])):
        query_id = str(capture["query_id"])
        leaf_id = str(capture["leaf_query_id"])
        pages = capture["pages"]
        raw_page_count += len(pages)
        projection = projector(
            query_id=query_id,
            query_text=str(capture["effective_cql"]),
            pages=pages,
            known_docdb_sources=known_map,
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
            "applicant_term": capture.get("applicant_term"),
            "partition_path": capture.get("partition_path"),
            "effective_cql": capture["effective_cql"],
            "capture_sha256": _digest(capture),
            "coverage": coverage,
            "mechanical_blockers": blockers,
        })

        normalized_by_identity = {
            row.get("docdb_publication_reference"): row
            for row in normalized
            if isinstance(row, dict) and isinstance(row.get("docdb_publication_reference"), str)
        }
        if len(normalized_by_identity) != len(normalized):
            raise ValueError(f"{leaf_id}: normalized patent identities are missing or duplicated")

        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{leaf_id}: candidate record must be object")
            identity = record.get("record_key")
            if not isinstance(identity, str) or identity not in normalized_by_identity:
                raise ValueError(f"{leaf_id}: candidate record has no normalized patent")
            normalized_row = normalized_by_identity[identity]
            digest = normalized_row.get("normalized_record_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"{leaf_id}/{identity}: normalized_record_sha256 missing/invalid")
            core = {
                "record_key": identity,
                "title": record.get("title"),
                "url": record.get("url"),
                "publisher": record.get("publisher"),
                "source_class": record.get("source_class"),
                "suggested_source_id": record.get("suggested_source_id"),
                "classification_hint": record.get("classification_hint"),
                "duplicate_of_source_id": record.get("duplicate_of_source_id"),
            }
            prior = union.get(identity)
            if prior is None:
                union[identity] = {
                    "normalized_patent": normalized_row,
                    "normalized_record_sha256": digest,
                    "candidate_input": core,
                    "query_ids": {query_id},
                    "leaf_query_ids": {leaf_id},
                }
                continue
            if prior["normalized_record_sha256"] != digest or prior["candidate_input"] != core:
                raise ValueError(f"Cross-leaf conflict for {identity}")
            prior["query_ids"].add(query_id)
            prior["leaf_query_ids"].add(leaf_id)

    normalized_patents: list[dict[str, Any]] = []
    known_duplicates: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    cross_query_repeat_count = 0
    for identity in sorted(union):
        row = union[identity]
        query_ids = sorted(row["query_ids"])
        leaf_ids = sorted(row["leaf_query_ids"])
        cross_query_repeat_count += max(0, len(leaf_ids) - 1)
        normalized_patents.append({
            "docdb_publication_reference": identity,
            "query_ids": query_ids,
            "leaf_query_ids": leaf_ids,
            "normalized_patent": row["normalized_patent"],
        })
        classified = {
            **row["candidate_input"],
            "query_ids": query_ids,
            "leaf_query_ids": leaf_ids,
            "normalized_record_sha256": row["normalized_record_sha256"],
        }
        if classified["classification_hint"] == "DUPLICATE":
            known_duplicates.append(classified)
        elif classified["classification_hint"] == "NEW":
            new_candidates.append(classified)
        else:
            raise ValueError(f"Unexpected patent discovery classification for {identity}")

    mechanically_complete = (
        scope == "FULL_PROGRAMME"
        and logical["all_logical_queries_represented"]
        and total_blockers == 0
        and not logical["partition_reconciliation_required"]
    )
    reconciliation = {
        "scope": scope,
        **logical,
        "executed_leaf_query_count": len(captures),
        "leaf_mechanical_blocker_count": total_blockers,
        "union_unique_docdb_publication_count": len(union),
        "known_controlled_duplicate_count": len(known_duplicates),
        "new_candidate_input_count": len(new_candidates),
        "cross_leaf_repeat_membership_count": cross_query_repeat_count,
        "materialized_source_namespace_count": known["materialized_source_count"],
        "patent_typed_source_count_before_run": known["patent_typed_source_count"],
        "known_docdb_publication_count_before_run": known["known_docdb_publication_count"],
        "raw_input_page_count": raw_page_count,
        "raw_ops_xml_emitted": False,
        "claims_or_description_emitted": False,
        "automatic_source_admission": False,
        "automatic_patent_family_creation": False,
        "automatic_applicant_or_inventor_entity_creation": False,
        "automatic_product_or_system_relationship_creation": False,
        "automatic_capability_claim_creation": False,
        "automatic_monitor_creation": False,
        "automatic_assessment_mutation": False,
        "human_adjudication_performed": False,
        "mechanically_complete": mechanically_complete,
        "global_neuroai_patent_recall_claim": False,
        "epo_database_completeness_claim": False,
        "patent_family_completeness_claim": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Mechanical completion, when true, applies only to exact unpartitioned configured OPS query traversals and "
            "the controlled Source namespace. Partitioned logical queries require a separate denominator/interval "
            "reconciliation proof before programme-level mechanical completion. No state establishes global patent "
            "recall, relevance, implementation, present ownership, family identity, validity/enforceability, freedom "
            "to operate, safety/effectiveness, system capability, assessment effect or canonical authority."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_SU_PATENTS_EPO_OPS_RECORDED_REPLAY_PROJECTION",
        "programme_id": programme["programme_id"],
        "input_provenance": {
            "bundle_sha256": _digest(bundle),
            "captured_at": bundle["captured_at"],
            "capture_scope": scope,
            "raw_ops_xml_retained_in_output": False,
            "known_docdb_index_sha256": _digest(known_map),
        },
        "known_source_index_summary": {
            "materialized_source_count": known["materialized_source_count"],
            "patent_typed_source_count": known["patent_typed_source_count"],
            "known_docdb_publication_count": known["known_docdb_publication_count"],
            "global_patent_completeness_claim": False,
        },
        "query_reports": query_reports,
        "normalized_patents": normalized_patents,
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
        ("normalized_patents", "normalized-patents.jsonl"),
        ("known_duplicates", "known-patent-duplicates.jsonl"),
        ("new_candidate_inputs", "new-patent-candidate-inputs.jsonl"),
    ):
        files.append(_write_jsonl(output_dir / filename, result[key]))
    for key, filename in (
        ("input_provenance", "input-provenance.json"),
        ("known_source_index_summary", "known-source-index-summary.json"),
        ("query_reports", "query-reports.json"),
        ("reconciliation", "reconciliation.json"),
    ):
        payload = _canonical_bytes(result[key])
        (output_dir / filename).write_bytes(payload)
        files.append({"path": filename, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "records": 1})
    manifest = {
        "programme_id": result["programme_id"],
        "status": result["status"],
        "files": sorted(files, key=lambda row: row["path"]),
        "file_count": len(files),
        "raw_ops_xml_emitted": False,
        "canonical_successor_ready": False,
    }
    payload = _canonical_bytes(manifest)
    (output_dir / "manifest.json").write_bytes(payload)
    return {**manifest, "manifest_sha256": hashlib.sha256(payload).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_replay(_load(args.input_bundle.resolve()))
    manifest = write_projection(result, args.output_dir.resolve())
    print(json.dumps({"reconciliation": result["reconciliation"], "manifest": manifest}, indent=2, sort_keys=True))
    return 0 if result["reconciliation"]["mechanically_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
