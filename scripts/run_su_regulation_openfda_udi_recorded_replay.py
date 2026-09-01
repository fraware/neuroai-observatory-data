#!/usr/bin/env python3
"""Deterministic recorded replay for bounded openFDA UDI/GUDID discovery."""

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
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from current_source_namespace import materialize_effective_source_namespace

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation/openfda_udi_discovery_programme_v0.1.json"
EXACT_UDI_RE = re.compile(r"UDI:([A-Za-z0-9._-]+):([A-Za-z0-9._-]+)", re.I)
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
    programme = _load(PROGRAMME)
    if programme.get("programme_id") != "SU-REGULATION-OPENFDA-UDI-v0.1":
        raise ValueError("Invalid UDI programme")
    if (programme.get("workbench_dependency") or {}).get("integration_state") != "AVAILABLE":
        raise ValueError("UDI programme requires AVAILABLE Workbench capability")
    return programme


def _load_projector() -> Projector:
    try:
        from neuroai_workbench.discovery import project_openfda_udi_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench capability project_openfda_udi_pages unavailable"
        ) from exc
    return project_openfda_udi_pages


def _eligible(source: Mapping[str, Any]) -> bool:
    source_class = str(source.get("source_class") or "").upper()
    locator = str(source.get("canonical_locator") or "").upper()
    return (
        "DEVICE" in source_class
        or "REGULATORY" in source_class
        or "UDI" in source_class
        or "GUDID" in locator
    )


def _exact_udi_from_locator(locator: str) -> set[str]:
    return {
        f"UDI:{match.group(1).upper()}:{match.group(2)}"
        for match in EXACT_UDI_RE.finditer(unquote(locator))
    }


def build_known_udi_source_index() -> dict[str, Any]:
    namespace = materialize_effective_source_namespace()
    sources = namespace.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Controlled Source namespace is missing sources")
    if namespace.get("materialized_source_count") != 248 or len(sources) != 248:
        raise ValueError("Expected exact 248-Source controlled namespace")

    all_ids: set[str] = set()
    eligible_ids: set[str] = set()
    identity_to_source: dict[str, str] = {}

    for source in sources:
        if not isinstance(source, Mapping):
            raise ValueError("Controlled Source namespace row must be an object")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("Controlled Source row missing source_id")
        if source_id in all_ids:
            raise ValueError(f"Duplicate controlled Source identity {source_id}")
        all_ids.add(source_id)

        if not _eligible(source):
            continue
        eligible_ids.add(source_id)
        locator = source.get("canonical_locator")
        if not isinstance(locator, str):
            continue
        for identity in _exact_udi_from_locator(locator):
            normalized_identity = identity.upper()
            prior = identity_to_source.get(normalized_identity)
            if prior and prior != source_id:
                raise ValueError(f"Conflicting controlled Sources for {identity}")
            identity_to_source[normalized_identity] = source_id

    source_id_set_sha256 = namespace.get("source_id_set_sha256")
    if not isinstance(source_id_set_sha256, str) or len(source_id_set_sha256) != 64:
        raise ValueError("Controlled Source namespace digest unavailable")

    return {
        "materialized_source_count": 248,
        "source_id_set_sha256": source_id_set_sha256,
        "udi_eligible_source_count": len(eligible_ids),
        "known_exact_udi_identity_count": len(identity_to_source),
        "udi_identity_to_source": dict(sorted(identity_to_source.items())),
        "global_udi_completeness_claim": False,
    }


def _active(programme: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["query_id"]: dict(row)
        for row in programme["query_streams"]
        if row.get("status") == "ACTIVE"
    }


def _validate_bundle(
    bundle: Mapping[str, Any], programme: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if (
        bundle.get("schema_version") != "0.1.0"
        or bundle.get("programme_id") != programme["programme_id"]
        or bundle.get("provider") != programme["provider_contract"]["provider"]
    ):
        raise ValueError("Replay identity mismatch")

    scope = bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME", "PARTIAL_VALIDATION"}:
        raise ValueError("Invalid capture_scope")

    captures = bundle.get("leaf_query_captures")
    configured = _active(programme)
    if not isinstance(captures, list) or not captures:
        raise ValueError("leaf_query_captures required")

    seen: set[str] = set()
    for capture in captures:
        if not isinstance(capture, dict):
            raise ValueError("leaf query capture must be an object")
        query_id = capture.get("query_id")
        leaf_id = capture.get("leaf_query_id")
        if (
            query_id not in configured
            or not isinstance(leaf_id, str)
            or not leaf_id
            or leaf_id in seen
        ):
            raise ValueError("Invalid or duplicate UDI leaf")
        seen.add(leaf_id)

        root_search = configured[query_id]["search"]
        effective_search = capture.get("effective_search")
        partition_path = capture.get("partition_path")
        if not isinstance(partition_path, list) or not isinstance(effective_search, str):
            raise ValueError(f"{leaf_id}: invalid search/partition")
        if not partition_path and effective_search != root_search:
            raise ValueError(f"{leaf_id}: unpartitioned search must equal programme control")
        if partition_path:
            if (
                len(partition_path) != 1
                or partition_path[0].get("dimension") != "PUBLIC_VERSION_DATE"
            ):
                raise ValueError(
                    f"{leaf_id}: only PUBLIC_VERSION_DATE partition supported"
                )
            lower = partition_path[0].get("lower_bound")
            upper = partition_path[0].get("upper_bound")
            expected = (
                f"({root_search})+AND+public_version_date:[{lower}+TO+{upper}]"
            )
            if effective_search != expected:
                raise ValueError(
                    f"{leaf_id}: partitioned search must exactly bind public-version-date interval"
                )

        pages = capture.get("pages")
        if (
            not isinstance(pages, list)
            or not pages
            or not all(isinstance(page, dict) for page in pages)
        ):
            raise ValueError(f"{leaf_id}: pages required")

    return str(scope), captures, configured


def _leaf_blockers(
    coverage: Mapping[str, Any], programme: Mapping[str, Any]
) -> list[str]:
    blockers: list[str] = []
    missing = set(programme["coverage_contract"]["required_metrics_per_leaf_query"]) - set(
        coverage
    )
    if missing:
        blockers.append("MISSING_METRICS:" + ",".join(sorted(missing)))
    for key, expected in programme["coverage_contract"][
        "mechanical_completion_requires"
    ].items():
        if coverage.get(key) != expected:
            blockers.append(f"GATE:{key}:{coverage.get(key)!r}!={expected!r}")
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
    known = dict(known_index) if known_index is not None else build_known_udi_source_index()
    known_map = known["udi_identity_to_source"]

    reports: list[dict[str, Any]] = []
    union: dict[str, dict[str, Any]] = {}
    blocker_count = 0
    represented = {capture["query_id"] for capture in captures}
    partitioned = sum(bool(capture["partition_path"]) for capture in captures)
    unresolved_total = 0
    multiple_total = 0

    for capture in sorted(captures, key=lambda row: row["leaf_query_id"]):
        projection = projector(
            query_id=capture["query_id"],
            search=capture["effective_search"],
            pages=capture["pages"],
            known_udi_sources=known_map,
        )
        coverage = projection.get("coverage")
        records = projection.get("result_records")
        normalized_records = projection.get("normalized_records")
        if (
            not isinstance(coverage, dict)
            or not isinstance(records, list)
            or not isinstance(normalized_records, list)
        ):
            raise ValueError("Invalid Workbench UDI projection shape")

        blockers = _leaf_blockers(coverage, programme)
        blocker_count += len(blockers)
        unresolved_total += int(coverage.get("unresolved_primary_di_count") or 0)
        multiple_total += int(coverage.get("multiple_primary_di_count") or 0)
        reports.append(
            {
                "query_id": capture["query_id"],
                "leaf_query_id": capture["leaf_query_id"],
                "partition_path": capture["partition_path"],
                "effective_search": capture["effective_search"],
                "capture_sha256": _digest(capture),
                "coverage": coverage,
                "mechanical_blockers": blockers,
            }
        )

        normalized_by_identity = {
            row.get("record_identity"): row
            for row in normalized_records
            if isinstance(row, dict)
        }
        if len(normalized_by_identity) != len(normalized_records):
            raise ValueError("Missing/duplicate normalized UDI identity")

        for record in records:
            identity = record.get("record_key")
            if identity not in normalized_by_identity:
                raise ValueError("UDI candidate lacks normalized record")
            normalized = normalized_by_identity[identity]
            digest = normalized.get("normalized_record_sha256")
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
            if prior:
                if (
                    prior["normalized_record_sha256"] != digest
                    or prior["candidate"] != candidate
                ):
                    raise ValueError(f"Cross-query conflict for UDI identity {identity}")
                prior["query_memberships"].add(capture["query_id"])
            else:
                union[identity] = {
                    "normalized": normalized,
                    "normalized_record_sha256": digest,
                    "candidate": candidate,
                    "query_memberships": {capture["query_id"]},
                }

    normalized_output: list[dict[str, Any]] = []
    known_duplicates: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    for identity in sorted(union):
        row = union[identity]
        normalized = dict(row["normalized"])
        normalized["query_memberships"] = sorted(row["query_memberships"])
        normalized_output.append(normalized)

        candidate = dict(row["candidate"])
        candidate["query_memberships"] = sorted(row["query_memberships"])
        if candidate.get("classification_hint") == "DUPLICATE":
            known_duplicates.append(candidate)
        else:
            new_candidates.append(candidate)

    all_queries = set(configured) == represented
    mechanically_complete = (
        scope == "FULL_PROGRAMME"
        and all_queries
        and partitioned == 0
        and blocker_count == 0
    )

    reconciliation = {
        "capture_scope": scope,
        "materialized_source_namespace_count": known["materialized_source_count"],
        "controlled_source_id_set_sha256": known.get("source_id_set_sha256"),
        "known_exact_udi_identity_count": known["known_exact_udi_identity_count"],
        "configured_active_query_count": len(configured),
        "represented_query_count": len(represented),
        "all_logical_queries_represented": all_queries,
        "partitioned_leaf_count": partitioned,
        "partition_reconciliation_required": partitioned > 0,
        "leaf_mechanical_blocker_count": blocker_count,
        "union_unique_udi_identity_count": len(union),
        "unresolved_primary_di_count": unresolved_total,
        "multiple_primary_di_count": multiple_total,
        "known_controlled_duplicate_count": len(known_duplicates),
        "new_candidate_input_count": len(new_candidates),
        "mechanically_complete": mechanically_complete,
        "automatic_di_relationship_creation": False,
        "automatic_premarket_authorization_relationship_creation": False,
        "automatic_current_commercial_availability_claim_creation": False,
        "automatic_marketing_authorization_claim_creation": False,
        "automatic_effectiveness_claim_creation": False,
        "automatic_system_conformance_claim_creation": False,
        "automatic_reopening_decision": False,
        "automatic_assessment_mutation": False,
        "canonical_successor_ready": False,
        "global_neuroai_udi_coverage_claim": False,
    }

    return {
        "normalized_records": normalized_output,
        "known_duplicates": known_duplicates,
        "new_candidates": new_candidates,
        "query_reports": reports,
        "known_source_index_summary": {
            key: value for key, value in known.items() if key != "udi_identity_to_source"
        },
        "reconciliation": reconciliation,
        "input_provenance": {
            "programme_id": programme["programme_id"],
            "provider": programme["provider_contract"]["provider"],
            "captured_at": bundle.get("captured_at"),
            "input_sha256": _digest(bundle),
        },
    }


def write_projection(result: Mapping[str, Any], output: Path) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "normalized-udi-records.jsonl": b"".join(
            _canon(row) for row in result["normalized_records"]
        ),
        "known-udi-duplicates.jsonl": b"".join(
            _canon(row) for row in result["known_duplicates"]
        ),
        "new-udi-candidate-inputs.jsonl": b"".join(
            _canon(row) for row in result["new_candidates"]
        ),
        "query-reports.json": _canon(result["query_reports"]),
        "reconciliation.json": _canon(result["reconciliation"]),
        "known-source-index-summary.json": _canon(result["known_source_index_summary"]),
        "input-provenance.json": _canon(result["input_provenance"]),
    }
    manifest_files: dict[str, str] = {}
    for name, data in files.items():
        (output / name).write_bytes(data)
        manifest_files[name] = hashlib.sha256(data).hexdigest()

    manifest_bytes = _canon(
        {
            "files": dict(sorted(manifest_files.items())),
            "raw_openfda_pages_emitted": False,
            "customer_contacts_emitted": False,
            "labeler_duns_emitted": False,
            "canonical_successor_ready": False,
        }
    )
    (output / "manifest.json").write_bytes(manifest_bytes)
    manifest_files["manifest.json"] = hashlib.sha256(manifest_bytes).hexdigest()
    return manifest_files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_projection(build_replay(_load(args.input)), args.output)


if __name__ == "__main__":
    main()
