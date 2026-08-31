from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace('.', '_'), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


control = _load("project_v16_control_state_to_v2.py")
aggregate = _load("reconcile_v16_semantic_coverage.py")


class V16ControlCoverageTests(unittest.TestCase):
    def test_top_level_sections_are_fail_closed_and_fully_accounted(self) -> None:
        result = control.project()
        rec = result["reconciliation"]
        self.assertEqual(rec["unknown_top_level_sections"], [])
        self.assertEqual(rec["missing_expected_top_level_sections"], [])
        self.assertEqual(rec["top_level_section_count"], rec["accounted_top_level_section_count"])
        self.assertEqual(rec["control_record_count"], 4)
        self.assertEqual(rec["baseline_canonical_sha256"], "00985fa168b26c4e02df485895d728ee30191aea436b4e3956c60657e2ffc3be")
        self.assertIs(rec["baseline_immutable"], True)
        self.assertEqual(rec["predecessor_payload_roundtrip_failure_count"], 0)
        self.assertEqual(rec["withheld_claim_loss_count"], 0)
        self.assertEqual(rec["withheld_to_positive_claim_fabrication_count"], 0)
        self.assertEqual(rec["refresh_time_to_event_time_fabrication_count"], 0)
        self.assertFalse(rec["canonical_successor_ready"])

    def test_withheld_claims_are_preserved_as_control_state(self) -> None:
        result = control.project()
        row = next(r for r in result["control_records"] if r["section"] == "withheld_claims")
        self.assertEqual(row["value"], row["predecessor"]["payload"])
        self.assertTrue(row["value"])
        self.assertEqual(row["record_family"], "RELEASE_CONTROL_PROVENANCE")

    def test_aggregate_v16_reconciliation_has_no_mechanical_blockers(self) -> None:
        result = aggregate.reconcile()
        self.assertEqual(result["slice_count"], 5)
        self.assertEqual(result["mechanical_blocker_count"], 0)
        self.assertEqual(result["mechanical_blockers"], [])
        self.assertTrue(result["all_known_v16_top_level_sections_accounted"])
        self.assertFalse(result["canonical_successor_ready"])


if __name__ == "__main__":
    unittest.main()
