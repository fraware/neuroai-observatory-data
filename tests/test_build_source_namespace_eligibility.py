from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "source_namespace_eligibility.py"
SPEC = importlib.util.spec_from_file_location("source_namespace_eligibility", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
eligibility = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eligibility)

MANIFEST_PATH = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"
POLICY_PATH = ROOT / "curation" / "source_namespace_eligibility_policy_v0.1.json"


def _load() -> tuple[dict[str, object], dict[str, object]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    return manifest, policy


class SourceNamespaceEligibilityTests(unittest.TestCase):
    def test_policy_is_explicit_noncanonical_and_valid(self) -> None:
        _, policy = _load()
        eligibility.validate_policy(policy)
        self.assertEqual(policy["status"], "NONCANONICAL_POLICY")
        self.assertEqual(
            policy["precedence"],
            "SOURCE_NAMESPACE_ELIGIBILITY_OVERRIDES_MECHANICAL_REGISTRATION_ACTION",
        )
        self.assertIn("CONTROLLED ADJUDICATION", policy["ineligible_evidence_markers"])

    def test_braingate_controlled_adjudication_fails_namespace_gate(self) -> None:
        manifest, policy = _load()
        proposal = next(row for row in manifest["proposals"] if row["proposal_id"] == "LEGACY-SRC-PROP-033")
        result = eligibility.evaluate_proposal(proposal, policy)
        self.assertEqual(proposal["action"], "REGISTER_NEW_SOURCE")
        self.assertEqual(result["effective_action"], "CURATION_REQUIRED")
        self.assertFalse(result["source_namespace_eligible"])
        self.assertEqual(result["eligibility_reason"], "ASSESSMENT_LOCAL_CONTROLLED_ADJUDICATION")
        self.assertEqual(result["matched_ineligible_markers"], ["CONTROLLED ADJUDICATION"])
        self.assertTrue(result["checksum_is_provenance_only"])
        self.assertEqual([row["evidence_id"] for row in proposal["linked_evidence"]], ["EV-T15-012"])
        self.assertIsNone(proposal["normalized_public_url"])
        self.assertTrue(proposal["checksum"])

    def test_effective_action_counts_correct_mechanical_candidate_layer(self) -> None:
        manifest, policy = _load()
        evaluations = eligibility.evaluate_manifest(manifest, policy)
        counts = Counter(row["effective_action"] for row in evaluations)
        self.assertEqual(
            counts,
            {
                "REGISTER_NEW_SOURCE": 32,
                "REGISTER_MISSING_EXPLICIT_SOURCE": 1,
                "CURATION_REQUIRED": 2,
            },
        )
        by_id = {row["proposal_id"]: row for row in evaluations}
        exact_key_eligible_evidence = sum(
            len(proposal["linked_evidence"])
            for proposal in manifest["proposals"]
            if proposal["action"] == "REGISTER_NEW_SOURCE"
            and by_id[proposal["proposal_id"]]["source_namespace_eligible"]
        )
        self.assertEqual(exact_key_eligible_evidence, 34)

    def test_fda_ev15_remains_curation_required(self) -> None:
        manifest, policy = _load()
        proposal = next(row for row in manifest["proposals"] if row["proposal_id"] == "LEGACY-SRC-PROP-034")
        result = eligibility.evaluate_proposal(proposal, policy)
        self.assertEqual(proposal["action"], "CURATION_REQUIRED")
        self.assertEqual(result["effective_action"], "CURATION_REQUIRED")
        self.assertFalse(result["source_namespace_eligible"])
        self.assertEqual([row["evidence_id"] for row in proposal["linked_evidence"]], ["EV-15"])

    def test_prima_missing_explicit_source_remains_namespace_eligible(self) -> None:
        manifest, policy = _load()
        proposal = next(row for row in manifest["proposals"] if row["proposal_id"] == "LEGACY-SRC-PROP-035")
        result = eligibility.evaluate_proposal(proposal, policy)
        self.assertEqual(result["effective_action"], "REGISTER_MISSING_EXPLICIT_SOURCE")
        self.assertTrue(result["source_namespace_eligible"])
        self.assertEqual(proposal["requested_source_id"], "SRC-PR-011")

    def test_marker_blocks_future_controlled_adjudication_without_explicit_override(self) -> None:
        _, policy = _load()
        synthetic = {
            "proposal_id": "LEGACY-SRC-PROP-999",
            "action": "REGISTER_NEW_SOURCE",
            "linked_evidence": [
                {
                    "system": "Synthetic",
                    "assessment_version": "v0",
                    "evidence_id": "EV-X",
                    "evidence_type": "CONTROLLED ADJUDICATION",
                    "evidence_class": None,
                    "source_label": "Assessment-local record",
                    "publication_state": "Controlled assessment record",
                }
            ],
        }
        result = eligibility.evaluate_proposal(synthetic, policy)
        self.assertEqual(result["effective_action"], "CURATION_REQUIRED")
        self.assertFalse(result["source_namespace_eligible"])
        self.assertEqual(result["eligibility_rule"], "INELIGIBLE_ASSESSMENT_LOCAL_EVIDENCE_CLASS")

    def test_conflicting_override_cannot_make_ineligible_evidence_registerable(self) -> None:
        manifest, policy = _load()
        mutated = copy.deepcopy(policy)
        mutated["action_overrides"]["LEGACY-SRC-PROP-033"]["effective_action"] = "REGISTER_NEW_SOURCE"
        proposal = next(row for row in manifest["proposals"] if row["proposal_id"] == "LEGACY-SRC-PROP-033")
        with self.assertRaisesRegex(eligibility.NamespaceEligibilityError, "conflicts with ineligible evidence marker"):
            eligibility.evaluate_proposal(proposal, mutated)

    def test_policy_checkpoint_records_candidate_vs_eligible_distinction(self) -> None:
        _, policy = _load()
        checkpoint = policy["expected_checkpoint"]
        self.assertEqual(checkpoint["exact_key_candidate_evidence_count"], 35)
        self.assertEqual(checkpoint["source_namespace_eligible_exact_key_evidence_count"], 34)
        self.assertEqual(checkpoint["prospective_newly_joinable_evidence_count"], 35)
        self.assertEqual(checkpoint["projected_matched_evidence_count"], 50)
        self.assertEqual(checkpoint["projected_unresolved_evidence_count"], 2)
        self.assertEqual(checkpoint["projected_added_source_identity_count"], 33)
        self.assertEqual(checkpoint["projected_effective_source_count"], 281)


if __name__ == "__main__":
    unittest.main()
