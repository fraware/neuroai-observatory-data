#!/usr/bin/env python3
"""Deterministic recorded replay for bounded openFDA device-classification discovery."""
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
except ModuleNotFoundError:
    from current_source_namespace import materialize_effective_source_namespace

ROOT = Path(__file__).parents[1]
PROGRAMME = ROOT / "curation/openfda_device_classification_discovery_programme_v0.1.json"
EXPLICIT_PRODUCT_CODE_RE = re.compile(
    r'(?:FDA-CLASS:|product_code\s*[:=]\s*["\']?)([A-Za-z]{3})(?![A-Za-z])',
    re.IGNORECASE,
)
Projector = Callable[..., dict[str, Any]]


def _canon(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _programme() -> dict[str, Any]:
    programme = _load(PROGRAMME)
    if programme.get("programme_id") != "SU-REGULATION-OPENFDA-DEVICE-CLASSIFICATION-v0.1":
        raise ValueError("Invalid device-classification programme")
    if (programme.get("workbench_dependency") or {}).get("integration_state") != "AVAILABLE":
        raise ValueError("Device-classification programme requires AVAILABLE Workbench capability")
    return programme


def _load_projector() -> Projector:
    try:
        from neuroai_workbench.discovery import project_openfda_device_classification_pages
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Required Workbench capability project_openfda_device_classification_pages unavailable"
        ) from exc
    return project_openfda_device_classification_pages


def _eligible(source: Mapping[str, Any]) -> bool:
    source_class = str(source.get("source_class") or "").upper()
    locator = str(source.get("canonical_locator") or "").upper()
    return (
        "CLASSIFICATION" in source_class
        or "/DEVICE/CLASSIFICATION" in locator
        or "PRODUCT_CODE" in locator
        or "FDA-CLASS:" in locator
    )


def _exact_product_codes_from_locator(locator: str) -> set[str]:
    decoded = unquote(locator)
    return {match.group(1).upper() for match in EXPLICIT_PRODUCT_CODE_RE.finditer(decoded)}


def build_known_product_code_source_index() -> dict[str, Any]:
    namespace = materialize_effective_source_namespace()
    sources = namespace.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Controlled Source namespace is missing sources")
    if namespace.get("materialized_source_count") != 248 or len(sources) != 248:
        raise ValueError("Expected exact 248-Source controlled namespace")

    all_ids: set[str] = set()
    eligible_ids: set[str] = set()
    product_code_to_source: dict[str, str] = {}

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
        for product_code in _exact_product_codes_from_locator(locator):
            prior = product_code_to_source.get(product_code)
            if prior and prior != source_id:
                raise ValueError(
                    f"Conflicting controlled Sources for FDA product code {product_code}"
                )
            product_code_to_source[product_code] = source_id

    digest = namespace.get("source_id_set_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Controlled Source namespace digest unavailable")

    return {
        "materialized_source_count": 248,
        "source_id_set_sha256": digest,
        "classification_eligible_source_count": len(eligible_ids),
        "known_exact_product_code_count": len(product_code_to_source),
        "product_code_to_source": dict(sorted(product_code_to_source.items())),
        "global_classification_completeness_claim": False,
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
            raise ValueError("Invalid or duplicate device-classification leaf")
        seen.add(leaf_id)
        if capture.get("partition_path") != []:
            raise ValueError(
                f"{leaf_id}: v0.1 device-classification replay does not authorize partitioned traversals"
            )
        if capture.get("effective_search") != configured[query_id]["search"]:
            raise ValueError(f"{leaf_id}: search must exactly equal programme control")
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
    required = set(programme["coverage_contract"]["required_metrics_per_leaf_query"])
    missing = required - set(coverage)
    if missing:
        blockers.append("MISSING_METRICS:" + ",".join(sorted(missing)))
    for key, expected in programme["coverage_contract"]["mechanical_completion_requires"].items():
        if coverage.get(key) != expected:
            blockers.append(f"GATE:{key}:{coverage.get(key)!r}!={expected!r}")
    if coverage.get("product_code_is_exact_device_identity_claim") is not False:
        blockers.append("DEVICE_IDENTITY_BOUNDARY_LOST")
    if coverage.get("classification_record_is_marketing_authorization_claim") is not False:
        blockers.append("MARKETING_AUTHORIZATION_BOUNDARY_LOST")
    if coverage.get("classification_record_is_clearance_or_approval_claim") is not False:
        blockers.append("CLEARANCE_APPROVAL_BOUNDARY_LOST")
    if coverage.get("device_class_is_system_conformance_claim") is not False:
        blockers.append("SYSTEM_CONFORMANCE_BOUNDARY_LOST")
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
    known = dict(known_index) if known_index is not None else build_known_product_code_source_index()
    known_map = known["product_code_to_source"]

    reports: list[dict[str, Any]] = []
    union: dict[str, dict[str, Any]] = {}
    blocker_count = 0
    represented = {capture["query_id"] for capture in captures}
    unresolved_product_code_count = 0
    regulation_referenced_count = 0
    proposed_not_final_count = 0

    for capture in sorted(captures, key=lambda row: row["leaf_query_id"]):
        projection = projector(
            query_id=capture["query_id"],
            search=capture["effective_search"],
            pages=capture["pages"],
            known_product_code_sources=known_map,
        )
        coverage = projection.get("coverage")
        records = projection.get("result_records")
        normalized_records = projection.get("normalized_records")
        if (
            not isinstance(coverage, dict)
            or not isinstance(records, list)
            or not isinstance(normalized_records, list)
        ):
            raise ValueError("Invalid Workbench device-classification projection shape")

        blockers = _leaf_blockers(coverage, programme)
        blocker_count += len(blockers)
        unresolved_product_code_count += int(coverage.get("unresolved_product_code_count") or 0)
        regulation_referenced_count += int(
            coverage.get("regulation_referenced_classification_count") or 0
        )
        proposed_not_final_count += int(
            coverage.get("proposed_not_final_classification_count") or 0
        )
        reports.append(
            {
                "query_id": capture["query_id"],
                "leaf_query_id": capture["leaf_query_id"],
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
            raise ValueError("Missing/duplicate normalized device-classification identity")

        for record in records:
            identity = record.get("record_key")
            if identity not in normalized_by_identity:
                raise ValueError("Classification candidate lacks normalized product-code record")
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
                    raise ValueError(
                        f"Cross-query conflict for device-classification product code {identity}"
                    )
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
        scope == "FULL_PROGRAMME" and all_queries and blocker_count == 0
    )

    reconciliation = {
        "capture_scope": scope,
        "materialized_source_namespace_count": known["materialized_source_count"],
        "controlled_source_id_set_sha256": known.get("source_id_set_sha256"),
        "known_exact_product_code_count": known["known_exact_product_code_count"],
        "configured_active_query_count": len(configured),
        "represented_query_count": len(represented),
        "all_logical_queries_represented": all_queries,
        "partition_strategy_authorized": False,
        "leaf_mechanical_blocker_count": blocker_count,
        "union_unique_product_code_count": len(union),
        "unresolved_product_code_count": unresolved_product_code_count,
        "regulation_referenced_classification_count": regulation_referenced_count,
        "proposed_not_final_classification_count": proposed_not_final_count,
        "known_controlled_duplicate_count": len(known_duplicates),
        "new_candidate_input_count": len(new_candidates),
        "mechanically_complete": mechanically_complete,
        "product_code_is_exact_device_identity_claim": False,
        "classification_record_is_marketing_authorization_claim": False,
        "classification_record_is_clearance_or_approval_claim": False,
        "device_class_is_system_conformance_claim": False,
        "automatic_product_code_relationship_creation": False,
        "automatic_regulation_relationship_creation": False,
        "automatic_marketing_authorization_claim_creation": False,
        "automatic_clearance_or_approval_claim_creation": False,
        "automatic_exact_device_identity_claim_creation": False,
        "automatic_system_conformance_claim_creation": False,
        "automatic_reopening_decision": False,
        "automatic_assessment_mutation": False,
        "canonical_successor_ready": False,
        "global_neuroai_classification_coverage_claim": False,
    }

    return {
        "normalized_records": normalized_output,
        "known_duplicates": known_duplicates,
        "new_candidates": new_candidates,
        "query_reports": reports,
        "known_source_index_summary": {
            key: value for key, value in known.items() if key != "product_code_to_source"
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
        "normalized-device-classifications.jsonl": b"".join(
            _canon(row) for row in result["normalized_records"]
        ),
        "known-device-classification-duplicates.jsonl": b"".join(
            _canon(row) for row in result["known_duplicates"]
        ),
        "new-device-classification-candidate-inputs.jsonl": b"".join(
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

    manifest = {
        "files": dict(sorted(manifest_files.items())),
        "raw_openfda_pages_emitted": False,
        "openfda_harmonized_identity_fields_emitted": False,
        "exact_device_identity_claim_created": False,
        "authorization_claim_created": False,
        "canonical_successor_ready": False,
    }
    manifest_bytes = _canon(manifest)
    (output / "manifest.json").write_bytes(manifest_bytes)
    manifest_files["manifest.json"] = hashlib.sha256(manifest_bytes).hexdigest()
    return dict(sorted(manifest_files.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    bundle = _load(args.bundle)
    if not isinstance(bundle, dict):
        raise ValueError("Replay input must be an object")
    result = build_replay(bundle)
    write_projection(result, args.output)


if __name__ == "__main__":
    main()
