from __future__ import annotations

import copy
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
acquisition = _load_module("acquire_science_candidates", SCRIPTS / "acquire_science_candidates.py")
sys.modules["acquire_science_candidates"] = acquisition
sys.modules["validate_science_graph"] = _load_module("validate_science_graph", SCRIPTS / "validate_science_graph.py")
sys.modules["validate_source_universes"] = _load_module("validate_source_universes", SCRIPTS / "validate_source_universes.py")
provenance = _load_module("verify_science_candidate_provenance", SCRIPTS / "verify_science_candidate_provenance.py")
sys.modules["verify_science_candidate_provenance"] = provenance
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


def _rewrite_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _refresh_run_id(root: Path):
    manifest_path = root / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    results = [json.loads((root / relative).read_text()) for relative in manifest["query_unit_result_paths"]]
    run_basis = {
        "plan_sha256": manifest["plan_sha256"],
        "selected_query_unit_ids": [result["query_unit_id"] for result in results],
        "result_digests": [
            acquisition._sha256_json(
                {
                    "query_unit_id": result["query_unit_id"],
                    "status": result["status"],
                    "freeze": result["freeze"],
                    "coverage": result["coverage"],
                    "candidates_sha256": result["candidates_sha256"],
                }
            )
            for result in results
        ],
    }
    run_sha = acquisition._sha256_json(run_basis)
    manifest["run_id"] = f"SCIENCE-ACQ-{run_sha[:20].upper()}"
    _rewrite_json(manifest_path, manifest)


class ScienceAcquisitionVerificationTests(unittest.TestCase):
    def test_verified_scoped_run_builds_provenance_bound_candidate_and_coverage_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _build_verified_run(root)
            candidate_manifest, coverage_index = verification.verify_acquisition(plan, root)
            self.assertEqual(candidate_manifest["selected_query_units"], 2)
            self.assertEqual(candidate_manifest["complete_query_units"], 2)
            self.assertEqual(candidate_manifest["candidate_record_occurrences"], 2)
            self.assertEqual(candidate_manifest["release_eligibility"], verification.RELEASE_INELIGIBLE)
            self.assertEqual(candidate_manifest["provenance_verification_status"], "RAW_RESPONSE_PROVENANCE_VERIFIED")
            self.assertTrue(candidate_manifest["provenance_verification_id"].startswith("SCIENCE-PROVENANCE-"))
            self.assertEqual(len(candidate_manifest["provenance_verification_sha256"]), 64)
            self.assertEqual(len(coverage_index["complete_query_unit_coverages"]), 2)
            self.assertFalse(coverage_index["full_plan_complete"])
            self.assertEqual(
                coverage_index["aggregate_denominator_claim"],
                "NOT_CLAIMED_QUERY_UNITS_OVERLAP",
            )
            verification.write_verified_products(root, candidate_manifest, coverage_index)
            self.assertTrue((root / "candidate-manifest.json").is_file())
            self.assertTrue((root / "coverage-index.json").is_file())

    def test_rehashed_subset_plan_cannot_be_verified_as_frozen_plan(self):
        plan, _unit_ids = _plan_and_unit_ids()
        x = copy.deepcopy(plan)
        x["query_units"] = x["query_units"][:2]
        x["unit_count"] = 2
        x["provider_counts"] = {"CROSSREF": 2, "EUROPE_PMC": 0}
        x["plan_sha256"] = acquisition._sha256_json(acquisition._plan_basis(x))
        x["plan_id"] = f"SCIENCE-QUERY-PLAN-{x['plan_sha256'][:20].upper()}"
        with self.assertRaisesRegex(ValueError, "does not match the frozen Phase 4 v0.1 plan identity"):
            verification.validate_plan(x)

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

    def test_page_request_identity_tampering_fails_even_if_page_manifest_is_rehashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _build_verified_run(root)
            manifest = json.loads((root / "run-manifest.json").read_text())
            result_path = root / manifest["query_unit_result_paths"][0]
            result = json.loads(result_path.read_text())
            result["page_manifest"][0]["request_url_sha256"] = "0" * 64
            page_sha = acquisition._sha256_json(result["page_manifest"])
            result["freeze"]["raw_response_manifest_sha256"] = page_sha
            result["freeze"]["source_state_identity"] = f"OBSERVED-{page_sha[:32].upper()}"
            _rewrite_json(result_path, result)
            _refresh_run_id(root)
            with self.assertRaisesRegex(ValueError, "page request URL digest mismatch"):
                verification.verify_acquisition(plan, root)

    def test_provider_source_forgery_fails_against_raw_provenance_even_when_manifest_is_reconciled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _build_verified_run(root)
            manifest = json.loads((root / "run-manifest.json").read_text())
            epmc_result_path = next(
                root / relative
                for relative in manifest["query_unit_result_paths"]
                if json.loads((root / relative).read_text())["freeze"]["source_universe_id"] == "SU-SCI-EUROPEPMC"
            )
            result = json.loads(epmc_result_path.read_text())
            candidate_path = root / result["candidates_path"]
            rows = [json.loads(line) for line in candidate_path.read_text().splitlines() if line.strip()]
            rows[0]["provider_record_source"] = "PPR"
            candidate_bytes = b"".join(acquisition._canonical_bytes(row) + b"\n" for row in rows)
            candidate_path.write_bytes(candidate_bytes)
            result["candidates_sha256"] = acquisition._sha256_bytes(candidate_bytes)
            _rewrite_json(epmc_result_path, result)
            _refresh_run_id(root)
            with self.assertRaisesRegex(ValueError, "provider identity/observation does not match"):
                verification.verify_acquisition(plan, root)

    def test_release_eligibility_mutation_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _build_verified_run(root)
            manifest_path = root / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["release_eligibility"] = "AUTHORIZED"
            _rewrite_json(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "release-eligibility boundary"):
                verification.verify_acquisition(plan, root)


if __name__ == "__main__":
    unittest.main()
