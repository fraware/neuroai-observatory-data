from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class CTGovFirstCaptureBoundaryDocTests(unittest.TestCase):
    def test_boundary_keeps_capture_quarantine_and_monitor_succession_separate(self) -> None:
        text = (ROOT / "docs" / "CTGOV_FIRST_CAPTURE_BOUNDARY.md").read_text(encoding="utf-8")
        required = [
            "PRIMARY",
            "/api/v2/studies/{NCT}",
            "RETRIEVED_BYTES_NOT_SUBSTANTIVELY_ADJUDICATED",
            "APPROVED_FOR_HANDOFF",
            "Raw bytes do not enter S2",
            "Do not create a monitor-registry successor from retrieval alone",
            "public `/study/{NCT}` HTML route is liveness corroboration only",
        ]
        for phrase in required:
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
