from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.source_universe_programme_control import require_source_universe_stream

CONTROL = Path("curation/source_universe_expansion_backlog_v0.1.json")


class SourceUniverseProgrammeControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.control = json.loads(CONTROL.read_text(encoding="utf-8"))

    def test_current_control_resolves_structured_streams(self):
        for stream_id in (
            "SU-PUBLICATIONS-BIOMED",
            "SU-PATENTS-EPO",
            "SU-GRANTS-US",
            "SU-REGULATORY-US",
            "SU-SAFETY-US",
        ):
            row = require_source_universe_stream(self.control, stream_id)
            self.assertEqual(row["stream_id"], stream_id)

    def test_noncanonical_boundary_fails_closed(self):
        control = copy.deepcopy(self.control)
        control["status"] = "CANONICAL"
        with self.assertRaisesRegex(ValueError, "must remain noncanonical"):
            require_source_universe_stream(control, "SU-PATENTS-EPO")

    def test_missing_invariant_fails_closed(self):
        control = copy.deepcopy(self.control)
        control["programme_invariants"].remove("NO_SILENT_CANONICAL_MUTATION")
        with self.assertRaisesRegex(ValueError, "Missing source-universe programme invariants"):
            require_source_universe_stream(control, "SU-PATENTS-EPO")

    def test_unknown_stream_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Expected exactly one"):
            require_source_universe_stream(self.control, "SU-NOT-REAL")


if __name__ == "__main__":
    unittest.main()
