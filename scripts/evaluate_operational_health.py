#!/usr/bin/env python3
"""Evaluate registered-universe operational health without escalating retrieval into scientific claims."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
UNHEALTHY = "UNHEALTHY"
BOUNDARY = (
    "Operational health covers execution and accountability over the declared effective source namespace only. "
    "Typed retrieval failures remain source-operation outcomes and do not establish assessment failure, source falsity, "
    "scientific invalidity, regulatory/clinical status, governance approval, UNESCO endorsement, or release authority."
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _count(mapping: Any, key: str) -> int:
    if not isinstance(mapping, dict):
        return 0
    value = mapping.get(key, 0)
    return int(value) if isinstance(value, int | float) else 0


def evaluate_health(
    *,
    accountability: dict[str, Any],
    development_registry: dict[str, Any],
    plan: dict[str, Any] | None = None,
    run: dict[str, Any] | None = None,
    wall_clock_seconds: float | None = None,
    performance_budget_seconds: float | None = None,
) -> dict[str, Any]:
    """Return deterministic blocking/warning alerts and an overall operational state."""
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    current = accountability.get("current", {}) if isinstance(accountability, dict) else {}
    current_counts = current.get("counts", {}) if isinstance(current, dict) else {}
    candidate = accountability.get("candidate_accountability", {}) if isinstance(accountability, dict) else {}
    registry_meta = development_registry.get("metadata", {}) if isinstance(development_registry, dict) else {}

    expected_decomposition = {
        "MONITORED": 224,
        "EXEMPT_WITH_RATIONALE": 15,
        "MANUAL_ONLY": 6,
        "GAP": 3,
    }
    observed_decomposition = {key: _count(current_counts, key) for key in expected_decomposition}
    if observed_decomposition != expected_decomposition:
        blocking.append(
            {
                "code": "CURRENT_ACCOUNTABILITY_DECOMPOSITION_DRIFT",
                "expected": expected_decomposition,
                "observed": observed_decomposition,
            }
        )

    if current.get("effective_source_count") != 248:
        blocking.append(
            {
                "code": "EFFECTIVE_SOURCE_COUNT_DRIFT",
                "expected": 248,
                "observed": current.get("effective_source_count"),
            }
        )

    if candidate.get("coverage_fraction") != 1.0 or candidate.get("gap_source_ids"):
        blocking.append(
            {
                "code": "CANDIDATE_ACCOUNTABILITY_NOT_COMPLETE",
                "coverage_fraction": candidate.get("coverage_fraction"),
                "gap_source_ids": candidate.get("gap_source_ids", []),
            }
        )

    if registry_meta.get("status") != "DEVELOPMENT_MONITOR_REGISTRY_VIEW_NOT_CANONICAL":
        blocking.append(
            {
                "code": "DEVELOPMENT_REGISTRY_STATUS_INVALID",
                "observed": registry_meta.get("status"),
            }
        )
    expected_registry_meta = {
        "record_count": 227,
        "predecessor_record_count": 224,
        "extension_record_count": 3,
        "effective_source_count": 248,
        "candidate_accountability_coverage_fraction": 1.0,
    }
    observed_registry_meta = {key: registry_meta.get(key) for key in expected_registry_meta}
    if observed_registry_meta != expected_registry_meta:
        blocking.append(
            {
                "code": "DEVELOPMENT_REGISTRY_INVARIANT_DRIFT",
                "expected": expected_registry_meta,
                "observed": observed_registry_meta,
            }
        )

    plan_counts: dict[str, int] = {"due": 0, "manual": 0, "not_due": 0}
    if plan is not None:
        raw_counts = plan.get("counts", {}) if isinstance(plan, dict) else {}
        plan_counts = {key: _count(raw_counts, key) for key in plan_counts}
        if plan_counts["manual"] > 0:
            warnings.append({"code": "MANUAL_MONITOR_WORK_PRESENT", "count": plan_counts["manual"]})

    run_metrics: dict[str, Any] | None = None
    if run is not None:
        execution_status = run.get("execution_status")
        slo = run.get("slo", {}) if isinstance(run.get("slo"), dict) else {}
        counts = run.get("counts", {}) if isinstance(run.get("counts"), dict) else {}
        if execution_status not in {"COMPLETE", "COMPLETE_WITH_SOURCE_FAILURES"}:
            blocking.append({"code": "RUN_NOT_OPERATIONALLY_COMPLETE", "execution_status": execution_status})
        if slo.get("source_accountability_coverage") != 1.0:
            blocking.append(
                {
                    "code": "SOURCE_ACCOUNTABILITY_SLO_BREACH",
                    "observed": slo.get("source_accountability_coverage"),
                }
            )
        if slo.get("target_execution_coverage") != 1.0:
            blocking.append(
                {
                    "code": "TARGET_EXECUTION_SLO_BREACH",
                    "observed": slo.get("target_execution_coverage"),
                }
            )
        if _count(counts, "incomplete") > 0:
            blocking.append({"code": "INCOMPLETE_SOURCE_OUTCOMES", "count": _count(counts, "incomplete")})
        if _count(counts, "failed") > 0:
            warnings.append({"code": "TYPED_SOURCE_FAILURES_PRESENT", "count": _count(counts, "failed")})
        if _count(counts, "retries") > 0:
            warnings.append({"code": "RETRIES_PRESENT", "count": _count(counts, "retries")})
        if _count(counts, "retryable_failures_exhausted") > 0:
            warnings.append(
                {
                    "code": "RETRYABLE_FAILURES_EXHAUSTED",
                    "count": _count(counts, "retryable_failures_exhausted"),
                }
            )
        run_metrics = {
            "execution_status": execution_status,
            "run_id": run.get("run_id"),
            "plan_id": run.get("plan_id"),
            "counts": counts,
            "slo": slo,
        }

    if wall_clock_seconds is not None:
        if wall_clock_seconds < 0:
            blocking.append({"code": "INVALID_WALL_CLOCK", "observed": wall_clock_seconds})
        elif performance_budget_seconds is not None and wall_clock_seconds > performance_budget_seconds:
            warnings.append(
                {
                    "code": "PERFORMANCE_BUDGET_EXCEEDED",
                    "wall_clock_seconds": wall_clock_seconds,
                    "budget_seconds": performance_budget_seconds,
                }
            )

    state = UNHEALTHY if blocking else DEGRADED if warnings else HEALTHY
    report: dict[str, Any] = {
        "schema_version": "1",
        "state": state,
        "blocking_alerts": blocking,
        "warnings": warnings,
        "accountability": {
            "effective_sources": current.get("effective_source_count"),
            "current_counts": observed_decomposition,
            "candidate_coverage_fraction": candidate.get("coverage_fraction"),
            "candidate_gap_source_ids": candidate.get("gap_source_ids", []),
        },
        "registry": {
            "automatic_monitors": registry_meta.get("record_count"),
            "manual_on_change_sources": observed_decomposition["MANUAL_ONLY"],
            "archival_static_sources": observed_decomposition["EXEMPT_WITH_RATIONALE"],
            "registry_view_sha256": registry_meta.get("registry_view_sha256"),
            "predecessor_registry_sha256": registry_meta.get("predecessor_registry_sha256"),
        },
        "plan_counts": plan_counts if plan is not None else None,
        "run": run_metrics,
        "telemetry": {
            "wall_clock_seconds": wall_clock_seconds,
            "performance_budget_seconds": performance_budget_seconds,
        },
        "boundary": BOUNDARY,
    }
    report["health_report_sha256"] = sha256(report)
    return report


def verify_health_report(report: dict[str, Any], **inputs: Any) -> None:
    expected = evaluate_health(**inputs)
    if canonical_bytes(expected) != canonical_bytes(report):
        raise ValueError("Operational health report does not match recomputed inputs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accountability", type=Path, required=True)
    parser.add_argument("--development-registry", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--wall-clock-seconds", type=float)
    parser.add_argument("--performance-budget-seconds", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def load(path: Path | None) -> dict[str, Any] | None:
        if path is None:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object in {path}")
        return value

    accountability = load(args.accountability)
    registry = load(args.development_registry)
    if accountability is None or registry is None:
        raise ValueError("Accountability and development registry are required")
    plan = load(args.plan)
    run = load(args.run)
    report = evaluate_health(
        accountability=accountability,
        development_registry=registry,
        plan=plan,
        run=run,
        wall_clock_seconds=args.wall_clock_seconds,
        performance_budget_seconds=args.performance_budget_seconds,
    )
    verify_health_report(
        report,
        accountability=accountability,
        development_registry=registry,
        plan=plan,
        run=run,
        wall_clock_seconds=args.wall_clock_seconds,
        performance_budget_seconds=args.performance_budget_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "state": report["state"],
                "blocking": len(report["blocking_alerts"]),
                "warnings": len(report["warnings"]),
                "sha256": report["health_report_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["state"] != UNHEALTHY else 2


if __name__ == "__main__":
    raise SystemExit(main())
