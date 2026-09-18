from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_patstat_baseline_a.py"


class PatstatBaselineAIndependentAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=ROOT,
        )
        cls.audit = json.loads(result.stdout)

    def test_exact_source_and_row_bindings(self) -> None:
        self.assertEqual(
            self.audit["source_binding"]["source_main_commit"],
            "825f8702cda66dd6b9740f563d2e8fb3e7144f5f",
        )
        rows = self.audit["row_integrity"]
        self.assertEqual(rows["strata_rows"], 9)
        self.assertEqual(rows["judged_rows"], 235_738)
        self.assertEqual(rows["gold_rows"], 333)
        self.assertEqual(rows["pool_rows"], 118_629)
        self.assertEqual(rows["judged_rows"], rows["judged_unique_ids"])
        self.assertEqual(rows["gold_rows"], rows["gold_unique_ids"])
        self.assertEqual(rows["pool_rows"], rows["pool_unique_ids"])
        self.assertTrue(rows["gold_ids_all_present_in_judged"])
        self.assertTrue(rows["gold_cheap_labels_match_judged"])

    def test_public_export_does_not_support_four_missing_label_rows(self) -> None:
        verdicts = self.audit["verdict_integrity"]
        self.assertEqual(verdicts["rows_with_missing_neuro_or_ml"], 2)
        self.assertEqual(
            {
                row["docdb_family_id"]
                for row in verdicts["missing_label_rows"]
            },
            {"50277015", "55911278"},
        )
        self.assertEqual(verdicts["rows_with_nonstandard_raw_verdict"], 13)
        self.assertIn(
            "91282470",
            {
                row["docdb_family_id"]
                for row in verdicts["nonstandard_raw_verdict_rows"]
            },
        )
        self.assertFalse(
            verdicts["analysis_statement_four_rows_carried_missing_supported_by_export"]
        )

    def test_reported_agreement_metrics_are_disambiguated(self) -> None:
        agreement = self.audit["reread_agreement"]
        self.assertAlmostEqual(
            agreement["cohen_kappa_three_class"],
            0.469085111494529,
            places=12,
        )
        self.assertTrue(agreement["analysis_kappa_0_469_reproduced_as_three_class"])
        binary = agreement["binary_label2_vs_rest"]
        self.assertEqual(
            (binary["tp"], binary["fp"], binary["fn"], binary["tn"]),
            (51, 53, 5, 224),
        )
        self.assertAlmostEqual(binary["precision"], 0.49038461538461536)
        self.assertAlmostEqual(binary["recall"], 0.9107142857142857)
        self.assertAlmostEqual(
            binary["cohen_kappa_binary"],
            0.5360780169100693,
        )

    def test_headline_points_reproduce_but_visible_uncertainty_does_not(self) -> None:
        points = self.audit["point_estimate_reproduction"]
        self.assertAlmostEqual(points["cheap_only_corpus"], 99_719.78842171596)
        self.assertAlmostEqual(points["public_script_corpus"], 49_671.276601037025)
        self.assertAlmostEqual(points["public_script_pool"], 33_277.42584399009)
        self.assertAlmostEqual(points["public_script_recall"], 0.669953102097145)
        self.assertAlmostEqual(points["public_script_missed"], 16_393.850757046937)

        uncertainty = self.audit["uncertainty_audit"]
        self.assertAlmostEqual(
            uncertainty["public_script_first_stage_sd_only"],
            3_235.101682815138,
        )
        self.assertEqual(uncertainty["readme_reported_interval"], [40_256, 57_854])
        self.assertEqual(uncertainty["analysis_reported_interval"], [41_512, 58_192])
        self.assertFalse(
            uncertainty["readme_interval_reproduced_by_visible_variance"]
        )
        self.assertFalse(
            uncertainty["analysis_interval_reproduced_by_visible_variance"]
        )
        self.assertFalse(uncertainty["full_interval_validated"])
        self.assertFalse(uncertainty["recall_ratio_uncertainty_validated"])

    def test_second_stage_and_pool_sensitivity_remain_fail_closed(self) -> None:
        second = self.audit["second_stage_allocation"]
        self.assertFalse(
            second["exact_selection_probabilities_reconstructible_from_public_extract"]
        )
        self.assertFalse(second["design_unbiasedness_validated"])

        allocation = {
            (row["stratum"], row["cheap_label"]): row
            for row in second["observed_allocation_by_original_stratum_and_cheap_label"]
        }
        self.assertEqual(allocation[("1", "1")]["second_stage_count"], 6)
        self.assertEqual(allocation[("1", "1")]["first_stage_count"], 6)
        self.assertEqual(allocation[("5", "1")]["second_stage_count"], 0)
        self.assertEqual(allocation[("6", "1")]["second_stage_count"], 0)
        self.assertEqual(allocation[("7", "1")]["second_stage_count"], 0)
        self.assertEqual(allocation[("8", "1")]["second_stage_count"], 0)

        sensitivity = self.audit["sensitivity_only_not_validated_estimands"]
        self.assertAlmostEqual(
            sensitivity["preserve_original_binary_cell_before_pool_mask"]["pool"],
            33_780.40117912892,
        )
        self.assertAlmostEqual(
            sensitivity["preserve_original_binary_cell_before_pool_mask"][
                "recall_using_public_corpus"
            ],
            0.6800791823905662,
        )
        self.assertAlmostEqual(
            sensitivity["preserve_original_three_class_correction_cells"]["pool"],
            33_772.01941569191,
        )
        self.assertAlmostEqual(
            sensitivity["borderline_as_relevant_under_public_algorithm"]["corpus"],
            49_901.021209663166,
        )

    def test_cluster_field_is_mechanically_inconsistent_with_cluster_ids(self) -> None:
        cluster = self.audit["pool_cluster_field_audit"]
        self.assertEqual(cluster["blank_cluster_rows"], 96_239)
        self.assertEqual(cluster["nonblank_cluster_rows"], 22_390)
        self.assertEqual(cluster["values_in_declared_cluster_id_range_0_20"], 0)
        self.assertEqual(cluster["cluster_equals_same_row_docdb_family_id"], 6_400)
        self.assertTrue(cluster["nonblank_values_form_contiguous_file_prefix"])
        self.assertEqual(
            cluster["offset_matches_to_docdb_family_id"],
            {"0": 6400, "1": 1290, "2": 299, "3": 8432, "4": 5969},
        )
        self.assertFalse(cluster["estimator_consumes_cluster_field"])

    def test_low_score_zero_event_calculation_is_explicitly_assumption_bound(self) -> None:
        low = self.audit["low_score_zero_event_sensitivity"]
        self.assertIn("simple-random sampling", low["assumption"])
        self.assertAlmostEqual(
            low["sum_of_stratum_upper_counts"],
            6_838.468898921577,
        )

    def test_no_scientific_or_governance_authority_is_created(self) -> None:
        disposition = self.audit["scientific_disposition"]
        self.assertEqual(
            disposition["state"],
            "PARTIAL_INDEPENDENT_AUDIT_BLOCKED_ON_MISSING_PROVENANCE",
        )
        self.assertTrue(disposition["public_point_estimates_mechanically_reproduced"])
        for key in (
            "historical_estimator_fully_reconstructed",
            "design_unbiasedness_established",
            "reported_intervals_validated",
            "retrieval_recall_uncertainty_validated",
            "human_reference_standard_established",
            "global_population_generalization_established",
            "rights_clearance_established",
        ):
            self.assertFalse(disposition[key], key)

        authority = self.audit["authority"]
        for key in (
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "canonical_scientific_finding",
            "canonical_s2_authority",
            "publication_authority",
        ):
            self.assertFalse(authority[key], key)
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
