from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AMENDMENT_PATH = ROOT / "docs" / "migration" / "phase4-repository-split-destination-amendment-v0.2.json"


class Phase4DestinationAmendmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.amendment = json.loads(AMENDMENT_PATH.read_text(encoding="utf-8"))

    def test_predecessor_and_collision_evidence_are_exact(self) -> None:
        predecessor = self.amendment["predecessor_manifest"]
        self.assertEqual(predecessor["git_blob_sha"], "9bc48a821ebc8d08896d94be4caf6143a8f3cf95")
        self.assertEqual(predecessor["source_head_sha"], "ee51f6fcbd679d2b0ed5aeb4593424543201e496")

        evidence = self.amendment["workbench_boundary_evidence"]
        self.assertEqual(evidence["base_commit_sha"], "2349a1f0125ceadbe4f6802e3686963e74360b7f")
        self.assertEqual(evidence["existing_module_path"], "src/neuroai_workbench/observatory.py")
        self.assertEqual(evidence["existing_module_git_blob_sha"], "afc278709468e6391f1b27178adf1acf47204c74")
        self.assertEqual(evidence["corrected_runtime_package_root"], "src/neuroai_workbench/science_observatory/")

    def test_all_overrides_are_unique_and_source_bound(self) -> None:
        overrides = self.amendment["overrides"]
        self.assertEqual(self.amendment["override_count"], 22)
        self.assertEqual(len(overrides), 22)
        self.assertEqual(len({item["source_path"] for item in overrides}), 22)
        self.assertEqual(len({item["destination_path"] for item in overrides}), 22)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", item["source_git_blob_sha"]) for item in overrides))

    def test_runtime_destinations_use_noncolliding_package(self) -> None:
        runtime = [item for item in self.amendment["overrides"] if item["source_path"].startswith("scripts/")]
        tests = [item for item in self.amendment["overrides"] if item["source_path"].startswith("tests/")]

        self.assertEqual(len(runtime), 11)
        self.assertEqual(len(tests), 11)
        self.assertTrue(
            all(item["destination_path"].startswith("src/neuroai_workbench/science_observatory/") for item in runtime)
        )
        self.assertTrue(all(item["destination_path"].startswith("tests/unit/science_observatory/") for item in tests))
        self.assertFalse(any("src/neuroai_workbench/observatory/science/" in item["destination_path"] for item in runtime))

    def test_configuration_and_provenance_boundaries_fail_closed(self) -> None:
        policy = self.amendment["destination_policy"]
        self.assertIn("explicit versioned inputs", policy["configuration_rule"])
        self.assertIn("not assume", policy["configuration_rule"])
        self.assertIn("source Git blob identity", policy["provenance_rule"])
        self.assertFalse(self.amendment["migration_executed"])
        self.assertFalse(self.amendment["destination_blob_identities_bound"])
        self.assertIn("does not move files", self.amendment["authority_boundary"])


if __name__ == "__main__":
    unittest.main()
