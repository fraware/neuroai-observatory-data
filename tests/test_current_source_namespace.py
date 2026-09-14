from __future__ import annotations

import unittest

from scripts.current_source_namespace import (
    EXPECTED_PRIMA_IDS,
    materialize_effective_source_namespace,
)


class CurrentSourceNamespaceTests(unittest.TestCase):
    def test_materializes_exact_effective_controlled_namespace(self) -> None:
        result = materialize_effective_source_namespace()

        self.assertEqual(result["materialized_source_count"], 248)
        self.assertEqual(
            result["family_counts"],
            {
                "V1_4_BASELINE": 224,
                "V1_6_REFRESH": 12,
                "V1_7_PRIMA_SUPPLEMENTAL": 12,
            },
        )
        self.assertEqual(len(result["sources"]), 248)
        self.assertEqual(len({row["source_id"] for row in result["sources"]}), 248)
        self.assertFalse(result["global_completeness_claim"])
        self.assertFalse(result["network_execution_performed"])
        self.assertFalse(result["migration_performed"])
        self.assertFalse(result["canonical_mutation_performed"])
        self.assertFalse(result["publication_authority_created"])

    def test_prima_supplemental_identity_set_is_exact_and_noninvented(self) -> None:
        result = materialize_effective_source_namespace()
        prima_ids = tuple(
            row["source_id"]
            for row in result["sources"]
            if row["lineage_family"] == "V1_7_PRIMA_SUPPLEMENTAL"
        )

        self.assertEqual(set(prima_ids), set(EXPECTED_PRIMA_IDS))
        self.assertNotIn("SRC-PR-003", prima_ids)
        self.assertNotIn("SRC-PR-004", prima_ids)
        self.assertNotIn("SRC-PR-011", prima_ids)

    def test_namespace_digest_is_deterministic(self) -> None:
        first = materialize_effective_source_namespace()
        second = materialize_effective_source_namespace()

        self.assertEqual(first["source_id_set_sha256"], second["source_id_set_sha256"])
        self.assertEqual(first["sources"], second["sources"])


if __name__ == "__main__":
    unittest.main()
