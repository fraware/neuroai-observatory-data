from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_analytical_projection import build_tables, load_inputs  # noqa: E402
from build_current_monitor_accountability import build_projection, verify_expected_current_checkpoint  # noqa: E402


class CurrentMonitorAccountabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        inputs = load_inputs((ROOT / "releases/data-v0.1.0-public-governing/records").resolve(), supplemental_dir=(ROOT / "supplemental_records").resolve())
        tables = build_tables(inputs)
        cls.sources = tables["sources"]
        cls.monitors = tables["source_monitors"]
        cls.projection = build_projection(cls.sources, cls.monitors)

    def test_exact_current_checkpoint(self) -> None:
        verify_expected_current_checkpoint(self.projection)
        self.assertEqual(self.projection["current"]["effective_source_count"], 248)
        self.assertEqual(
            {key: self.projection["current"]["counts"].get(key, 0) for key in ("MONITORED", "EXEMPT_WITH_RATIONALE", "MANUAL_ONLY", "GAP")},
            {"MONITORED": 224, "EXEMPT_WITH_RATIONALE": 15, "MANUAL_ONLY": 6, "GAP": 3},
        )

    def test_only_recurring_unmonitored_sources_become_monitor_candidates(self) -> None:
        candidate = self.projection["monitor_extension_candidate"]
        self.assertEqual(candidate["candidate_record_count"], 3)
        self.assertEqual(len({record["source_id"] for record in candidate["candidate_records"]}), 3)
        self.assertTrue(all(record["cadence"] for record in candidate["candidate_records"]))
        self.assertTrue(all(record["current_status"] == "DEVELOPMENT_MONITOR_EXTENSION_NOT_CANONICAL" for record in candidate["candidate_records"]))

    def test_dsmb_announcement_remains_archival_even_when_title_mentions_trial(self) -> None:
        rows = {row["source_id"]: row for row in self.projection["current"]["sources"]}
        self.assertEqual(rows["SRC-PR-010"]["accountability_state"], "EXEMPT_WITH_RATIONALE")
        self.assertEqual(rows["SRC-PR-010"]["recommended_mode"], "ARCHIVAL_STATIC")
        candidate_ids = {
            record["source_id"] for record in self.projection["monitor_extension_candidate"]["candidate_records"]
        }
        self.assertNotIn("SRC-PR-010", candidate_ids)

    def test_candidate_reaches_zero_gap_without_rewriting_predecessor(self) -> None:
        candidate = self.projection["candidate_accountability"]
        self.assertEqual(candidate["coverage_fraction"], 1.0)
        self.assertEqual(candidate["gap_source_ids"], [])
        self.assertEqual(self.projection["monitor_extension_candidate"]["predecessor_monitor_count"], 224)
        self.assertEqual(len(self.monitors), 224)

    def test_projection_is_deterministic(self) -> None:
        again = build_projection(self.sources, self.monitors)
        self.assertEqual(self.projection["projection_sha256"], again["projection_sha256"])
        self.assertEqual(self.projection, again)

    def test_archival_and_on_change_are_explicit_not_silent_gaps(self) -> None:
        rows = [row for row in self.projection["current"]["sources"] if row["accountability_state"] != "MONITORED"]
        archival = [row for row in rows if row["accountability_state"] == "EXEMPT_WITH_RATIONALE"]
        manual = [row for row in rows if row["accountability_state"] == "MANUAL_ONLY"]
        gaps = [row for row in rows if row["accountability_state"] == "GAP"]
        self.assertEqual(len(archival), 15)
        self.assertEqual(len(manual), 6)
        self.assertEqual(len(gaps), 3)
        self.assertTrue(all(row["rationale"] for row in archival + manual + gaps))


if __name__ == "__main__":
    unittest.main()
