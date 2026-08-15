from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from source_lifecycle_overlay import load_json, sha256

MANIFEST = ROOT / "curation/lifecycle_monitoring_transition_manifest_v0.1.json"
OVERLAY = ROOT / "curation/source_lifecycle_monitoring_overlay_v0.1.json"
WATCHES = ROOT / "curation/successor_discovery_watches_v0.1.json"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class MonitoringTransitionManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_json(MANIFEST)
        cls.overlay = load_json(OVERLAY)
        cls.watches = load_json(WATCHES)

    def test_manifest_hash_is_exact(self) -> None:
        unsigned = copy.deepcopy(self.manifest)
        observed = unsigned.pop("manifest_sha256")
        self.assertRegex(observed, _HEX64)
        self.assertEqual(observed, sha256(unsigned))

    def test_accountability_closes_without_manufactured_monitor(self) -> None:
        accountability = self.manifest["accountability"]
        self.assertEqual(accountability["effective_source_count"], 248)
        self.assertEqual(accountability["governing_predecessor_monitor_count"], 224)
        self.assertEqual(accountability["active_extension_monitor_count"], 2)
        self.assertEqual(accountability["active_monitor_count"], 226)
        self.assertEqual(accountability["coverage_fraction"], 1.0)
        self.assertEqual(
            accountability["active_monitor_count"]
            + accountability["manual_on_change_source_count"]
            + accountability["archival_static_source_count"]
            + accountability["lifecycle_resolved_source_count"],
            accountability["effective_source_count"],
        )
        self.assertEqual(
            accountability["governing_predecessor_monitor_count"]
            + accountability["active_extension_monitor_count"],
            accountability["active_monitor_count"],
        )

    def test_lifecycle_binding_matches_overlay_exactly(self) -> None:
        transition = self.manifest["lifecycle_transition"]
        overlay_transition = self.overlay["transitions"][0]
        self.assertEqual(transition["source_id"], "SRC-PR-015")
        self.assertEqual(transition["lifecycle_state"], "NO_LONGER_LISTED")
        self.assertEqual(transition["monitoring_state"], "LIFECYCLE_RESOLVED_ARCHIVAL")
        self.assertFalse(transition["active_recurring_monitor"])
        self.assertEqual(transition["overlay_sha256"], self.overlay["overlay_sha256"])
        self.assertEqual(
            transition["transition_sha256"], overlay_transition["transition_sha256"]
        )
        self.assertEqual(
            transition["successor_discovery_watch_id"],
            overlay_transition["successor_discovery_watch_id"],
        )

    def test_successor_discovery_binding_is_candidate_only(self) -> None:
        discovery = self.manifest["successor_discovery"]
        watch = self.watches["watches"][0]
        self.assertEqual(discovery["watch_id"], watch["watch_id"])
        self.assertEqual(discovery["official_host"], watch["official_host"])
        self.assertTrue(discovery["candidate_only"])
        self.assertFalse(discovery["automatic_source_registration"])
        self.assertFalse(discovery["automatic_assessment_mutation"])

    def test_pretransition_evidence_is_exactly_bound(self) -> None:
        evidence = self.manifest["pretransition_live_evidence"]
        overlay_evidence = self.overlay["transitions"][0]["live_evidence"]
        self.assertEqual(
            evidence["workflow_run_id"], overlay_evidence["workflow_run_id"]
        )
        self.assertEqual(
            evidence["workflow_head_sha"], overlay_evidence["workflow_head_sha"]
        )
        self.assertRegex(evidence["workflow_head_sha"], _HEX40)
        self.assertEqual(
            evidence["route_policy_sha256"], overlay_evidence["route_policy_sha256"]
        )
        self.assertEqual(
            evidence["route_report_sha256"], overlay_evidence["route_report_sha256"]
        )
        self.assertEqual(
            evidence["lifecycle_report_sha256"],
            overlay_evidence["lifecycle_report_sha256"],
        )
        self.assertEqual(evidence["source_accountability_coverage"], 1.0)
        self.assertEqual(evidence["target_execution_coverage"], 1.0)
        self.assertEqual(evidence["resume_additional_transport_sends"], 0)

    def test_workbench_dependency_is_exact_commit(self) -> None:
        workbench = self.manifest["workbench"]
        self.assertEqual(workbench["repository"], "fraware/neuroai-workbench")
        self.assertEqual(
            workbench["commit_sha"], "428b4e8d797c0729bc4f36678daec88711688689"
        )
        self.assertRegex(workbench["commit_sha"], _HEX40)

    def test_authority_and_mutation_flags_remain_false(self) -> None:
        metadata = self.manifest["metadata"]
        self.assertEqual(
            metadata["status"],
            "DEVELOPMENT_MONITORING_TRANSITION_MANIFEST_NOT_CANONICAL",
        )
        for field in (
            "automatic_source_registration",
            "automatic_source_mutation",
            "automatic_assessment_mutation",
            "canonical_promotion_authorized",
            "publication_authorized",
            "human_governance_performed",
        ):
            self.assertIs(metadata[field], False, field)

    def test_tampered_manifest_hash_is_detected(self) -> None:
        tampered = json.loads(json.dumps(self.manifest))
        tampered["accountability"]["active_monitor_count"] = 227
        unsigned = copy.deepcopy(tampered)
        observed = unsigned.pop("manifest_sha256")
        self.assertNotEqual(observed, sha256(unsigned))


if __name__ == "__main__":
    unittest.main()
