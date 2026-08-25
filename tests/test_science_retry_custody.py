from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


compiler = _load_module(
    "compile_science_queries_for_retry_custody_tests",
    SCRIPTS / "compile_science_queries.py",
)
acquisition = _load_module(
    "acquire_science_candidates",
    SCRIPTS / "acquire_science_candidates.py",
)
sys.modules["acquire_science_candidates"] = acquisition
strict = _load_module(
    "acquire_science_candidates_strict",
    SCRIPTS / "acquire_science_candidates_strict.py",
)
sys.modules["acquire_science_candidates_strict"] = strict
verification = _load_module(
    "verify_science_retry_custody",
    SCRIPTS / "verify_science_retry_custody.py",
)

PROTOCOL = json.loads(
    (ROOT / "science" / "discovery-protocol-v0.1.json").read_text()
)
COMPILATION = json.loads(
    (ROOT / "science" / "query-compilation-v0.2.json").read_text()
)
PLAN = compiler.compile_plan(PROTOCOL, COMPILATION)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def fetch(self, _url):
        self.calls += 1
        if not self.responses:
            raise RuntimeError("unexpected transport call")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, payload, headers = item
        body = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )
        return acquisition.HttpResult(status=status, headers=headers, body=body)


class Clock:
    def __init__(self, minute="30"):
        self.second = 0
        self.minute = minute

    def __call__(self):
        value = f"2026-08-25T06:{self.minute}:{self.second:02d}Z"
        self.second += 1
        return value


def success_payload(doi="10.1234/retry-custody"):
    return {
        "message": {
            "total-results": 1,
            "items": [
                {
                    "DOI": doi,
                    "title": ["Retry custody example"],
                    "published": {"date-parts": [[2015, 1, 2]]},
                }
            ],
            "next-cursor": "done",
        }
    }


def run_strict(root: Path, responses, *, max_attempts=5, clock=None):
    transport = FakeTransport(responses)
    manifest = strict.acquire_plan(
        PLAN,
        output_root=root,
        transport=transport,
        max_units=1,
        max_attempts=max_attempts,
        sleep_fn=lambda _: None,
        clock_fn=clock or Clock(),
    )
    return manifest, transport


def result_for(root: Path, manifest):
    return json.loads((root / manifest["query_unit_result_paths"][0]).read_text())


class ScienceRetryCustodyTests(unittest.TestCase):
    def test_429_then_200_preserves_both_http_responses(self):
        responses = [
            (
                429,
                {"error": "rate limited"},
                {"retry-after": "0", "content-type": "application/json"},
            ),
            (200, success_payload(), {"content-type": "application/json"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(root, responses, max_attempts=2)
            result = result_for(root, manifest)
            attempts = result["attempt_response_manifest"]
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual([row["http_status"] for row in attempts], [429, 200])
            self.assertEqual(result["received_http_response_count"], 2)
            self.assertEqual(result["transport_error_attempt_count"], 0)
            self.assertTrue(
                all(
                    (root / row["raw_custody_pointer"]).is_file()
                    for row in attempts
                )
            )
            report = verification.verify_retry_custody(PLAN, root)
            self.assertEqual(
                report["status"],
                "RECEIVED_HTTP_RESPONSE_CUSTODY_AND_EXECUTION_IDENTITY_VERIFIED",
            )
            self.assertEqual(report["received_http_responses"], 2)
            self.assertEqual(report["execution_id"], manifest["execution_id"])

    def test_multiple_503_retries_then_success_are_one_logical_request(self):
        responses = [
            (503, {"error": "temporary-1"}, {"retry-after": "0"}),
            (503, {"error": "temporary-2"}, {"retry-after": "0"}),
            (200, success_payload("10.1234/retry-three"), {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(root, responses, max_attempts=3)
            result = result_for(root, manifest)
            attempts = result["attempt_response_manifest"]
            self.assertEqual([row["attempt_index"] for row in attempts], [1, 2, 3])
            self.assertEqual(
                {row["logical_request_index"] for row in attempts}, {1}
            )
            self.assertEqual(
                [row["http_status"] for row in attempts], [503, 503, 200]
            )
            self.assertTrue(verification.verify_retry_custody(PLAN, root))

    def test_terminal_nonretryable_http_error_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(
                root,
                [(404, {"error": "not found"}, {})],
                max_attempts=3,
            )
            result = result_for(root, manifest)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["received_http_response_count"], 1)
            self.assertEqual(
                result["attempt_response_manifest"][0]["http_status"], 404
            )
            self.assertFalse(
                result["attempt_response_manifest"][0]["retryable"]
            )
            self.assertTrue(
                (
                    root
                    / result["attempt_response_manifest"][0][
                        "raw_custody_pointer"
                    ]
                ).is_file()
            )
            self.assertTrue(verification.verify_retry_custody(PLAN, root))

    def test_retry_exhaustion_preserves_every_503_response(self):
        responses = [
            (503, {"error": "temporary-1"}, {}),
            (503, {"error": "temporary-2"}, {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(root, responses, max_attempts=2)
            result = result_for(root, manifest)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(
                [
                    row["http_status"]
                    for row in result["attempt_response_manifest"]
                ],
                [503, 503],
            )
            self.assertEqual(
                [
                    row["retryable"]
                    for row in result["attempt_response_manifest"]
                ],
                [True, False],
            )
            self.assertTrue(verification.verify_retry_custody(PLAN, root))

    def test_transport_error_then_success_records_error_without_fabricating_response_bytes(self):
        responses = [
            urllib.error.URLError("synthetic transport failure"),
            (200, success_payload("10.1234/transport-retry"), {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(root, responses, max_attempts=2)
            result = result_for(root, manifest)
            attempts = result["attempt_response_manifest"]
            self.assertEqual(attempts[0]["outcome"], "TRANSPORT_ERROR")
            self.assertIsNone(attempts[0]["http_status"])
            self.assertIsNone(attempts[0]["content_sha256"])
            self.assertIsNone(attempts[0]["raw_custody_pointer"])
            self.assertEqual(attempts[1]["http_status"], 200)
            report = verification.verify_retry_custody(PLAN, root)
            self.assertEqual(report["transport_error_attempts"], 1)
            self.assertEqual(report["received_http_responses"], 1)

    def test_tampered_retry_body_fails_independent_verification(self):
        responses = [
            (429, {"error": "rate limited"}, {"retry-after": "0"}),
            (200, success_payload(), {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(root, responses, max_attempts=2)
            result = result_for(root, manifest)
            retry = result["attempt_response_manifest"][0]
            (root / retry["raw_custody_pointer"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verification.verify_retry_custody(PLAN, root)

    def test_reordered_attempts_fail_even_if_attempt_digest_is_recomputed(self):
        responses = [
            (503, {"error": "temporary"}, {}),
            (200, success_payload(), {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(root, responses, max_attempts=2)
            result_path = root / manifest["query_unit_result_paths"][0]
            result = json.loads(result_path.read_text())
            result["attempt_response_manifest"] = list(
                reversed(result["attempt_response_manifest"])
            )
            result["attempt_response_manifest_sha256"] = acquisition._sha256_json(
                result["attempt_response_manifest"]
            )
            result_path.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n"
            )
            with self.assertRaisesRegex(
                ValueError, "attempt indices are not contiguous"
            ):
                verification.verify_retry_custody(PLAN, root)

    def test_successful_attempt_bound_to_wrong_request_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(
                root, [(200, success_payload(), {})], max_attempts=1
            )
            result_path = root / manifest["query_unit_result_paths"][0]
            result = json.loads(result_path.read_text())
            result["attempt_response_manifest"][0]["request_url_sha256"] = (
                "0" * 64
            )
            result["attempt_response_manifest_sha256"] = acquisition._sha256_json(
                result["attempt_response_manifest"]
            )
            result_path.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n"
            )
            with self.assertRaisesRegex(ValueError, "request URL digest mismatch"):
                verification.verify_retry_custody(PLAN, root)

    def test_reuse_has_distinct_execution_identity_without_new_provider_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, first_transport = run_strict(
                root,
                [(200, success_payload("10.1234/reuse"), {})],
                max_attempts=1,
                clock=Clock("30"),
            )
            second, second_transport = run_strict(
                root,
                [],
                max_attempts=1,
                clock=Clock("31"),
            )
            third, third_transport = run_strict(
                root,
                [],
                max_attempts=1,
                clock=Clock("32"),
            )

            self.assertEqual(first_transport.calls, 1)
            self.assertEqual(second_transport.calls, 0)
            self.assertEqual(third_transport.calls, 0)
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertEqual(second["run_id"], third["run_id"])
            self.assertEqual(
                len({first["execution_id"], second["execution_id"], third["execution_id"]}),
                3,
            )
            self.assertEqual(first["acquired_query_units_this_execution"], 1)
            self.assertEqual(first["reused_complete_query_units_this_execution"], 0)
            self.assertEqual(second["acquired_query_units_this_execution"], 0)
            self.assertEqual(second["reused_complete_query_units_this_execution"], 1)
            self.assertEqual(third["acquired_query_units_this_execution"], 0)
            self.assertEqual(third["reused_complete_query_units_this_execution"], 1)
            self.assertEqual(
                len(list((root / "executions").glob("SCIENCE-EXECUTION-*/run-manifest.json"))),
                3,
            )
            report = verification.verify_retry_custody(PLAN, root)
            self.assertEqual(report["execution_id"], third["execution_id"])
            self.assertEqual(report["reused_complete_query_units_this_execution"], 1)

    def test_execution_identity_tampering_fails_independent_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _transport = run_strict(
                root,
                [(200, success_payload("10.1234/execution-tamper"), {})],
                max_attempts=1,
            )
            manifest_path = root / "run-manifest.json"
            tampered = json.loads(manifest_path.read_text())
            tampered["execution_id"] = "SCIENCE-EXECUTION-00000000000000000000"
            manifest_path.write_text(
                json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "execution_id mismatch"):
                verification.verify_retry_custody(PLAN, root)


if __name__ == "__main__":
    unittest.main()
