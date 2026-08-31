from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/project_v14_provenance_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v14_provenance_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V14ProvenanceProjectionTests(unittest.TestCase):
    def test_exact_reconciliation(self) -> None:
        result = module.project()["reconciliation"]
        self.assertEqual(result["input_record_count"], 48)
        self.assertEqual(result["projected_record_count"], 48)
        self.assertEqual(result["release_control_record_count"], 3)
        self.assertEqual(result["organization_resolution_count"], 26)
        self.assertEqual(result["regional_expansion_count"], 13)
        self.assertEqual(result["data_quality_finding_count"], 6)
        self.assertEqual(result["source_linked_record_count"], 32)
        self.assertEqual(result["source_unresolved_record_count"], 7)
        self.assertEqual(result["source_not_recorded_record_count"], 6)
        self.assertEqual(result["source_not_applicable_control_record_count"], 3)
        self.assertEqual(result["organization_resolution_exact_date_count"], 26)
        self.assertEqual(result["regional_add_count"], 10)
        self.assertEqual(result["regional_reverify_count"], 3)
        self.assertEqual(result["data_quality_high_count"], 3)
        self.assertEqual(result["data_quality_medium_count"], 3)
        for key in (
            "identity_mismatch_count",
            "predecessor_payload_roundtrip_failure_count",
            "claim_boundary_loss_count",
            "source_reference_loss_count",
            "dangling_source_reference_count",
            "source_linkage_fabrication_count",
            "temporal_precision_fabrication_count",
            "knowledge_time_fabrication_count",
            "invented_predecessor_field_value_count",
        ):
            self.assertEqual(result[key], 0, (key, result[key]))
        self.assertFalse(result["canonical_successor_ready"])

    def test_control_records_are_not_promoted_to_world_observations(self) -> None:
        rows = module.project()["records"]
        controls = [
            row
            for row in rows
            if row["provenance_kind"] in {"RELEASE_METADATA", "METHODOLOGY", "COVERAGE"}
        ]
        self.assertEqual(len(controls), 3)
        self.assertTrue(all(row["observed_at"] is None for row in controls))
        self.assertTrue(
            all(
                row["source_linkage_state"] == "SOURCE_LINKAGE_NOT_APPLICABLE_CONTROL_RECORD"
                for row in controls
            )
        )

    def test_source_less_organization_resolution_is_explicit(self) -> None:
        rows = module.project()["records"]
        unresolved = [
            row
            for row in rows
            if row["provenance_kind"] == "ORGANIZATION_RESOLUTION" and not row["source_ids"]
        ]
        self.assertEqual(len(unresolved), 7)
        self.assertTrue(
            all(
                row["source_linkage_state"] == "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED"
                for row in unresolved
            )
        )

    def test_data_quality_is_not_an_assessment_failure(self) -> None:
        rows = module.project()["records"]
        findings = [row for row in rows if row["provenance_kind"] == "DATA_QUALITY_FINDING"]
        self.assertEqual({row["normalized_details"]["severity"] for row in findings}, {"HIGH", "MEDIUM"})
        self.assertTrue(all(row["action_or_disposition"] is None for row in findings))
        self.assertTrue(all("assessment outcome" in row["authority_boundary"] for row in findings))


if __name__ == "__main__":
    unittest.main()
