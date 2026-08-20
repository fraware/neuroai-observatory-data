from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("validate_identity_foundation", ROOT / "scripts" / "validate_identity_foundation.py")
m = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)

BUNDLE = json.loads((ROOT / "fixtures" / "vnext" / "identity-bundle.synthetic.json").read_text())
REGISTRY = json.loads((ROOT / "identity" / "namespaces-v0.1.json").read_text())


class IdentityFoundationTests(unittest.TestCase):
    def test_valid_bundle(self):
        self.assertTrue(m.validate_bundle(copy.deepcopy(BUNDLE)))

    def test_namespace_registry_covers_required_classes(self):
        namespaces = m.load_namespace_registry(copy.deepcopy(REGISTRY))
        self.assertTrue({"ORCID","ROR","DOI","NCT","NIH_PROJECT","FDA_KNUMBER","FDA_PMA","EPO_PUBLICATION","EPO_FAMILY","DANDISET","OPENNEURO"}.issubset(namespaces))

    def test_unknown_namespace_fails(self):
        x = copy.deepcopy(BUNDLE)
        x["external_identifiers"][0]["namespace_id"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "unknown namespace"):
            m.validate_bundle(x)

    def test_normalization_mismatch_fails(self):
        x = copy.deepcopy(BUNDLE)
        doi = next(r for r in x["external_identifiers"] if r["namespace_id"] == "DOI")
        doi["normalized_value"] = doi["normalized_value"].upper()
        with self.assertRaisesRegex(ValueError, "normalization mismatch"):
            m.validate_bundle(x)

    def test_malformed_identifier_fails(self):
        x = copy.deepcopy(BUNDLE)
        nct = next(r for r in x["external_identifiers"] if r["namespace_id"] == "NCT")
        nct["observed_value"] = "NCT123"
        nct["normalized_value"] = "NCT123"
        with self.assertRaisesRegex(ValueError, "malformed normalized"):
            m.validate_bundle(x)

    def test_disallowed_entity_type_fails(self):
        x = copy.deepcopy(BUNDLE)
        nct = next(r for r in x["external_identifiers"] if r["namespace_id"] == "NCT")
        nct["entity_id"] = "PERSON-SYN-001"
        with self.assertRaisesRegex(ValueError, "not allowed for entity type"):
            m.validate_bundle(x)

    def test_accepted_identifier_collision_fails(self):
        x = copy.deepcopy(BUNDLE)
        original = next(r for r in x["external_identifiers"] if r["namespace_id"] == "ROR")
        collision = copy.deepcopy(original)
        collision["identifier_record_id"] = "XID-ROR-SYN-COLLISION"
        collision["entity_id"] = "ORG-SYN-002"
        x["external_identifiers"].append(collision)
        with self.assertRaisesRegex(ValueError, "accepted identifier collision"):
            m.validate_bundle(x)

    def test_dangling_source_observation_fails(self):
        x = copy.deepcopy(BUNDLE)
        x["external_identifiers"][0]["source_observation_id"] = "OBS-MISSING"
        with self.assertRaisesRegex(ValueError, "dangling source observation"):
            m.validate_bundle(x)

    def test_self_match_candidate_fails(self):
        x = copy.deepcopy(BUNDLE)
        x["resolution_candidates"][0]["right_entity_id"] = x["resolution_candidates"][0]["left_entity_id"]
        with self.assertRaisesRegex(ValueError, "self-match"):
            m.validate_bundle(x)

    def test_cross_type_candidate_fails(self):
        x = copy.deepcopy(BUNDLE)
        x["resolution_candidates"][0]["right_entity_id"] = "PERSON-SYN-001"
        with self.assertRaisesRegex(ValueError, "crosses entity types"):
            m.validate_bundle(x)

    def test_candidate_can_never_auto_merge(self):
        x = copy.deepcopy(BUNDLE)
        x["resolution_candidates"][0]["automatic_merge_permitted"] = True
        with self.assertRaises(ValueError):
            m.validate_bundle(x)

    def test_candidate_dangling_evidence_fails(self):
        x = copy.deepcopy(BUNDLE)
        x["resolution_candidates"][0]["signals"][0]["evidence_references"] = ["OBS-MISSING"]
        with self.assertRaisesRegex(ValueError, "dangling candidate evidence"):
            m.validate_bundle(x)

    def test_decision_requires_human_adjudication(self):
        x = copy.deepcopy(BUNDLE)
        x["resolution_decisions"][0]["authority_mode"] = "AUTOMATED"
        with self.assertRaises(ValueError):
            m.validate_bundle(x)

    def test_decision_pair_must_match_candidate(self):
        x = copy.deepcopy(BUNDLE)
        x["resolution_decisions"][0]["right_entity_id"] = "ORG-SYN-001"
        with self.assertRaisesRegex(ValueError, "does not match candidate"):
            m.validate_bundle(x)

    def test_same_entity_requires_successor_effect(self):
        x = copy.deepcopy(BUNDLE)
        d = x["resolution_decisions"][0]
        d["disposition"] = "SAME_ENTITY"
        d["canonical_effect"] = "NO_MERGE"
        with self.assertRaisesRegex(ValueError, "canonical_effect"):
            m.validate_bundle(x)

    def test_duplicate_final_decision_fails(self):
        x = copy.deepcopy(BUNDLE)
        duplicate = copy.deepcopy(x["resolution_decisions"][0])
        duplicate["decision_id"] = "ERD-ORG-SYN-002"
        duplicate["disposition"] = "INSUFFICIENT_EVIDENCE"
        duplicate["canonical_effect"] = "NO_CANONICAL_EFFECT"
        x["resolution_decisions"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "contradictory or duplicate"):
            m.validate_bundle(x)

    def test_accepted_time_cannot_precede_observation(self):
        x = copy.deepcopy(BUNDLE)
        x["external_identifiers"][0]["accepted_at"] = "2026-08-20T08:00:00Z"
        with self.assertRaisesRegex(ValueError, "precedes observed"):
            m.validate_bundle(x)

    def test_adjudicated_candidate_requires_decision(self):
        x = copy.deepcopy(BUNDLE)
        x["resolution_decisions"] = []
        with self.assertRaisesRegex(ValueError, "lacks decision"):
            m.validate_bundle(x)


if __name__ == "__main__":
    unittest.main()
