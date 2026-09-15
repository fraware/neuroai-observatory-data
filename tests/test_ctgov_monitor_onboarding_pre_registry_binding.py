from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import review_ctgov_monitoring_onboarding as onboarding
from tests.test_ctgov_monitor_onboarding import _write_decisions, _write_materialization


class CTGovPreRegistryBindingTests(unittest.TestCase):
    def test_first_capture_template_requires_onboarding_manifest_not_registry_digest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            _write_materialization(materialization)
            decisions = _write_decisions(root, materialization)
            result = onboarding.build_onboarding(materialization, decisions)
            plan = result["onboarding"]["plans"][0]
            required = plan["first_capture_request_template"]["required_execution_fields"]
            self.assertEqual(
                required,
                [
                    "requested_at",
                    "onboarding_manifest_sha256",
                    "collector_version",
                    "configuration_hash",
                    "boundary",
                ],
            )
            self.assertNotIn("registry_sha256", required)
            self.assertEqual(plan["monitor_registry_state"], "NOT_CREATED")
            self.assertIn("no monitor-registry digest exists yet", plan["first_capture_requirement"])


if __name__ == "__main__":
    unittest.main()
