from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/project_v16_sources_observations_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v16_sources_observations_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V16SourceObservationProjectionTests(unittest.TestCase):
    def test_exact_reconciliation(self) -> None:
        result = module.project()["reconciliation"]
        self.assertEqual(result["input_source_count"], 12)
        self.assertEqual(result["input_check_count"], 12)
        self.assertEqual(result["projected_source_count"], 12)
        self.assertEqual(result["projected_observation_count"], 12)
        self.assertEqual(result["one_to_one_source_check_pair_count"], 12)
        self.assertEqual(result["exact_timestamp_observation_count"], 12)
        self.assertEqual(result["source_published_date_count"], 10)
        self.assertEqual(result["source_published_unresolved_count"], 2)
        self.assertEqual(result["content_hash_unavailable_count"], 12)
        self.assertEqual(result["new_or_backfill_comparison_count"], 10)
        self.assertEqual(result["no_material_change_comparison_count"], 2)
        for key in (
            "source_identity_loss_count",
            "source_payload_roundtrip_failure_count",
            "observation_payload_roundtrip_failure_count",
            "claim_boundary_loss_count",
            "source_reference_loss_count",
            "content_hash_fabrication_count",
            "locator_fabrication_count",
            "http_metadata_fabrication_count",
            "temporal_precision_fabrication_count",
            "protected_bytes_in_public_record_count",
        ):
            self.assertEqual(result[key], 0, (key, result[key]))
        self.assertFalse(result["canonical_successor_ready"])

    def test_page_hash_sentinel_does_not_become_content_digest(self) -> None:
        for observation in module.project()["observations"]:
            self.assertEqual(
                observation["predecessor"]["payload"]["page_content_hash"],
                "NOT_AVAILABLE_FROM_WEB_RESEARCH_INTERFACE",
            )
            self.assertIsNone(observation["content_sha256"])
            self.assertEqual(
                observation["content_hash_state"],
                "NOT_AVAILABLE_FROM_PREDECESSOR_INTERFACE",
            )

    def test_observations_do_not_invent_transport_metadata(self) -> None:
        for observation in module.project()["observations"]:
            self.assertIsNone(observation["requested_locator"])
            self.assertIsNone(observation["resolved_locator"])
            self.assertIsNone(observation["http_status"])
            self.assertIsNone(observation["content_type"])
            self.assertFalse(observation["protected_bytes_in_record"])

    def test_v16_extension_fields_remain_optional_in_base_observation_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/observatory-v1-observation.schema.json").read_text(encoding="utf-8")
        )
        for field in ("content_hash_state", "comparison_state", "metadata_digest_sha256", "predecessor"):
            self.assertIn(field, schema["properties"])
            self.assertNotIn(field, schema["required"])
        for observation in module.project()["observations"]:
            self.assertIn("content_hash_state", observation)
            self.assertIn("comparison_state", observation)
            self.assertIn("metadata_digest_sha256", observation)
            self.assertIsInstance(observation["predecessor"], dict)


if __name__ == "__main__":
    unittest.main()
