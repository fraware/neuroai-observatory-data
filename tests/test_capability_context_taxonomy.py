from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_capability_context_taxonomy.py"
spec = importlib.util.spec_from_file_location("d2_validator", SCRIPT)
validator = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(validator)


class CapabilityContextTaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((ROOT / "curation" / "CAPABILITY_CONTEXT_TAXONOMY_v0.1.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((ROOT / "schemas" / "capability-context-taxonomy-v0.1.schema.json").read_text(encoding="utf-8"))

    def assertInvalid(self, mutate):
        doc = copy.deepcopy(self.doc)
        mutate(doc)
        with self.assertRaises(validator.ValidationError):
            validator.validate_document(doc, self.schema)

    def test_reference_artifact_passes(self):
        validator.validate_document(copy.deepcopy(self.doc), self.schema)

    def test_technical_artifact_cannot_approve_g1(self):
        self.assertInvalid(lambda doc: doc["governance"].__setitem__("g1_approved", True))

    def test_draft_cannot_gain_publication_authority(self):
        self.assertInvalid(lambda doc: doc["governance"].__setitem__("publication_authority", True))

    def test_gray_third_cannot_become_canonical_population(self):
        self.assertInvalid(lambda doc: doc["gray_third"].__setitem__("canonical_population_class", True))

    def test_proxy_only_sensing_cannot_be_primary_inclusion_evidence(self):
        def mutate(doc):
            for term in doc["axes"]["sensing_modality"]:
                if term["id"] == "SENSE_EMG":
                    term["default_inclusion_evidence_role"] = "PRIMARY_CAPABILITY_EVIDENCE"
                    return
            raise AssertionError("SENSE_EMG missing from fixture")
        self.assertInvalid(mutate)

    def test_unknown_state_is_mandatory(self):
        def mutate(doc):
            doc["axes"]["deployment_context"] = [
                term for term in doc["axes"]["deployment_context"] if term["id"] != "CONTEXT_UNKNOWN"
            ]
        self.assertInvalid(mutate)

    def test_duplicate_ids_fail_closed(self):
        def mutate(doc):
            doc["axes"]["inferred_state"][1]["id"] = doc["axes"]["inferred_state"][0]["id"]
        self.assertInvalid(mutate)

    def test_predicted_harm_must_remain_prohibited(self):
        self.assertInvalid(lambda doc: doc["mapping_scaffold"].__setitem__("predicted_harm_allowed", True))

    def test_gray_family_set_is_exact(self):
        def mutate(doc):
            doc["gray_third"]["search_families"].pop()
        self.assertInvalid(mutate)


if __name__ == "__main__":
    unittest.main()
