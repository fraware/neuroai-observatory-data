from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "curation" / "PATSTAT_PUBLIC_EXTRACT_RIGHTS_REVIEW_2026-09-05_v0.1.json"
README = ROOT / "patent-evidence-extract" / "README.md"
EXTRACT = ROOT / "patent-evidence-extract"

EXPECTED_PUBLIC_FILES = {
    "patent-evidence-extract/README.md",
    "patent-evidence-extract/abstracts_sample.csv",
    "patent-evidence-extract/clusters.csv",
    "patent-evidence-extract/gold_labels.csv",
    "patent-evidence-extract/judged_sample.csv",
    "patent-evidence-extract/pool_frame.csv",
    "patent-evidence-extract/reproduce.py",
    "patent-evidence-extract/strata.csv",
}

REQUIRED_ATTRIBUTION = (
    "This product contains data sourced from EPO databases, © European Patent Organisation"
)


class PatstatRightsBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.review = json.loads(REVIEW.read_text(encoding="utf-8"))
        cls.readme = README.read_text(encoding="utf-8")

    def test_review_is_fail_closed_and_non_authoritative(self) -> None:
        self.assertEqual(self.review["status"], "RIGHTS_REVIEW_OPEN_FAIL_CLOSED")
        self.assertEqual(self.review["governing_issue"], 210)
        self.assertFalse(self.review["rights_evidence"]["exact_license_order_terms_verified_in_repository"])
        self.assertFalse(self.review["rights_evidence"]["exact_written_redistribution_authorization_verified"])
        self.assertFalse(self.review["rights_evidence"]["legal_conclusion_made"])
        self.assertFalse(self.review["authority"]["rights_clearance"])
        self.assertFalse(self.review["authority"]["canonical_authority"])
        self.assertFalse(self.review["authority"]["publication_authority"])
        self.assertFalse(self.review["authority"]["mutation_authority"])
        self.assertEqual(self.review["authority"]["assessment_effect"], "NONE")

    def test_every_current_public_extract_file_has_a_disposition(self) -> None:
        recorded = {row["path"] for row in self.review["file_dispositions"]}
        actual = {
            f"patent-evidence-extract/{path.name}"
            for path in EXTRACT.iterdir()
            if path.is_file()
        }
        self.assertEqual(actual, EXPECTED_PUBLIC_FILES)
        self.assertEqual(recorded, EXPECTED_PUBLIC_FILES)

    def test_no_file_is_claimed_cleared(self) -> None:
        for row in self.review["file_dispositions"]:
            self.assertFalse(row["publication_clearance_claimed"], row["path"])

    def test_direct_abstract_text_remains_high_priority_unresolved(self) -> None:
        row = next(
            item
            for item in self.review["file_dispositions"]
            if item["path"] == "patent-evidence-extract/abstracts_sample.csv"
        )
        self.assertTrue(row["direct_epo_text_present"])
        self.assertEqual(row["rights_state"], "HIGH_PRIORITY_RIGHTS_UNRESOLVED")

    def test_public_readme_contains_required_epo_attribution_and_open_review_warning(self) -> None:
        self.assertIn(REQUIRED_ATTRIBUTION, self.readme)
        self.assertIn("Rights status — review open", self.readme)
        self.assertIn("Issue #210", self.readme)
        self.assertIn("public presence must not", self.readme)
        self.assertIn("every row-level field is cleared for redistribution", self.readme)

    def test_review_cannot_be_misread_as_deletion_or_history_rewrite_authority(self) -> None:
        boundary = self.review["programme_boundary"]
        self.assertFalse(boundary["history_rewrite_authorized"])
        self.assertFalse(boundary["deletion_authorized"])
        self.assertFalse(boundary["may_be_cited_as_rights_cleared_public_programme_evidence"])
        self.assertFalse(boundary["may_authorize_s2_publication"])
        self.assertFalse(boundary["may_authorize_assessment_mutation"])
        self.assertGreaterEqual(len(boundary["required_next_evidence"]), 4)


if __name__ == "__main__":
    unittest.main()
