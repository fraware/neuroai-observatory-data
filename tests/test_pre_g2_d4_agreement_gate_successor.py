from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "curation" / "PRE_G2_D4_PILOT_READINESS_POLICY_2026-09-12_v0.2.json"
DISPOSITION = ROOT / "curation" / "HUMAN_D4_AGREEMENT_GATE_DISPOSITION_2026-09-12_v0.1.json"
EXECUTOR = ROOT / "scripts" / "execute_pre_g2_d4_final_selection_v0_2.py"


class D4AgreementGateSuccessorBindingTests(unittest.TestCase):
    def test_human_disposition_is_exact_and_non_authorizing(self) -> None:
        disposition = json.loads(DISPOSITION.read_text(encoding="utf-8"))
        self.assertEqual(disposition["governing_issue"], 242)
        self.assertEqual(disposition["source"]["comment_id"], 5646135687)
        self.assertEqual(disposition["source"]["github_login"], "fraware")
        self.assertEqual(
            disposition["decision"],
            "APPROVE_REMOVE_RAW_EXACT_AGREEMENT_FROM_AUTOMATED_GATE",
        )
        self.assertFalse(disposition["authority"]["g2_passed"])
        self.assertFalse(disposition["authority"]["publication_authority"])

    def test_successor_preserves_raw_agreement_as_human_review_diagnostic(self) -> None:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        aggregate = policy["aggregate_contract"]
        self.assertFalse(aggregate["raw_agreement_is_automated_gate"])
        self.assertTrue(aggregate["raw_agreement_count_remains_required"])
        self.assertTrue(aggregate["raw_agreement_rate_remains_reported"])
        self.assertIn("RAW_EXACT_AGREEMENT_COUNT_AND_RATE", policy["mandatory_human_review"])
        self.assertEqual(policy["automated_readiness_controls"]["maximum_unresolved_disagreement_count"], 3)

    def test_real_composed_entrypoint_uses_successor_evaluator(self) -> None:
        source = EXECUTOR.read_text(encoding="utf-8")
        self.assertIn("scripts.evaluate_pre_g2_d4_pilot_readiness_v0_2", source)
        self.assertNotIn(
            "from scripts.evaluate_pre_g2_d4_pilot_readiness import",
            source,
        )


if __name__ == "__main__":
    unittest.main()
