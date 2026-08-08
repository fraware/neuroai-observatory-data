from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "build_monitoring_eligibility.py"
SPEC = importlib.util.spec_from_file_location("build_monitoring_eligibility", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
eligibility = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eligibility)


def _source(source_id: str, source_class: str, title: str = "Example") -> dict[str, object]:
    return {
        "record_id": source_id,
        "record_type": "source",
        "name": title,
        "publisher": "Example",
        "source_class": source_class,
        "source_release": "v1.7",
        "source_section": "test",
        "url": f"https://example.org/{source_id}",
        "payload": {"source_id": source_id, "title": title},
    }


class MonitoringEligibilityTests(unittest.TestCase):
    def test_existing_monitor_is_preserved(self) -> None:
        sources = [_source("SRC-1", "PEER_REVIEWED_PRIMARY_CLINICAL_STUDY")]
        monitors = [
            {
                "record_id": "SRC-1",
                "payload": {"source_id": "SRC-1", "cadence": "WEEKLY"},
            }
        ]
        result = eligibility.classify_monitoring(sources, monitors)
        row = result["sources"][0]
        self.assertTrue(row["monitor_present"])
        self.assertEqual(row["recommended_mode"], "EXISTING_MONITOR")
        self.assertEqual(row["recommended_cadence"], "WEEKLY")
        self.assertEqual(result["metadata"]["unmonitored_effective_source_count"], 0)

    def test_unmonitored_rules_cover_dynamic_static_and_slow_sources(self) -> None:
        sources = [
            _source("SRC-TRIAL", "OFFICIAL_TRIAL_REGISTRY"),
            _source("SRC-TECH", "OFFICIAL_COMPANY_TECHNOLOGY_PAGE"),
            _source("SRC-GUIDE", "OFFICIAL_REGULATOR_PROCEDURAL_GUIDANCE"),
            _source("SRC-LAW", "OFFICIAL_LEGAL_TEXT"),
            _source("SRC-MANUAL", "PUBLIC_HISTORICAL_PATIENT_MANUAL"),
            _source("SRC-PAPER", "PEER_REVIEWED_PRIMARY_CLINICAL_STUDY"),
            _source("SRC-ANN", "OFFICIAL_COMPANY_OWNERSHIP_ANNOUNCEMENT"),
            _source("SRC-JOB", "COMPANY_OPERATIONAL_CAPACITY_SIGNAL", "Vision Rehabilitation Specialist"),
            _source("SRC-OTHER", "UNCLASSIFIED_SOURCE"),
        ]
        result = eligibility.classify_monitoring(sources, [])
        by_id = {row["source_id"]: row for row in result["sources"]}

        self.assertEqual(by_id["SRC-TRIAL"]["recommended_mode"], "RECURRING")
        self.assertEqual(by_id["SRC-TRIAL"]["recommended_cadence"], "MONTHLY")
        self.assertEqual(by_id["SRC-TRIAL"]["priority"], "HIGH")
        self.assertEqual(by_id["SRC-TECH"]["recommended_mode"], "RECURRING")
        self.assertEqual(by_id["SRC-JOB"]["recommended_mode"], "RECURRING")
        self.assertEqual(by_id["SRC-GUIDE"]["recommended_mode"], "ON_CHANGE")
        self.assertEqual(by_id["SRC-LAW"]["recommended_cadence"], "QUARTERLY")
        self.assertEqual(by_id["SRC-MANUAL"]["recommended_mode"], "ARCHIVAL_STATIC")
        self.assertEqual(by_id["SRC-PAPER"]["recommended_mode"], "ARCHIVAL_STATIC")
        self.assertEqual(by_id["SRC-ANN"]["recommended_mode"], "ARCHIVAL_STATIC")
        self.assertEqual(by_id["SRC-OTHER"]["recommended_mode"], "ON_CHANGE")
        self.assertEqual(result["metadata"]["effective_source_count"], 9)
        self.assertEqual(result["metadata"]["unmonitored_effective_source_count"], 9)
        self.assertFalse(result["metadata"]["automatic_registry_mutation"])

    def test_duplicate_or_missing_effective_source_ids_fail(self) -> None:
        row = _source("SRC-1", "OFFICIAL_PAGE")
        with self.assertRaisesRegex(ValueError, "Duplicate effective source_id"):
            eligibility.classify_monitoring([row, dict(row)], [])
        missing = dict(row)
        missing["record_id"] = ""
        with self.assertRaisesRegex(ValueError, "missing record_id"):
            eligibility.classify_monitoring([missing], [])

    def test_outputs_are_machine_readable(self) -> None:
        result = eligibility.classify_monitoring(
            [_source("SRC-1", "OFFICIAL_TRIAL_REGISTRY")],
            [],
        )
        with tempfile.TemporaryDirectory() as temp:
            outputs = eligibility.write_outputs(result, Path(temp))
            payload = json.loads(Path(outputs["json"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["effective_source_count"], 1)
            csv_text = Path(outputs["csv"]).read_text(encoding="utf-8")
            self.assertTrue(csv_text.startswith("source_id,title,publisher"))
            self.assertIn("RECURRING", csv_text)


if __name__ == "__main__":
    unittest.main()
