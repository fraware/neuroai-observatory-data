from __future__ import annotations

import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "curation" / "PATSTAT_BASELINE_A_SCIENTIFIC_STATUS_2026-09-05_v0.1.json"
EXTRACT = ROOT / "patent-evidence-extract"
README = EXTRACT / "README.md"

SOURCE_COMMIT = "2a09c02f7ec313a1da929c94a2b4ed6e0e88beb8"
APPROVED_D1_DISPOSITIONS = {"INCLUDE", "EXCLUDE", "BORDERLINE", "ABSTAIN"}


class PatstatBaselineAScientificStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.control = json.loads(CONTROL.read_text(encoding="utf-8"))
        cls.readme = README.read_text(encoding="utf-8")

    def test_baseline_is_exactly_bound_and_non_authoritative(self) -> None:
        self.assertEqual(
            self.control["status"],
            "PRE_G2_PRELIMINARY_MODEL_ANCHORED_BASELINE",
        )
        self.assertEqual(self.control["governing_issue"], 220)
        self.assertEqual(self.control["rights_issue"], 210)
        self.assertEqual(self.control["source"]["source_commit"], SOURCE_COMMIT)
        self.assertEqual(len(self.control["source"]["source_artifact_git_blobs"]), 8)
        authority = self.control["authority"]
        self.assertFalse(authority["g0_passed"])
        self.assertFalse(authority["g2_passed"])
        self.assertFalse(authority["g5_passed"])
        self.assertFalse(authority["canonical_scientific_finding"])
        self.assertFalse(authority["global_completeness_claim"])
        self.assertFalse(authority["rights_clearance"])
        self.assertFalse(authority["canonical_s2_authority"])
        self.assertFalse(authority["publication_authority"])
        self.assertEqual(authority["assessment_effect"], "NONE")

    def test_stratified_sampling_frame_matches_extract(self) -> None:
        with (EXTRACT / "strata.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 9)
        self.assertEqual(sum(int(row["N_families"]) for row in rows), 69_273_903)
        self.assertEqual(sum(int(row["n_judged"]) for row in rows), 235_738)
        for row in rows[-3:]:
            self.assertEqual(int(row["N_families"]), int(row["n_judged"]))

    def test_second_stage_is_model_reread_not_human_gold(self) -> None:
        with (EXTRACT / "gold_labels.csv").open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(
                reader.fieldnames,
                ["docdb_family_id", "stratum", "gold_neuro", "cheap_neuro"],
            )
            rows = list(reader)
        self.assertEqual(len(rows), 333)
        self.assertFalse(self.control["reference_standard"]["human_gold_present"])
        self.assertFalse(
            self.control["reference_standard"]["second_stage_is_independent_human_reference_standard"]
        )
        self.assertFalse(self.control["reference_standard"]["may_be_used_as_d3_human_gold"])

    def test_historical_boundary_is_not_silently_equated_to_d1(self) -> None:
        semantics = self.control["historical_boundary_semantics"]
        self.assertEqual(semantics["headline_binary_estimand"], "historical label 2 only")
        self.assertEqual(
            semantics["borderline_treatment_in_reproduce_py"],
            "mapped to 0 in the headline binary estimand",
        )
        self.assertFalse(semantics["approved_d1_equivalence_established"])
        self.assertEqual(set(semantics["approved_d1_allowed_dispositions"]), APPROVED_D1_DISPOSITIONS)
        reproduce = (EXTRACT / "reproduce.py").read_text(encoding="utf-8")
        self.assertIn('REL = lambda v: 1.0 if v == "2" else 0.0', reproduce)

    def test_public_reproducer_still_reconstructs_only_the_bound_point_estimates(self) -> None:
        result = subprocess.run(
            [sys.executable, str(EXTRACT / "reproduce.py")],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertIn("49,671", result.stdout)
        self.assertIn("33,277", result.stdout)
        self.assertIn("67.0%", result.stdout)
        self.assertIn("16,394", result.stdout)
        uncertainty = self.control["uncertainty_audit"]
        self.assertTrue(uncertainty["public_reproduce_py_reproduces_point_estimates"])
        self.assertFalse(uncertainty["public_reproduce_py_prints_or_reconstructs_reported_interval"])
        self.assertFalse(uncertainty["second_stage_correction_variance_independently_certified_from_public_extract"])
        self.assertFalse(uncertainty["query_pool_recall_ratio_uncertainty_independently_certified_from_public_extract"])

    def test_programme_roles_and_rights_remain_separate(self) -> None:
        integration = self.control["programme_integration"]
        self.assertEqual(integration["d3_patent_benchmark_status"], "NOT_D3")
        self.assertEqual(integration["d5_classifier_evaluation_status"], "NOT_G5_VALIDATED")
        self.assertTrue(integration["requires_human_d3_before_g5"])
        self.assertFalse(integration["may_replace_human_adjudication"])
        rights = self.control["rights_boundary"]
        self.assertFalse(rights["rights_clearance_established"])
        self.assertFalse(rights["scientific_validation_implies_redistribution_rights"])
        self.assertFalse(rights["redistribution_rights_imply_scientific_validity"])

    def test_cluster_field_question_remains_open_without_estimator_overclaim(self) -> None:
        questions = {item["id"]: item for item in self.control["data_integrity_questions"]}
        cluster = questions["POOL_FRAME_CLUSTER_FIELD"]
        self.assertEqual(cluster["status"], "OPEN")
        self.assertIn("does not invalidate", cluster["estimator_effect"])
        with (EXTRACT / "clusters.csv").open(newline="", encoding="utf-8") as handle:
            cluster_ids = {int(row["cluster"]) for row in csv.DictReader(handle)}
        self.assertEqual(cluster_ids, set(range(21)))

    def test_readme_exposes_scientific_status_and_keeps_rights_warning(self) -> None:
        self.assertIn("Scientific status — preliminary Baseline A", self.readme)
        self.assertIn("Issue #220", self.readme)
        self.assertIn("not human gold labels", self.readme)
        self.assertIn("Rights status — review open", self.readme)
        self.assertIn("Issue #210", self.readme)


if __name__ == "__main__":
    unittest.main()
