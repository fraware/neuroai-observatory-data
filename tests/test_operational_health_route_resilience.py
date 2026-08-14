from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_analytical_projection import build_tables, load_inputs  # noqa: E402
from build_current_monitor_accountability import build_projection  # noqa: E402
from build_development_monitor_registry import build_development_registry  # noqa: E402
from evaluate_operational_health import (  # noqa: E402
    DEGRADED,
    ENGINEERING_BLOCKED,
    ENGINEERING_READY,
    HEALTHY,
    evaluate_health,
    verify_health_report,
)


def failed_run() -> dict:
    return {
        "run_id": "CRUN-route-test",
        "plan_id": "PLAN-route-test",
        "execution_status": "COMPLETE_WITH_SOURCE_FAILURES",
        "counts": {
            "succeeded": 2,
            "failed": 2,
            "skipped": 0,
            "incomplete": 0,
            "logical_sources": 4,
            "collection_attempts": 4,
            "retries": 0,
            "retryable_failures_exhausted": 0,
        },
        "slo": {
            "source_accountability_coverage": 1.0,
            "target_execution_coverage": 1.0,
        },
        "outcomes": [
            {"source_id": "SRC-PR-002", "status": "FAILURE"},
            {"source_id": "SRC-PR-015", "status": "FAILURE"},
            {"source_id": "SRC-PR-007", "status": "RESULT"},
            {"source_id": "SRC-OTHER", "status": "RESULT"},
        ],
    }


def route_report(*, include_science: bool = True) -> dict:
    reports = [
        {
            "source_id": "SRC-PR-002",
            "availability_state": "AVAILABLE_FALLBACK",
            "primary_route_state": "DEGRADED",
            "selected_route_id": "SRC-PR-002:api-v2-id-query",
            "selected_route_class": "IDENTITY_EQUIVALENT",
            "evidence_substitution_allowed": True,
            "lifecycle": None,
        }
    ]
    if include_science:
        reports.append(
            {
                "source_id": "SRC-PR-015",
                "availability_state": "UNRESOLVED",
                "primary_route_state": "DEGRADED",
                "selected_route_id": None,
                "selected_route_class": None,
                "evidence_substitution_allowed": False,
                "lifecycle": {
                    "resolution_state": "RESOLVED_LIFECYCLE_CHANGE",
                    "lifecycle_state": "NO_LONGER_LISTED",
                    "source_active_expected": False,
                    "evidence_substitution_allowed": False,
                    "report_sha256": "c" * 64,
                },
            }
        )
    return {
        "source_resolution_state": "HEALTHY" if include_science else "DEGRADED",
        "active_source_availability_state": "HEALTHY",
        "active_evidence_payload_availability_state": "HEALTHY",
        "source_availability_state": "HEALTHY",
        "evidence_payload_availability_state": "HEALTHY",
        "lifecycle_transition_count": 1 if include_science else 0,
        "report_sha256": "a" * 64,
        "counts": {
            "AVAILABLE_PRIMARY": 0,
            "AVAILABLE_FALLBACK": 1,
            "UNRESOLVED": 1 if include_science else 0,
            "RETIRED": 0,
            "RESOLVED_LIFECYCLE_CHANGE": 1 if include_science else 0,
            "PRIMARY_DEGRADED": len(reports),
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
        cls.accountability = build_projection(tables["sources"], tables["source_monitors"])
        cls.registry = build_development_registry(inputs)

    def test_route_and_lifecycle_resolution_restores_active_health(self) -> None:
        routes = route_report()
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=failed_run(),
            route_resilience=routes,
        )
        self.assertEqual(report["state"], DEGRADED)
        self.assertEqual(report["engineering_state"], ENGINEERING_READY)
        self.assertEqual(report["source_resolution_state"], HEALTHY)
        self.assertEqual(report["active_source_availability_state"], HEALTHY)
        self.assertEqual(report["active_evidence_payload_availability_state"], HEALTHY)
        self.assertEqual(report["source_availability_state"], HEALTHY)
        self.assertEqual(report["route_resilience"]["lifecycle_resolved_failed_source_ids"], ["SRC-PR-015"])
        codes = {warning["code"] for warning in report["warnings"]}
        self.assertIn("TYPED_SOURCE_FAILURES_PRESENT", codes)
        self.assertIn("TYPED_SOURCE_FAILURES_RESOLVED_BY_REGISTERED_ROUTE", codes)
        self.assertIn("TYPED_SOURCE_FAILURES_RESOLVED_AS_LIFECYCLE_CHANGE", codes)
        self.assertNotIn("FAILED_SOURCES_UNRESOLVED_AFTER_REGISTERED_RESOLUTION", codes)
        verify_health_report(
            report,
            accountability=self.accountability,
            development_registry=self.registry,
            run=failed_run(),
            route_resilience=routes,
        )

    def test_missing_failed_source_keeps_resolution_degraded(self) -> None:
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=failed_run(),
            route_resilience=route_report(include_science=False),
        )
        self.assertEqual(report["engineering_state"], ENGINEERING_READY)
        self.assertEqual(report["source_resolution_state"], DEGRADED)
        self.assertEqual(
            report["route_resilience"]["unresolved_failed_source_ids"],
            ["SRC-PR-015"],
        )
        self.assertIn(
            "FAILED_SOURCES_UNRESOLVED_AFTER_REGISTERED_RESOLUTION",
            {warning["code"] for warning in report["warnings"]},
        )

    def test_duplicate_route_source_report_is_blocking(self) -> None:
        routes = route_report()
        routes["source_reports"].append(copy.deepcopy(routes["source_reports"][0]))
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=failed_run(),
            route_resilience=routes,
        )
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "ROUTE_RESILIENCE_DUPLICATE_SOURCE_REPORT",
            {alert["code"] for alert in report["blocking_alerts"]},
        )

    def test_invalid_top_level_resolution_state_is_blocking(self) -> None:
        routes = route_report()
        routes["source_resolution_state"] = "UNKNOWN"
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=failed_run(),
            route_resilience=routes,
        )
        self.assertEqual(report["engineering_state"], ENGINEERING_BLOCKED)
        self.assertIn(
            "SOURCE_RESOLUTION_STATE_INVALID",
            {alert["code"] for alert in report["blocking_alerts"]},
        )

    def test_route_report_tampering_changes_health_digest_and_verification(self) -> None:
        routes = route_report()
        report = evaluate_health(
            accountability=self.accountability,
            development_registry=self.registry,
            run=failed_run(),
            route_resilience=routes,
        )
        tampered_routes = copy.deepcopy(routes)
        tampered_routes["report_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "does not match recomputed"):
            verify_health_report(
                report,
                accountability=self.accountability,
                development_registry=self.registry,
                run=failed_run(),
                route_resilience=tampered_routes,
            )


if __name__ == "__main__":
    unittest.main()
