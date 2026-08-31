from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/project_v16_change_candidates_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v16_change_candidates_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V16ChangeCandidateProjectionTests(unittest.TestCase):
    def test_exact_reconciliation(self) -> None:
        result = module.project()["reconciliation"]
        self.assertEqual(result["input_candidate_count"], 9)
        self.assertEqual(result["projected_candidate_count"], 9)
        self.assertEqual(result["historical_backfill_count"], 6)
        self.assertEqual(result["pre_cutoff_after_freeze_count"], 3)
        self.assertEqual(
            (result["high_materiality_count"], result["medium_materiality_count"], result["low_materiality_count"]),
            (2, 5, 2),
        )
        self.assertEqual(result["source_reference_count"], 10)
        self.assertEqual(result["observation_reference_count"], 10)
        self.assertEqual(result["explicit_promotion_link_count"], 0)
        for key in (
            "identity_mismatch_count",
            "predecessor_payload_roundtrip_failure_count",
            "source_reference_loss_count",
            "observation_reference_loss_count",
            "subject_resolution_fabrication_count",
            "promotion_linkage_fabrication_count",
            "event_time_precision_fabrication_count",
            "knowledge_time_fabrication_count",
        ):
            self.assertEqual(result[key], 0, (key, result[key]))
        self.assertFalse(result["canonical_successor_ready"])

    def test_no_candidate_is_promoted_by_migration(self) -> None:
        for candidate in module.project()["candidates"]:
            self.assertEqual(candidate["record_state"], "NONCANONICAL_CANDIDATE")
            self.assertEqual(candidate["promoted_record_ids"], [])
            self.assertEqual(
                candidate["promotion_linkage_state"],
                "PREDECESSOR_PROMOTION_LINKAGE_NOT_EXPLICIT",
            )
            self.assertIsNone(candidate["subject_reference"]["entity_id"])

    def test_candidate_schema_encodes_nonpromotion_boundary(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/observatory-v2-change-candidate.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["record_state"]["const"], "NONCANONICAL_CANDIDATE")
        self.assertEqual(schema["properties"]["promoted_record_ids"]["maxItems"], 0)
        self.assertEqual(
            schema["properties"]["promotion_linkage_state"]["const"],
            "PREDECESSOR_PROMOTION_LINKAGE_NOT_EXPLICIT",
        )


if __name__ == "__main__":
    unittest.main()
