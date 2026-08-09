from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "validate_legacy_source_registration.py"
SPEC = importlib.util.spec_from_file_location("validate_legacy_source_registration", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

MANIFEST_PATH = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"
SCHEMA_PATH = ROOT / "schemas" / "legacy-source-registration-proposals.schema.json"
NATURE_URL = "https://www.nature.com/articles/s41591-026-04414-6"
BUSINESS_WIRE_URL = (
    "https://www.businesswire.com/news/home/20260722965902/en/"
    "Science-Corp.-Announces-European-Commercial-Launch-of-PRIMA-the-Only-Treatment-to-Restore-"
    "Functional-Central-Vision-to-Patients-with-Geographic-Atrophy-Caused-by-Age-Related-Macular-"
    "Degeneration-a-Leading-Cause-of-Blindness"
)


def _load() -> tuple[dict[str, object], dict[str, object]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return manifest, schema


class LegacySourceRegistrationTests(unittest.TestCase):
    def test_manifest_validates_against_schema_and_semantic_contract(self) -> None:
        manifest, schema = _load()
        validator.validate_manifest(manifest, schema)

    def test_verified_programme_checkpoint_is_fixed(self) -> None:
        manifest, _ = _load()
        checkpoint = manifest["derived_from"]
        self.assertEqual(checkpoint["programme_checkpoint"], "v2.2.0")
        self.assertEqual(checkpoint["source_universe_count"], 248)
        self.assertEqual(checkpoint["assessment_evidence_count"], 52)
        self.assertEqual(checkpoint["deterministic_matched_evidence_count"], 15)
        self.assertEqual(checkpoint["unresolved_evidence_count"], 37)
        self.assertEqual(checkpoint["registration_eligible_evidence_count"], 35)
        self.assertEqual(checkpoint["exact_identity_source_proposal_count"], 33)
        self.assertEqual(checkpoint["missing_explicit_source_count"], 1)
        self.assertEqual(checkpoint["curation_required_count"], 1)
        self.assertFalse(checkpoint["fuzzy_matching"])

    def test_action_counts_and_unresolved_evidence_accounting(self) -> None:
        manifest, _ = _load()
        proposals = manifest["proposals"]
        self.assertEqual(len(proposals), 35)
        counts = Counter(proposal["action"] for proposal in proposals)
        self.assertEqual(
            counts,
            {
                "REGISTER_NEW_SOURCE": 33,
                "CURATION_REQUIRED": 1,
                "REGISTER_MISSING_EXPLICIT_SOURCE": 1,
            },
        )

        new_source_evidence = sum(
            len(proposal["linked_evidence"])
            for proposal in proposals
            if proposal["action"] == "REGISTER_NEW_SOURCE"
        )
        unresolved_evidence = sum(len(proposal["linked_evidence"]) for proposal in proposals)
        self.assertEqual(new_source_evidence, 35)
        self.assertEqual(unresolved_evidence, 37)

    def test_exact_identity_proposals_are_deduplicated(self) -> None:
        manifest, _ = _load()
        new_sources = [proposal for proposal in manifest["proposals"] if proposal["action"] == "REGISTER_NEW_SOURCE"]
        urls = [proposal["normalized_public_url"] for proposal in new_sources if proposal["normalized_public_url"]]
        checksums = [proposal["checksum"] for proposal in new_sources if proposal["checksum"]]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(len(checksums), len(set(checksums)))
        self.assertTrue(all(proposal["existing_source_id"] is None for proposal in new_sources))
        self.assertTrue(all(proposal["requested_source_id"] is None for proposal in new_sources))

    def test_only_multi_evidence_exact_group_is_braingate_nature_medicine(self) -> None:
        manifest, _ = _load()
        new_sources = [proposal for proposal in manifest["proposals"] if proposal["action"] == "REGISTER_NEW_SOURCE"]
        multi = [proposal for proposal in new_sources if len(proposal["linked_evidence"]) > 1]
        self.assertEqual(len(multi), 1)
        proposal = multi[0]
        self.assertEqual(proposal["normalized_public_url"], NATURE_URL)
        self.assertEqual(
            {row["evidence_id"] for row in proposal["linked_evidence"]},
            {"EV-T15-001", "EV-T15-009", "EV-T15-010"},
        )
        self.assertEqual({row["system"] for row in proposal["linked_evidence"]}, {"BrainGate2 T15"})

    def test_fda_ev15_remains_curation_only_without_source_identity(self) -> None:
        manifest, _ = _load()
        proposal = next(proposal for proposal in manifest["proposals"] if proposal["action"] == "CURATION_REQUIRED")
        self.assertEqual([row["evidence_id"] for row in proposal["linked_evidence"]], ["EV-15"])
        self.assertEqual([row["system"] for row in proposal["linked_evidence"]], ["FDA adaptive DBS"])
        self.assertIsNone(proposal["normalized_public_url"])
        self.assertIsNone(proposal["checksum"])
        self.assertIsNone(proposal["existing_source_id"])
        self.assertIsNone(proposal["requested_source_id"])

    def test_prima_missing_explicit_source_is_restored_from_controlled_metadata(self) -> None:
        manifest, _ = _load()
        proposal = next(
            proposal for proposal in manifest["proposals"] if proposal["action"] == "REGISTER_MISSING_EXPLICIT_SOURCE"
        )
        self.assertEqual(proposal["requested_source_id"], "SRC-PR-011")
        self.assertEqual([row["evidence_id"] for row in proposal["linked_evidence"]], ["EV-PR-011"])
        source = proposal["proposed_source_record"]
        self.assertEqual(source["source_id"], "SRC-PR-011")
        self.assertEqual(source["title"], "Science Corp. Announces European Commercial Launch of PRIMA")
        self.assertEqual(source["publisher"], "Business Wire")
        self.assertEqual(source["url"], BUSINESS_WIRE_URL)
        self.assertEqual(source["published"], "2026-07-22")
        self.assertEqual(source["retrieved"], "2026-07-29")
        self.assertEqual(source["source_class"], "PRESS_RELEASE_SYNDICATION")
        self.assertIn("not independent regulatory evidence", source["claim_boundary"].lower())

    def test_all_records_remain_noncanonical_proposals(self) -> None:
        manifest, _ = _load()
        self.assertEqual(manifest["status"], "NONCANONICAL_PROPOSAL")
        self.assertTrue(all(proposal["review_state"] == "PROPOSED_NONCANONICAL" for proposal in manifest["proposals"]))
        self.assertIn("neither changes historical assessments", manifest["authority_boundary"])

    def test_validator_rejects_new_source_id_assignment(self) -> None:
        manifest, schema = _load()
        mutated = copy.deepcopy(manifest)
        proposal = next(proposal for proposal in mutated["proposals"] if proposal["action"] == "REGISTER_NEW_SOURCE")
        proposal["requested_source_id"] = "SRC-INVENTED"
        with self.assertRaisesRegex(validator.ValidationError, "must not assign a canonical source ID"):
            validator.validate_manifest(mutated, schema)

    def test_validator_rejects_unexpected_schema_fields(self) -> None:
        manifest, schema = _load()
        mutated = copy.deepcopy(manifest)
        mutated["proposals"][0]["fuzzy_candidate"] = "SRC-MAYBE"
        with self.assertRaisesRegex(validator.ValidationError, "unexpected property"):
            validator.validate_manifest(mutated, schema)


if __name__ == "__main__":
    unittest.main()
