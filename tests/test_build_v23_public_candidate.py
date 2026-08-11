from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "verify_v23_public_candidate.py"
SPEC = importlib.util.spec_from_file_location("verify_v23_public_candidate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)
RELEASE = ROOT / "releases" / "data-v0.2.0-v2.3.0-dev-candidate"


class V23PublicCandidateTests(unittest.TestCase):
    def test_full_candidate_verifies(self) -> None:
        verify.verify_all(RELEASE)

    def test_population_contract(self) -> None:
        outcomes = json.loads((RELEASE / "records/comparisons/source-outcomes.json").read_text())
        comparisons = json.loads((RELEASE / "records/comparisons/comparison-index.json").read_text())
        self.assertEqual(len(outcomes["records"]), 25)
        self.assertEqual(len(comparisons["records"]), 21)
        self.assertTrue(all(row["finding_effect"] == "NONE" for row in outcomes["records"]))

    def test_authority_boundary(self) -> None:
        descriptor = json.loads((RELEASE / "release-descriptor.json").read_text())
        self.assertEqual(descriptor["governance_state"], "DEFERRED")
        self.assertFalse(descriptor["governance_layer_applied"])
        self.assertEqual(descriptor["canonical_publication_state"], "NOT_AUTHORIZED")
        self.assertFalse(descriptor["canonical_successor_written"])
        self.assertFalse(descriptor["assessment_mutation_performed"])
        self.assertFalse(descriptor["current_pointer_updated"])

    def test_delta_is_hash_bound_not_reconstructed(self) -> None:
        delta = json.loads((RELEASE / "records/delta/development-delta-reference.json").read_text())
        self.assertEqual(delta["operation_count"], 14)
        self.assertFalse(delta["operation_bodies_in_this_repository"])
        self.assertEqual(delta["operation_body_state"], "WITHHELD_FROM_PUBLIC_PROJECTION")
        self.assertFalse(delta["substantive_authority"])

    def test_failures_remain_operational(self) -> None:
        outcomes = json.loads((RELEASE / "records/comparisons/source-outcomes.json").read_text())
        failures = {
            row["source_id"]: row
            for row in outcomes["records"]
            if row["outcome_type"] not in {"CONTENT_CHANGED", "NO_CHANGE"}
        }
        self.assertEqual(set(failures), {"SRC-0041", "SRC-0115", "SRC-0124", "SRC-14-007"})
        self.assertTrue(all(row["finding_effect"] == "NONE" for row in failures.values()))

    def test_predecessor_is_reference_not_rewrite(self) -> None:
        state = json.loads((RELEASE / "records/programme-state.json").read_text())
        self.assertEqual(state["predecessor"]["release_tag"], "data-v0.1.0-public-governing")
        self.assertTrue(state["predecessor"]["immutable"])
        self.assertFalse(state["current_pointer_updated"])


if __name__ == "__main__":
    unittest.main()
