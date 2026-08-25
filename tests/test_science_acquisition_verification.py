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


compiler = _load_module("compile_science_queries_for_verification_tests", SCRIPTS / "compile_science_queries.py")
acquisition = _load_module("acquire_science_candidates_for_verification_tests", SCRIPTS / "acquire_science_candidates.py")
sys.modules["validate_science_graph"] = _load_module("validate_science_graph", SCRIPTS / "validate_science_graph.py")
sys.modules["validate_source_universes"] = _load_module("validate_source_universes", SCRIPTS / "validate_source_universes.py")
verification = _load_module("verify_science_acquisition", SCRIPTS / "verify_science_acquisition.py")

PROTOCOL = json.loads((ROOT / "science" / "discovery-protocol-v0.1.json").read_text())
COMPILATION = json.loads((ROOT / "science" / "query-compilation-v0.1.json").read_text())


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)

    def fetch(self, _url):
        if not self.responses:
            raise RuntimeError("unexpected transport call")
        status, payload, headers = self.responses.pop(0)
        return acquisition.HttpResult(
            status=status,
            headers=headers,
            body=json.dumps(payload).encode("utf-8"),
        )


class Clock:
    def __init__(self):
        self.second = 0

    def __call__(self):
        value = f"2026-08-25T04:10:{self.second:02d}Z"
        self.second += 1
        return value


def _plan_and_unit_ids():
    plan = compiler.compile_plan(PROTOCOL, COMPILATION)
    crossref = next(unit for unit in plan["query_units"] if unit["provider"] == "CROSSREF")
    europe_pmc = next(unit for unit in plan["query_units"] if unit["provider"] == "EUROPE_PMC")
    return plan, {crossref["query_unit_id"], europe_pmc["query_unit_id"]}


def _responses():
    return [
        (
            200,
            {
                "message": {
                    "total-results": 1,
                    "items": [
                        {
                            "DOI": "10.1234/shared",
                            "title": ["Shared neural interface record"],
                            "published": {"date-parts": [[2015, 3, 1]]},
                        }
                    ],
                    "next-cursor": "crossref-done",
                }
            },
            {"content-type": "application/json"},
        ),
        (
            200,
            {
                "hitCount": 1,
                "nextCursorMark": "epmc-done",
                "resultList": {
                    "result": [
                        {
                            "source": "MED",
                            "id": "123456",
                            "doi": "10.1234/shared",
                            "pmid": "123456",
                            "pmcid": "PMC999",
                            "title": "Shared neural interface record",
                            "pubYear": "2015",
                        }
                    ]
                },
            },
            {"content-type": "application/json"},
        ),
    ]


def _build_verified_run(root: Path):
    plan, unit_ids = _plan_and_unit_ids()
    acquisition.acquire_plan(
        plan,
        output_root=root,
        transport=FakeTransport(_responses()),
        query_unit_ids=unit_ids,
        sleep_fn=lambda _: None,
        clock_fn=Clock(),
    )
    return plan


class ScienceAcquisitionVerificationTests(unittest.TestCase):
    def test_verified_scoped_run_builds_candidate_and_coverage_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _build_verified_run(root)
            candidate_manifest, coverage_index = verification.verify_acquisition(plan, root)
            self.assertEqual(candidate_manifest["selected_query_units"], 2)
            self.assertEqual(candidate_manifest["complete_query_units"], 2)
            self.assertEqual(candidate_manifest["candidate_record_occurrences"], 2)
            self.assertEqual(candidate_manifest["release_eligibility"], verification.RELEASE_INELIGIBLE)
            self.assertEqual(len(coverage_index["complete_query_unit_coverages"]), 2)
            self.assertFalse(coverage_index["full_plan_complete"])
            self.assertEqual(
                coverage_index["aggregate_denominator_claim"],
                "NOT_CLAIMED_QUERY_UNITS_OVERLAP",
            )
            verification.write_verified_products(root, candidate_manifest, coverage_index)
            self.assertTrue((root / "candidate-manifest.json").is_file())
            self.assertTrue((root / "coverage-index.json").is_file())

    def test_raw_byte_tampering_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _build_verified_run(root)
            raw_file = next((root / "raw" / "sha256").rglob("*.json"))
            raw_file.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "raw response SHA-256 mismatch"):
                verification.verify_acquisition(plan, root)

    def test_candidate_file_tampering_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _build_verified_run(root)
            candidate_file = next((root / "units").rglob("candidates.jsonl"))
            candidate_file.write_text(candidate_file.read_text() + "{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "candidate JSONL SHA-256 mismatch"):
                verification.verify_acquisition(plan, root)

    def test_release_eligibility_mutation_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _build_verified_run(root)
            manifest_path = root / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["release_eligibility"] = "AUTHORIZED"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "release-eligibility boundary"):
                verification.verify_acquisition(plan, root)


if __name__ == "__main__":
    unittest.main()
