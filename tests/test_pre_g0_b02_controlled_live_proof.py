from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

proof = importlib.import_module("run_pre_g0_b02_controlled_live_proof")


class PreG0B02ControlledLiveProofTests(unittest.TestCase):
    def _package(self) -> dict:
        return {
            "status": proof.SHADOW_EVALUATION_STATUS,
            "metadata": {
                "authorization": {
                    "authorization_id": "AUTH-TEST-001",
                    "authorization_sha256": "a" * 64,
                    "authorized_by": "test-operator",
                    "authorized_at": "2026-09-02T13:00:00Z",
                    "purpose": "Controlled unit test.",
                    "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
                }
            },
            "collector": {
                "handoff_enabled": False,
                "default_transport": "PinnedSocketHttpTransport",
                "dns_guard": "DnsGuard",
            },
            "collection_run": {
                "run_id": "CRUN-test",
                "status": "COMPLETE",
                "counts": {"total": 1, "succeeded": 1, "failed": 0, "skipped": 0},
                "outcomes": [
                    {
                        "source_id": proof.PROOF_SOURCE_ID,
                        "status": "RESULT",
                        "record_id": "RES-test",
                    }
                ],
            },
            "capture_digests": [
                {
                    "source_id": proof.PROOF_SOURCE_ID,
                    "result_id": "RES-test",
                    "sha256": "b" * 64,
                    "http_status": 200,
                    "size_bytes": 1234,
                    "media_type": "text/html",
                    "evidence_state": "CAPTURED",
                }
            ],
            "content_safety": {
                "scope": "ALL_DURABLE_RESULTS_IN_QUARANTINE_ROOT",
                "durable_result_records_checked": 1,
                "scans_created": 1,
                "existing_scans_verified": 0,
                "state_counts": {proof.EXPECTED_SCAN_STATE: 1},
                "scanner_ids": [proof.EXPECTED_SCANNER_ID],
                "detail_exposed": False,
            },
        }

    def test_fixed_source_identity_is_fail_closed(self) -> None:
        registry = {"sources": [dict(proof.PROOF_SOURCE_EXPECTED)]}
        resolved = proof._resolve_fixed_source(registry)
        self.assertEqual(resolved["source_id"], proof.PROOF_SOURCE_ID)

        tampered = {"sources": [dict(proof.PROOF_SOURCE_EXPECTED, url="https://example.com/")]}
        with self.assertRaisesRegex(ValueError, "fixed proof source identity changed"):
            proof._resolve_fixed_source(tampered)

    def test_sanitized_proof_accepts_only_exact_success_boundary(self) -> None:
        result = proof.build_sanitized_proof(
            self._package(),
            authorization_id="AUTH-TEST-001",
            as_of="2026-09-02",
            workbench_commit=proof.EXPECTED_WORKBENCH_COMMIT,
        )
        self.assertEqual(result["status"], proof.STATUS)
        self.assertEqual(result["source"]["source_id"], proof.PROOF_SOURCE_ID)
        self.assertFalse(result["controls"]["handoff_enabled"])
        self.assertFalse(result["controls"]["canonical_publication_performed"])
        self.assertFalse(result["content_safety"]["substantive_clean_claim"])
        self.assertNotIn("body", result["collection"]["capture"])

    def test_retrieval_failure_cannot_be_reported_as_b02_proof(self) -> None:
        package = self._package()
        package["collection_run"]["counts"]["succeeded"] = 0
        package["collection_run"]["counts"]["failed"] = 1
        with self.assertRaisesRegex(ValueError, "requires one successful retrieval"):
            proof.build_sanitized_proof(
                package,
                authorization_id="AUTH-TEST-001",
                as_of="2026-09-02",
                workbench_commit=proof.EXPECTED_WORKBENCH_COMMIT,
            )

    def test_clean_scan_claim_cannot_pass_default_proof(self) -> None:
        package = self._package()
        package["content_safety"]["state_counts"] = {"CLEAN": 1}
        with self.assertRaisesRegex(ValueError, "remain fail-closed"):
            proof.build_sanitized_proof(
                package,
                authorization_id="AUTH-TEST-001",
                as_of="2026-09-02",
                workbench_commit=proof.EXPECTED_WORKBENCH_COMMIT,
            )

    def test_live_authorization_environment_is_scoped_and_restored(self) -> None:
        prior_live = os.environ.get(proof.LIVE_COLLECTION_ENV)
        prior_auth = os.environ.get(proof.LIVE_AUTHORIZATION_ENV)
        os.environ[proof.LIVE_COLLECTION_ENV] = "prior-live"
        os.environ[proof.LIVE_AUTHORIZATION_ENV] = "prior-auth"

        def fake_live(**kwargs):
            self.assertEqual(os.environ[proof.LIVE_COLLECTION_ENV], "1")
            self.assertIn("authorization_sha256", os.environ[proof.LIVE_AUTHORIZATION_ENV])
            self.assertEqual(kwargs["registry_sha256"], "c" * 64)
            return {"status": "synthetic"}

        try:
            with mock.patch.object(proof, "run_live_cohort_collection", side_effect=fake_live):
                returned = proof._execute_live(
                    plan={"due": [], "not_due": [], "manual": []},
                    registry={"sources": []},
                    registry_sha256="c" * 64,
                    quarantine_root=Path("synthetic-quarantine"),
                    authorization_id="AUTH-TEST-ENV",
                    actor="test-operator",
                )
            self.assertEqual(returned, {"status": "synthetic"})
            self.assertEqual(os.environ[proof.LIVE_COLLECTION_ENV], "prior-live")
            self.assertEqual(os.environ[proof.LIVE_AUTHORIZATION_ENV], "prior-auth")
        finally:
            if prior_live is None:
                os.environ.pop(proof.LIVE_COLLECTION_ENV, None)
            else:
                os.environ[proof.LIVE_COLLECTION_ENV] = prior_live
            if prior_auth is None:
                os.environ.pop(proof.LIVE_AUTHORIZATION_ENV, None)
            else:
                os.environ[proof.LIVE_AUTHORIZATION_ENV] = prior_auth

    def test_workflow_is_manual_fixed_source_and_sanitized_artifact_only(self) -> None:
        workflow = (ROOT / ".github/workflows/pre-g0-b02-controlled-live-proof.yml").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "scripts/run_pre_g0_b02_controlled_live_proof.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn(f"ref: {proof.EXPECTED_WORKBENCH_COMMIT}", workflow)
        self.assertNotIn("source-id", workflow)
        self.assertIn('PROOF_SOURCE_ID = "SRC-0002"', script)
        self.assertIn('"url": "https://neurosity.co/"', script)
        self.assertIn("run_live_cohort_collection", script)
        self.assertNotIn("CollectionScheduler", script)
        self.assertIn("proof.json", workflow)
        self.assertNotIn("quarantine/**", workflow)
        self.assertIn("rm -rf \"$RUNNER_TEMP/pre-g0-b02-proof/workspace\"", workflow)


if __name__ == "__main__":
    unittest.main()
