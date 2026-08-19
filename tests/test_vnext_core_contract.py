from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import ValidationError

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "validate_vnext_core.py"
SPEC = importlib.util.spec_from_file_location("validate_vnext_core", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate)
FIXTURE = ROOT / "fixtures" / "vnext" / "core-bundle.json"


class VNextCoreContractTests(unittest.TestCase):
    def _bundle(self) -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _validate_mutation(self, bundle: dict) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bundle.json"
            path.write_text(json.dumps(bundle), encoding="utf-8")
            validate.validate_bundle(path)

    def test_synthetic_bundle_passes(self) -> None:
        counts = validate.validate_bundle(FIXTURE)
        self.assertEqual(counts["ENTITY"], 3)
        self.assertEqual(counts["SOURCE_OBSERVATION"], 1)

    def test_unknown_predicate_fails_closed(self) -> None:
        bundle = self._bundle()
        bundle["relationships"][0]["predicate"] = "UNREGISTERED_EDGE"
        with self.assertRaisesRegex(validate.ContractError, "unknown predicate"):
            self._validate_mutation(bundle)

    def test_dangling_entity_reference_fails_closed(self) -> None:
        bundle = self._bundle()
        bundle["relationships"][0]["object_id"] = "SYS-MISSING-9999"
        with self.assertRaisesRegex(validate.ContractError, "dangling object"):
            self._validate_mutation(bundle)

    def test_duplicate_record_id_fails_closed(self) -> None:
        bundle = self._bundle()
        duplicate = copy.deepcopy(bundle["entities"][0])
        duplicate["canonical_name"] = "Duplicate"
        bundle["entities"].append(duplicate)
        with self.assertRaisesRegex(validate.ContractError, "duplicate record id"):
            self._validate_mutation(bundle)

    def test_invalid_valid_time_fails_closed(self) -> None:
        bundle = self._bundle()
        bundle["entities"][0]["valid_time"] = {
            "valid_from": "2026-09-01",
            "valid_to": "2026-08-01",
        }
        with self.assertRaisesRegex(validate.ContractError, "valid_from is after valid_to"):
            self._validate_mutation(bundle)

    def test_accepted_record_without_provenance_fails_schema(self) -> None:
        bundle = self._bundle()
        del bundle["entities"][0]["source_observation_ids"]
        with self.assertRaises(ValidationError):
            self._validate_mutation(bundle)

    def test_unknown_rights_state_fails_schema(self) -> None:
        bundle = self._bundle()
        bundle["source_observations"][0]["rights_class"] = "ASSUMED_PUBLIC"
        with self.assertRaises(ValidationError):
            self._validate_mutation(bundle)

    def test_assertion_cannot_have_object_and_value(self) -> None:
        bundle = self._bundle()
        bundle["assertions"][0]["object_id"] = "SYS-SYN-0001"
        with self.assertRaises(ValidationError):
            self._validate_mutation(bundle)

    def test_predicate_domain_range_fails_closed(self) -> None:
        bundle = self._bundle()
        bundle["relationships"][0]["subject_id"] = "SYS-SYN-0001"
        with self.assertRaisesRegex(validate.ContractError, "invalid subject type"):
            self._validate_mutation(bundle)

    def test_superseded_record_requires_existing_successor(self) -> None:
        bundle = self._bundle()
        entity = bundle["entities"][0]
        entity["resolution_state"] = "SUPERSEDED"
        entity["superseded_at"] = "2026-08-20T18:10:00Z"
        entity["successor_record_id"] = "ORG-SYN-MISSING"
        with self.assertRaisesRegex(validate.ContractError, "dangling successor"):
            self._validate_mutation(bundle)


if __name__ == "__main__":
    unittest.main()
