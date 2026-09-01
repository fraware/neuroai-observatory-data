"""Audit a NeuroAI source-monitor registry without making network or truth claims."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

DEFAULT_REGISTRY = Path(
    "releases/data-v0.1.0-public-governing/records/source_monitor_registry_v1.5.json"
)


def _locator_kind(locator: str) -> str:
    token = locator.strip()
    if token.startswith(("https://", "http://")):
        return "EXTERNAL_HTTP"
    if token.startswith("/mnt/data/"):
        return "CONTROLLED_LOCAL_INPUT"
    return "OTHER"


def _normalized_http_locator(locator: str) -> str:
    parts = urlsplit(locator.strip())
    host = (parts.hostname or "").lower()
    port = parts.port
    if port is not None and not (
        (parts.scheme.lower() == "https" and port == 443)
        or (parts.scheme.lower() == "http" and port == 80)
    ):
        host = f"{host}:{port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


def _duplicate_groups(rows: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = str(row.get(key_name) or "").strip()
        if value:
            grouped[value].append(row)
    return [
        {
            key_name: value,
            "record_count": len(items),
            "source_ids": sorted(str(item.get("source_id") or "") for item in items),
            "monitor_ids": sorted(str(item.get("monitor_id") or "") for item in items),
        }
        for value, items in sorted(grouped.items())
        if len(items) > 1
    ]


def audit_registry(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise TypeError("Registry root must be a JSON array")

    seen_monitor_ids: set[str] = set()
    seen_source_ids: set[str] = set()
    prepared: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []

    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise TypeError(f"Registry row {index} must be an object")
        row = dict(raw)
        monitor_id = str(row.get("monitor_id") or "").strip()
        source_id = str(row.get("source_id") or "").strip()
        locator = str(row.get("url") or "").strip()
        if not monitor_id or not source_id or not locator:
            raise ValueError(
                f"Registry row {index} requires monitor_id, source_id, and url"
            )
        if monitor_id in seen_monitor_ids:
            raise ValueError(f"Duplicate monitor_id {monitor_id!r}")
        if source_id in seen_source_ids:
            raise ValueError(f"Duplicate source_id {source_id!r}")
        seen_monitor_ids.add(monitor_id)
        seen_source_ids.add(source_id)

        kind = _locator_kind(locator)
        normalized = _normalized_http_locator(locator) if kind == "EXTERNAL_HTTP" else None
        prepared.append(
            {
                **row,
                "locator_kind": kind,
                "normalized_http_locator": normalized,
            }
        )

        if kind == "CONTROLLED_LOCAL_INPUT" and row.get("network_access_required") is True:
            anomalies.append(
                {
                    "code": "LOCAL_INPUT_MARKED_NETWORK_REQUIRED",
                    "source_id": source_id,
                    "monitor_id": monitor_id,
                    "url": locator,
                }
            )
        if kind == "OTHER":
            anomalies.append(
                {
                    "code": "UNCLASSIFIED_LOCATOR_KIND",
                    "source_id": source_id,
                    "monitor_id": monitor_id,
                    "url": locator,
                }
            )

    locator_kind_counts = Counter(str(row["locator_kind"]) for row in prepared)
    external_rows = [row for row in prepared if row["locator_kind"] == "EXTERNAL_HTTP"]
    local_rows = [
        row for row in prepared if row["locator_kind"] == "CONTROLLED_LOCAL_INPUT"
    ]

    exact_locator_duplicates = _duplicate_groups(prepared, "url")
    normalized_external_duplicates = _duplicate_groups(
        external_rows, "normalized_http_locator"
    )

    return {
        "metadata": {
            "title": "NeuroAI source-monitor registry structural audit",
            "audit_scope": "OFFLINE_STRUCTURAL_ONLY",
            "network_requests_performed": False,
            "retrieval_success_reverified": False,
            "source_truth_reverified": False,
            "canonical_mutation_performed": False,
        },
        "counts": {
            "registry_record_count": len(prepared),
            "unique_monitor_id_count": len(seen_monitor_ids),
            "unique_source_id_count": len(seen_source_ids),
            "external_http_record_count": len(external_rows),
            "controlled_local_input_record_count": len(local_rows),
            "other_locator_record_count": locator_kind_counts.get("OTHER", 0),
            "unique_exact_locator_count": len(
                {str(row["url"]).strip() for row in prepared}
            ),
            "unique_external_normalized_locator_count": len(
                {
                    str(row["normalized_http_locator"])
                    for row in external_rows
                    if row.get("normalized_http_locator")
                }
            ),
            "exact_duplicate_locator_group_count": len(exact_locator_duplicates),
            "normalized_external_duplicate_locator_group_count": len(
                normalized_external_duplicates
            ),
        },
        "distributions": {
            "locator_kind": dict(sorted(locator_kind_counts.items())),
            "source_class": dict(
                sorted(Counter(str(row.get("source_class") or "MISSING") for row in prepared).items())
            ),
            "cadence": dict(
                sorted(Counter(str(row.get("cadence") or "MISSING") for row in prepared).items())
            ),
            "baseline_evidence_state": dict(
                sorted(
                    Counter(
                        str(row.get("baseline_evidence_state") or "MISSING")
                        for row in prepared
                    ).items()
                )
            ),
            "baseline_verification_state": dict(
                sorted(
                    Counter(
                        str(row.get("baseline_verification_state") or "MISSING")
                        for row in prepared
                    ).items()
                )
            ),
            "last_successful_retrieval": dict(
                sorted(
                    Counter(
                        str(row.get("last_successful_retrieval") or "MISSING")
                        for row in prepared
                    ).items()
                )
            ),
        },
        "exact_duplicate_locators": exact_locator_duplicates,
        "normalized_external_duplicate_locators": normalized_external_duplicates,
        "controlled_local_inputs": [
            {
                "monitor_id": row["monitor_id"],
                "source_id": row["source_id"],
                "url": row["url"],
                "publisher": row.get("publisher"),
                "source_class": row.get("source_class"),
                "network_access_required": row.get("network_access_required"),
            }
            for row in local_rows
        ],
        "anomalies": sorted(
            anomalies,
            key=lambda item: (str(item.get("code")), str(item.get("source_id"))),
        ),
        "interpretation_boundary": (
            "This audit establishes only structural properties of the registry bytes. "
            "A last_successful_retrieval field is a recorded assertion until independently "
            "corroborated by capture provenance. Locator presence does not establish source "
            "availability, evidentiary validity, scientific truth, authorization, conformance, "
            "or completeness of the NeuroAI source universe."
        ),
    }


def load_registry(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("Registry root must be a JSON array")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = audit_registry(load_registry(args.registry))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
