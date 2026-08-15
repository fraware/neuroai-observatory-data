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


def active_failed_run() -> dict:
    return {
        "run_id": "CRUN-route-test",
        "plan_id": "PLAN-route-test",
        "execution_status": "COMPLETE_WITH_SOURCE_FAILURES",
        "counts": {
            "succeeded": 2,
            "failed": 1,
            "skipped": 0,
            "incomplete": 0,
            "logical_sources": 3,
            "collection_attempts": 3,
            "retries": 0,
            "retryable_failures_exhausted": 0,
        },
        "slo": {
            "source_accountability_coverage": 1.0,
            "target_execution_coverage": 1.0,
        },
        "outcomes": [
            {"source_id": "SRC-PR-002", "status": "FAILURE"},
            {"source_id": "SRC-PR-007", "status": "RESULT"},
            {"source_id": "SRC-OTHER", "status": "RESULT"},
        ],
    }


def active_route_report() -> dict:
    reports = [
        {
            "source_id": "SRC-PR-002",
            "availability_state": "AVAILABLE_FALLBACK",
            "primary_route_state": "DEGRADED",
            "selected_route_id": "SRC-PR-002:api-v2-id-query",
            "selected_route_class": "IDENTITY_EQUIVALENT",
            "evidence_substitution_allowed": True,
        }
    ]
    return {
        "source_resolution_state": "HEALTHY",
        "active_source_availability_state": "HEALTHY",
        "active_evidence_payload_availability_state": "HEALTHY",
        "report_sha256": "a" * 64,
        "counts": {
            "AVAILABLE_PRIMARY": 0,
            "AVAILABLE_FALLBACK": 1,
            "UNRESOLVED": 0,
            "RETIRED": 0,
            "RESOLVED_LIFECYCLE_CHANGE": 0,
            "PRIMARY_DEGRADED": 1,
            "EVIDENCE_SUBSTITUTABLE_FALLBACK": 1,
            "LIVENESS_ONLY_FALLBACK": 0,
        },
        "source_reports": reports,
    }


class RouteAwareOperationalHealthTests(unittest.TestCase):
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

    def test_registered_active_route_resolution_restores_active_health(self) -> None:
        routes = active_route_report()
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=active_failed_run(),
            route_resilience=routes,
        )
        self.assertEqual(report["state"], DEGRADED)
        self.assertEqual(report["engineering_state"], ENGINEERING_READY)
        self.assertEqual(report["source_resolution_state"], HEALTHY)
        self.assertEqual(report["active_source_availability_state"], HEALTHY)
        self.assertEqual(report["active_evidence_payload_availability_state"], HEALTHY)
        self.assertEqual(
            report["route_resilience"]["resolved_failed_source_ids"], ["SRC-PR-002"]
        )
        self.assertEqual(
            report["route_resilience"][
                "lifecycle_resolved_source_ids_excluded_from_probe"
            ],
            ["SRC-PR-015"],
        )
        codes = {warning["code"] for warning in report["warnings"]}
        self.assertIn("TYPED_SOURCE_FAILURES_PRESENT", codes)
        self.assertIn("TYPED_SOURCE_FAILURES_RESOLVED_BY_REGISTERED_ROUTE", codes)
        self.assertNotIn("FAILED_SOURCES_UNRESOLVED_AFTER_REGISTERED_RESOLUTION", codes)
        verify_health_report(
            report,
            accountability=self.accountability,
            development_registry=self.registry,
            run=active_failed_run(),
            route_resilience=routes,
        )

    def test_missing_active_failed_source_keeps_resolution_degraded(self) -> None:
        routes = active_route_report()
        routes["source_reports"] = []
        routes["source_resolution_state"] = "DEGRADED"
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=active_failed_run(),
            route_resilience=routes,
        )
        self.assertEqual(report["engineering_state"], ENGINEERING_READY)
        self.assertEqual(report["source_resolution_state"], DEGRADED)
        self.assertEqual(
            report["route_resilience"]["unresolved_failed_source_ids"], ["SRC-PR-002"]
        )
        self.assertIn(
            "FAILED_SOURCES_UNRESOLVED_AFTER_REGISTERED_RESOLUTION",
            {warning["code"] for warning in report["warnings"]},
        )

    def test_lifecycle_resolved_source_in_route_report_is_blocking(self) -> None:
        routes = active_route_report()
        routes["source_reports"].append(
            {
                "source_id": "SRC-PR-015",
                "availability_state": "UNRESOLVED",
                "primary_route_state": "DEGRADED",
                "selected_route_id": None,
                "selected_route_class": None,
                "evidence_substitution_allowed": False,
            }
        )
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=active_failed_run(),
            route_resilience=routes,
        )
        self.assertEqual(report["state"], UNHEALTHY)
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "LIFECYCLE_RESOLVED_SOURCE_REPROBED",
            {alert["code"] for alert in report["blocking_alerts"]},
        )

    def test_lifecycle_resolved_failed_execution_is_blocking(self) -> None:
        run = active_failed_run()
        run["outcomes"].append({"source_id": "SRC-PR-015", "status": "FAILURE"})
        run["counts"]["failed"] += 1
        run["counts"]["logical_sources"] += 1
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=run,
            route_resilience=active_route_report(),
        )
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "LIFECYCLE_RESOLVED_SOURCE_EXECUTED",
            {alert["code"] for alert in report["blocking_alerts"]},
        )

    def test_lifecycle_resolved_successful_execution_is_also_blocking(self) -> None:
        run = active_failed_run()
        run["outcomes"].append({"source_id": "SRC-PR-015", "status": "RESULT"})
        run["counts"]["succeeded"] += 1
        run["counts"]["logical_sources"] += 1
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=run,
            route_resilience=active_route_report(),
        )
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "LIFECYCLE_RESOLVED_SOURCE_EXECUTED",
            {alert["code"] for alert in report["blocking_alerts"]},
        )

    def test_duplicate_active_route_source_report_is_blocking(self) -> None:
        routes = active_route_report()
        routes["source_reports"].append(copy.deepcopy(routes["source_reports"][0]))
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=active_failed_run(),
            route_resilience=routes,
        )
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "ROUTE_RESILIENCE_DUPLICATE_SOURCE_REPORT",
            {alert["code"] for alert in report["blocking_alerts"]},
        )

    def test_invalid_top_level_resolution_state_is_blocking(self) -> None:
        routes = active_route_report()
        routes["source_resolution_state"] = "UNKNOWN"
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=active_failed_run(),
            route_resilience=routes,
        )
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "SOURCE_RESOLUTION_STATE_INVALID",
            {alert["code"] for alert in report["blocking_alerts"]},
        )

    def test_route_report_tampering_changes_health_verification(self) -> None:
        routes = active_route_report()
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=active_failed_run(),
            route_resilience=routes,
        )
        tampered_routes = copy.deepcopy(routes)
        tampered_routes["report_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "does not match recomputed"):
            verify_health_report(
                report,
                accountability=self.accountability,
                development_registry=self.registry,
                run=active_failed_run(),
                route_resilience=tampered_routes,
            )


if __name__ == "__main__":
    unittest.main()
