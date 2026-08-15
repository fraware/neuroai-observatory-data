from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_analytical_projection import build_tables, load_inputs
from build_current_monitor_accountability import build_projection
from build_development_monitor_registry import build_development_registry
from evaluate_operational_health import (
    DEGRADED,
    ENGINEERING_BLOCKED,
    ENGINEERING_READY,
    HEALTHY,
    UNHEALTHY,
    evaluate_health,
    verify_health_report,
)
from source_lifecycle_overlay import load_verified_lifecycle_overlay


def complete_run(*, failed: int = 0, retries: int = 0, exhausted: int = 0) -> dict:
    status = "COMPLETE_WITH_SOURCE_FAILURES" if failed else "COMPLETE"
    outcomes = []
    if failed:
        outcomes.append({"source_id": "SRC-PR-002", "status": "FAILURE"})
    return {
        "run_id": "CRUN-test",
        "plan_id": "PLAN-test",
        "execution_status": status,
        "counts": {
            "succeeded": 10 - failed,
            "failed": failed,
            "skipped": 0,
            "incomplete": 0,
            "logical_sources": 10,
            "collection_attempts": 10 + retries,
            "retries": retries,
            "retryable_failures_exhausted": exhausted,
        },
        "slo": {
            "source_accountability_coverage": 1.0,
            "target_execution_coverage": 1.0,
        },
        "outcomes": outcomes,
    }


class OperationalHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        inputs = load_inputs(
            (ROOT / "releases/data-v0.1.0-public-governing/records").resolve(),
            supplemental_dir=(ROOT / "supplemental_records").resolve(),
        )
        tables = build_tables(inputs)
        source_ids = {
            str(row["record_id"]) for row in tables["sources"] if row.get("record_id")
        }
        monitor_ids = {
            str(row["record_id"])
            for row in tables["source_monitors"]
            if row.get("record_id")
        }
        _, _, cls.transitions = load_verified_lifecycle_overlay(
            effective_source_ids=source_ids,
            governing_monitor_source_ids=monitor_ids,
        )
        cls.accountability = build_projection(
            tables["sources"], tables["source_monitors"], cls.transitions
        )
        cls.registry = build_development_registry(inputs, cls.transitions)
        cls.plan = {"counts": {"due": 10, "manual": 0, "not_due": 216}}

    def test_exact_current_state_is_healthy_with_clean_complete_run(self) -> None:
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            plan=self.plan,
            run=complete_run(),
            wall_clock_seconds=20.0,
            performance_budget_seconds=60.0,
        )
        self.assertEqual(report["state"], HEALTHY)
        self.assertEqual(report["engineering_state"], ENGINEERING_READY)
        self.assertEqual(report["source_availability_state"], HEALTHY)
        self.assertEqual(report["blocking_alerts"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["accountability"]["effective_sources"], 248)
        self.assertEqual(
            report["accountability"]["lifecycle_resolved_source_ids"], ["SRC-PR-015"]
        )
        self.assertEqual(report["registry"]["automatic_monitors"], 226)
        self.assertEqual(report["registry"]["manual_on_change_sources"], 6)
        self.assertEqual(report["registry"]["archival_static_sources"], 15)
        self.assertEqual(report["registry"]["lifecycle_resolved_sources"], 1)
        self.assertEqual(len(report["health_report_sha256"]), 64)
        verify_health_report(
            report,
            accountability=self.accountability,
            development_registry=self.registry,
            plan=self.plan,
            run=complete_run(),
            wall_clock_seconds=20.0,
            performance_budget_seconds=60.0,
        )

    def test_typed_active_source_failures_and_retries_degrade_sources_not_engineering(
        self,
    ) -> None:
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            plan=self.plan,
            run=complete_run(failed=1, retries=3, exhausted=1),
        )
        self.assertEqual(report["state"], DEGRADED)
        self.assertEqual(report["engineering_state"], ENGINEERING_READY)
        self.assertEqual(report["source_availability_state"], DEGRADED)
        self.assertEqual(report["blocking_alerts"], [])
        self.assertEqual(
            {alert["code"] for alert in report["warnings"]},
            {
                "TYPED_SOURCE_FAILURES_PRESENT",
                "RETRIES_PRESENT",
                "RETRYABLE_FAILURES_EXHAUSTED",
            },
        )

    def test_manual_warning_alone_does_not_mark_sources_unavailable(self) -> None:
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            plan={"counts": {"due": 1, "manual": 2, "not_due": 223}},
            run=complete_run(),
        )
        self.assertEqual(report["state"], DEGRADED)
        self.assertEqual(report["engineering_state"], ENGINEERING_READY)
        self.assertEqual(report["source_availability_state"], HEALTHY)

    def test_internal_incomplete_or_slo_breach_blocks_engineering(self) -> None:
        run = complete_run()
        run["execution_status"] = "INCOMPLETE_INTERNAL_ERROR"
        run["counts"]["incomplete"] = 1
        run["slo"]["target_execution_coverage"] = 0.9
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=run,
        )
        self.assertEqual(report["state"], UNHEALTHY)
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        codes = {alert["code"] for alert in report["blocking_alerts"]}
        self.assertEqual(
            codes,
            {
                "RUN_NOT_OPERATIONALLY_COMPLETE",
                "TARGET_EXECUTION_SLO_BREACH",
                "INCOMPLETE_SOURCE_OUTCOMES",
            },
        )

    def test_namespace_registry_or_lifecycle_drift_is_unhealthy(self) -> None:
        accountability = copy.deepcopy(self.accountability)
        accountability["current"]["effective_source_count"] = 247
        accountability["current"]["counts"]["GAP"] = 3
        accountability["current"]["lifecycle_resolved_source_ids"] = []
        registry = copy.deepcopy(self.registry)
        registry["metadata"]["record_count"] = 227
        report = evaluate_health(
            accountability=accountability, development_registry=registry
        )
        self.assertEqual(report["state"], UNHEALTHY)
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        codes = {alert["code"] for alert in report["blocking_alerts"]}
        self.assertTrue(
            {
                "CURRENT_ACCOUNTABILITY_DECOMPOSITION_DRIFT",
                "LIFECYCLE_RESOLVED_SOURCE_SET_DRIFT",
                "EFFECTIVE_SOURCE_COUNT_DRIFT",
                "DEVELOPMENT_REGISTRY_INVARIANT_DRIFT",
            }.issubset(codes)
        )

    def test_candidate_gap_is_blocking(self) -> None:
        accountability = copy.deepcopy(self.accountability)
        accountability["candidate_accountability"]["coverage_fraction"] = 0.99
        accountability["candidate_accountability"]["gap_source_ids"] = ["SRC-X"]
        report = evaluate_health(
            accountability=accountability, development_registry=self.registry
        )
        self.assertEqual(report["state"], UNHEALTHY)
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "CANDIDATE_ACCOUNTABILITY_NOT_COMPLETE",
            {a["code"] for a in report["blocking_alerts"]},
        )

    def test_manual_work_and_slow_run_are_warnings(self) -> None:
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            plan={"counts": {"due": 1, "manual": 2, "not_due": 223}},
            run=complete_run(),
            wall_clock_seconds=61.0,
            performance_budget_seconds=60.0,
        )
        self.assertEqual(report["state"], DEGRADED)
        self.assertEqual(report["engineering_state"], ENGINEERING_READY)
        self.assertEqual(
            {alert["code"] for alert in report["warnings"]},
            {"MANUAL_MONITOR_WORK_PRESENT", "PERFORMANCE_BUDGET_EXCEEDED"},
        )

    def test_negative_wall_clock_is_blocking(self) -> None:
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            wall_clock_seconds=-1.0,
        )
        self.assertEqual(report["state"], UNHEALTHY)
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "INVALID_WALL_CLOCK", {a["code"] for a in report["blocking_alerts"]}
        )

    def test_report_tampering_is_detected(self) -> None:
        report = evaluate_health(
            accountability=self.accountability, development_registry=self.registry
        )
        tampered = copy.deepcopy(report)
        tampered["engineering_state"] = ENGINEERING_BLOCKED
        with self.assertRaisesRegex(ValueError, "does not match recomputed"):
            verify_health_report(
                tampered,
                accountability=self.accountability,
                development_registry=self.registry,
            )


if __name__ == "__main__":
    unittest.main()
