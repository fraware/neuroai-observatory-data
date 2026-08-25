from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
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
    "compile_science_queries_for_gated_runner_tests",
    SCRIPTS / "compile_science_queries.py",
)
acquisition = _load_module(
    "acquire_science_candidates",
    SCRIPTS / "acquire_science_candidates.py",
)
sys.modules["acquire_science_candidates"] = acquisition
sys.modules["validate_science_graph"] = _load_module(
    "validate_science_graph", SCRIPTS / "validate_science_graph.py"
)
sys.modules["validate_source_universes"] = _load_module(
    "validate_source_universes", SCRIPTS / "validate_source_universes.py"
)
provenance = _load_module(
    "verify_science_candidate_provenance",
    SCRIPTS / "verify_science_candidate_provenance.py",
)
sys.modules["verify_science_candidate_provenance"] = provenance
acquisition_verification = _load_module(
    "verify_science_acquisition",
    SCRIPTS / "verify_science_acquisition.py",
)
sys.modules["verify_science_acquisition"] = acquisition_verification
strict = _load_module(
    "acquire_science_candidates_strict",
    SCRIPTS / "acquire_science_candidates_strict.py",
)
sys.modules["acquire_science_candidates_strict"] = strict
retry_verification = _load_module(
    "verify_science_retry_custody",
    SCRIPTS / "verify_science_retry_custody.py",
)
sys.modules["verify_science_retry_custody"] = retry_verification
http_transport = _load_module(
    "science_http_transport",
    SCRIPTS / "science_http_transport.py",
)
sys.modules["science_http_transport"] = http_transport
runner = _load_module(
    "run_science_acquisition",
    SCRIPTS / "run_science_acquisition.py",
)

PROTOCOL = json.loads(
    (ROOT / "science" / "discovery-protocol-v0.1.json").read_text()
)
COMPILATION = json.loads(
    (ROOT / "science" / "query-compilation-v0.2.json").read_text()
)
PLAN = compiler.compile_plan(PROTOCOL, COMPILATION)


class Clock:
    def __init__(self, minute: int):
        self.minute = minute
        self.second = 0

    def __call__(self) -> str:
        value = f"2026-08-25T07:{self.minute:02d}:{self.second:02d}Z"
        self.second += 1
        return value


class FakeNoRedirectTransport:
    redirect_policy = runner.REQUIRED_REDIRECT_POLICY

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def fetch(self, _url: str):
        self.calls += 1
        if not self.responses:
            raise RuntimeError("unexpected transport call")
        status, payload, headers = self.responses.pop(0)
        return acquisition.HttpResult(
            status=status,
            headers=headers,
            body=json.dumps(payload).encode("utf-8"),
        )


class UnsafeRedirectTransport(FakeNoRedirectTransport):
    redirect_policy = "AUTO_FOLLOW"


def _crossref_success_payload(doi: str = "10.1234/gated-runner") -> dict:
    return {
        "message": {
            "total-results": 1,
            "items": [
                {
                    "DOI": doi,
                    "title": ["Gated science acquisition example"],
                    "published": {"date-parts": [[2015, 2, 3]]},
                }
            ],
            "next-cursor": "complete",
        }
    }


def _run(root: Path, transport, *, minute: int):
    return runner.run_acquisition(
        PLAN,
        output_root=root,
        transport=transport,
        max_units=1,
        max_attempts=2,
        max_pages=10,
        sleep_fn=lambda _: None,
        clock_fn=Clock(minute),
    )


class RunScienceAcquisitionTests(unittest.TestCase):
    def test_gated_entrypoint_binds_verified_scoped_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transport = FakeNoRedirectTransport(
                [(200, _crossref_success_payload(), {"content-type": "application/json"})]
            )

            envelope = _run(root, transport, minute=40)

            self.assertEqual(transport.calls, 1)
            self.assertEqual(envelope["plan_id"], PLAN["plan_id"])
            self.assertEqual(envelope["plan_sha256"], PLAN["plan_sha256"])
            self.assertEqual(envelope["selected_query_units"], 1)
            self.assertEqual(envelope["complete_query_units"], 1)
            self.assertEqual(envelope["partial_query_units"], 0)
            self.assertEqual(envelope["failed_query_units"], 0)
            self.assertFalse(envelope["selected_is_full_plan"])
            self.assertFalse(envelope["full_plan_complete"])
            self.assertEqual(envelope["acquired_query_units_this_execution"], 1)
            self.assertEqual(envelope["reused_complete_query_units_this_execution"], 0)
            self.assertEqual(
                envelope["release_eligibility"], acquisition.RELEASE_INELIGIBLE
            )
            self.assertEqual(
                envelope["state"],
                "ACQUISITION_EVIDENCE_VERIFIED_NOT_RELEASE_AUTHORIZED",
            )

            manifest = json.loads((root / "run-manifest.json").read_text())
            self.assertEqual(envelope["result_state_id"], manifest["result_state_id"])
            self.assertEqual(envelope["execution_id"], manifest["execution_id"])
            self.assertEqual(
                envelope["execution_identity_sha256"],
                manifest["execution_identity_sha256"],
            )

            for name in runner.VERIFIED_EXECUTION_PRODUCTS:
                self.assertTrue((root / name).is_file(), name)
                self.assertTrue(
                    (root / "executions" / envelope["execution_id"] / name).is_file(),
                    name,
                )

            retry_report = retry_verification.verify_retry_custody(PLAN, root)
            self.assertEqual(retry_report["execution_id"], envelope["execution_id"])
            self.assertEqual(
                retry_report["status"],
                "RECEIVED_HTTP_RESPONSE_CUSTODY_AND_EXECUTION_IDENTITY_VERIFIED",
            )

    def test_reuse_creates_new_execution_without_new_provider_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_transport = FakeNoRedirectTransport(
                [(200, _crossref_success_payload("10.1234/reuse-gated"), {})]
            )
            first = _run(root, first_transport, minute=41)

            second_transport = FakeNoRedirectTransport([])
            second = _run(root, second_transport, minute=42)

            self.assertEqual(first_transport.calls, 1)
            self.assertEqual(second_transport.calls, 0)
            self.assertEqual(first["result_state_id"], second["result_state_id"])
            self.assertNotEqual(first["execution_id"], second["execution_id"])
            self.assertNotEqual(
                first["verification_envelope_id"], second["verification_envelope_id"]
            )
            self.assertEqual(second["acquired_query_units_this_execution"], 0)
            self.assertEqual(second["reused_complete_query_units_this_execution"], 1)

            for execution_id in (first["execution_id"], second["execution_id"]):
                archive = root / "executions" / execution_id
                self.assertTrue((archive / "run-manifest.json").is_file())
                self.assertTrue((archive / "verification-envelope.json").is_file())

    def test_gated_entrypoint_rejects_redirect_following_transport_before_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = UnsafeRedirectTransport(
                [(200, _crossref_success_payload("10.1234/unsafe"), {})]
            )
            with self.assertRaisesRegex(
                ValueError,
                "disables automatic redirects",
            ):
                _run(Path(tmp), transport, minute=43)
            self.assertEqual(transport.calls, 0)


if __name__ == "__main__":
    unittest.main()
