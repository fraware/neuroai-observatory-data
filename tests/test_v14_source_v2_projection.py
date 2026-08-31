from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "project_v14_sources_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v14_sources_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V14SourceV2ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = module.project()
        cls.reconciliation = cls.result["reconciliation"]

    def test_all_224_v14_sources_are_projected(self) -> None:
        self.assertEqual(self.reconciliation["input_source_count"], 224)
        self.assertEqual(self.reconciliation["projected_source_count"], 224)
        self.assertEqual(len(self.result["sources"]), 224)

    def test_source_slice_reconciliation_is_lossless_within_declared_scope(self) -> None:
        self.assertEqual(
            self.reconciliation["semantic_reconciliation_state"],
            "EXECUTED_FOR_SOURCE_VERTICAL_SLICE_ONLY",
        )
        self.assertEqual(self.reconciliation["normalized_core_mismatch_count"], 0)
        self.assertEqual(
            self.reconciliation["predecessor_payload_roundtrip_failure_count"], 0
        )
        self.assertEqual(self.reconciliation["source_field_loss_count"], 0)
        self.assertEqual(self.reconciliation["claim_boundary_loss_count"], 0)
        self.assertEqual(self.reconciliation["source_reference_loss_count"], 0)
        self.assertEqual(self.reconciliation["temporal_precision_fabrication_count"], 0)
        self.assertEqual(
            self.reconciliation["invented_predecessor_field_value_count"], 0
        )
        self.assertFalse(self.reconciliation["canonical_successor_ready"])

    def test_predecessor_payload_is_preserved_exactly(self) -> None:
        for source in self.result["sources"]:
            predecessor = source["predecessor"]
            self.assertEqual(predecessor["record_id"], source["source_id"])
            self.assertEqual(predecessor["payload"]["source_id"], source["source_id"])
            self.assertEqual(
                predecessor["record_sha256"], module._digest(predecessor["payload"])
            )

    def test_observations_never_invent_capture_or_transport_metadata(self) -> None:
        for observation in self.result["observations"]:
            self.assertEqual(
                observation["retrieval_outcome"], "PREDECESSOR_RECORDED_OBSERVATION"
            )
            self.assertEqual(observation["capture_state"], "CAPTURE_STATE_UNRESOLVED")
            self.assertEqual(observation["redistribution_state"], "RIGHTS_UNRESOLVED")
            self.assertIsNone(observation["requested_locator"])
            self.assertIsNone(observation["resolved_locator"])
            self.assertIsNone(observation["http_status"])
            self.assertIsNone(observation["content_sha256"])
            self.assertFalse(observation["protected_bytes_in_record"])

    def test_observation_time_preserves_predecessor_precision(self) -> None:
        for source in self.result["sources"]:
            retrieved = source["predecessor"]["payload"].get("retrieved")
            if retrieved is None:
                continue
            observation_id = module._observation_id(source["source_id"])
            observation = next(
                row
                for row in self.result["observations"]
                if row["observation_id"] == observation_id
            )
            self.assertEqual(observation["observed_at"]["value"], retrieved)
            if len(retrieved) == 10:
                self.assertEqual(observation["observed_at"]["precision"], "DATE")


if __name__ == "__main__":
    unittest.main()
