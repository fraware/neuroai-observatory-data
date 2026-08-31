from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/project_v17_prima_sources_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v17_prima_sources_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V17PrimaSourceProjectionTests(unittest.TestCase):
    def test_exact_supplemental_population_and_reconciliation(self) -> None:
        result = module.project()
        rec = result["reconciliation"]
        self.assertEqual(rec["input_source_count"], 12)
        self.assertEqual(rec["projected_source_count"], 12)
        self.assertEqual(rec["projected_observation_count"], 12)
        self.assertEqual(rec["actual_source_ids"], module.EXPECTED_IDS)
        self.assertEqual(rec["inferred_missing_source_id_count"], 0)
        self.assertEqual(rec["date_precision_observation_count"], 12)
        self.assertEqual(rec["explicit_local_hash_count"], 2)
        self.assertEqual(rec["available_content_hash_count"], 2)
        self.assertEqual(rec["explicit_redistribution_state_count"], 2)
        self.assertEqual(rec["rights_unresolved_count"], 10)
        for key in (
            "source_id_loss_count",
            "predecessor_payload_roundtrip_failure_count",
            "claim_boundary_loss_count",
            "temporal_precision_fabrication_count",
            "local_hash_loss_or_fabrication_count",
            "capture_custody_fabrication_count",
            "redistribution_state_loss_or_fabrication_count",
            "protected_byte_violation_count",
        ):
            self.assertEqual(rec[key], 0, (key, rec[key]))
        self.assertFalse(rec["canonical_successor_ready"])

    def test_missing_numeric_ids_are_not_inferred(self) -> None:
        result = module.project()
        ids = {row["source_id"] for row in result["sources"]}
        self.assertNotIn("SRC-PR-003", ids)
        self.assertNotIn("SRC-PR-004", ids)
        self.assertNotIn("SRC-PR-011", ids)
        self.assertEqual(ids, set(module.EXPECTED_IDS))

    def test_hash_does_not_invent_custody(self) -> None:
        result = module.project()
        hashed = [o for o in result["observations"] if o["content_sha256"]]
        self.assertEqual(len(hashed), 2)
        self.assertTrue(all(o["content_hash_state"] == "AVAILABLE" for o in hashed))
        self.assertTrue(all(o["capture_state"] == "CAPTURE_STATE_UNRESOLVED" for o in hashed))
        self.assertTrue(all(o["capture_reference_class"] is None for o in hashed))
        self.assertTrue(all(o["protected_bytes_in_record"] is False for o in hashed))

    def test_explicit_redistribution_wording_is_preserved(self) -> None:
        result = module.project()
        by_id = {o["source_id"]: o for o in result["observations"]}
        self.assertEqual(by_id["SRC-PR-001"]["redistribution_state"], "NOT_PACKAGED_COPYRIGHTED_SOURCE")
        self.assertEqual(by_id["SRC-PR-006"]["redistribution_state"], "NOT_PACKAGED_SOURCE_COPY")
        self.assertEqual(by_id["SRC-PR-002"]["redistribution_state"], "RIGHTS_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
