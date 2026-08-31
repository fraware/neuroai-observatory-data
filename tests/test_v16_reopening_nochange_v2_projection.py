from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/project_v16_reopening_nochange_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v16_reopening_nochange_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V16ReopeningNoChangeProjectionTests(unittest.TestCase):
    def test_exact_reconciliation(self) -> None:
        result = module.project()
        rec = result["reconciliation"]
        self.assertEqual(rec["input_reopening_decision_count"], 6)
        self.assertEqual(rec["projected_reopening_decision_count"], 6)
        self.assertEqual(
            rec["decision_counts"],
            {
                "METADATA_UPDATE_ONLY": 1,
                "NO_REOPENING_TRIGGER_IDENTIFIED": 3,
                "REOPEN_REQUIRED": 1,
                "UPDATE_REQUIRED_NO_ASSESSMENT_REOPEN": 1,
            },
        )
        self.assertEqual(rec["empty_basis_decision_count"], 3)
        self.assertEqual(rec["basis_reference_count"], 5)
        self.assertEqual(rec["unresolved_accepted_basis_reference_count"], 0)
        self.assertEqual(rec["input_no_change_confirmation_count"], 2)
        self.assertEqual(rec["projected_no_change_confirmation_count"], 2)
        self.assertEqual(rec["no_change_source_reference_count"], 2)
        self.assertEqual(rec["no_change_observation_reference_count"], 2)
        for key in (
            "predecessor_payload_roundtrip_failure_count",
            "basis_loss_count",
            "required_action_loss_count",
            "decision_time_fabrication_count",
            "no_change_source_reference_loss_count",
            "no_change_observation_reference_loss_count",
            "world_absence_claim_fabrication_count",
        ):
            self.assertEqual(rec[key], 0, (key, rec[key]))
        self.assertFalse(rec["canonical_successor_ready"])

    def test_empty_basis_remains_empty_and_non_mutating(self) -> None:
        result = module.project()
        empty = [r for r in result["reopening_decisions"] if not r["basis_record_ids"]]
        self.assertEqual(len(empty), 3)
        self.assertTrue(all(r["basis_resolution_state"] == "EMPTY_PREDECESSOR_BASIS" for r in empty))
        self.assertTrue(all(r["record_state"] == "NONCANONICAL_MIGRATED_CANDIDATE" for r in empty))
        self.assertTrue(all(r["decided_at"] is None for r in empty))

    def test_no_change_is_bounded_comparison_provenance(self) -> None:
        result = module.project()
        rows = result["comparison_provenance"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({sid for row in rows for sid in row["source_ids"]}, {"SRC-16-011", "SRC-16-012"})
        self.assertTrue(all(row["world_absence_claim"] is False for row in rows))
        self.assertTrue(all(row["comparison_scope"] == "BOUNDED_PREDECESSOR_SOURCE_COMPARISON" for row in rows))
        self.assertTrue(all(row["observed_at"]["precision"] == "TIMESTAMP" for row in rows))

    def test_predecessor_payloads_are_exact(self) -> None:
        refresh = json.loads(module.DEFAULT_REFRESH.read_text(encoding="utf-8"))
        result = module.project()
        by_id = {r["decision_id"]: r for r in result["reopening_decisions"]}
        for predecessor in refresh["reopening_decisions"]:
            self.assertEqual(by_id[predecessor["decision_id"]]["predecessor"]["payload"], predecessor)
        projected_nochange = result["comparison_provenance"]
        self.assertEqual([r["predecessor"]["payload"] for r in projected_nochange], refresh["no_change_confirmations"])


if __name__ == "__main__":
    unittest.main()
