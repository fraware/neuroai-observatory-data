from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import importlib.util

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("acquire_science_candidates", ROOT / "scripts" / "acquire_science_candidates.py")
m = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        if not self.responses:
            raise RuntimeError("unexpected transport call")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, payload, headers = item
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return m.HttpResult(status=status, headers=headers, body=body)


class Clock:
    def __init__(self):
        self.second = 0

    def __call__(self):
        value = f"2026-08-25T04:00:{self.second:02d}Z"
        self.second += 1
        return value


def crossref_unit():
    return {
        "query_unit_id": "QUNIT-CROSSREF-AAAAAAAAAAAAAAAAAAAA",
        "provider": "CROSSREF",
        "endpoint": "https://api.crossref.org/works",
        "parameters": {
            "query.title": "brain-computer interface",
            "filter": "from-pub-date:2015-01-01,until-pub-date:2015-12-31",
            "rows": "1000",
            "cursor": "*",
        },
        "query_family_id": "QF-NEURAL-INTERFACE",
        "term_index": 1,
        "term": "brain-computer interface",
        "window": {"from": "2015-01-01", "through": "2015-12-31"},
        "adapter_id": "ADAPTER-CROSSREF-WORKS",
        "source_universe_id": "SU-SCI-CROSSREF",
        "request_identity_sha256": "a" * 64,
        "evidence_cutoff": "2026-08-20T00:00:00Z",
    }


def europe_pmc_unit():
    return {
        "query_unit_id": "QUNIT-EUROPE_PMC-BBBBBBBBBBBBBBBBBBBB",
        "provider": "EUROPE_PMC",
        "endpoint": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        "parameters": {
            "query": '(TITLE:"brain-computer interface" OR ABSTRACT:"brain-computer interface") AND FIRST_PDATE:[2015-01-01 TO 2015-12-31]',
            "resultType": "core",
            "format": "json",
            "pageSize": "1000",
            "cursorMark": "*",
        },
        "query_family_id": "QF-NEURAL-INTERFACE",
        "term_index": 1,
        "term": "brain-computer interface",
        "window": {"from": "2015-01-01", "through": "2015-12-31"},
        "adapter_id": "ADAPTER-EUROPEPMC-SEARCH",
        "source_universe_id": "SU-SCI-EUROPEPMC",
        "request_identity_sha256": "b" * 64,
        "evidence_cutoff": "2026-08-20T00:00:00Z",
    }


class ScienceAcquisitionTests(unittest.TestCase):
    def test_crossref_complete_two_page_query_unit(self):
        responses = [
            (200, {"message": {"total-results": 2, "items": [{"DOI": "10.1234/A", "title": ["First"], "published": {"date-parts": [[2015, 2, 3]]}}], "next-cursor": "cursor-2"}}, {"content-type": "application/json"}),
            (200, {"message": {"total-results": 2, "items": [{"DOI": "10.1234/B", "title": ["Second"], "published": {"date-parts": [[2015]]}}], "next-cursor": "cursor-3"}}, {"content-type": "application/json"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = m.acquire_query_unit(crossref_unit(), output_root=Path(tmp), transport=FakeTransport(responses), sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["candidate_count"], 2)
            self.assertEqual(result["provider_total"], 2)
            self.assertEqual(result["coverage_state"], "ISSUED_COMPLETE_QUERY_UNIT")
            self.assertEqual(result["coverage"]["rates"]["discovery"], 1.0)
            self.assertEqual(result["freeze"]["retrieval_cutoff"], "2026-08-20T00:00:00Z")
            candidates = list(m._load_jsonl(Path(tmp) / result["candidates_path"]))
            self.assertEqual([row["identifiers"]["doi"] for row in candidates], ["10.1234/a", "10.1234/b"])
            self.assertEqual(candidates[0]["publication_date"], "2015-02-03")
            self.assertEqual(candidates[1]["publication_date"], "2015")
            self.assertEqual(len(list((Path(tmp) / "raw" / "sha256").rglob("*.json"))), 2)

    def test_europe_pmc_identifiers_normalize_and_ids_are_schema_safe(self):
        responses = [(200, {"hitCount": 1, "nextCursorMark": "cursor-2", "resultList": {"result": [{"id": "123456", "doi": "https://doi.org/10.5555/ABC", "pmid": "123456", "pmcid": "pmc999", "title": "Example", "pubYear": "2015"}]}}, {"content-type": "application/json"})]
        with tempfile.TemporaryDirectory() as tmp:
            result = m.acquire_query_unit(europe_pmc_unit(), output_root=Path(tmp), transport=FakeTransport(responses), sleep_fn=lambda _: None, clock_fn=Clock())
            candidate = next(m._load_jsonl(Path(tmp) / result["candidates_path"]))
            self.assertEqual(result["status"], "COMPLETE")
            self.assertTrue(candidate["candidate_id"].startswith("SCI-CAND-EUROPE-PMC-"))
            self.assertTrue(result["freeze"]["freeze_id"].startswith("AF-SCI-EUROPE-PMC-"))
            self.assertTrue(result["coverage"]["coverage_id"].startswith("COV-EUROPE-PMC-"))
            self.assertEqual(candidate["identifiers"]["doi"], "10.5555/abc")
            self.assertEqual(candidate["identifiers"]["pmid"], "123456")
            self.assertEqual(candidate["identifiers"]["pmcid"], "PMC999")

    def test_cursor_stall_is_partial_and_coverage_is_not_issued(self):
        responses = [(200, {"message": {"total-results": 2, "items": [{"DOI": "10.1/a", "title": ["A"]}], "next-cursor": "*"}}, {})]
        with tempfile.TemporaryDirectory() as tmp:
            result = m.acquire_query_unit(crossref_unit(), output_root=Path(tmp), transport=FakeTransport(responses), sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(result["freeze"]["failure_reason"], "CURSOR_DID_NOT_ADVANCE_BEFORE_PROVIDER_TOTAL")
            self.assertIsNone(result["coverage"])
            self.assertEqual(result["coverage_state"], "NOT_ISSUED_INCOMPLETE_QUERY_UNIT")

    def test_provider_total_change_is_partial(self):
        responses = [
            (200, {"message": {"total-results": 3, "items": [{"DOI": "10.1/a", "title": ["A"]}], "next-cursor": "c2"}}, {}),
            (200, {"message": {"total-results": 4, "items": [{"DOI": "10.1/b", "title": ["B"]}], "next-cursor": "c3"}}, {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = m.acquire_query_unit(crossref_unit(), output_root=Path(tmp), transport=FakeTransport(responses), sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(result["freeze"]["failure_reason"], "PROVIDER_TOTAL_CHANGED_DURING_TRAVERSAL")

    def test_transient_http_retries_then_succeeds(self):
        transport = FakeTransport([(429, {"error": "rate"}, {"retry-after": "0"}), (200, {"ok": True}, {})])
        sleeps = []
        result = m.fetch_with_retries(transport, "https://example.invalid/test", max_attempts=2, sleep_fn=sleeps.append)
        self.assertEqual(result.status, 200)
        self.assertEqual(sleeps, [0.0])
        self.assertEqual(len(transport.urls), 2)

    def test_scoped_plan_cannot_claim_full_plan_completion(self):
        plan = {"status": "FROZEN_QUERY_PLAN_NO_ACQUISITION_EXECUTED", "plan_id": "SCIENCE-QUERY-PLAN-TEST", "plan_sha256": "c" * 64, "evidence_cutoff": "2026-08-20T00:00:00Z", "query_units": [crossref_unit(), europe_pmc_unit()]}
        response = (200, {"message": {"total-results": 1, "items": [{"DOI": "10.1/a", "title": ["A"]}], "next-cursor": "done"}}, {})
        with tempfile.TemporaryDirectory() as tmp:
            manifest = m.acquire_plan(plan, output_root=Path(tmp), transport=FakeTransport([response]), max_units=1, sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(manifest["complete_query_units"], 1)
            self.assertFalse(manifest["selected_is_full_plan"])
            self.assertFalse(manifest["full_plan_complete"])
            self.assertEqual(manifest["status"], "PARTIAL_OR_SCOPED_ACQUISITION")

    def test_exact_doi_dedup_is_candidate_only(self):
        plan = {"status": "FROZEN_QUERY_PLAN_NO_ACQUISITION_EXECUTED", "plan_id": "SCIENCE-QUERY-PLAN-TEST", "plan_sha256": "c" * 64, "evidence_cutoff": "2026-08-20T00:00:00Z", "query_units": [crossref_unit(), europe_pmc_unit()]}
        responses = [
            (200, {"message": {"total-results": 1, "items": [{"DOI": "10.1/shared", "title": ["Shared"]}], "next-cursor": "done"}}, {}),
            (200, {"hitCount": 1, "nextCursorMark": "done", "resultList": {"result": [{"id": "123", "doi": "10.1/shared", "title": "Shared", "pubYear": "2015"}]}}, {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = m.acquire_plan(plan, output_root=Path(tmp), transport=FakeTransport(responses), sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertTrue(manifest["full_plan_complete"])
            report = json.loads((Path(tmp) / "dedup-report.json").read_text())
            doi_groups = report["duplicate_identifier_groups"]["DOI"]
            self.assertEqual(len(doi_groups), 1)
            self.assertEqual(doi_groups[0]["normalized_identifier"], "10.1/shared")
            self.assertEqual(doi_groups[0]["candidate_count"], 2)
            self.assertFalse(report["canonical_merge_performed"])
            self.assertFalse(report["fuzzy_matching_performed"])

    def test_repository_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the Git repository"):
            m.validate_output_root(ROOT / "acquisition-output")


if __name__ == "__main__":
    unittest.main()
