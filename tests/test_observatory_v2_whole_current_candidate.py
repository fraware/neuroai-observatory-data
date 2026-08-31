from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_observatory_v2_whole_current_candidate as candidate


class WholeCurrentCandidateTests(unittest.TestCase):
    def test_cross_family_reconciliation(self) -> None:
        result = candidate.build()
        rec = result["reconciliation"]

        self.assertEqual(rec["slice_blocker_count"], 0, rec["slice_blockers"])
        self.assertEqual(rec["conflicting_duplicate_identity_count"], 0, rec["family_identity_conflicts"])
        self.assertEqual(rec["unresolved_source_reference_count"], 0, rec["unresolved_source_references"])
        self.assertEqual(rec["unresolved_observation_reference_count"], 0, rec["unresolved_observation_references"])
        self.assertEqual(rec["effective_source_count_mismatch_count"], 0)
        self.assertEqual(rec["effective_state_mismatch_count"], 0, rec["effective_state_reconciliation"])
        self.assertEqual(rec["repeated_delta_double_counting_count"], 0)
        self.assertTrue(rec["mechanically_clean"])
        self.assertFalse(rec["global_completeness_claim"])
        self.assertFalse(rec["scientific_validity_claim"])
        self.assertFalse(rec["canonical_successor_ready"])

    def test_exact_current_family_counts(self) -> None:
        result = candidate.build()
        counts = result["reconciliation"]["family_counts"]
        self.assertEqual(counts["sources"], 248)
        self.assertEqual(counts["observations"], 248)
        self.assertEqual(counts["entities"], 243)
        self.assertEqual(counts["assertions"], 3107)
        self.assertEqual(counts["relationships"], 23)
        self.assertEqual(counts["events"], 11)
        self.assertEqual(counts["change_candidates"], 9)
        self.assertEqual(counts["reopening_decisions"], 6)
        self.assertEqual(result["reconciliation"]["comparison_provenance_record_count"], 2)
        self.assertEqual(result["reconciliation"]["successor_lineage_record_count"], 1)

    def test_effective_state_is_reconstructed_not_expanded_from_counts(self) -> None:
        effective = candidate.build()["reconciliation"]["effective_state_reconciliation"]
        self.assertEqual(effective["mismatch_count"], 0, effective)
        self.assertEqual(effective["materialized_counts"]["organizations"], 153)
        self.assertEqual(effective["materialized_counts"]["current_verified_organizations"], 150)
        self.assertEqual(effective["materialized_counts"]["capital_and_ownership_events"], 7)
        self.assertEqual(effective["materialized_counts"]["representative_model_records"], 15)
        self.assertEqual(effective["materialized_counts"]["supplier_dependency_relationships"], 10)
        self.assertEqual(effective["materialized_counts"]["source_records"], 248)
        self.assertEqual(effective["declared_completed_system_assessments"], 4)
        self.assertEqual(effective["assessment_object_materialization_state"], "NOT_EXPANDED_FROM_SUMMARY_COUNT")

    def test_candidate_output_is_deterministic(self) -> None:
        first = candidate.build()
        second = candidate.build()
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            json.dumps(second, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ma = candidate.write_candidate(first, Path(a))
            mb = candidate.write_candidate(second, Path(b))
            self.assertEqual(ma["manifest_sha256"], mb["manifest_sha256"])
            self.assertFalse(ma["canonical_successor_ready"])


if __name__ == "__main__":
    unittest.main()
