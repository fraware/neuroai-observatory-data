#!/usr/bin/env python3
"""Project recorded Europe PMC search pages into a deterministic SU-PUBLICATIONS package.

Raw Europe PMC pages are ephemeral input only. This runner emits selected normalized
publication metadata, exact bibliographic-source duplicate/new classification, query coverage,
cross-query reconciliation, anchor observations, and provenance digests. It does not emit raw
pages or full text, admit Sources, create relationships/monitors, mutate assessments, make human
relevance decisions, or authorize canonical publication.
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
PROGRAMME = ROOT / "curation" / "europepmc_publications_discovery_programme_v0.1.json"

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_PUBMED_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", re.I)
_PMCID_RE = re.compile(r"\bPMC\d+\b", re.I)
_EPMC_ARTICLE_RE = re.compile(r"europepmc\.org/article/([^/?#]+)/([^/?#]+)", re.I)

Projector = Callable[..., dict[str, Any]]


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_workbench_capability() -> Projector:
    try:
        from neuroai_workbench.discovery import project_europepmc_search_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench capability project_europepmc_search_pages is unavailable; "
            "SU-PUBLICATIONS Europe PMC integration remains PENDING_S1_MERGE"
        ) from exc
    return project_europepmc_search_pages


def _normalize_doi(raw: str) -> str:
    return raw.strip().lower()


def _publication_identities_from_locator(locator: str) -> set[str]:
    """Extract exact publication identifiers from one controlled bibliographic locator."""
    text = unquote(locator.strip())
    identities: set[str] = set()

    for match in _DOI_RE.findall(text):
        identities.add(f"DOI:{_normalize_doi(match)}")

    pubmed = _PUBMED_URL_RE.search(text)
    if pubmed:
        identities.add(f"PMID:{pubmed.group(1)}")

    for pmcid in _PMCID_RE.findall(text):
        identities.add(f"PMCID:{pmcid.upper()}")

    epmc = _EPMC_ARTICLE_RE.search(text)
    if epmc:
        source = epmc.group(1).upper()
        ext_id = epmc.group(2)
        identities.add(f"EPMC:{source}:{ext_id}")
        if source == "MED" and ext_id.isdigit():
            identities.add(f"PMID:{ext_id}")
        if source == "PMC" and _PMCID_RE.fullmatch(ext_id.upper()):
            identities.add(f"PMCID:{ext_id.upper()}")

    return identities


def _bibliographic_source_class(source_class: Any) -> bool:
    token = str(source_class or "").upper()
    return "BIBLIOGRAPHIC" in token or token == "PUBLICATION_RECORD"


def build_known_publication_source_index() -> dict[str, Any]:
    """Derive exact publication-identity aliases for controlled bibliographic Sources.

    Primary journal articles, preprints and other substantive publication Sources are not treated
    as duplicate Europe PMC metadata Sources solely because they concern the same publication.
    Duplicate recognition is therefore restricted to controlled bibliographic-metadata Source
    classes. Exact identity aliases that map to multiple eligible Sources fail closed.
    """
    modules = (
        ("V1_4_BASELINE", project_v14_sources_to_v2),
        ("V1_6_REFRESH", project_v16_sources_observations_to_v2),
        ("V1_7_PRIMA_SUPPLEMENTAL", project_v17_prima_sources_to_v2),
    )
    all_source_ids: set[str] = set()
    bibliographic_source_ids: set[str] = set()
    identity_to_source: dict[str, str] = {}
    identity_lineage: dict[str, dict[str, str]] = {}

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
                raise ValueError(f"Duplicate Source identity in effective namespace: {source_id}")
            all_source_ids.add(source_id)

            if not _bibliographic_source_class(source.get("source_class")):
                continue
            bibliographic_source_ids.add(source_id)
            locator = source.get("canonical_locator")
            if not isinstance(locator, str) or not locator.strip():
                continue
            for identity in sorted(_publication_identities_from_locator(locator)):
                prior = identity_to_source.get(identity)
                if prior is not None and prior != source_id:
                    raise ValueError(
                        "Controlled bibliographic namespace maps exact publication identity "
                        f"{identity} to conflicting Sources {prior} and {source_id}"
                    )
                identity_to_source[identity] = source_id
                identity_lineage[identity] = {
                    "source_id": source_id,
                    "lineage_family": family,
                }

    if len(all_source_ids) != 248:
        raise ValueError(f"Expected materialized 248-source namespace, found {len(all_source_ids)}")

    return {
        "materialized_source_count": len(all_source_ids),
        "eligible_bibliographic_source_count": len(bibliographic_source_ids),
        "known_publication_identity_count": len(identity_to_source),
        "identity_to_source": dict(sorted(identity_to_source.items())),
        "identity_lineage": {
            key: identity_lineage[key] for key in sorted(identity_lineage)
        },
        "source_admission_completeness_claim": False,
        "publication_universe_completeness_claim": False,
    }


def _programme() -> dict[str, Any]:
    value = _load(PROGRAMME)
    if not isinstance(value, dict) or value.get("programme_id") != "SU-PUBLICATIONS-EUROPEPMC-v0.1":
        raise ValueError("Invalid SU-PUBLICATIONS Europe PMC programme control")
    if (value.get("workbench_dependency") or {}).get("integration_state") != "PENDING_S1_MERGE":
        raise ValueError("Europe PMC replay requires programme integration_state PENDING_S1_MERGE")
    return value


def _anchor_aliases(programme: Mapping[str, Any]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for row in programme.get("known_identifier_anchors") or []:
        if not isinstance(row, Mapping):
            raise ValueError("Known anchor must be an object")
        anchor_id = str(row.get("anchor_id") or "")
        if not anchor_id or anchor_id in aliases:
            raise ValueError("Known anchor IDs must be non-empty and unique")
        values: set[str] = set()
        doi = row.get("doi")
        if isinstance(doi, str) and doi.strip():
            values.add(f"DOI:{_normalize_doi(doi)}")
        pmid = row.get("pmid")
        if isinstance(pmid, str) and pmid.isdigit():
            values.add(f"PMID:{pmid}")
        if not values:
            raise ValueError(f"Known anchor {anchor_id} has no exact identifier alias")
        aliases[anchor_id] = values
    return aliases


def _validate_bundle(
    bundle: Any, programme: Mapping[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(bundle, dict):
        raise ValueError("Replay input bundle must be an object")
    if bundle.get("schema_version") != "0.1.0":
        raise ValueError("Replay input schema_version must be 0.1.0")
    if bundle.get("programme_id") != programme["programme_id"]:
        raise ValueError("Replay input programme_id mismatch")
    if bundle.get("provider") != "Europe PMC":
        raise ValueError("Replay input provider must be Europe PMC")
    scope = bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME", "PARTIAL_VALIDATION"}:
        raise ValueError("capture_scope must be FULL_PROGRAMME or PARTIAL_VALIDATION")
    captured_at = bundle.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise ValueError("captured_at must be non-empty")
    if bundle.get("raw_input_contains_full_text") is not False:
        raise ValueError("Recorded replay input must not contain full-text payloads")
    if bundle.get("participant_level_data_expected") is not False:
        raise ValueError("Participant-level data is outside the replay contract")

    captures = bundle.get("query_captures")
    if not isinstance(captures, list) or not captures or not all(
        isinstance(row, dict) for row in captures
    ):
        raise ValueError("query_captures must be a non-empty array of objects")

    configured = {
        row["query_id"]: row
        for row in programme["query_streams"]
        if row.get("status") == "ACTIVE"
    }
    provider = programme["provider_contract"]
    seen: set[str] = set()
    for capture in captures:
        query_id = capture.get("query_id")
        if query_id not in configured:
            raise ValueError(f"Unconfigured or inactive query capture {query_id!r}")
        if query_id in seen:
            raise ValueError(f"Duplicate query capture {query_id}")
        seen.add(str(query_id))
        if capture.get("query_term") != configured[query_id]["query_term"]:
            raise ValueError(f"{query_id}: captured query term does not match programme control")
        request = capture.get("request")
        if not isinstance(request, dict):
            raise ValueError(f"{query_id}: request must be an object")
        expected_request = {
            "endpoint": provider["api_endpoint"],
            "format": provider["format"],
            "result_type": provider["result_type"],
            "page_size": provider["page_size"],
            "synonym_expansion": provider["synonym_expansion"],
            "first_cursor_mark": provider["first_cursor_mark"],
        }
        if request != expected_request:
            raise ValueError(f"{query_id}: request contract does not match programme control")
        pages = capture.get("pages")
        if not isinstance(pages, list) or not pages or not all(
            isinstance(page, dict) for page in pages
        ):
            raise ValueError(f"{query_id}: pages must be a non-empty object array")

    if scope == "FULL_PROGRAMME" and seen != set(configured):
        raise ValueError(
            "FULL_PROGRAMME replay requires all active query streams; "
            f"missing={sorted(set(configured) - seen)}"
        )
    return str(scope), captures


def _mechanical_query_blockers(
    coverage: Mapping[str, Any], programme: Mapping[str, Any]
) -> list[str]:
    blockers: list[str] = []
    required_metrics = set(programme["coverage_contract"]["required_metrics_per_query"])
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
    projector: Projector | None = None,
    known_index: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    programme = _programme()
    scope, captures = _validate_bundle(bundle, programme)
    projector = projector or _load_workbench_capability()
    known = dict(known_index) if known_index is not None else build_known_publication_source_index()
    known_map = known.get("identity_to_source")
    if not isinstance(known_map, dict):
        raise ValueError("Known publication index missing identity_to_source")

    anchor_aliases = _anchor_aliases(programme)
    all_anchor_aliases = sorted(set().union(*anchor_aliases.values()))
    configured = {
        row["query_id"]: row
        for row in programme["query_streams"]
        if row.get("status") == "ACTIVE"
    }

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
            query_id=query_id,
            query_text=config["query_term"],
            pages=pages,
            known_publication_sources=known_map,
            known_anchor_identities=all_anchor_aliases,
        )
        coverage = projection.get("coverage")
        records = projection.get("result_records")
        normalized = projection.get("normalized_records")
        if not isinstance(coverage, dict) or not isinstance(records, list) or not isinstance(normalized, list):
            raise ValueError(f"{query_id}: Workbench projector returned invalid shape")

        normalized_by_identity: dict[str, dict[str, Any]] = {}
        for row in normalized:
            if not isinstance(row, dict):
                raise ValueError(f"{query_id}: normalized publication must be object")
            identity = row.get("resolved_identity")
            if not isinstance(identity, str) or not identity:
                raise ValueError(f"{query_id}: normalized publication missing resolved_identity")
            if identity in normalized_by_identity:
                raise ValueError(f"{query_id}: duplicate normalized identity {identity}")
            digest = row.get("normalized_record_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"{query_id}/{identity}: normalized_record_sha256 missing/invalid")
            normalized_by_identity[identity] = row

        blockers = _mechanical_query_blockers(coverage, programme)
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
            identity = record.get("record_key")
            if not isinstance(identity, str) or identity not in normalized_by_identity:
                raise ValueError(f"{query_id}: candidate record has no matching normalized publication")
            normalized_row = normalized_by_identity[identity]
            content_digest = normalized_row["normalized_record_sha256"]
            candidate_core = {
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
                    "normalized_publication": normalized_row,
                    "normalized_record_sha256": content_digest,
                    "candidate_input": candidate_core,
                    "query_ids": {query_id},
                }
                continue
            if prior["normalized_record_sha256"] != content_digest:
                raise ValueError(f"Cross-query normalized-content conflict for {identity}")
            if prior["candidate_input"] != candidate_core:
                raise ValueError(f"Cross-query candidate-classification conflict for {identity}")
            prior["query_ids"].add(query_id)

    active_ids = set(configured)
    executed_ids = {str(row["query_id"]) for row in captures}
    all_active_executed = executed_ids == active_ids

    normalized_publications: list[dict[str, Any]] = []
    known_duplicates: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    cross_query_repeat_count = 0
    union_identities = set(union)

    for identity in sorted(union):
        row = union[identity]
        query_ids = sorted(row["query_ids"])
        cross_query_repeat_count += max(0, len(query_ids) - 1)
        normalized_row = dict(row["normalized_publication"])
        normalized_row["query_memberships"] = query_ids
        normalized_publications.append(normalized_row)
        classified = {
            **row["candidate_input"],
            "query_ids": query_ids,
            "normalized_record_sha256": row["normalized_record_sha256"],
        }
        if classified["classification_hint"] == "DUPLICATE":
            known_duplicates.append(classified)
        elif classified["classification_hint"] == "NEW":
            new_candidates.append(classified)
        else:
            raise ValueError(
                f"Unexpected union discovery classification for {identity}: "
                f"{classified['classification_hint']!r}"
            )

    recovered_anchor_ids: list[str] = []
    missing_anchor_ids: list[str] = []
    for anchor_id, aliases in sorted(anchor_aliases.items()):
        if aliases & union_identities:
            recovered_anchor_ids.append(anchor_id)
        else:
            missing_anchor_ids.append(anchor_id)

    mechanically_complete = (
        scope == "FULL_PROGRAMME"
        and all_active_executed
        and query_blocker_count == 0
    )
    reconciliation = {
        "scope": scope,
        "configured_active_query_count": len(active_ids),
        "executed_query_count": len(executed_ids),
        "all_active_queries_executed": all_active_executed,
        "query_mechanical_blocker_count": query_blocker_count,
        "union_unique_publication_identity_count": len(union),
        "known_bibliographic_duplicate_count": len(known_duplicates),
        "new_candidate_input_count": len(new_candidates),
        "cross_query_repeat_membership_count": cross_query_repeat_count,
        "materialized_source_namespace_count": known.get("materialized_source_count"),
        "eligible_bibliographic_source_count": known.get("eligible_bibliographic_source_count"),
        "known_publication_identity_count_before_run": known.get("known_publication_identity_count"),
        "configured_anchor_count": len(anchor_aliases),
        "recovered_anchor_count": len(recovered_anchor_ids),
        "recovered_anchor_ids": recovered_anchor_ids,
        "missing_anchor_ids": missing_anchor_ids,
        "anchor_recall_claim": False,
        "raw_input_page_count": raw_page_count,
        "raw_api_page_payloads_emitted": False,
        "full_text_emitted": False,
        "participant_level_data_emitted": False,
        "automatic_source_admission": False,
        "automatic_relationship_creation": False,
        "automatic_monitor_creation": False,
        "automatic_assessment_mutation": False,
        "human_relevance_adjudication_performed": False,
        "mechanically_complete": mechanically_complete,
        "publication_database_completeness_claim": False,
        "query_recall_claim": False,
        "global_neuroai_publication_recall_claim": False,
        "canonical_successor_ready": False,
        "authority_boundary": (
            "Mechanical completion applies only to the exact configured Europe PMC query "
            "traversals and controlled bibliographic-source namespace. It does not establish "
            "Europe PMC completeness, NeuroAI publication recall, publication relevance, "
            "evidence quality, scientific truth, Source admission, relationship validity, "
            "assessment effect, or canonical publication authority."
        ),
    }
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_SU_PUBLICATIONS_EUROPEPMC_RECORDED_REPLAY_PROJECTION",
        "programme_id": programme["programme_id"],
        "input_provenance": {
            "bundle_sha256": _digest(bundle),
            "captured_at": bundle["captured_at"],
            "capture_scope": scope,
            "api_data_timestamp": bundle.get("api_data_timestamp"),
            "raw_pages_retained_in_output": False,
            "full_text_retained_in_output": False,
            "known_publication_index_sha256": _digest(known_map),
        },
        "known_source_index_summary": {
            "materialized_source_count": known.get("materialized_source_count"),
            "eligible_bibliographic_source_count": known.get("eligible_bibliographic_source_count"),
            "known_publication_identity_count": known.get("known_publication_identity_count"),
            "source_admission_completeness_claim": False,
            "publication_universe_completeness_claim": False,
        },
        "query_reports": query_reports,
        "normalized_publications": normalized_publications,
        "known_bibliographic_duplicates": known_duplicates,
        "new_candidate_inputs": new_candidates,
        "reconciliation": reconciliation,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload = b"".join(_canonical_bytes(row) for row in rows)
    path.write_bytes(payload)
    return {
        "path": path.name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "records": len(rows),
    }


def write_projection(result: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for key, filename in (
        ("normalized_publications", "normalized-publications.jsonl"),
        ("known_bibliographic_duplicates", "known-bibliographic-duplicates.jsonl"),
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
        "raw_api_page_payloads_emitted": False,
        "full_text_emitted": False,
        "canonical_successor_ready": False,
    }
    manifest_payload = _canonical_bytes(manifest)
    (output_dir / "manifest.json").write_bytes(manifest_payload)
    return {
        **manifest,
        "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    bundle = _load(args.input_bundle.resolve())
    result = build_replay(bundle)
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
