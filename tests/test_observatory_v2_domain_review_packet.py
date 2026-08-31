from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_observatory_v2_domain_review_packet as review

EXPECTED = {"SECURITY", "METHODOLOGY", "DATA_GOVERNANCE", "ACCESSIBILITY", "DOMAIN", "AFFECTED_COMMUNITY"}


class DomainReviewPacketTests(unittest.TestCase):
    def test_default_packet_is_pending_and_blocked_on_execution_verification(self) -> None:
        packet = review.build()
        self.assertEqual({row["track"] for row in packet["tracks"]}, EXPECTED)
        self.assertEqual(len(packet["tracks"]), 6)
        self.assertTrue(all(row["state"] == "PENDING" for row in packet["tracks"]))
        self.assertTrue(all(row["reviewer"]["name"] is None for row in packet["tracks"]))
        self.assertIn("V2-EXECUTION-VERIFICATION", {row["condition_id"] for row in packet["blocking_conditions"]})
        self.assertFalse(packet["release_authorized"])

    def test_execution_verification_must_bind_exact_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "verification.json"
            path.write_text(json.dumps({
                "schema_version": "1.0.0-draft",
                "candidate_manifest_sha256": "0" * 64,
                "execution_state": "VERIFIED_EXECUTED",
                "executor": "test",
                "execution_environment": "test",
                "executed_at": "2026-08-31T00:00:00Z",
                "tests_executed": ["whole-current candidate suite"],
                "result": "PASS",
                "identity_boundary": "test identity is not authentication"
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                review.build(execution_verification=path)

    def test_packet_cannot_authorize_release(self) -> None:
        packet = review.build()
        self.assertFalse(packet["release_authorized"])
        for track in packet["tracks"]:
            self.assertIsNone(track["rationale"])
            self.assertEqual(track["conditions"], [])
            self.assertEqual(track["evidence_requests"], [])


if __name__ == "__main__":
    unittest.main()
