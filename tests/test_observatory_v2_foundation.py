from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "verify_v2_foundation.py"
SPEC = importlib.util.spec_from_file_location("verify_v2_foundation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verify_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_module)


class ObservatoryV2FoundationTests(unittest.TestCase):
    def test_foundation_verifies(self) -> None:
        result = verify_module.verify()
        self.assertEqual(result["record_state"], "NONCANONICAL_CANDIDATE")
        self.assertFalse(result["protected_bytes_in_record"])
        self.assertEqual(
            result["authority_boundary"],
            "STRUCTURAL_TEST_ONLY_NO_SUBSTANTIVE_OR_PUBLICATION_AUTHORITY",
        )

    def test_assertion_and_observation_are_separate_objects(self) -> None:
        assertion = json.loads(
            (ROOT / "fixtures/v2-foundation/assertion.example.json").read_text()
        )
        observation = json.loads(
            (ROOT / "fixtures/v2-foundation/observation.example.json").read_text()
        )
        self.assertNotEqual(assertion["assertion_id"], observation["observation_id"])
        self.assertIn(observation["observation_id"], assertion["observation_ids"])
        self.assertIn(observation["source_id"], assertion["source_ids"])

    def test_public_observation_schema_forbids_protected_bytes(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/observatory-v1-observation.schema.json").read_text()
        )
        protected_field = schema["properties"]["protected_bytes_in_record"]
        self.assertIs(protected_field["const"], False)
        self.assertIn("protected_bytes_in_record", schema["required"])

    def test_assertion_schema_requires_exactly_one_object_form(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/observatory-v2-assertion.schema.json").read_text()
        )
        self.assertEqual(len(schema["oneOf"]), 2)
        self.assertIn("object_id", schema["oneOf"][0]["required"])
        self.assertIn("value", schema["oneOf"][1]["required"])

    def test_foundation_fixture_cannot_claim_canonical_authority(self) -> None:
        assertion = json.loads(
            (ROOT / "fixtures/v2-foundation/assertion.example.json").read_text()
        )
        self.assertEqual(assertion["record_state"], "NONCANONICAL_CANDIDATE")
        self.assertIsNone(assertion["first_release_id"])
        self.assertIn("canonical publication", assertion["authority_boundary"].lower())

    def test_source_universe_registry_is_explicitly_noncanonical_and_unique(self) -> None:
        registry = json.loads(
            (ROOT / "curation/source_universe_registry_v0.1.json").read_text()
        )
        self.assertEqual(registry["status"], "NONCANONICAL_PROGRAMME_CONTROL")
        ids = [row["universe_id"] for row in registry["universes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 8)
        self.assertTrue(
            all(row["canonical_completeness_claim"] is False for row in registry["universes"])
        )
        self.assertTrue(
            all(row["implementation_state"] in {"CURRENT_BOUNDED", "PARTIAL", "PLANNED"} for row in registry["universes"])
        )

    def test_source_universe_schema_forbids_global_completeness_flag(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/source-universe-registry.schema.json").read_text()
        )
        universe = schema["$defs"]["universe"]
        self.assertIs(universe["properties"]["canonical_completeness_claim"]["const"], False)
        self.assertIn("canonical_completeness_claim", universe["required"])


if __name__ == "__main__":
    unittest.main()
