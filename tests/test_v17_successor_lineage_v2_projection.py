from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/project_v17_successor_lineage_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v17_successor_lineage_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V17SuccessorLineageProjectionTests(unittest.TestCase):
    def test_compact_successor_reconciles_without_reemitting_v16_delta(self) -> None:
        result = module.project()
        rec = result["reconciliation"]
        self.assertEqual(rec["top_level_section_count"], 10)
        self.assertEqual(rec["unknown_top_level_sections"], [])
        self.assertEqual(rec["missing_expected_top_level_sections"], [])
        self.assertTrue(rec["repeated_v16_delta_equal"])
        self.assertEqual(rec["repeated_v16_delta_new_identity_count"], 0)
        self.assertEqual(rec["carried_reopening_decision_count"], 5)
        self.assertEqual(rec["carried_reopening_mismatch_count"], 0)
        self.assertEqual(rec["new_successor_reopening_decision_count"], 1)
        self.assertEqual(rec["source_delta_new_unique_source_count_provenance_only"], 12)
        self.assertEqual(rec["fabricated_source_record_count"], 0)
        self.assertEqual(rec["assessment_reinterpretation_count"], 0)
        self.assertEqual(rec["count_expansion_to_entities_count"], 0)
        self.assertEqual(rec["predecessor_payload_roundtrip_failure_count"], 0)
        self.assertFalse(rec["canonical_successor_ready"])

    def test_reopening_transition_is_exact(self) -> None:
        row = module.project()["successor_lineage"]
        transition = row["reopening_transition"]
        self.assertEqual(transition["predecessor_decision_id"], "ROP-16-001")
        self.assertEqual(transition["predecessor_state"], "REOPEN_REQUIRED")
        self.assertEqual(transition["successor_decision_id"], "ROP-17-001")
        self.assertEqual(transition["successor_state"], "REOPENING_EXECUTED_RECORD_UPDATED_OPEN_CONDITIONS")
        self.assertEqual(row["new_reopening_decision"]["decision_id"], "ROP-17-001")

    def test_assessment_state_is_preserved_not_recomputed(self) -> None:
        row = module.project()["successor_lineage"]
        assessment = row["assessment_successor_state"]
        self.assertEqual(assessment["assessment_id"], "PRIMA-PUBLIC-2026-001")
        self.assertEqual(assessment["assessment_version"], "v4.2.1")
        self.assertEqual(assessment["target_level"], "CL-4")
        self.assertEqual(assessment["decision"], "CL-4_NOT_ESTABLISHED")
        self.assertEqual(assessment["open_p0_gaps"], 19)
        self.assertEqual(row["bounded_system_record"]["conformance_state"], "CL-4_NOT_ESTABLISHED")

    def test_source_delta_counts_do_not_create_sources(self) -> None:
        row = module.project()["successor_lineage"]
        source_delta = row["source_delta_provenance"]
        self.assertEqual(source_delta["assessment_sources_registered"], 15)
        self.assertEqual(source_delta["new_unique_source_records_relative_to_v1_6"], 12)
        self.assertEqual(source_delta["reused_v1_6_source_ids"], ["SRC-16-001", "SRC-16-002"])
        self.assertEqual(row["repeated_v16_delta_state"], "VERIFIED_REFERENCE_NOT_REEMITTED")


if __name__ == "__main__":
    unittest.main()
