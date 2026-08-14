#!/usr/bin/env python3
"""Probe pre-registered official routes and resolve source-level availability."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from neuroai_workbench.collector.config import CollectorConfig
from neuroai_workbench.collector.errors import CollectionFailureError
from neuroai_workbench.collector.http_client import HttpClient
from neuroai_workbench.collector.source_routes import RouteSpec, run_registered_route_failover
from neuroai_workbench.collector.transport import StdlibHttpTransport

_HTTP_STATUS_RE = re.compile(r"\bstatus\s+(\d{3})\b", re.IGNORECASE)
BOUNDARY = (
    "Live route probing evaluates operational availability through pre-registered official routes only. "
    "It does not establish source truth, assessment validity, clinical/regulatory status, governance approval, "
    "UNESCO endorsement, canonical release authority, or publication authority."
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _extract_nct_ids(payload: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(payload, dict):
        protocol = payload.get("protocolSection")
        if isinstance(protocol, dict):
            identification = protocol.get("identificationModule")
            if isinstance(identification, dict) and isinstance(identification.get("nctId"), str):
                ids.add(identification["nctId"].upper())
        studies = payload.get("studies")
        if isinstance(studies, list):
            for study in studies:
                ids.update(_extract_nct_ids(study))
    elif isinstance(payload, list):
        for item in payload:
            ids.update(_extract_nct_ids(item))
    return ids


def _check_body(body: bytes, check: dict[str, str]) -> bool:
    kind = check["kind"]
    expected = check["expected"]
    if kind == "JSON_NCT_ID":
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return expected.upper() in _extract_nct_ids(payload)
    if kind == "TEXT_CONTAINS":
        return expected.casefold() in body.decode("utf-8", errors="replace").casefold()
    raise ValueError(f"unsupported live route check kind {kind}")


def probe_policy(policy: dict[str, Any]) -> dict[str, Any]:
    sources = policy.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("route policy requires a non-empty sources array")

    config = CollectorConfig(
        collector_version="route-resilience-live-v0.1",
        configuration_hash="0" * 64,
        max_response_bytes=5 * 1024 * 1024,
        max_redirects=8,
        connect_timeout_seconds=10.0,
        read_timeout_seconds=20.0,
        total_timeout_seconds=30.0,
        max_attempts=1,
        requests_per_host_per_minute=20,
    )
    client = HttpClient(config=config, transport=StdlibHttpTransport())
    reports: list[dict[str, Any]] = []

    for raw_source in sources:
        if not isinstance(raw_source, dict):
            raise ValueError("route policy source must be an object")
        raw_routes = raw_source.get("retrieval_routes")
        if not isinstance(raw_routes, list):
            raise ValueError("route policy source requires retrieval_routes")
        route_config = {
            str(item["route_id"]): item
            for item in raw_routes
            if isinstance(item, dict) and isinstance(item.get("route_id"), str)
        }

        def probe(route: RouteSpec) -> dict[str, Any]:
            raw = route_config[route.route_id]
            accept = raw.get("accept")
            headers = {"Accept": str(accept)} if isinstance(accept, str) and accept.strip() else None
            try:
                response = client.fetch(route.url, conditional_headers=headers)
            except CollectionFailureError as exc:
                observation: dict[str, Any] = {
                    "outcome": "FAILURE",
                    "failure_class": exc.failure_class,
                }
                if exc.failure_class == "HTTP_ERROR":
                    match = _HTTP_STATUS_RE.search(exc.message)
                    if match:
                        observation["http_status"] = int(match.group(1))
                return observation

            final_host = (urlparse(response.url).hostname or "").lower()
            allowed_redirect_hosts = raw.get("allowed_redirect_hosts", [route.official_host])
            if not isinstance(allowed_redirect_hosts, list) or not all(
                isinstance(item, str) and item for item in allowed_redirect_hosts
            ):
                raise ValueError(f"{route.route_id}.allowed_redirect_hosts must be a string array")
            allowed = {str(item).lower() for item in allowed_redirect_hosts}
            if final_host not in allowed:
                return {
                    "outcome": "FAILURE",
                    "failure_class": "ROUTE_HOST_DRIFT",
                    "http_status": response.status,
                }

            observation = {
                "outcome": "SUCCESS",
                "http_status": response.status,
                "final_host": final_host,
                "redirect_hops": len(response.redirect_chain),
                "content_sha256": hashlib.sha256(response.body).hexdigest(),
            }
            if route.identity_check is not None:
                observation["identity_match"] = _check_body(response.body, route.identity_check)
            if route.corroboration_check is not None:
                observation["corroboration_match"] = _check_body(response.body, route.corroboration_check)
            return observation

        report = run_registered_route_failover(source_record=raw_source, probe=probe)
        reports.append(report)

    counts = {
        "AVAILABLE_PRIMARY": sum(1 for item in reports if item["availability_state"] == "AVAILABLE_PRIMARY"),
        "AVAILABLE_FALLBACK": sum(1 for item in reports if item["availability_state"] == "AVAILABLE_FALLBACK"),
        "UNRESOLVED": sum(1 for item in reports if item["availability_state"] == "UNRESOLVED"),
        "RETIRED": sum(1 for item in reports if item["availability_state"] == "RETIRED"),
        "PRIMARY_DEGRADED": sum(1 for item in reports if item["primary_route_state"] == "DEGRADED"),
        "EVIDENCE_SUBSTITUTABLE_FALLBACK": sum(
            1
            for item in reports
            if item["availability_state"] == "AVAILABLE_FALLBACK" and item["evidence_substitution_allowed"] is True
        ),
        "LIVENESS_ONLY_FALLBACK": sum(
            1
            for item in reports
            if item["availability_state"] == "AVAILABLE_FALLBACK" and item["evidence_substitution_allowed"] is False
        ),
    }
    semantic = {
        "schema_version": "1",
        "policy_sha256": sha256(policy),
        "source_count": len(reports),
        "source_availability_state": "HEALTHY" if counts["UNRESOLVED"] == 0 else "DEGRADED",
        "counts": counts,
        "source_reports": sorted(reports, key=lambda item: str(item["source_id"])),
        "boundary": BOUNDARY,
    }
    result = dict(semantic)
    result["report_sha256"] = sha256(semantic)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError("route policy must be a JSON object")
    report = probe_policy(policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "SANITIZED_ROUTE_RESILIENCE="
        + json.dumps(
            {
                "source_availability_state": report["source_availability_state"],
                "counts": report["counts"],
                "sources": [
                    {
                        "source_id": item["source_id"],
                        "availability_state": item["availability_state"],
                        "primary_route_state": item["primary_route_state"],
                        "selected_route_id": item["selected_route_id"],
                        "selected_route_class": item["selected_route_class"],
                        "evidence_substitution_allowed": item["evidence_substitution_allowed"],
                    }
                    for item in report["source_reports"]
                ],
                "report_sha256": report["report_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["source_availability_state"] == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
