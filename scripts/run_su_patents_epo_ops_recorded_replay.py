#!/usr/bin/env python3
"""Deterministic recorded replay for bounded EPO OPS patent discovery.

Raw OPS XML is ephemeral input. Outputs are noncanonical discovery projections only.
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

try:
    from scripts.current_source_namespace import materialize_effective_source_namespace
except ModuleNotFoundError:  # direct `python scripts/...py`
    from current_source_namespace import materialize_effective_source_namespace

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation" / "epo_ops_patent_discovery_programme_v0.1.json"
DOCDB_DOTTED_RE = re.compile(r"\b([A-Z]{2})\.([A-Z0-9./-]+)\.([A-Z][A-Z0-9]*)\b", re.I)
DOCDB_LITERAL_RE = re.compile(
    r"\bDOCDB:([A-Z]{2}):([A-Z0-9./-]+):([A-Z][A-Z0-9]*)\b", re.I
)
ESPACENET_PN_RE = re.compile(r"(?:[?&]q=pn%3D|[?&]q=pn=)([A-Z]{2})([0-9][A-Z0-9./-]+?)([A-Z][0-9]?)\b", re.I)

Projector = Callable[..., dict[str, Any]]


def _canon(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _programme() -> dict[str, Any]:
    value = _load(PROGRAMME)
    if value.get("programme_id") != "SU-PATENTS-EPO-OPS-v0.1":
        raise ValueError("Invalid SU-PATENTS EPO OPS programme control")
    dependency = value.get("workbench_dependency") or {}
    if dependency.get("required_capability") != "project_epo_ops_search_pages":
        raise ValueError("Unexpected Workbench EPO OPS capability")
    if dependency.get("integration_state") != "AVAILABLE":
        raise ValueError("EPO OPS programme requires AVAILABLE Workbench capability")
    return value


def _load_projector() -> Projector:
    try:
        from neuroai_workbench.discovery import project_epo_ops_search_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench capability project_epo_ops_search_pages unavailable"
        ) from exc
    return project_epo_ops_search_pages


def _eligible_patent_source(source: Mapping[str, Any]) -> bool:
    return "PATENT" in str(source.get("source_class") or "").upper()


def _docdb_identities_from_locator(locator: str) -> set[str]:
    """Extract only explicit publication identities from a patent-typed Source locator."""
    text = unquote(locator.strip())
    identities: set[str] = set()
    for pattern in (DOCDB_LITERAL_RE, DOCDB_DOTTED_RE):
        for country, number, kind in pattern.findall(text):
            identities.add(f"DOCDB:{country.upper()}:{number.upper()}:{kind.upper()}")
    for country, number, kind in ESPACENET_PN_RE.findall(text):
        identities.add(f"DOCDB:{country.upper()}:{number.upper()}:{kind.upper()}")
    return identities


def build_known_docdb_source_index() -> dict[str, Any]:
    namespace = materialize_effective_source_namespace()
    sources = namespace.get("sources")
    if (
        not isinstance(sources, list)
        or namespace.get("materialized_source_count") != 248
        or len(sources) != 248
    ):
        raise ValueError("Expected exact 248-Source controlled namespace")
    source_id_set_sha256 = namespace.get("source_id_set_sha256")
    if not isinstance(source_id_set_sha256, str) or len(source_id_set_sha256) != 64:
        raise ValueError("Controlled Source namespace digest unavailable")

    eligible_ids: set[str] = set()
    mapping: dict[str, str] = {}
    lineage: dict[str, dict[str, str]] = {}
    for source in sources:
        if not isinstance(source, Mapping):
            raise ValueError("Controlled Source row must be object")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("Controlled Source row missing source_id")
        if not _eligible_patent_source(source):
            continue
        eligible_ids.add(source_id)
        locator = source.get("canonical_locator")
        if not isinstance(locator, str) or not locator.strip():
            continue
        for identity in sorted(_docdb_identities_from_locator(locator)):
            prior = mapping.get(identity)
            if prior is not None and prior != source_id:
                raise ValueError(
                    f"Controlled patent namespace maps {identity} to conflicting Sources "
                    f"{prior} and {source_id}"
                )
            mapping[identity] = source_id
            lineage[identity] = {
                "source_id": source_id,
                "lineage_family": str(source.get("lineage_family") or ""),
            }

    return {
        "materialized_source_count": 248,
        "source_id_set_sha256": source_id_set_sha256,
        "patent_typed_source_count": len(eligible_ids),
        "known_docdb_publication_count": len(mapping),
        "docdb_to_source": dict(sorted(mapping.items())),
        "docdb_lineage": {key: lineage[key] for key in sorted(lineage)},
        "global_patent_completeness_claim": False,
    }


def _active_queries(programme: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["query_id"]): dict(row)
        for row in programme["query_streams"]
        if row.get("status") == "ACTIVE"
    }


def _root_cql(config: Mapping[str, Any], applicant_term: Any) -> str:
    if config.get("query_mode") == "APPLICANT_WATCH_SET":
        terms = config.get("applicant_terms") or []
        if applicant_term not in terms:
            raise ValueError("invalid applicant_term")
        return str(config["cql_template"]).format(applicant_term=applicant_term)
    if applicant_term is not None:
        raise ValueError("applicant_term only allowed for applicant watch")
    return str(config["cql"])


def _validate_partition_path(path: Any, leaf_id: str) -> list[dict[str, str]]:
    if not isinstance(path, list):
        raise ValueError(f"{leaf_id}: partition_path must be an array")
    normalized: list[dict[str, str]] = []
    for index, row in enumerate(path):
        if not isinstance(row, Mapping):
            raise ValueError(f"{leaf_id}: partition_path[{index}] must be object")
        if set(row) != {"dimension", "lower_bound", "upper_bound"}:
            raise ValueError(f"{leaf_id}: partition_path[{index}] fields changed")
        dimension = row.get("dimension")
        if dimension not in {"PUBLICATION_DATE_YEAR", "PUBLICATION_DATE_MONTH"}:
            raise ValueError(f"{leaf_id}: unsupported partition dimension")
        lower = row.get("lower_bound")
        upper = row.get("upper_bound")
        if not isinstance(lower, str) or not lower or not isinstance(upper, str) or not upper:
            raise ValueError(f"{leaf_id}: partition bounds must be non-empty strings")
        normalized.append(
            {"dimension": str(dimension), "lower_bound": lower, "upper_bound": upper}
        )
    return normalized


def _partition_interval_from_effective_cql(root_cql: str, effective_cql: str) -> tuple[str, str] | None:
    prefix = f"({root_cql}) and pd within "
    if not effective_cql.startswith(prefix):
        return None
    suffix = effective_cql[len(prefix):]
    match = re.fullmatch(r'"([0-9]{8}) ([0-9]{8})"', suffix)
    if match is None:
        return None
    return match.group(1), match.group(2)


def _validate_bundle(
    bundle: Mapping[str, Any], programme: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if bundle.get("schema_version") != "0.1.0":
        raise ValueError("Replay input schema_version must be 0.1.0")
    if bundle.get("programme_id") != programme["programme_id"]:
        raise ValueError("Replay input programme_id mismatch")
    if bundle.get("provider") != programme["provider_contract"]["provider"]:
        raise ValueError("Replay input provider mismatch")
    scope = bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME", "PARTIAL_VALIDATION"}:
        raise ValueError("Invalid capture_scope")
    captured_at = bundle.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise ValueError("captured_at must be non-empty")
    captures = bundle.get("leaf_query_captures")
    if not isinstance(captures, list) or not captures:
        raise ValueError("leaf_query_captures required")

    configured = _active_queries(programme)
    seen_leaf_ids: set[str] = set()
    for capture in captures:
        if not isinstance(capture, dict):
            raise ValueError("leaf query capture must be object")
        query_id = capture.get("query_id")
        if query_id not in configured:
            raise ValueError(f"Unconfigured or inactive OPS query capture {query_id!r}")
        leaf_id = capture.get("leaf_query_id")
        if not isinstance(leaf_id, str) or not leaf_id or leaf_id in seen_leaf_ids:
            raise ValueError("Invalid or duplicate leaf_query_id")
        seen_leaf_ids.add(leaf_id)
        root_cql = _root_cql(configured[str(query_id)], capture.get("applicant_term"))
        effective_cql = capture.get("effective_cql")
        if not isinstance(effective_cql, str) or not effective_cql:
            raise ValueError(f"{leaf_id}: effective_cql required")
        partition_path = _validate_partition_path(capture.get("partition_path"), leaf_id)
        if not partition_path:
            if effective_cql != root_cql:
                raise ValueError(
                    f"{leaf_id}: unpartitioned effective_cql must exactly match programme control"
                )
        else:
            interval = _partition_interval_from_effective_cql(root_cql, effective_cql)
            if interval is None:
                raise ValueError(
                    f"{leaf_id}: partitioned effective_cql must be exact root plus pd within interval"
                )
        provider = programme["provider_contract"]
        if capture.get("search_constituent") != provider["search_constituent"]:
            raise ValueError(f"{leaf_id}: search_constituent mismatch")
        if capture.get("response_media_type") != provider["response_media_type"]:
            raise ValueError(f"{leaf_id}: response_media_type mismatch")
        if capture.get("range_transport") != provider["range_transport"]:
            raise ValueError(f"{leaf_id}: range_transport mismatch")
        pages = capture.get("pages")
        if (
            not isinstance(pages, list)
            or not pages
            or not all(
                isinstance(page, dict)
                and isinstance(page.get("xml"), str)
                and page["xml"].strip()
                for page in pages
            )
        ):
            raise ValueError(f"{leaf_id}: pages must contain non-empty XML")
    return str(scope), captures, configured


def _logical_coverage(
    captures: list[dict[str, Any]], configured: Mapping[str, Mapping[str, Any]]
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
            present = {row.get("applicant_term") for row in rows}
            for term in config["applicant_terms"]:
                if term not in present:
                    missing_applicant_terms.append(term)

    partitioned = [row for row in captures if row.get("partition_path")]
    return {
        "configured_active_query_count": len(configured),
        "represented_query_count": len(by_query),
        "missing_query_ids": sorted(missing_query_ids),
        "missing_applicant_terms": sorted(missing_applicant_terms),
        "partitioned_leaf_count": len(partitioned),
        "partition_reconciliation_required": bool(partitioned),
        "all_logical_queries_represented": not missing_query_ids
        and not missing_applicant_terms,
    }


def _leaf_blockers(
    coverage: Mapping[str, Any], programme: Mapping[str, Any]
) -> list[str]:
    blockers: list[str] = []
    required = set(programme["coverage_contract"]["required_metrics_per_leaf_query"])
    missing = sorted(required - set(coverage))
    if missing:
        blockers.append("MISSING_COVERAGE_METRICS:" + ",".join(missing))
    for key, expected in programme["coverage_contract"][
        "mechanical_completion_requires"
    ].items():
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
    projector = projector or _load_projector()
    known = dict(known_index) if known_index is not None else build_known_docdb_source_index()
    if known.get("materialized_source_count") != 248:
        raise ValueError("Known Source index must bind exact 248-Source namespace")
    source_digest = known.get("source_id_set_sha256")
    if not isinstance(source_digest, str) or len(source_digest) != 64:
        raise ValueError("Known Source index must include source_id_set_sha256")
    known_map = known.get("docdb_to_source")
    if not isinstance(known_map, dict):
        raise ValueError("Known DOCDB index missing docdb_to_source")

    logical = _logical_coverage(captures, configured)
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
        if (
            not isinstance(coverage, dict)
            or not isinstance(records, list)
            or not isinstance(normalized, list)
        ):
            raise ValueError(f"{leaf_id}: invalid Workbench projection shape")
        blockers = _leaf_blockers(coverage, programme)
        total_blockers += len(blockers)
        query_reports.append(
            {
                "query_id": query_id,
                "leaf_query_id": leaf_id,
                "applicant_term": capture.get("applicant_term"),
                "partition_path": capture.get("partition_path"),
                "effective_cql": capture["effective_cql"],
                "capture_sha256": _digest(capture),
                "coverage": coverage,
                "mechanical_blockers": blockers,
            }
        )

        normalized_by_identity: dict[str, dict[str, Any]] = {}
        for row in normalized:
            if not isinstance(row, dict):
                raise ValueError(f"{leaf_id}: normalized patent must be object")
            identity = row.get("docdb_publication_reference")
            if not isinstance(identity, str) or not identity or identity in normalized_by_identity:
                raise ValueError(f"{leaf_id}: normalized patent identities missing/duplicated")
            digest = row.get("normalized_record_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"{leaf_id}/{identity}: invalid normalized digest")
            normalized_by_identity[identity] = row

        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{leaf_id}: candidate record must be object")
            identity = record.get("record_key")
            if not isinstance(identity, str) or identity not in normalized_by_identity:
                raise ValueError(f"{leaf_id}: candidate lacks matching normalized patent")
            normalized_row = normalized_by_identity[identity]
            digest = normalized_row["normalized_record_sha256"]
            candidate = {
                key: record.get(key)
                for key in (
                    "record_key",
                    "title",
                    "url",
                    "publisher",
                    "source_class",
                    "suggested_source_id",
                    "classification_hint",
                    "duplicate_of_source_id",
                )
            }
            prior = union.get(identity)
            if prior is None:
                union[identity] = {
                    "normalized_patent": normalized_row,
                    "normalized_record_sha256": digest,
                    "candidate_input": candidate,
                    "query_ids": {query_id},
                    "leaf_query_ids": {leaf_id},
                }
            else:
                if (
                    prior["normalized_record_sha256"] != digest
                    or prior["candidate_input"] != candidate
                ):
                    raise ValueError(f"Cross-leaf conflict for {identity}")
                prior["query_ids"].add(query_id)
                prior["leaf_query_ids"].add(leaf_id)

    normalized_patents: list[dict[str, Any]] = []
    known_duplicates: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    repeat_memberships = 0
    for identity in sorted(union):
        row = union[identity]
        query_ids = sorted(row["query_ids"])
        leaf_ids = sorted(row["leaf_query_ids"])
        repeat_memberships += max(0, len(leaf_ids) - 1)
        normalized_patents.append(
            {
                "docdb_publication_reference": identity,
                "query_ids": query_ids,
                "leaf_query_ids": leaf_ids,
                "normalized_patent": row["normalized_patent"],
            }
        )
        classified = {
            **row["candidate_input"],
            "query_ids": query_ids,
            "leaf_query_ids": leaf_ids,
            "normalized_record_sha256": row["normalized_record_sha256"],
        }
        hint = classified.get("classification_hint")
        if hint == "DUPLICATE":
            known_duplicates.append(classified)
        elif hint == "NEW":
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
        "cross_leaf_repeat_membership_count": repeat_memberships,
        "materialized_source_namespace_count": 248,
        "controlled_source_id_set_sha256": source_digest,
        "patent_typed_source_count_before_run": known.get("patent_typed_source_count"),
        "known_docdb_publication_count_before_run": known.get(
            "known_docdb_publication_count"
        ),
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
            "Mechanical completion applies only to exact unpartitioned configured OPS traversals "
            "and the controlled Source namespace. Any partitioned logical query requires the "
            "separate dated denominator/interval proof. No replay state establishes global patent "
            "recall, relevance, implementation, present ownership, family identity, validity, "
            "enforceability, freedom to operate, system capability, safety/effectiveness, "
            "assessment effect, or canonical authority."
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
            "controlled_source_id_set_sha256": source_digest,
            "known_docdb_index_sha256": _digest(known_map),
        },
        "known_source_index_summary": {
            "materialized_source_count": 248,
            "source_id_set_sha256": source_digest,
            "patent_typed_source_count": known.get("patent_typed_source_count"),
            "known_docdb_publication_count": known.get(
                "known_docdb_publication_count"
            ),
            "global_patent_completeness_claim": False,
        },
        "query_reports": query_reports,
        "normalized_patents": normalized_patents,
        "known_duplicates": known_duplicates,
        "new_candidate_inputs": new_candidates,
        "reconciliation": reconciliation,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload = b"".join(_canon(row) for row in rows)
    path.write_bytes(payload)
    return {
        "path": path.name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "records": len(rows),
    }


def write_projection(result: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for key, filename in (
        ("normalized_patents", "normalized-patents.jsonl"),
        ("known_duplicates", "known-patent-duplicates.jsonl"),
        ("new_candidate_inputs", "new-patent-candidate-inputs.jsonl"),
    ):
        files.append(_write_jsonl(output_dir / filename, list(result[key])))
    for key, filename in (
        ("input_provenance", "input-provenance.json"),
        ("known_source_index_summary", "known-source-index-summary.json"),
        ("query_reports", "query-reports.json"),
        ("reconciliation", "reconciliation.json"),
    ):
        payload = _canon(result[key])
        (output_dir / filename).write_bytes(payload)
        files.append(
            {
                "path": filename,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "records": 1,
            }
        )
    manifest = {
        "programme_id": result["programme_id"],
        "status": result["status"],
        "files": sorted(files, key=lambda row: row["path"]),
        "file_count": len(files),
        "raw_ops_xml_emitted": False,
        "canonical_successor_ready": False,
    }
    payload = _canon(manifest)
    (output_dir / "manifest.json").write_bytes(payload)
    return {**manifest, "manifest_sha256": hashlib.sha256(payload).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_replay(_load(args.input_bundle.resolve()))
    manifest = write_projection(result, args.output_dir.resolve())
    print(
        json.dumps(
            {"reconciliation": result["reconciliation"], "manifest": manifest},
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["reconciliation"]["mechanically_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
