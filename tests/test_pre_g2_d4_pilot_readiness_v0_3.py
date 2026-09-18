from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.build_pre_g2_d4_pilot_readiness_aggregate_v0_2 import (
    build_pilot_readiness_aggregate,
)
from scripts.evaluate_pre_g2_d4_pilot_readiness_v0_3 import (
    D4PilotReadinessError,
    READINESS_POLICY_ID,
    evaluate_pilot_readiness,
)
from tests.test_pre_g2_d4_pilot_execution import (
    PILOT_KEY,
    _write_pilot,
)


class D4PilotReadinessV03Tests(unittest.TestCase):
    def _aggregate(self) -> dict[str, object]:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        manifest, _ = _write_pilot(root)
        return build_pilot_readiness_aggregate(
            manifest,
            root / "packets",
            PILOT_KEY,
        )

    def tearDown(self) -> None:
        tempdir = getattr(self, "tempdir", None)
        if tempdir is not None:
            tempdir.cleanup()

    def test_successor_binds_complete_four_way_confusion_matrix(self) -> None:
        aggregate = self._aggregate()
        matrix = aggregate["primary_secondary_confusion_matrix"]
        self.assertEqual(
            sum(
                count
                for row in matrix.values()
                for count in row.values()
            ),
            60,
        )
        self.assertEqual(
            sum(matrix[label][label] for label in matrix),
            aggregate["primary_secondary_exact_agreement_count"],
        )
        self.assertEqual(matrix["INCLUDE"]["EXCLUDE"], 12)

        result = evaluate_pilot_readiness(aggregate)
        self.assertTrue(result["quantitative_gate_passed"])
        self.assertEqual(result["readiness_policy_id"], READINESS_POLICY_ID)
        self.assertEqual(result["include_exclude_reversal_count"], 12)
        self.assertEqual(
            result["borderline_or_abstain_disagreement_count"],
            0,
        )
        self.assertTrue(
            result["full_confusion_matrix_required_for_human_calibration"]
        )
        self.assertFalse(result["authority"]["g2_passed"])

    def test_missing_matrix_fails_closed(self) -> None:
        aggregate = self._aggregate()
        aggregate.pop("primary_secondary_confusion_matrix")
        with self.assertRaises(D4PilotReadinessError):
            evaluate_pilot_readiness(aggregate)

    def test_matrix_total_must_equal_exactly_60(self) -> None:
        aggregate = self._aggregate()
        matrix = aggregate["primary_secondary_confusion_matrix"]
        matrix["INCLUDE"]["EXCLUDE"] += 1
        with self.assertRaisesRegex(
            D4PilotReadinessError,
            "exactly 60",
        ):
            evaluate_pilot_readiness(aggregate)

    def test_matrix_diagonal_must_match_reported_agreement(self) -> None:
        aggregate = self._aggregate()
        matrix = aggregate["primary_secondary_confusion_matrix"]
        matrix["INCLUDE"]["INCLUDE"] -= 1
        matrix["INCLUDE"]["EXCLUDE"] += 1
        with self.assertRaisesRegex(
            D4PilotReadinessError,
            "confusion-matrix diagonal",
        ):
            evaluate_pilot_readiness(aggregate)

    def test_boolean_matrix_cell_is_rejected_as_non_integer(self) -> None:
        aggregate = self._aggregate()
        tampered = copy.deepcopy(aggregate)
        matrix = tampered["primary_secondary_confusion_matrix"]
        matrix["ABSTAIN"]["ABSTAIN"] = False
        with self.assertRaisesRegex(
            D4PilotReadinessError,
            "must be an integer",
        ):
            evaluate_pilot_readiness(tampered)


if __name__ == "__main__":
    unittest.main()
