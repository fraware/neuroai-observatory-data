from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from probe_source_route_resilience import _check_body, _extract_nct_ids, canonical_bytes, sha256  # noqa: E402


class SourceRouteResilienceTests(unittest.TestCase):
    def test_extract_nct_id_from_single_study(self) -> None:
        payload = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT04676854"}
            }
        }
        self.assertEqual(_extract_nct_ids(payload), {"NCT04676854"})

    def test_extract_nct_id_from_search_response(self) -> None:
        payload = {
            "studies": [
                {"protocolSection": {"identificationModule": {"nctId": "NCT04676854"}}},
                {"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}}},
            ]
        }
        self.assertEqual(_extract_nct_ids(payload), {"NCT04676854", "NCT00000001"})

    def test_json_identity_check_requires_exact_nct(self) -> None:
        body = json.dumps(
            {"protocolSection": {"identificationModule": {"nctId": "NCT04676854"}}}
        ).encode()
        self.assertTrue(_check_body(body, {"kind": "JSON_NCT_ID", "expected": "NCT04676854"}))
        self.assertFalse(_check_body(body, {"kind": "JSON_NCT_ID", "expected": "NCT99999999"}))
        self.assertFalse(_check_body(b"not-json", {"kind": "JSON_NCT_ID", "expected": "NCT04676854"}))

    def test_text_liveness_check_is_case_insensitive(self) -> None:
        body = b"<html><title>Vision Rehabilitation Specialist, EU</title></html>"
        self.assertTrue(
            _check_body(
                body,
                {"kind": "TEXT_CONTAINS", "expected": "vision rehabilitation specialist, eu"},
            )
        )
        self.assertFalse(_check_body(body, {"kind": "TEXT_CONTAINS", "expected": "different role"}))

    def test_unknown_check_kind_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported live route check kind"):
            _check_body(b"x", {"kind": "REGEX_EVERYTHING", "expected": "x"})

    def test_hashing_is_deterministic(self) -> None:
        left = {"b": 2, "a": 1}
        right = {"a": 1, "b": 2}
        self.assertEqual(canonical_bytes(left), canonical_bytes(right))
        self.assertEqual(sha256(left), sha256(right))


if __name__ == "__main__":
    unittest.main()
