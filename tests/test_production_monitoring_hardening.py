from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH_SHA = "33414065e53c45221d29209ef4703b6d900781f7"
PINNED_TRANSPORT = "PinnedSocketHttpTransport"
LEGACY_TRANSPORT = "StdlibHttpTransport"
UPLOAD_ARTIFACT_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"

NETWORK_SCRIPTS = (
    "scripts/run_operational_due_cycle.py",
    "scripts/probe_source_route_resilience.py",
    "scripts/run_successor_discovery.py",
    "scripts/run_live_interruption_resume_drill.py",
)
LIVE_WORKFLOWS = (
    ".github/workflows/operational-live-cycle.yml",
    ".github/workflows/successor-discovery.yml",
    ".github/workflows/operational-interruption-resume-drill.yml",
    ".github/workflows/pre-g0-b02-controlled-live-proof.yml",
)
WORKBENCH_COUPLED_WORKFLOWS = LIVE_WORKFLOWS + (
    ".github/workflows/pre-g0-b02-contract.yml",
)
HARDENED_WORKFLOWS = WORKBENCH_COUPLED_WORKFLOWS + (
    ".github/workflows/observatory-v2-release.yml",
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ProductionMonitoringHardeningTests(unittest.TestCase):
    def test_all_live_network_paths_use_dns_pinned_transport(self) -> None:
        for path in NETWORK_SCRIPTS:
            with self.subTest(path=path):
                text = _read(path)
                self.assertIn(PINNED_TRANSPORT, text)
                self.assertNotIn(LEGACY_TRANSPORT, text)

    def test_all_workbench_coupled_workflows_pin_exact_current_workbench(self) -> None:
        for path in WORKBENCH_COUPLED_WORKFLOWS:
            with self.subTest(path=path):
                text = _read(path)
                self.assertIn(f"ref: {WORKBENCH_SHA}", text)
                self.assertNotIn("428b4e8d797c0729bc4f36678daec88711688689", text)
                self.assertNotIn("65c32abce505f0915e8b5a146b914c9ce7be07f8", text)

    def test_workflow_actions_are_immutable_sha_pins(self) -> None:
        floating = re.compile(
            r"uses:\s+actions/(?:checkout|setup-python|upload-artifact)@v\d+"
        )
        immutable = re.compile(
            r"uses:\s+actions/(?:checkout|setup-python|upload-artifact)@[0-9a-f]{40}"
        )
        for path in HARDENED_WORKFLOWS:
            with self.subTest(path=path):
                text = _read(path)
                self.assertIsNone(floating.search(text))
                self.assertIsNotNone(immutable.search(text))

    def test_sanitized_operational_outputs_are_retained(self) -> None:
        expectations = {
            ".github/workflows/operational-live-cycle.yml": "operational-live-report.json",
            ".github/workflows/successor-discovery.yml": "successor-discovery.json",
            ".github/workflows/operational-interruption-resume-drill.yml": "report.json",
            ".github/workflows/pre-g0-b02-controlled-live-proof.yml": "proof.json",
        }
        for path, artifact_path in expectations.items():
            with self.subTest(path=path):
                text = _read(path)
                self.assertIn(f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}", text)
                self.assertIn(artifact_path, text)
                self.assertIn("retention-days: 90", text)
                self.assertIn("if-no-files-found: error", text)

    def test_reports_declare_transport_security_contract(self) -> None:
        for path in NETWORK_SCRIPTS:
            with self.subTest(path=path):
                self.assertIn("DNS_PINNED_VALIDATED_ADDRESS_SET", _read(path))

    def test_interruption_drill_consumes_verified_lifecycle_overlay(self) -> None:
        script = _read("scripts/run_live_interruption_resume_drill.py")
        self.assertIn("load_verified_lifecycle_overlay", script)
        self.assertIn("build_development_registry(inputs, transitions)", script)
        self.assertIn(
            "forbidden_lifecycle_ids = set(transitions) & set(source_index)", script
        )
        self.assertNotIn("registry = build_development_registry(inputs)\n", script)

    def test_pre_g0_b02_proof_delegates_to_governed_live_facade(self) -> None:
        script = _read("scripts/run_pre_g0_b02_controlled_live_proof.py")
        workflow = _read(".github/workflows/pre-g0-b02-controlled-live-proof.yml")
        contract = _read(".github/workflows/pre-g0-b02-contract.yml")
        self.assertIn("run_live_cohort_collection", script)
        self.assertNotIn("CollectionScheduler", script)
        self.assertIn('PROOF_SOURCE_ID = "SRC-0002"', script)
        self.assertIn('"url": "https://neurosity.co/"', script)
        self.assertIn("source_ids=[PROOF_SOURCE_ID]", script)

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("raw_response_body_exposed", workflow)
        self.assertIn('rm -rf "$RUNNER_TEMP/pre-g0-b02-proof/workspace"', workflow)

        self.assertIn("pull_request:", contract)
        self.assertIn("push:", contract)
        self.assertNotIn("workflow_dispatch:", contract)
        self.assertNotIn("--authorization-id", contract)
        self.assertNotIn("Execute one-source governed controlled-live proof", contract)
        self.assertIn('test -z "${NEUROAI_LIVE_COLLECTION:-}"', contract)
        self.assertIn(
            'test -z "${NEUROAI_LIVE_COLLECTION_AUTHORIZATION_JSON:-}"',
            contract,
        )


if __name__ == "__main__":
    unittest.main()
