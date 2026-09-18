from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = (
    ROOT
    / "curation"
    / "PATSTAT_PUBLIC_EXTRACT_RIGHTS_REVIEW_2026-09-18_PUBLIC_EVIDENCE_SUCCESSOR_v0.2.json"
)
README = ROOT / "patent-evidence-extract" / "README.md"
EXTRACT = ROOT / "patent-evidence-extract"

EXPECTED_PUBLIC_FILES = {
    "patent-evidence-extract/ANALYSIS.md",
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
        cls.fields = {
            row["path"]: row for row in cls.review["field_dispositions"]
        }

    def test_review_is_a_fail_closed_successor(self) -> None:
        self.assertEqual(self.review["status"], "RIGHTS_REVIEW_OPEN_FAIL_CLOSED")
        self.assertEqual(self.review["governing_issue"], 210)
        self.assertEqual(
            self.review["predecessor"]["git_blob_sha"],
            "d4c837833ca53e94243228d6964370623e14a07b",
        )
        evidence = self.review["rights_evidence"]
        self.assertFalse(
            evidence["exact_autumn_2025_order_acceptance_terms_verified_in_repository"]
        )
        self.assertFalse(evidence["exact_amendments_in_force_for_delivery_verified"])
        self.assertFalse(
            evidence["exact_written_redistribution_authorization_verified"]
        )
        self.assertFalse(evidence["legal_or_licensor_determination_verified"])
        self.assertFalse(evidence["legal_conclusion_made"])

        authority = self.review["authority"]
        self.assertFalse(authority["rights_clearance"])
        self.assertFalse(authority["canonical_authority"])
        self.assertFalse(authority["publication_authority"])
        self.assertFalse(authority["mutation_authority"])
        self.assertEqual(authority["assessment_effect"], "NONE")

    def test_every_public_extract_file_has_a_field_level_disposition(self) -> None:
        actual = {
            f"patent-evidence-extract/{path.name}"
            for path in EXTRACT.iterdir()
            if path.is_file()
        }
        self.assertEqual(actual, EXPECTED_PUBLIC_FILES)
        self.assertEqual(set(self.fields), EXPECTED_PUBLIC_FILES)
        for path, row in self.fields.items():
            self.assertFalse(row["publication_clearance_claimed"], path)

    def test_direct_text_and_mixed_row_level_files_are_explicitly_separated(self) -> None:
        abstracts = self.fields["patent-evidence-extract/abstracts_sample.csv"]
        self.assertEqual(
            set(abstracts["fields"]["direct_or_high_priority_source_linked"]),
            {"docdb_family_id", "title", "abstract"},
        )
        self.assertEqual(
            set(abstracts["fields"]["derived"]),
            {"stratum", "score", "neuro", "ml", "verdict"},
        )
        self.assertEqual(
            abstracts["provisional_rights_state"],
            "HIGH_PRIORITY_RIGHTS_UNRESOLVED",
        )

        pool = self.fields["patent-evidence-extract/pool_frame.csv"]
        self.assertEqual(
            set(pool["fields"]["direct_or_source_derived"]),
            {"docdb_family_id", "earliest_year", "office", "family_size", "g06n"},
        )
        self.assertEqual(
            set(pool["fields"]["derived"]),
            {
                "bloc",
                "similarity",
                "ai_score",
                "found_by_query",
                "band",
                "era",
                "cluster",
                "neuro",
                "ml",
            },
        )
        self.assertEqual(
            pool["provisional_rights_state"],
            "HIGH_PRIORITY_RIGHTS_UNRESOLVED_FOR_ROW_LEVEL_PUBLICATION",
        )

    def test_field_inventory_matches_export_headers_for_row_level_files(self) -> None:
        expected_headers = {
            "abstracts_sample.csv": {
                "docdb_family_id",
                "stratum",
                "score",
                "neuro",
                "ml",
                "verdict",
                "title",
                "abstract",
            },
            "judged_sample.csv": {
                "docdb_family_id",
                "stratum",
                "score",
                "neuro",
                "ml",
                "verdict",
            },
            "gold_labels.csv": {
                "docdb_family_id",
                "stratum",
                "gold_neuro",
                "cheap_neuro",
            },
            "pool_frame.csv": {
                "docdb_family_id",
                "earliest_year",
                "office",
                "bloc",
                "family_size",
                "similarity",
                "ai_score",
                "found_by_query",
                "band",
                "era",
                "g06n",
                "cluster",
                "neuro",
                "ml",
            },
        }
        for filename, expected in expected_headers.items():
            with (EXTRACT / filename).open(newline="", encoding="utf-8") as handle:
                header = set(next(csv.reader(handle)))
            row = self.fields[f"patent-evidence-extract/{filename}"]
            classified = set()
            for values in row["fields"].values():
                classified.update(values)
            self.assertEqual(header, expected, filename)
            self.assertEqual(classified, expected, filename)

    def test_current_first_party_terms_are_recorded_without_substituting_for_contract(self) -> None:
        evidence = self.review["rights_evidence"]
        self.assertEqual(evidence["current_public_terms_rechecked_on"], "2026-09-18")
        urls = {source["url"] for source in evidence["first_party_sources"]}
        self.assertEqual(
            urls,
            {
                "https://www.epo.org/en/service-support/ordering/raw-data-terms-and-conditions",
                "https://www.epo.org/en/about-us/observatory-patents-and-technology/observatory-tools/patstat/new-to-patstat",
            },
        )
        combined = " ".join(
            finding
            for source in evidence["first_party_sources"]
            for finding in source["findings"]
        )
        self.assertIn("Article 5.2", combined)
        self.assertIn("Article 5.4", combined)
        self.assertIn("Article 10.2", combined)
        self.assertIn("Article 17", combined)
        self.assertFalse(
            evidence["exact_autumn_2025_order_acceptance_terms_verified_in_repository"]
        )

    def test_conservative_profile_is_precomputed_but_not_authorized(self) -> None:
        profile = self.review["conservative_public_profile"]
        self.assertFalse(profile["currently_authorized_for_execution"])
        self.assertIn(
            "title and abstract text",
            profile["controlled_s3_candidates"],
        )
        self.assertIn(
            "DOCDB family membership lists and row-level source identifiers",
            profile["controlled_s3_candidates"],
        )
        self.assertIn(
            "opaque commitments/digests where membership binding is needed",
            profile["public_substitute_for_controlled_rows"],
        )

    def test_scenarios_do_not_manufacture_deletion_or_history_rewrite_authority(self) -> None:
        scenarios = {
            row["scenario"]: row for row in self.review["scenario_actions"]
        }
        restricted = scenarios[
            "EXACT_CONTRACT_OR_AUTHORITATIVE_EPO_RESPONSE_RESTRICTS_CURRENT_ROW_LEVEL_PUBLICATION"
        ]
        self.assertIn("normal corrective successor", restricted["action"])
        self.assertIn(
            "only if",
            restricted["history_rewrite"],
        )

        boundary = self.review["programme_boundary"]
        self.assertTrue(boundary["corrective_containment_plan_precomputed"])
        self.assertFalse(boundary["corrective_containment_currently_authorized"])
        self.assertFalse(boundary["history_rewrite_authorized"])
        self.assertFalse(boundary["deletion_authorized"])
        self.assertFalse(
            boundary["may_be_cited_as_rights_cleared_public_programme_evidence"]
        )
        self.assertFalse(boundary["may_authorize_s2_publication"])
        self.assertFalse(boundary["may_authorize_assessment_mutation"])

    def test_public_readme_retains_attribution_and_open_review_warning(self) -> None:
        self.assertIn(REQUIRED_ATTRIBUTION, self.readme)
        self.assertIn("Rights status — review open", self.readme)
        self.assertIn("Issue #210", self.readme)
        self.assertIn("public presence must not", self.readme)
        self.assertIn("every row-level field is cleared for redistribution", self.readme)

    def test_minimum_remaining_inputs_are_narrow_and_explicit(self) -> None:
        remaining = self.review["minimum_remaining_inputs"]
        self.assertEqual(len(remaining), 4)
        self.assertTrue(any("Autumn 2025" in item for item in remaining))
        self.assertTrue(any("amendments" in item for item in remaining))
        self.assertTrue(any("written EPO authorization" in item for item in remaining))
        self.assertTrue(any("allowed licensee product" in item for item in remaining))


if __name__ == "__main__":
    unittest.main()
