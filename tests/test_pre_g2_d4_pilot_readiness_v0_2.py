from __future__ import annotations

import copy
import unittest

from scripts.evaluate_pre_g2_d4_pilot_readiness_v0_2 import (
    READINESS_POLICY_ID,
    evaluate_pilot_readiness,
)
from tests.test_pre_g2_d4_sampling_calibration import _pilot_report


DISPOSITIONS = ("ABSTAIN", "BORDERLINE", "EXCLUDE", "INCLUDE")


def _sync_confusion_matrix(report: dict[str, object]) -> dict[str, object]:
    agreement = int(report["primary_secondary_exact_agreement_count"])
    matrix = {
        primary: {secondary: 0 for secondary in DISPOSITIONS}
        for primary in DISPOSITIONS
    }
    matrix["INCLUDE"]["INCLUDE"] = agreement
    matrix["INCLUDE"]["EXCLUDE"] = 60 - agreement
    report["primary_secondary_confusion_matrix"] = matrix
    return report


def _successor_report() -> dict[str, object]:
    return _sync_confusion_matrix(_pilot_report())


class D4PilotReadinessV02Tests(unittest.TestCase):
    def test_raw_agreement_is_reported_but_not_an_automated_gate(self) -> None:
        report = _successor_report()
        report["primary_secondary_exact_agreement_count"] = 30
        report["adjudicated_disagreement_count"] = 27
        report["unresolved_disagreement_count"] = 3
        _sync_confusion_matrix(report)
        result = evaluate_pilot_readiness(report)
        self.assertTrue(result["quantitative_gate_passed"])
        self.assertEqual(result["state"], "READY_FOR_HUMAN_CALIBRATION_DISPOSITION")
        self.assertEqual(result["agreement_count"], 30)
        self.assertEqual(result["agreement_rate"], 0.5)
        self.assertEqual(result["readiness_policy_id"], READINESS_POLICY_ID)
        self.assertNotIn(
            "PRIMARY_SECONDARY_EXACT_AGREEMENT_BELOW_48_OF_60",
            result["violations"],
        )

    def test_unresolved_disagreement_ceiling_remains_fail_closed(self) -> None:
        report = _pilot_report()
        report["primary_secondary_exact_agreement_count"] = 30
        report["adjudicated_disagreement_count"] = 26
        report["unresolved_disagreement_count"] = 4
        report["resolved_disposition_counts"]["BORDERLINE"] = 18
        _sync_confusion_matrix(report)
        result = evaluate_pilot_readiness(report)
        self.assertFalse(result["quantitative_gate_passed"])
        self.assertIn("UNRESOLVED_DISAGREEMENT_ABOVE_3_OF_60", result["violations"])

    def test_confusion_matrix_must_account_for_60_and_match_agreement(self) -> None:
        report = _successor_report()
        report["primary_secondary_confusion_matrix"]["INCLUDE"]["EXCLUDE"] -= 1
        with self.assertRaisesRegex(ValueError, "exactly 60"):
            evaluate_pilot_readiness(report)

        report = _successor_report()
        report["primary_secondary_confusion_matrix"]["INCLUDE"]["INCLUDE"] -= 1
        report["primary_secondary_confusion_matrix"]["EXCLUDE"]["INCLUDE"] += 1
        with self.assertRaisesRegex(ValueError, "diagonal"):
            evaluate_pilot_readiness(report)

    def test_successor_report_shape_and_protocol_id_remain_required(self) -> None:
        report = _pilot_report()
        report["protocol_id"] = "WRONG"
        with self.assertRaisesRegex(ValueError, "protocol_id"):
            evaluate_pilot_readiness(report)

    def test_authority_remains_non_authorizing(self) -> None:
        result = evaluate_pilot_readiness(copy.deepcopy(_successor_report()))
        self.assertFalse(result["authority"]["reviewer_competence_established"])
        self.assertFalse(result["authority"]["benchmark_adequacy_established"])
        self.assertFalse(result["authority"]["g2_passed"])
        self.assertFalse(result["authority"]["canonical_s2_authority"])
        self.assertFalse(result["authority"]["publication_authority"])
        self.assertEqual(result["authority"]["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
