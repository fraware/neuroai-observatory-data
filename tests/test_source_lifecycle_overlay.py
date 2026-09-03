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
from source_lifecycle_overlay import (
    DEFAULT_LIFECYCLE_OVERLAY,
    DEFAULT_ROUTE_POLICY,
    build_active_route_policy,
    load_json,
    sha256,
    verify_lifecycle_overlay,
)


class SourceLifecycleOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        inputs = load_inputs(
            (ROOT / "releases/data-v0.1.0-public-governing/records").resolve(),
            supplemental_dir=(ROOT / "supplemental_records").resolve(),
        )
        tables = build_tables(inputs)
        cls.source_ids = {
            str(row["record_id"]) for row in tables["sources"] if row.get("record_id")
        }
        cls.monitor_ids = {
            str(row["record_id"])
            for row in tables["source_monitors"]
            if row.get("record_id")
        }
        cls.route_policy = load_json(DEFAULT_ROUTE_POLICY)
        cls.overlay = load_json(DEFAULT_LIFECYCLE_OVERLAY)

    def _verify(self, overlay=None, route_policy=None):
        return verify_lifecycle_overlay(
            overlay or self.overlay,
            route_policy or self.route_policy,
            effective_source_ids=self.source_ids,
            governing_monitor_source_ids=self.monitor_ids,
        )

    def test_exact_overlay_is_valid_and_source_bound(self) -> None:
        transitions = self._verify()
        self.assertEqual(set(transitions), {"SRC-PR-015"})
        transition = transitions["SRC-PR-015"]
        self.assertEqual(transition["lifecycle_state"], "NO_LONGER_LISTED")
        self.assertEqual(transition["monitoring_state"], "LIFECYCLE_RESOLVED_ARCHIVAL")
        self.assertFalse(transition["source_active_expected"])
        self.assertFalse(transition["evidence_substitution_allowed"])
        self.assertEqual(
            transition["successor_discovery_watch_id"], "DISC-SCIENCE-CAREERS-001"
        )
        evidence = transition["live_evidence"]
        self.assertEqual(evidence["workflow_run_id"], 31841215730)
        self.assertEqual(
            evidence["workflow_head_sha"], "3ad4e30ad80082ae9a86c45c43c512110ff1bcce"
        )
        self.assertEqual(evidence["primary_http_status"], 404)
        self.assertEqual(evidence["identity_equivalent_http_statuses"], [404])
        self.assertEqual(evidence["publisher_listing_http_status"], 200)
        self.assertFalse(evidence["publisher_listing_identity_present"])

    def test_transition_is_non_mutating_and_does_not_register_successor(self) -> None:
        self.assertFalse(self.overlay["metadata"]["automatic_source_mutation"])
        self.assertFalse(self.overlay["metadata"]["automatic_assessment_mutation"])
        transition = self.overlay["transitions"][0]
        self.assertEqual(transition["source_id"], "SRC-PR-015")
        self.assertFalse(transition["evidence_substitution_allowed"])
        self.assertNotIn("successor_source_id", transition)

    def test_active_route_policy_excludes_lifecycle_source_only(self) -> None:
        transitions = self._verify()
        active = build_active_route_policy(self.route_policy, transitions)
        ids = {row["source_id"] for row in active["sources"]}
        self.assertEqual(ids, {"SRC-0064", "SRC-14-019", "SRC-PR-002"})
        self.assertEqual(
            active["metadata"]["excluded_lifecycle_source_ids"], ["SRC-PR-015"]
        )
        self.assertEqual(active["metadata"]["source_count"], 3)

    def test_active_route_policy_is_exactly_bound_to_parent_policy(self) -> None:
        transitions = self._verify()
        active = build_active_route_policy(self.route_policy, transitions)
        self.assertEqual(
            active["metadata"]["status"], "DERIVED_ACTIVE_ROUTE_POLICY_NOT_CANONICAL"
        )
        self.assertEqual(
            active["metadata"]["derived_from_policy_sha256"], sha256(self.route_policy)
        )

    def test_route_policy_drift_fails_closed(self) -> None:
        policy = copy.deepcopy(self.route_policy)
        policy["sources"][1]["url"] += "?changed=1"
        with self.assertRaisesRegex(ValueError, "route-policy hash mismatch"):
            self._verify(route_policy=policy)

    def test_transition_hash_tampering_fails_closed(self) -> None:
        overlay = copy.deepcopy(self.overlay)
        overlay["transitions"][0]["monitoring_state"] = "RECURRING"
        with self.assertRaisesRegex(ValueError, "unsupported monitoring state"):
            self._verify(overlay=overlay)

    def test_live_evidence_hash_drift_fails_closed(self) -> None:
        overlay = copy.deepcopy(self.overlay)
        overlay["transitions"][0]["live_evidence"]["route_report_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self._verify(overlay=overlay)

    def test_404_without_publisher_listing_success_fails_closed(self) -> None:
        overlay = copy.deepcopy(self.overlay)
        overlay["transitions"][0]["live_evidence"]["publisher_listing_http_status"] = (
            503
        )
        with self.assertRaisesRegex(ValueError, "successful publisher listing"):
            self._verify(overlay=overlay)

    def test_identity_present_fails_closed(self) -> None:
        overlay = copy.deepcopy(self.overlay)
        overlay["transitions"][0]["live_evidence"][
            "publisher_listing_identity_present"
        ] = True
        with self.assertRaisesRegex(ValueError, "exact identity absence"):
            self._verify(overlay=overlay)

    def test_nxdomain_style_primary_status_cannot_lifecycle_resolve(self) -> None:
        # Disposition C: durable DNS non-existence is not lifecycle-overlay evidence.
        # Overlay requires primary 404/410 + publisher listing; NXDOMAIN has neither.
        overlay = copy.deepcopy(self.overlay)
        overlay["transitions"][0]["live_evidence"]["primary_http_status"] = None
        with self.assertRaisesRegex(ValueError, "requires primary 404/410 evidence"):
            self._verify(overlay=overlay)

    def test_route_policy_does_not_register_parking_host_for_src_14_021(self) -> None:
        # Disposition C: sonafrica.org is a non-identity parking page and must not be
        # registered as IDENTITY_EQUIVALENT / official failover.
        serialized = (
            ROOT / "curation" / "source_route_resilience_v0.1.json"
        ).read_text(encoding="utf-8")
        self.assertNotIn("sonafrica.org", serialized)
        self.assertNotIn("SRC-14-021", serialized)
        for source in self.route_policy["sources"]:
            for route in source.get("retrieval_routes") or []:
                host = str(route.get("official_host") or "").lower()
                self.assertNotEqual(host, "sonafrica.org")
                self.assertNotIn("sonafrica.org", str(route.get("url") or "").lower())

    def test_governing_monitor_cannot_be_suppressed(self) -> None:
        overlay = copy.deepcopy(self.overlay)
        transition = overlay["transitions"][0]
        transition["source_id"] = next(iter(sorted(self.monitor_ids)))
        with self.assertRaisesRegex(
            ValueError, "cannot suppress governing predecessor monitor"
        ):
            self._verify(overlay=overlay)

    def test_unknown_effective_source_fails_closed(self) -> None:
        overlay = copy.deepcopy(self.overlay)
        overlay["transitions"][0]["source_id"] = "SRC-NOT-REAL"
        with self.assertRaisesRegex(ValueError, "unknown effective source"):
            self._verify(overlay=overlay)


if __name__ == "__main__":
    unittest.main()
