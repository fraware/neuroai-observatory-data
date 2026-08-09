from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
PROVENANCE_PATH = ROOT / "curation" / "legacy_assessment_source_registration_provenance_v0.1.json"
MANIFEST_PATH = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"
EXPECTED_WORKBOOK_SHA256 = "db5bfca8c30e8b1945c52dc208dcbb486d1e0146adeb125b7fef9f557fcaa49a"
EXPECTED_CROSSWALK_COMMIT = "1a44e1c0f9f3fd60793f57579b4e043c5117b467"


class LegacySourceRegistrationProvenanceTests(unittest.TestCase):
    def test_external_checkpoint_is_byte_pinned(self) -> None:
        provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        checkpoint = provenance["source_checkpoint"]
        self.assertEqual(checkpoint["filename"], "UNESCO_NeuroAI_All_Data_Combined_v2.2.0.xlsx")
        self.assertEqual(checkpoint["sha256"], EXPECTED_WORKBOOK_SHA256)
        self.assertRegex(checkpoint["sha256"], re.compile(r"^[0-9a-f]{64}$"))
        self.assertEqual(checkpoint["size_bytes"], 1400027)
        self.assertIn("external controlled programme artifact", checkpoint["availability_boundary"])

    def test_workbook_surfaces_and_source_universe_are_explicit(self) -> None:
        provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        surfaces = provenance["workbook_surfaces"]
        self.assertEqual(surfaces["baseline_sources"], {"sheet": "Sources", "range": "A1:K225", "data_rows": 224})
        self.assertEqual(
            surfaces["assessment_evidence"],
            {"sheet": "Assessment_Evidence", "range": "A1:AI53", "data_rows": 52},
        )
        self.assertEqual(
            surfaces["assessment_findings"],
            {"sheet": "Assessment_Findings", "range": "A1:AG313", "data_rows": 312},
        )
        universe = provenance["effective_source_universe"]
        self.assertEqual(universe["baseline_source_rows"], 224)
        self.assertEqual(universe["v1_6_successor_additions"], 12)
        self.assertEqual(universe["v1_7_prima_additions"], 12)
        self.assertEqual(universe["effective_source_count"], 248)
        self.assertEqual(224 + 12 + 12, universe["effective_source_count"])

    def test_normalization_contract_is_pinned_to_crosswalk_commit(self) -> None:
        provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        normalization = provenance["normalization_contract"]
        self.assertEqual(normalization["workbench_crosswalk_commit"], EXPECTED_CROSSWALK_COMMIT)
        self.assertIn("exact normalized URL", normalization["identity"])
        self.assertIn("No fuzzy", normalization["identity"])
        self.assertTrue(any("remove URL fragment" in rule for rule in normalization["public_url"]))
        self.assertTrue(any("NOT CLAIMED" in rule for rule in normalization["checksum"]))

    def test_provenance_checkpoint_matches_manifest_checkpoint(self) -> None:
        provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        derived = provenance["derived_checkpoint"]
        manifest_checkpoint = manifest["derived_from"]
        for key, value in derived.items():
            self.assertEqual(manifest_checkpoint[key], value, key)
        self.assertEqual(provenance["effective_source_universe"]["effective_source_count"], manifest_checkpoint["source_universe_count"])

    def test_reproduction_contract_preserves_authority_boundaries(self) -> None:
        provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        contract = "\n".join(provenance["reproduction_contract"])
        self.assertIn("Verify that the input workbook bytes match", contract)
        self.assertIn("explicit current source ID", contract)
        self.assertIn("exact normalized URL", contract)
        self.assertIn("human curation", contract)
        self.assertIn("Do not mutate completed assessments", contract)


if __name__ == "__main__":
    unittest.main()
