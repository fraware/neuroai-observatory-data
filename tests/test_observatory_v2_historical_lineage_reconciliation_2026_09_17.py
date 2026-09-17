from __future__ import annotations

import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from current_source_namespace import materialize_effective_source_namespace

CONTROL = ROOT / "curation" / "OBSERVATORY_V2_HISTORICAL_LINEAGE_RECONCILIATION_2026-09-17_v0.1.json"
EXPECTED_ISSUES = {54, 55, 56, 58, 59, 61, 63, 65, 67, 69, 71, 73, 75, 77, 79, 81, 83, 85, 87}
ALLOWED = {
    "SATISFIED_BY_CURRENT_ARCHITECTURE",
    "SUPERSEDED_BY_STRICTER_CURRENT_ARCHITECTURE",
    "SUPERSEDED_BY_CHANGED_GOVERNANCE_MODEL",
}


class ObservatoryV2HistoricalLineageReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.control = json.loads(CONTROL.read_text(encoding="utf-8"))

    def test_exact_historical_issue_set_and_unique_dispositions(self) -> None:
        rows = self.control["historical_issue_dispositions"]
        self.assertEqual(len(rows), len(EXPECTED_ISSUES))
        self.assertEqual({row["issue"] for row in rows}, EXPECTED_ISSUES)
        self.assertEqual(len({row["issue"] for row in rows}), len(rows))
        self.assertTrue(all(row["disposition"] in ALLOWED for row in rows))
        self.assertTrue(all(row["current_evidence"] for row in rows))
        self.assertTrue(all(row["reason"].strip() for row in rows))

    def test_summary_matches_issue_rows(self) -> None:
        rows = self.control["historical_issue_dispositions"]
        counts = Counter(row["disposition"] for row in rows)
        summary = self.control["summary"]
        self.assertEqual(summary["historical_issue_count"], len(rows))
        self.assertEqual(summary["satisfied_by_current_architecture_count"], counts["SATISFIED_BY_CURRENT_ARCHITECTURE"])
        self.assertEqual(summary["superseded_by_stricter_current_architecture_count"], counts["SUPERSEDED_BY_STRICTER_CURRENT_ARCHITECTURE"])
        self.assertEqual(summary["superseded_by_changed_governance_model_count"], counts["SUPERSEDED_BY_CHANGED_GOVERNANCE_MODEL"])

    def test_historical_feature_stack_is_not_rewritten_as_main(self) -> None:
        history = self.control["historical_feature_stack"]
        self.assertEqual(history["whole_current_candidate_pull_request"], 86)
        self.assertFalse(history["whole_current_candidate_merged_to_observatory_main"])
        self.assertEqual(history["six_domain_review_pull_request"], 88)
        self.assertFalse(history["six_domain_review_merged"])
        self.assertFalse(self.control["summary"]["historical_feature_stack_promoted_to_current_main"])
        self.assertFalse(self.control["summary"]["current_architecture_recreates_historical_candidate_shape"])

    def test_gate_a_identity_and_authority_boundary(self) -> None:
        gate = self.control["current_architecture"]["gate_a_execution"]
        self.assertEqual(gate["decision"], "PASS_REPRESENTATIONAL_MIGRATION_MECHANICALLY_COMPLETE")
        self.assertEqual(gate["physical_predecessor_record_occurrences"], 842)
        self.assertEqual(gate["leaf_field_occurrences"], 11664)
        self.assertEqual(gate["native_object_count"], 403)
        self.assertEqual(gate["native_source_count"], 236)
        for key in (
            "unmapped_required_predecessor_fields",
            "invented_values",
            "claim_boundary_losses",
            "source_reference_losses",
            "history_lineage_losses",
            "temporal_precision_losses",
            "cross_class_id_collision_count",
        ):
            self.assertEqual(gate[key], 0, key)
        self.assertTrue(gate["representational_scope_complete"])
        self.assertFalse(gate["native_v2_materialization_complete"])
        self.assertFalse(gate["release_authorized"])

    def test_248_source_namespace_is_distinct_from_gate_a_native_source_count(self) -> None:
        namespace = materialize_effective_source_namespace(ROOT)
        declared = self.control["current_architecture"]["current_controlled_source_namespace"]
        self.assertEqual(namespace["materialized_source_count"], 248)
        self.assertEqual(namespace["family_counts"], declared["family_counts"])
        self.assertEqual(declared["materialized_source_count"], 248)
        self.assertEqual(declared["relation_to_gate_a_native_sources"], "SEPARATE_CONTROLLED_DISCOVERY_NAMESPACE_VIEW")
        self.assertEqual(self.control["current_architecture"]["gate_a_execution"]["native_source_count"], 236)
        self.assertFalse(namespace["global_completeness_claim"])
        self.assertFalse(namespace["migration_performed"])
        self.assertFalse(namespace["canonical_mutation_performed"])
        self.assertFalse(namespace["publication_authority_created"])

    def test_no_authority_created_by_reconciliation(self) -> None:
        summary = self.control["summary"]
        self.assertTrue(summary["current_gate_a_passed"])
        for key in (
            "current_gate_a_authorizes_s2_release",
            "current_s2_candidate_created_by_this_reconciliation",
            "canonical_s2_mutation_performed",
            "publication_performed",
            "assessment_mutation_performed",
        ):
            self.assertFalse(summary[key], key)
        governance = self.control["current_architecture"]["governance_model"]
        self.assertFalse(governance["gate_a_human_domain_review_required"])
        self.assertTrue(governance["candidate_authorization_publication_separate"])


if __name__ == "__main__":
    unittest.main()
