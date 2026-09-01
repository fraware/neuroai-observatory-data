#!/usr/bin/env python3
"""Project recorded openFDA/MAUDE device-event pages into a deterministic SU-REGULATION package.

Raw provider pages are ephemeral input only. Output is restricted to the Workbench's minimized
report/device projection, exact controlled-source duplicate/new classification, query coverage and
provenance digests. No patient data, MDR narratives, raw pages, causal/safety signals, regulatory
actions, system/entity links, assessment mutations, or canonical authority are created here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote_plus

import project_v14_sources_to_v2
import project_v16_sources_observations_to_v2
import project_v17_prima_sources_to_v2

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation" / "openfda_device_event_discovery_programme_v0.1.json"
_MDR_LOCATOR_RE = re.compile(r'mdr_report_key:\s*"?([^"&\s]+)"?', re.I)

Projector = Callable[..., dict[str, Any]]


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_workbench_capability() -> Projector:
    try:
        from neuroai_workbench.discovery import project_openfda_device_event_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench capability project_openfda_device_event_pages is unavailable; "
            "SU-REGULATION openFDA integration remains PENDING_S1_MERGE"
        ) from exc
    return project_openfda_device_event_pages


def _programme() -> dict[str, Any]:
    value = _load(PROGRAMME)
    if not isinstance(value, dict) or value.get("programme_id") != "SU-REGULATION-OPENFDA-DEVICE-EVENTS-v0.1":
        raise ValueError("Invalid SU-REGULATION openFDA device-event programme control")
    return value


def _eligible_maude_source(source: Mapping[str, Any]) -> bool:
    token = str(source.get("source_class") or "").upper()
    return any(part in token for part in ("MAUDE", "ADVERSE_EVENT", "POSTMARKET"))


def _mdr_key_from_locator(locator: str) -> str | None:
    decoded = unquote_plus(locator)
    match = _MDR_LOCATOR_RE.search(decoded)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def build_known_mdr_source_index() -> dict[str, Any]:
    """Derive exact MDR aliases only from controlled post-market Sources with explicit keys."""
    modules = (
        ("V1_4_BASELINE", project_v14_sources_to_v2),
        ("V1_6_REFRESH", project_v16_sources_observations_to_v2),
        ("V1_7_PRIMA_SUPPLEMENTAL", project_v17_prima_sources_to_v2),
    )
    all_source_ids: set[str] = set()
    eligible_source_ids: set[str] = set()
    key_to_source: dict[str, str] = {}
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
            if not _eligible_maude_source(source):
                continue
            eligible_source_ids.add(source_id)
            locator = source.get("canonical_locator")
            if not isinstance(locator, str) or not locator.strip():
                continue
            key = _mdr_key_from_locator(locator)
            if key is None:
                continue
            prior = key_to_source.get(key)
            if prior is not None and prior != source_id:
                raise ValueError(f"Controlled post-market namespace maps MDR key {key} to conflicting Sources {prior} and {source_id}")
            key_to_source[key] = source_id
            lineage[key] = {"source_id": source_id, "lineage_family": family}

    if len(all_source_ids) != 248:
        raise ValueError(f"Expected materialized 248-source namespace, found {len(all_source_ids)}")
    return {
        "materialized_source_count": len(all_source_ids),
        "postmarket_typed_source_count": len(eligible_source_ids),
        "known_mdr_report_key_count": len(key_to_source),
        "mdr_to_source": dict(sorted(key_to_source.items())),
        "mdr_lineage": {key: lineage[key] for key in sorted(lineage)},
        "global_postmarket_completeness_claim": False,
    }


def _active_queries(programme: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["query_id"]): dict(row) for row in programme["query_streams"] if row.get("status") == "ACTIVE"}


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
        raise ValueError("leaf_query_captures must be a non-empty object array")

    configured = _active_queries(programme)
    seen_leaf_ids: set[str] = set()
    for capture in captures:
        query_id = capture.get("query_id")
        if query_id not in configured:
            raise ValueError(f"Unconfigured or inactive openFDA query capture {query_id!r}")
        leaf_id = capture.get("leaf_query_id")
        if not isinstance(leaf_id, str) or not leaf_id.strip():
            raise ValueError(f"{query_id}: leaf_query_id must be non-empty")
        if leaf_id in seen_leaf_ids:
            raise ValueError(f"Duplicate leaf_query_id {leaf_id}")
        seen_leaf_ids.add(leaf_id)
        effective_search = capture.get("effective_search")
        if not isinstance(effective_search, str) or not effective_search.strip():
            raise ValueError(f"{leaf_id}: effective_search must be non-empty")
        root = configured[str(query_id)]["search"]
        partition_path = capture.get("partition_path")
        if not isinstance(partition_path, list):
            raise ValueError(f"{leaf_id}: partition_path must be an array")
        if not partition_path:
            if effective_search != root:
                raise ValueError(f"{leaf_id}: unpartitioned effective_search must exactly match programme control")
        else:
            if len(partition_path) != 1:
                raise ValueError(f"{leaf_id}: v0.1 permits exactly one DATE_RECEIVED partition interval per leaf")
            part = partition_path[0]
            if not isinstance(part, dict) or part.get("dimension") != "DATE_RECEIVED":
                raise ValueError(f"{leaf_id}: only DATE_RECEIVED partitioning is permitted")
            lower = part.get("lower_bound")
            upper = part.get("upper_bound")
            if not isinstance(lower, str) or not re.fullmatch(r"\d{8}", lower) or not isinstance(upper, str) or not re.fullmatch(r"\d{8}", upper):
                raise ValueError(f"{leaf_id}: partition bounds must be YYYYMMDD")
            if lower > upper:
                raise ValueError(f"{leaf_id}: reversed date partition")
            expected = f"({root})+AND+date_received:[{lower}+TO+{upper}]"
            if effective_search != expected:
                raise ValueError(f"{leaf_id}: partitioned effective_search must exactly match declared date interval")
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
    if coverage.get("patient_level_fields_projected") is not False:
        blockers.append("PATIENT_FIELD_BOUNDARY_VIOLATION")
    if coverage.get("mdr_text_narrative_projected") is not False:
        blockers.append("MDR_NARRATIVE_BOUNDARY_VIOLATION")
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
    known = dict(known_index) if known_index is not None else build_known_mdr_source_index()
    known_map = known.get("mdr_to_source") or {}

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
            search=str(capture["effective_search"]),
            pages=pages,
            known_mdr_sources=known_map,
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
            "effective_search": capture["effective_search"],
            "capture_sha256": _digest(capture),
            "coverage": coverage,
            "mechanical_blockers": blockers,
        })

        normalized_by_key: dict[str, dict[str, Any]] = {}
        for row in normalized:
            if not isinstance(row, dict) or not isinstance(row.get("mdr_report_key"), str) or not row["mdr_report_key"]:
                raise ValueError(f"{leaf_id}: normalized MDR identity is missing")
            key = row["mdr_report_key"]
            if key in normalized_by_key:
                raise ValueError(f"{leaf_id}: duplicated normalized MDR key {key}")
            if row.get("patient_level_fields_included") is not False or row.get("mdr_text_narrative_included") is not False:
                raise ValueError(f"{leaf_id}/{key}: minimized metadata boundary violated")
            normalized_by_key[key] = row

        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{leaf_id}: candidate record must be object")
            key_token = record.get("record_key")
            if not isinstance(key_token, str) or not key_token.startswith("MAUDE:MDR:"):
                raise ValueError(f"{leaf_id}: invalid candidate record_key")
            key = key_token.removeprefix("MAUDE:MDR:")
            normalized_row = normalized_by_key.get(key)
            if normalized_row is None:
                raise ValueError(f"{leaf_id}: candidate record has no normalized MDR")
            digest = normalized_row.get("normalized_record_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"{leaf_id}/{key}: normalized_record_sha256 missing/invalid")
            candidate_core = {
                "mdr_report_key": key,
                "record_key": key_token,
                "title": record.get("title"),
                "url": record.get("url"),
                "publisher": record.get("publisher"),
                "source_class": record.get("source_class"),
                "suggested_source_id": record.get("suggested_source_id"),
                "classification_hint": record.get("classification_hint"),
                "duplicate_of_source_id": record.get("duplicate_of_source_id"),
                "normalized_record_sha256": digest,
            }
            prior = union.get(key)
            if prior is None:
                union[key] = {
                    "candidate": candidate_core,
                    "normalized": dict(normalized_row),
                    "query_memberships": {query_id},
                    "leaf_memberships": {leaf_id},
                }
            else:
                if prior["candidate"] != candidate_core:
                    raise ValueError(f"Cross-leaf candidate conflict for MDR report {key}")
                if prior["normalized"].get("normalized_record_sha256") != digest:
                    raise ValueError(f"Cross-leaf content conflict for MDR report {key}")
                prior["query_memberships"].add(query_id)
                prior["leaf_memberships"].add(leaf_id)

    normalized_output: list[dict[str, Any]] = []
    known_duplicates: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    for key in sorted(union):
        entry = union[key]
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
            raise ValueError(f"Unsupported candidate classification for MDR report {key}")

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
        "known_mdr_report_key_count": known.get("known_mdr_report_key_count", len(known_map)),
        **logical,
        "leaf_query_capture_count": len(captures),
        "raw_provider_page_count": raw_page_count,
        "leaf_mechanical_blocker_count": total_blockers,
        "union_unique_mdr_report_key_count": len(union),
        "known_controlled_duplicate_count": len(known_duplicates),
        "new_candidate_input_count": len(new_candidates),
        "mechanically_complete": mechanically_complete,
        "patient_level_fields_emitted": False,
        "mdr_text_narratives_emitted": False,
        "automatic_source_admission": False,
        "automatic_system_or_device_entity_creation": False,
        "automatic_manufacturer_entity_creation": False,
        "automatic_safety_signal_creation": False,
        "automatic_causality_claim_creation": False,
        "automatic_incidence_or_rate_claim_creation": False,
        "automatic_regulatory_action_creation": False,
        "automatic_assessment_mutation": False,
        "global_neuroai_postmarket_recall_claim": False,
        "causality_claim": False,
        "incidence_or_rate_claim": False,
        "comparative_safety_claim": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Recorded replay establishes deterministic processing of exact supplied openFDA/MAUDE pages only. "
            "It does not establish causality, incidence, comparative safety, FDA determination, recall/enforcement, "
            "device/system identity, relevance, assessment effect, global post-market recall or canonical authority."
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
        "patient_level_fields_retained_in_output": False,
        "mdr_text_narratives_retained_in_output": False,
    }
    return {
        "normalized_reports": normalized_output,
        "known_duplicates": known_duplicates,
        "new_candidates": new_candidates,
        "query_reports": query_reports,
        "reconciliation": reconciliation,
        "input_provenance": provenance,
        "known_source_index_summary": {
            key: value for key, value in known.items() if key not in {"mdr_to_source", "mdr_lineage"}
        },
    }


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_bytes(row) for row in rows)


def write_projection(result: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, bytes] = {
        "normalized-mdr-reports.jsonl": _jsonl(list(result["normalized_reports"])),
        "known-mdr-duplicates.jsonl": _jsonl(list(result["known_duplicates"])),
        "new-mdr-candidate-inputs.jsonl": _jsonl(list(result["new_candidates"])),
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
        "patient_level_fields_included": False,
        "mdr_text_narratives_included": False,
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
    result = build_replay(_load(args.input))
    written = write_projection(result, args.output_dir)
    print(json.dumps({"reconciliation": result["reconciliation"], **written}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
