from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_capability_context_taxonomy.py"
spec = importlib.util.spec_from_file_location("d2_validator", SCRIPT)
validator = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(validator)


class CapabilityContextTaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(
            (ROOT / "curation" / "CAPABILITY_CONTEXT_TAXONOMY_v0.1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.schema = json.loads(
            (ROOT / "schemas" / "capability-context-taxonomy-v0.1.schema.json").read_text(
                encoding="utf-8"
            )
        )

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
        self.assertInvalid(
            lambda doc: doc["governance"].__setitem__("publication_authority", True)
        )

    def test_gray_third_cannot_become_canonical_population(self):
        self.assertInvalid(
            lambda doc: doc["gray_third"].__setitem__("canonical_population_class", True)
        )

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
                term
                for term in doc["axes"]["deployment_context"]
                if term["id"] != "CONTEXT_UNKNOWN"
            ]

        self.assertInvalid(mutate)

    def test_duplicate_ids_fail_closed(self):
        def mutate(doc):
            doc["axes"]["inferred_state"][1]["id"] = doc["axes"]["inferred_state"][0]["id"]

        self.assertInvalid(mutate)

    def test_d1_binding_digest_mismatch_fails_closed(self):
        self.assertInvalid(
            lambda doc: doc["d1_contract_binding"].__setitem__(
                "canonical_json_sha256", "0" * 64
            )
        )

    def test_d1_binding_canonical_digest_is_line_ending_invariant(self):
        d1_path = ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json"
        d1 = json.loads(d1_path.read_text(encoding="utf-8"))
        lf_text = json.dumps(d1, ensure_ascii=False, indent=2) + "\n"
        crlf_text = lf_text.replace("\n", "\r\n")

        self.assertNotEqual(
            hashlib.sha256(lf_text.encode("utf-8")).hexdigest(),
            hashlib.sha256(crlf_text.encode("utf-8")).hexdigest(),
        )
        expected_digest = self.doc["d1_contract_binding"]["canonical_json_sha256"]

        with tempfile.TemporaryDirectory() as tmpdir:
            for name, text in (("d1-lf.json", lf_text), ("d1-crlf.json", crlf_text)):
                candidate = Path(tmpdir) / name
                candidate.write_bytes(text.encode("utf-8"))
                with patch.object(validator, "DEFAULT_D1_ARTIFACT", candidate):
                    identity = validator._load_d1_contract_identity()
                self.assertEqual(identity["canonical_json_sha256"], expected_digest)

    def test_d1_binding_question_mismatch_fails_closed(self):
        def mutate(doc):
            doc["d1_contract_binding"]["d2_question_bindings"] = [
                "RQ-02",
                "RQ-04",
                "RQ-05",
            ]

        self.assertInvalid(mutate)

    def test_d1_binding_sha_mismatch_fails_closed(self):
        self.assertInvalid(
            lambda doc: doc["d1_contract_binding"].__setitem__(
                "created_against_observatory_main_sha", "0" * 40
            )
        )

    def test_predicted_harm_must_remain_prohibited(self):
        self.assertInvalid(
            lambda doc: doc["mapping_scaffold"].__setitem__("predicted_harm_allowed", True)
        )

    def test_gray_family_set_is_exact(self):
        def mutate(doc):
            doc["gray_third"]["search_families"].pop()

        self.assertInvalid(mutate)

    def test_schema_rejects_unknown_property(self):
        self.assertInvalid(lambda doc: doc.__setitem__("unauthorized_extra", True))

    def test_schema_rejects_malformed_alias(self):
        def mutate(doc):
            doc["axes"]["inferred_state"][0]["aliases"] = [
                {"language": "en", "text": "motor intent", "extra": "x"}
            ]

        self.assertInvalid(mutate)


if __name__ == "__main__":
    unittest.main()
