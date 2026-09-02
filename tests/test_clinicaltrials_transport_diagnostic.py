from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/diagnose_clinicaltrials_transport.py"
WORKFLOW = ROOT / ".github/workflows/g0-clinicaltrials-transport-diagnostic.yml"
TARGET = "https://clinicaltrials.gov/api/v2/studies/NCT04676854"
WORKBENCH_SHA = "33414065e53c45221d29209ef4703b6d900781f7"


class ClinicalTrialsTransportDiagnosticContractTests(unittest.TestCase):
    def test_script_is_single_target_body_free_and_non_mutating(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(f'TARGET_URL = "{TARGET}"', text)
        self.assertIn('"response_body_retained": False', text)
        self.assertIn('"source_state_mutated": False', text)
        self.assertIn('"curl_default"', text)
        self.assertIn('"curl_http1_1"', text)
        self.assertIn('"python_requests_http1_1"', text)
        self.assertIn('"python_stdlib_hostname_http1_1"', text)
        self.assertIn('"workbench_pinned_http1_1"', text)
        self.assertIn('"curl_resolve_http1_1"', text)
        self.assertIn('"workbench_single_address_http1_1"', text)
        self.assertIn("DnsGuard().resolve(TARGET_URL)", text)
        self.assertNotIn("write_registry", text)
        self.assertNotIn("initialize_monitoring", text)
        self.assertNotIn("publication", text.lower().split("BOUNDARY =", 1)[0])

    def test_workflow_is_diagnostic_only_and_pins_workbench(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("push:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn(f"ref: {WORKBENCH_SHA}", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("response_body_retained", text)
        self.assertIn("source_state_mutated", text)
        self.assertIn("per_validated_address", text)
        self.assertIn("if: always()", text)


if __name__ == "__main__":
    unittest.main()
