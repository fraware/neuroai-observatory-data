from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "build_v2_migration_accounting.py"
SPEC = importlib.util.spec_from_file_location("build_v2_migration_accounting", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class V2MigrationAccountingTests(unittest.TestCase):
    def test_governing_release_is_inventoried_without_successor_claim(self) -> None:
        result = module.build_accounting()
        self.assertEqual(result["input_release"], "data-v0.1.0-public-governing")
        self.assertEqual(result["input_file_count"], 6)
        self.assertFalse(result["canonical_successor_ready"])
        self.assertEqual(result["silent_unmapped_section_count"], 0)
        self.assertEqual(result["invented_value_count"], 0)
        self.assertEqual(result["claim_boundary_loss_count"], 0)
        self.assertEqual(result["source_reference_loss_count"], 0)
        self.assertGreater(result["unique_field_path_count"], 0)

    def test_exact_governing_file_set_is_accounted(self) -> None:
        result = module.build_accounting()
        files = {row["file"] for row in result["files"]}
        self.assertEqual(files, set(module.GOVERNING_FILES))

    def test_monitor_registry_stays_operational_configuration(self) -> None:
        result = module.build_accounting()
        monitor_file = next(
            row for row in result["files"] if row["file"] == "source_monitor_registry_v1.5.json"
        )
        self.assertEqual(monitor_file["section_count"], 1)
        root = monitor_file["sections"][0]
        self.assertEqual(root["section"], "$root")
        self.assertEqual(root["target_family"], "MONITORING_CONFIGURATION")
        self.assertEqual(root["record_count"], 224)

    def test_unknown_sections_are_preserved_not_silently_dropped(self) -> None:
        result = module.build_accounting()
        preserved = [
            section
            for file_row in result["files"]
            for section in file_row["sections"]
            if section["target_family"] == "LEGACY_PRESERVATION_RECORD"
        ]
        self.assertEqual(len(preserved), result["preserved_section_count"])
        self.assertTrue(
            all(
                row["mapping_state"] == "PRESERVE_PENDING_EXACT_NORMALIZATION"
                for row in preserved
            )
        )


if __name__ == "__main__":
    unittest.main()
