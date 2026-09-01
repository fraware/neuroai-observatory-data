#!/usr/bin/env python3
"""Materialize the effective controlled public Source namespace from governing records.

This helper is deliberately narrower than the historical Observatory-v2 migration
projectors. It reads the three governing predecessor source families directly and
returns only the identity/locator metadata needed by discovery and recorded replay.
It performs no network I/O, migration, Source admission, graph mutation, assessment
mutation, or publication operation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
GOVERNING_RECORDS = ROOT / "releases" / "data-v0.1.0-public-governing" / "records"
V14_PATH = GOVERNING_RECORDS / "canonical_observatory_release_v1.4.json"
V16_PATH = GOVERNING_RECORDS / "canonical_live_refresh_release_v1.6.json"
V17_PRIMA_PATH = ROOT / "supplemental_records" / "PRIMA_NEW_UNIQUE_SOURCE_REGISTER_v1.7.json"

EXPECTED_FAMILY_COUNTS = {
    "V1_4_BASELINE": 224,
    "V1_6_REFRESH": 12,
    "V1_7_PRIMA_SUPPLEMENTAL": 12,
}
EXPECTED_TOTAL = sum(EXPECTED_FAMILY_COUNTS.values())
EXPECTED_PRIMA_IDS = (
    "SRC-PR-001",
    "SRC-PR-002",
    "SRC-PR-005",
    "SRC-PR-006",
    "SRC-PR-007",
    "SRC-PR-008",
    "SRC-PR-009",
    "SRC-PR-010",
    "SRC-PR-012",
    "SRC-PR-013",
    "SRC-PR-014",
    "SRC-PR-015",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _required_text(row: dict[str, Any], key: str, *, family: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{family}: source row missing non-empty {key!r}")
    return value.strip()


def _normalize_row(
    row: dict[str, Any],
    *,
    family: str,
    predecessor_file: str,
) -> dict[str, Any]:
    source_id = _required_text(row, "source_id", family=family)
    title = _required_text(row, "title", family=family)
    publisher = _required_text(row, "publisher", family=family)
    locator = _required_text(row, "url", family=family)
    source_class = _required_text(row, "source_class", family=family)
    claim_boundary = row.get("claim_boundary")
    if claim_boundary is not None and not isinstance(claim_boundary, str):
        raise ValueError(f"{family}/{source_id}: claim_boundary must be string/null")
    return {
        "source_id": source_id,
        "title": title,
        "publisher": publisher,
        "canonical_locator": locator,
        "source_class": source_class,
        "claim_boundary": claim_boundary,
        "lineage_family": family,
        "predecessor_file": predecessor_file,
    }


def materialize_effective_source_namespace(root: Path | None = None) -> dict[str, Any]:
    """Return the exact current 248-Source controlled identity namespace.

    The denominator is the programme's effective controlled predecessor namespace,
    not a claim of global NeuroAI source completeness.
    """
    repo_root = root or ROOT
    governing = repo_root / "releases" / "data-v0.1.0-public-governing" / "records"
    v14_path = governing / "canonical_observatory_release_v1.4.json"
    v16_path = governing / "canonical_live_refresh_release_v1.6.json"
    prima_path = repo_root / "supplemental_records" / "PRIMA_NEW_UNIQUE_SOURCE_REGISTER_v1.7.json"

    v14 = _load(v14_path)
    v16 = _load(v16_path)
    prima = _load(prima_path)

    if not isinstance(v14, dict) or not isinstance(v14.get("sources"), list):
        raise ValueError("v1.4 governing release must contain a sources array")
    if not isinstance(v16, dict) or not isinstance(v16.get("new_sources"), list):
        raise ValueError("v1.6 governing release must contain a new_sources array")
    if not isinstance(prima, list):
        raise ValueError("v1.7 PRIMA supplemental register must be an array")

    families: tuple[tuple[str, str, list[Any]], ...] = (
        ("V1_4_BASELINE", v14_path.name, v14["sources"]),
        ("V1_6_REFRESH", v16_path.name, v16["new_sources"]),
        ("V1_7_PRIMA_SUPPLEMENTAL", prima_path.name, prima),
    )

    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    family_counts: dict[str, int] = {}

    for family, predecessor_file, rows in families:
        expected_count = EXPECTED_FAMILY_COUNTS[family]
        if len(rows) != expected_count:
            raise ValueError(
                f"{family}: expected {expected_count} governing source rows, found {len(rows)}"
            )
        family_counts[family] = len(rows)
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError(f"{family}: every governing source row must be an object")
            source = _normalize_row(raw, family=family, predecessor_file=predecessor_file)
            source_id = source["source_id"]
            if source_id in seen:
                raise ValueError(f"Duplicate Source identity across governing families: {source_id}")
            seen.add(source_id)
            sources.append(source)

    prima_ids = tuple(
        source["source_id"]
        for source in sources
        if source["lineage_family"] == "V1_7_PRIMA_SUPPLEMENTAL"
    )
    if prima_ids != EXPECTED_PRIMA_IDS:
        raise ValueError(f"Unexpected PRIMA supplemental Source identities/order: {prima_ids}")

    if len(sources) != EXPECTED_TOTAL or len(seen) != EXPECTED_TOTAL:
        raise ValueError(
            f"Effective controlled Source namespace must contain {EXPECTED_TOTAL} unique identities"
        )

    ordered = sorted(sources, key=lambda row: row["source_id"])
    source_ids = [row["source_id"] for row in ordered]
    source_id_set_sha256 = _digest(source_ids)

    return {
        "schema_version": "0.1.0",
        "status": "GOVERNING_PREDECESSOR_SOURCE_NAMESPACE_VIEW",
        "materialized_source_count": len(ordered),
        "family_counts": family_counts,
        "source_id_set_sha256": source_id_set_sha256,
        "sources": ordered,
        "global_completeness_claim": False,
        "network_execution_performed": False,
        "migration_performed": False,
        "canonical_mutation_performed": False,
        "publication_authority_created": False,
        "boundary": (
            "This view reconstructs the effective controlled public Source identity namespace "
            "from exact governing predecessor records. The 248-record denominator is not a "
            "claim of global NeuroAI source completeness, source truth, currentness, or relevance."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(materialize_effective_source_namespace(), indent=2, sort_keys=True))
