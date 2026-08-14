from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_analytical_projection import build_tables, load_inputs  # noqa: E402
from build_current_monitor_accountability import sha256  # noqa: E402
from build_development_monitor_registry import (  # noqa: E402
    STATUS,
    build_development_registry,
    verify_development_registry,
)
from source_lifecycle_overlay import load_verified_lifecycle_overlay  # noqa: E402


class DevelopmentMonitorRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_inputs(
            (ROOT / "releases/data-v0.1.0-public-governing/records").resolve(),
            supplemental_dir=(ROOT / "supplemental_records").resolve(),
        )
        tables = build_tables(cls.inputs)
        source_ids = {str(row["record_id"]) for row in tables["sources"] if row.get("record_id")}
        monitor_ids = {str(row["record_id"]) for row in tables["source_monitors"] if row.get("record_id")}
        _, cls.overlay, cls.transitions = load_verified_lifecycle_overlay(
            effective_source_ids=source_ids,
            governing_monitor_source_ids=monitor_ids,
        )
        cls.predecessor = cls.inputs["v15_registry"]
        cls.predecessor_sha = sha256(cls.predecessor)
        cls.registry = build_development_registry(cls.inputs, cls.transitions)

    def test_exact_registry_view_counts_and_status(self) -> None:
        verify_development_registry(self.registry)
        metadata = self.registry["metadata"]
        self.assertEqual(metadata["status"], STATUS)
        self.assertEqual(metadata["record_count"], 226)
        self.assertEqual(metadata["predecessor_record_count"], 224)
        self.assertEqual(metadata["extension_record_count"], 2)
        self.assertEqual(metadata["lifecycle_resolved_source_count"], 1)
        self.assertEqual(metadata["lifecycle_resolved_source_ids"], ["SRC-PR-015"])
        self.assertEqual(metadata["effective_source_count"], 248)
        self.assertEqual(metadata["candidate_accountability_coverage_fraction"], 1.0)

    def test_predecessor_is_byte_semantically_unchanged(self) -> None:
        self.assertEqual(sha256(self.predecessor), self.predecessor_sha)
        self.assertEqual(self.registry["metadata"]["predecessor_registry_sha256"], self.predecessor_sha)
        self.assertEqual(self.registry["sources"][:224], self.predecessor)

    def test_only_exact_two_active_recurring_candidates_are_appended(self) -> None:
        extension = self.registry["sources"][224:]
        self.assertEqual(
            {record["source_id"] for record in extension},
            {"SRC-PR-002", "SRC-PR-007"},
        )
        self.assertTrue(
            all(record["current_status"] == "DEVELOPMENT_MONITOR_EXTENSION_NOT_CANONICAL" for record in extension)
        )
        self.assertTrue(all(record["cadence"] == "MONTHLY" for record in extension))
        self.assertNotIn("SRC-PR-015", {record["source_id"] for record in self.registry["sources"]})

    def test_lifecycle_source_remains_bound_in_metadata_not_monitor_records(self) -> None:
        metadata = self.registry["metadata"]
        self.assertEqual(metadata["lifecycle_resolved_source_ids"], ["SRC-PR-015"])
        self.assertEqual(
            metadata["lifecycle_transition_sha256s"],
            [self.transitions["SRC-PR-015"]["transition_sha256"]],
        )
        self.assertFalse(any(record["source_id"] == "SRC-PR-015" for record in self.registry["sources"]))

    def test_monitor_and_source_bindings_are_unique(self) -> None:
        monitors = self.registry["sources"]
        self.assertEqual(len({record["monitor_id"] for record in monitors}), 226)
        self.assertEqual(len({record["source_id"] for record in monitors}), 226)

    def test_registry_view_is_deterministic(self) -> None:
        again = build_development_registry(self.inputs, self.transitions)
        self.assertEqual(self.registry, again)
        self.assertEqual(
            self.registry["metadata"]["registry_view_sha256"],
            again["metadata"]["registry_view_sha256"],
        )

    def test_hash_tampering_fails_closed(self) -> None:
        tampered = copy.deepcopy(self.registry)
        tampered["sources"][-1]["url"] = "https://example.org/substituted"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify_development_registry(tampered)

    def test_reinserting_lifecycle_source_fails_closed(self) -> None:
        tampered = copy.deepcopy(self.registry)
        record = copy.deepcopy(tampered["sources"][-1])
        record["monitor_id"] = "MON-SRC-PR-015"
        record["source_id"] = "SRC-PR-015"
        tampered["sources"].append(record)
        tampered["metadata"]["record_count"] = 227
        with self.assertRaisesRegex(ValueError, "226 active monitors"):
            verify_development_registry(tampered)


if __name__ == "__main__":
    unittest.main()
