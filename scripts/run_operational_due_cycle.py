#!/usr/bin/env python3
"""Execute one controlled live due cycle against the lifecycle-aware noncanonical development registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_analytical_projection import (
    DEFAULT_RECORDS_DIR,
    DEFAULT_SUPPLEMENTAL_DIR,
    build_tables,
    load_inputs,
)
from build_current_monitor_accountability import build_projection
from build_development_monitor_registry import (
    build_development_registry,
    verify_development_registry,
    write_registry,
)
from evaluate_operational_health import evaluate_health
from neuroai_workbench.collector import (
    CollectionScheduler,
    CollectorConfig,
    SchedulerConfig,
)
from neuroai_workbench.collector.http_client import HttpRequest, HttpTransport
from neuroai_workbench.collector.transport import StdlibHttpTransport
from neuroai_workbench.monitoring import (
    initialize_monitoring,
    plan_monitoring_run,
    validate_source_registry,
)
from probe_source_route_resilience import probe_policy
from source_lifecycle_overlay import (
    DEFAULT_LIFECYCLE_OVERLAY,
    DEFAULT_ROUTE_POLICY,
    build_active_route_policy,
    load_verified_lifecycle_overlay,
    sha256,
)

BOUNDARY = (
    "This report is controlled operational evidence over the declared noncanonical lifecycle-aware development monitor "
    "view. Network success/failure, lifecycle monitoring eligibility, and successor-discovery separation are not assessment "
    "adjudication and do not authorize canonical publication or human governance claims."
)


@dataclass
class CountingTransport:
    inner: HttpTransport = field(default_factory=StdlibHttpTransport)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    sends: int = 0
    hosts: Counter[str] = field(default_factory=Counter)

    def send(
        self,
        request: HttpRequest,
        *,
        connect_timeout: float,
        read_timeout: float,
    ) -> tuple[int, dict[str, str], bytes]:
        from urllib.parse import urlparse

        host = (urlparse(request.url).hostname or "unknown").lower().rstrip(".")
        with self._lock:
            self.sends += 1
            self.hosts[host] += 1
        return self.inner.send(
            request,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )


def _configuration_hash() -> str:
    return hashlib.sha256(
        b"neuroai-operational-live-cycle-v3-lifecycle-active-monitoring"
    ).hexdigest()


def _failure_status_counts(run: dict[str, Any]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                str(item.get("status", "UNKNOWN")) for item in run.get("outcomes", [])
            ).items()
        )
    )


def _sanitize_route_observation(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    allowed = {
        "route_id",
        "outcome",
        "failure_class",
        "http_status",
        "final_host",
        "redirect_hops",
        "identity_match",
        "corroboration_match",
    }
    return {key: item.get(key) for key in sorted(allowed) if key in item}


def _sanitize_route_diagnostic(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    allowed = {
        "route_id",
        "state",
        "failure_class",
        "http_status",
        "failover_allowed",
        "rejection",
    }
    return {key: item.get(key) for key in sorted(allowed) if key in item}


def execute(
    *,
    records_dir: Path,
    supplemental_dir: Path,
    workspace: Path,
    as_of: str,
    max_workers: int,
    max_workers_per_host: int,
    performance_budget_seconds: float,
    route_policy_path: Path = DEFAULT_ROUTE_POLICY,
    lifecycle_overlay_path: Path = DEFAULT_LIFECYCLE_OVERLAY,
) -> dict[str, Any]:
    inputs = load_inputs(
        records_dir.resolve(), supplemental_dir=supplemental_dir.resolve()
    )
    tables = build_tables(inputs)
    source_ids = {
        str(row["record_id"]) for row in tables["sources"] if row.get("record_id")
    }
    governing_monitor_ids = {
        str(row["record_id"])
        for row in tables["source_monitors"]
        if row.get("record_id")
    }
    route_policy, lifecycle_overlay, transitions = load_verified_lifecycle_overlay(
        route_policy_path=route_policy_path,
        overlay_path=lifecycle_overlay_path,
        effective_source_ids=source_ids,
        governing_monitor_source_ids=governing_monitor_ids,
    )
    accountability = build_projection(
        tables["sources"], tables["source_monitors"], transitions
    )
    registry = build_development_registry(inputs, transitions)
    verify_development_registry(registry)

    registry_validation = validate_source_registry(registry)
    if not registry_validation.get("valid"):
        raise ValueError(
            f"Development monitor registry failed workbench validation: {registry_validation}"
        )

    workspace.mkdir(parents=True, exist_ok=True)
    registry_path = workspace / "development-monitor-registry.json"
    write_registry(registry, registry_path)
    monitoring = initialize_monitoring(
        workspace, registry_path, actor="operational-live-cycle"
    )
    plan = plan_monitoring_run(workspace, as_of=as_of)

    source_index = {str(record["source_id"]): record for record in registry["sources"]}
    forbidden_lifecycle_ids = set(transitions) & set(source_index)
    if forbidden_lifecycle_ids:
        raise ValueError(
            f"Lifecycle-resolved sources remain in active source index: {sorted(forbidden_lifecycle_ids)}"
        )

    transport = CountingTransport()
    collector_config = CollectorConfig(
        collector_version="0.3.0-dev-operational-lifecycle",
        configuration_hash=_configuration_hash(),
        connect_timeout_seconds=8.0,
        read_timeout_seconds=20.0,
        total_timeout_seconds=45.0,
        max_attempts=3,
        retry_initial_delay_seconds=0.5,
        retry_max_delay_seconds=4.0,
        requests_per_host_per_minute=30,
        allowed_content_types=frozenset(
            {
                "text/html",
                "text/plain",
                "text/csv",
                "application/json",
                "application/ld+json",
                "application/xml",
                "text/xml",
                "application/rss+xml",
                "application/atom+xml",
                "application/pdf",
                "application/octet-stream",
            }
        ),
    )
    scheduler_config = SchedulerConfig(
        max_workers=max_workers,
        max_workers_per_host=max_workers_per_host,
        resume_enabled=True,
        collection_enabled=True,
        handoff_enabled=False,
    )
    scheduler = CollectionScheduler(
        collector_config=collector_config,
        transport=transport,
        quarantine_root=workspace / "quarantine",
        scheduler_config=scheduler_config,
    )

    started = time.monotonic()
    first = scheduler.run_plan(
        plan,
        registry_sha256=str(monitoring["registry_sha256"]),
        source_index=source_index,
    )
    first_wall = time.monotonic() - started
    sends_after_first = transport.sends

    resumed = scheduler.run_plan(
        plan,
        registry_sha256=str(monitoring["registry_sha256"]),
        source_index=source_index,
    )
    sends_after_resume = transport.sends
    if first != resumed:
        raise ValueError(
            "Exact completed-run resume did not return the identical deterministic summary"
        )
    if sends_after_resume != sends_after_first:
        raise ValueError(
            f"Completed-run resume performed duplicate transport sends: first={sends_after_first} resume={sends_after_resume}"
        )

    execution_status = first.get("execution_status")
    if execution_status not in {"COMPLETE", "COMPLETE_WITH_SOURCE_FAILURES"}:
        raise ValueError(f"Live cycle is internally incomplete: {execution_status}")
    slo = first.get("slo", {})
    if (
        slo.get("source_accountability_coverage") != 1.0
        or slo.get("target_execution_coverage") != 1.0
    ):
        raise ValueError(f"Live cycle failed operational SLOs: {slo}")

    active_route_policy = build_active_route_policy(route_policy, transitions)
    route_resilience = probe_policy(active_route_policy)
    probed_source_ids = {
        str(item.get("source_id"))
        for item in route_resilience.get("source_reports", [])
        if isinstance(item, dict) and item.get("source_id")
    }
    reprobed_lifecycle_ids = sorted(probed_source_ids & set(transitions))
    if reprobed_lifecycle_ids:
        raise ValueError(
            f"Lifecycle-resolved source was re-probed: {reprobed_lifecycle_ids}"
        )

    health = evaluate_health(
        accountability=accountability,
        development_registry=registry,
        plan=plan,
        run=first,
        route_resilience=route_resilience,
        wall_clock_seconds=first_wall,
        performance_budget_seconds=performance_budget_seconds,
    )

    lifecycle_rows = [
        {
            "source_id": source_id,
            "lifecycle_state": transition["lifecycle_state"],
            "monitoring_state": transition["monitoring_state"],
            "successor_discovery_watch_id": transition["successor_discovery_watch_id"],
            "transition_sha256": transition["transition_sha256"],
            "route_report_sha256": transition["live_evidence"]["route_report_sha256"],
            "lifecycle_report_sha256": transition["live_evidence"][
                "lifecycle_report_sha256"
            ],
        }
        for source_id, transition in sorted(transitions.items())
    ]

    report: dict[str, Any] = {
        "schema_version": "4",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "boundary": BOUNDARY,
        "registry": {
            "effective_sources": 248,
            "automatic_monitors": len(registry["sources"]),
            "manual_on_change_sources": 6,
            "archival_static_sources": 15,
            "lifecycle_resolved_sources": len(transitions),
            "lifecycle_resolved_source_ids": sorted(transitions),
            "registry_sha256": monitoring["registry_sha256"],
            "development_registry_view_sha256": registry["metadata"][
                "registry_view_sha256"
            ],
        },
        "lifecycle_overlay": {
            "overlay_sha256": lifecycle_overlay["overlay_sha256"],
            "route_policy_sha256": sha256(route_policy),
            "transition_count": len(transitions),
            "transitions": lifecycle_rows,
        },
        "plan": {
            "plan_id": plan.get("plan_id"),
            "counts": plan.get("counts"),
            "lifecycle_resolved_source_ids_excluded": sorted(transitions),
        },
        "execution": {
            "run_id": first.get("run_id"),
            "execution_status": execution_status,
            "counts": first.get("counts"),
            "slo": slo,
            "semantic_summary_sha256": first.get("semantic_summary_sha256"),
            "manifest_sha256": first.get("manifest_sha256"),
            "binding_sha256": first.get("binding_sha256"),
            "source_outcome_status_counts": _failure_status_counts(first),
            "transport_sends": sends_after_first,
            "host_count": len(transport.hosts),
            "wall_clock_seconds": round(first_wall, 6),
        },
        "route_resilience": {
            "original_policy_sha256": sha256(route_policy),
            "active_policy_sha256": route_resilience.get("policy_sha256"),
            "report_sha256": route_resilience.get("report_sha256"),
            "source_resolution_state": route_resilience.get("source_resolution_state"),
            "active_source_availability_state": route_resilience.get(
                "active_source_availability_state"
            ),
            "active_evidence_payload_availability_state": route_resilience.get(
                "active_evidence_payload_availability_state"
            ),
            "excluded_lifecycle_source_ids": sorted(transitions),
            "counts": route_resilience.get("counts"),
            "sources": [
                {
                    "source_id": item.get("source_id"),
                    "availability_state": item.get("availability_state"),
                    "primary_route_state": item.get("primary_route_state"),
                    "selected_route_id": item.get("selected_route_id"),
                    "selected_route_class": item.get("selected_route_class"),
                    "evidence_substitution_allowed": item.get(
                        "evidence_substitution_allowed"
                    ),
                    "route_observations": [
                        cleaned
                        for raw in item.get("route_observations", [])
                        if (cleaned := _sanitize_route_observation(raw)) is not None
                    ],
                    "diagnostics": [
                        cleaned
                        for raw in item.get("diagnostics", [])
                        if (cleaned := _sanitize_route_diagnostic(raw)) is not None
                    ],
                }
                for item in route_resilience.get("source_reports", [])
                if isinstance(item, dict)
            ],
        },
        "resume_proof": {
            "identical_summary": True,
            "additional_transport_sends": sends_after_resume - sends_after_first,
            "transport_sends_after_resume": sends_after_resume,
        },
        "health": health,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument(
        "--supplemental-dir", type=Path, default=DEFAULT_SUPPLEMENTAL_DIR
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--as-of", default=datetime.now(timezone.utc).date().isoformat()
    )
    parser.add_argument("--max-workers", type=int, default=12)
    parser.add_argument("--max-workers-per-host", type=int, default=2)
    parser.add_argument("--performance-budget-seconds", type=float, default=300.0)
    parser.add_argument("--route-policy", type=Path, default=DEFAULT_ROUTE_POLICY)
    parser.add_argument(
        "--lifecycle-overlay", type=Path, default=DEFAULT_LIFECYCLE_OVERLAY
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = execute(
        records_dir=args.records_dir,
        supplemental_dir=args.supplemental_dir,
        workspace=args.workspace.resolve(),
        as_of=args.as_of,
        max_workers=args.max_workers,
        max_workers_per_host=args.max_workers_per_host,
        performance_budget_seconds=args.performance_budget_seconds,
        route_policy_path=args.route_policy,
        lifecycle_overlay_path=args.lifecycle_overlay,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "execution_status": report["execution"]["execution_status"],
                "health": report["health"]["state"],
                "engineering_state": report["health"]["engineering_state"],
                "source_resolution_state": report["health"]["source_resolution_state"],
                "active_source_availability_state": report["health"][
                    "active_source_availability_state"
                ],
                "active_evidence_payload_availability_state": report["health"][
                    "active_evidence_payload_availability_state"
                ],
                "automatic_monitors": report["registry"]["automatic_monitors"],
                "lifecycle_resolved_source_ids": report["registry"][
                    "lifecycle_resolved_source_ids"
                ],
                "route_sources": report["route_resilience"]["sources"],
                "source_accountability_coverage": report["execution"]["slo"][
                    "source_accountability_coverage"
                ],
                "target_execution_coverage": report["execution"]["slo"][
                    "target_execution_coverage"
                ],
                "additional_resume_sends": report["resume_proof"][
                    "additional_transport_sends"
                ],
                "wall_clock_seconds": report["execution"]["wall_clock_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
