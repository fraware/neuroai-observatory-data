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


compiler = _load_module("compile_science_queries_for_provenance_tests", SCRIPTS / "compile_science_queries.py")
acquisition = _load_module("acquire_science_candidates", SCRIPTS / "acquire_science_candidates.py")
sys.modules["acquire_science_candidates"] = acquisition
provenance = _load_module("verify_science_candidate_provenance", SCRIPTS / "verify_science_candidate_provenance.py")

PROTOCOL = json.loads((ROOT / "science" / "discovery-protocol-v0.1.json").read_text())
COMPILATION = json.loads((ROOT / "science" / "query-compilation-v0.1.json").read_text())


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)

    def fetch(self, _url):
        if not self.responses:
            raise RuntimeError("unexpected transport call")
        status, payload = self.responses.pop(0)
        return acquisition.HttpResult(
            status=status,
            headers={"content-type": "application/json"},
            body=json.dumps(payload).encode("utf-8"),
        )


class Clock:
    def __init__(self):
        self.second = 0

    def __call__(self):
        value = f"2026-08-25T04:20:{self.second:02d}Z"
        self.second += 1
        return value


def _selected_plan_units():
    plan = compiler.compile_plan(PROTOCOL, COMPILATION)
    crossref = next(unit for unit in plan["query_units"] if unit["provider"] == "CROSSREF")
    europe_pmc = next(unit for unit in plan["query_units"] if unit["provider"] == "EUROPE_PMC")
    return plan, {crossref["query_unit_id"], europe_pmc["query_unit_id"]}


def _build_run(root: Path, *, epmc_source="MED"):
    plan, unit_ids = _selected_plan_units()
    epmc_record = {
        "id": "123456",
        "doi": "10.1234/shared",
        "pmid": "123456",
        "pmcid": "PMC999",
        "title": "Shared neural interface record",
        "pubYear": "2015",
    }
    if epmc_source is not None:
        epmc_record["source"] = epmc_source
    responses = [
        (
            200,
            {
                "message": {
                    "total-results": 1,
                    "items": [{"DOI": "10.1234/shared", "title": ["Shared neural interface record"]}],
                    "next-cursor": "done-crossref",
                }
            },
        ),
        (
            200,
            {
                "hitCount": 1,
                "nextCursorMark": "done-epmc",
                "resultList": {"result": [epmc_record]},
            },
        ),
    ]
    acquisition.acquire_plan(
        plan,
        output_root=root,
        transport=FakeTransport(responses),
        query_unit_ids=unit_ids,
        sleep_fn=lambda _: None,
        clock_fn=Clock(),
    )
    return plan


class ScienceCandidateProvenanceTests(unittest.TestCase):
    def test_every_candidate_is_exactly_reproduced_from_captured_raw_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_run(root)
            report = provenance.verify_candidate_provenance(root)
            self.assertEqual(report["status"], "RAW_RESPONSE_PROVENANCE_VERIFIED")
            self.assertEqual(report["verified_candidates"], 2)
            self.assertEqual(report["verified_raw_records"], 2)
            self.assertEqual(report["europe_pmc_distinct_source_ids"], 1)
            self.assertEqual(report["canonical_effect"], "NONE")

    def test_candidate_source_hash_tampering_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_run(root)
            candidate_files = sorted((root / "units").rglob("candidates.jsonl"))
            candidate_file = next(
                path
                for path in candidate_files
                if any(
                    json.loads(line).get("provider") == "CROSSREF"
                    for line in path.read_text().splitlines()
                    if line.strip()
                )
            )
            rows = [json.loads(line) for line in candidate_file.read_text().splitlines() if line.strip()]
            rows[0]["source_record_sha256"] = "0" * 64
            candidate_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source_record_sha256 is not present"):
                provenance.verify_candidate_provenance(root)

    def test_candidate_normalized_metadata_tampering_fails_even_with_valid_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_run(root)
            candidate_file = next(
                path
                for path in (root / "units").rglob("candidates.jsonl")
                if any(
                    json.loads(line).get("provider") == "CROSSREF"
                    for line in path.read_text().splitlines()
                    if line.strip()
                )
            )
            rows = [json.loads(line) for line in candidate_file.read_text().splitlines() if line.strip()]
            rows[0]["title"] = "Forged normalized title"
            candidate_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "normalization does not reproduce exactly"):
                provenance.verify_candidate_provenance(root)

    def test_europe_pmc_provider_source_tampering_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_run(root)
            candidate_file = next(
                path
                for path in (root / "units").rglob("candidates.jsonl")
                if any(
                    json.loads(line).get("provider") == "EUROPE_PMC"
                    for line in path.read_text().splitlines()
                    if line.strip()
                )
            )
            rows = [json.loads(line) for line in candidate_file.read_text().splitlines() if line.strip()]
            rows[0]["provider_record_source"] = "PPR"
            candidate_file.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not resolve uniquely"):
                provenance.verify_candidate_provenance(root)

    def test_europe_pmc_source_database_code_is_required_for_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_run(root, epmc_source=None)
            with self.assertRaisesRegex(ValueError, "Europe PMC raw record lacks source database code"):
                provenance.verify_candidate_provenance(root)


if __name__ == "__main__":
    unittest.main()
