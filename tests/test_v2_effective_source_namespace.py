from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/reconcile_v2_effective_source_namespace.py"
SPEC = importlib.util.spec_from_file_location("reconcile_v2_effective_source_namespace", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class EffectiveSourceNamespaceTests(unittest.TestCase):
    def test_actual_records_materialize_exact_declared_namespace(self) -> None:
        result = module.reconcile()
        self.assertEqual(
            result["family_counts"],
            {"V1_4_BASELINE": 224, "V1_6_REFRESH": 12, "V1_7_PRIMA_SUPPLEMENTAL": 12},
        )
        self.assertEqual(result["family_count_mismatches"], {})
        self.assertEqual(result["materialized_unique_source_count"], 248)
        self.assertEqual(result["v1_7_declared_effective_source_count"], 248)
        self.assertTrue(result["materialized_matches_declared"])
        self.assertEqual(result["duplicate_source_id_count"], 0)
        self.assertEqual(result["duplicate_source_ids"], [])
        self.assertFalse(result["global_completeness_claim"])
        self.assertFalse(result["canonical_successor_ready"])

    def test_namespace_contains_only_actual_source_ids(self) -> None:
        result = module.reconcile()
        ids = {row["source_id"] for row in result["source_namespace"]}
        self.assertEqual(len(ids), 248)
        self.assertIn("SRC-0001", ids)
        self.assertIn("SRC-16-001", ids)
        self.assertIn("SRC-PR-001", ids)
        self.assertNotIn("SRC-PR-003", ids)
        self.assertNotIn("SRC-PR-004", ids)
        self.assertNotIn("SRC-PR-011", ids)

    def test_every_source_retains_lineage_family(self) -> None:
        result = module.reconcile()
        self.assertTrue(all(row["lineage_family"] in module.PROJECTORS for row in result["source_namespace"]))
        self.assertTrue(all(row["predecessor_file"] for row in result["source_namespace"]))
        self.assertTrue(all(row["predecessor_record_id"] for row in result["source_namespace"]))


if __name__ == "__main__":
    unittest.main()
