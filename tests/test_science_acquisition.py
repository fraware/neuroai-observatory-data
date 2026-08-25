from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


m = _load_module("acquire_science_candidates", ROOT / "scripts" / "acquire_science_candidates.py")
compiler = _load_module("compile_science_queries_for_acquisition_tests", ROOT / "scripts" / "compile_science_queries.py")
science_validator = _load_module("validate_science_graph_for_acquisition_tests", ROOT / "scripts" / "validate_science_graph.py")
coverage_validator = _load_module("validate_source_universes_for_acquisition_tests", ROOT / "scripts" / "validate_source_universes.py")

PROTOCOL = json.loads((ROOT / "science" / "discovery-protocol-v0.1.json").read_text())
COMPILATION = json.loads((ROOT / "science" / "query-compilation-v0.1.json").read_text())


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


def frozen_plan():
    return compiler.compile_plan(copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION))


def provider_unit(provider):
    plan = frozen_plan()
    unit = copy.deepcopy(next(row for row in plan["query_units"] if row["provider"] == provider))
    unit["evidence_cutoff"] = plan["evidence_cutoff"]
    return unit


def crossref_unit():
    return provider_unit("CROSSREF")


def europe_pmc_unit():
    return provider_unit("EUROPE_PMC")


def crossref_response(*, total=1, doi="10.1/a", title="A", next_cursor="done"):
    return (
        200,
        {
            "message": {
                "total-results": total,
                "items": [{"DOI": doi, "title": [title]}],
                "next-cursor": next_cursor,
            }
        },
        {"content-type": "application/json"},
    )


def epmc_response(*, total=1, record=None, next_cursor="done"):
    if record is None:
        record = {"source": "MED", "id": "123", "doi": "10.1/b", "title": "B", "pubYear": "2015"}
    return (
        200,
        {
            "hitCount": total,
            "nextCursorMark": next_cursor,
            "resultList": {"result": [record]},
        },
        {"content-type": "application/json"},
    )


class ScienceAcquisitionTests(unittest.TestCase):
    def assert_generated_contracts_validate(self, result, output_root):
        science_validator._structural(
            science_validator.FREEZE_VALIDATOR,
            result["freeze"],
            result["freeze"]["freeze_id"],
        )
        for candidate in m._load_jsonl(output_root / result["candidates_path"]):
            science_validator._structural(
                science_validator.CANDIDATE_VALIDATOR,
                candidate,
                candidate["candidate_id"],
            )
        if result["coverage"] is not None:
            self.assertTrue(coverage_validator.validate_coverage(result["coverage"]))

    def test_crossref_complete_two_page_query_unit(self):
        responses = [
            (200, {"message": {"total-results": 2, "items": [{"DOI": "10.1234/A", "title": ["First"], "published": {"date-parts": [[2015, 2, 3]]}}], "next-cursor": "cursor-2"}}, {"content-type": "application/json"}),
            (200, {"message": {"total-results": 2, "items": [{"DOI": "10.1234/B", "title": ["Second"], "published": {"date-parts": [[2015]]}}], "next-cursor": "cursor-3"}}, {"content-type": "application/json"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = m.acquire_query_unit(crossref_unit(), output_root=root, transport=FakeTransport(responses), sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["candidate_count"], 2)
            self.assertEqual(result["provider_total"], 2)
            self.assertEqual(result["coverage_state"], "ISSUED_COMPLETE_QUERY_UNIT")
            self.assertEqual(result["coverage"]["rates"]["discovery"], 1.0)
            self.assertEqual(result["freeze"]["retrieval_cutoff"], "2026-08-20T00:00:00Z")
            candidates = list(m._load_jsonl(root / result["candidates_path"]))
            self.assertEqual([row["identifiers"]["doi"] for row in candidates], ["10.1234/a", "10.1234/b"])
            self.assertEqual(candidates[0]["publication_date"], "2015-02-03")
            self.assertEqual(candidates[1]["publication_date"], "2015")
            self.assertEqual(len(list((root / "raw" / "sha256").rglob("*.json"))), 2)
            self.assertLess(result["page_manifest"][0]["requested_at"], result["page_manifest"][0]["observed_at"])
            self.assert_generated_contracts_validate(result, root)

    def test_europe_pmc_identity_is_source_aware_and_schema_safe(self):
        record = {
            "source": "med",
            "id": "123456",
            "doi": "https://doi.org/10.5555/ABC",
            "pmid": "123456",
            "pmcid": "pmc999",
            "title": "Example",
            "pubYear": "2015",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = m.acquire_query_unit(europe_pmc_unit(), output_root=root, transport=FakeTransport([epmc_response(record=record)]), sleep_fn=lambda _: None, clock_fn=Clock())
            candidate = next(m._load_jsonl(root / result["candidates_path"]))
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(candidate["provider_record_source"], "MED")
            self.assertEqual(candidate["provider_record_id"], "123456")
            self.assertTrue(candidate["candidate_id"].startswith("SCI-CAND-EUROPE-PMC-"))
            self.assertEqual(candidate["identifiers"]["doi"], "10.5555/abc")
            self.assertEqual(candidate["identifiers"]["pmid"], "123456")
            self.assertEqual(candidate["identifiers"]["pmcid"], "PMC999")
            self.assert_generated_contracts_validate(result, root)

    def test_europe_pmc_same_bare_id_different_sources_are_distinct_provider_records(self):
        records = [
            {"source": "MED", "id": "123", "title": "Published record", "pubYear": "2015"},
            {"source": "PPR", "id": "123", "title": "Preprint record", "pubYear": "2015"},
        ]
        response = (
            200,
            {"hitCount": 2, "nextCursorMark": "done", "resultList": {"result": records}},
            {"content-type": "application/json"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = m.acquire_query_unit(europe_pmc_unit(), output_root=root, transport=FakeTransport([response]), sleep_fn=lambda _: None, clock_fn=Clock())
            candidates = list(m._load_jsonl(root / result["candidates_path"]))
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual({(row["provider_record_source"], row["provider_record_id"]) for row in candidates}, {("MED", "123"), ("PPR", "123")})
            self.assertEqual(len({row["candidate_id"] for row in candidates}), 2)

    def test_europe_pmc_missing_source_fails_closed(self):
        record = {"id": "123", "title": "Missing source", "pubYear": "2015"}
        with tempfile.TemporaryDirectory() as tmp:
            result = m.acquire_query_unit(europe_pmc_unit(), output_root=Path(tmp), transport=FakeTransport([epmc_response(record=record)]), sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(result["status"], "PARTIAL")
            self.assertIn("provider source database code", result["freeze"]["failure_reason"])
            self.assertIsNone(result["coverage"])

    def test_cursor_stall_is_partial_and_coverage_is_not_issued(self):
        responses = [(200, {"message": {"total-results": 2, "items": [{"DOI": "10.1/a", "title": ["A"]}], "next-cursor": "*"}}, {})]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = m.acquire_query_unit(crossref_unit(), output_root=root, transport=FakeTransport(responses), sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(result["freeze"]["failure_reason"], "CURSOR_DID_NOT_ADVANCE_BEFORE_PROVIDER_TOTAL")
            self.assertIsNone(result["coverage"])
            self.assertEqual(result["coverage_state"], "NOT_ISSUED_INCOMPLETE_QUERY_UNIT")
            self.assert_generated_contracts_validate(result, root)

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
        plan = frozen_plan()
        with tempfile.TemporaryDirectory() as tmp:
            manifest = m.acquire_plan(plan, output_root=Path(tmp), transport=FakeTransport([crossref_response()]), max_units=1, sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(manifest["complete_query_units"], 1)
            self.assertFalse(manifest["selected_is_full_plan"])
            self.assertFalse(manifest["full_plan_complete"])
            self.assertEqual(manifest["status"], "PARTIAL_OR_SCOPED_ACQUISITION")

    def test_exact_doi_dedup_is_candidate_only(self):
        plan = frozen_plan()
        crossref = next(unit for unit in plan["query_units"] if unit["provider"] == "CROSSREF")
        epmc = next(unit for unit in plan["query_units"] if unit["provider"] == "EUROPE_PMC")
        responses = [
            crossref_response(doi="10.1/shared", title="Shared"),
            epmc_response(record={"source": "MED", "id": "123", "doi": "10.1/shared", "title": "Shared", "pubYear": "2015"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = m.acquire_plan(
                plan,
                output_root=root,
                transport=FakeTransport(responses),
                query_unit_ids={crossref["query_unit_id"], epmc["query_unit_id"]},
                sleep_fn=lambda _: None,
                clock_fn=Clock(),
            )
            self.assertFalse(manifest["full_plan_complete"])
            report = json.loads((root / "dedup-report.json").read_text())
            doi_groups = report["duplicate_identifier_groups"]["DOI"]
            self.assertEqual(len(doi_groups), 1)
            self.assertEqual(doi_groups[0]["normalized_identifier"], "10.1/shared")
            self.assertEqual(doi_groups[0]["candidate_count"], 2)
            self.assertFalse(report["canonical_merge_performed"])
            self.assertFalse(report["fuzzy_matching_performed"])

    def test_internally_rehashed_subset_cannot_impersonate_frozen_full_plan(self):
        plan = frozen_plan()
        x = copy.deepcopy(plan)
        x["query_units"] = x["query_units"][:2]
        x["unit_count"] = 2
        x["provider_counts"] = {"CROSSREF": 2, "EUROPE_PMC": 0}
        x["plan_sha256"] = m._sha256_json(m._plan_basis(x))
        x["plan_id"] = f"SCIENCE-QUERY-PLAN-{x['plan_sha256'][:20].upper()}"
        with self.assertRaisesRegex(ValueError, "does not match the frozen Phase 4 v0.1 plan identity"):
            m.validate_plan_integrity(x)

    def test_unknown_query_unit_selection_fails_instead_of_silently_dropping(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unknown ids"):
                m.acquire_plan(
                    frozen_plan(),
                    output_root=Path(tmp),
                    transport=FakeTransport([]),
                    query_unit_ids={"QUNIT-CROSSREF-NOTDECLARED"},
                    sleep_fn=lambda _: None,
                    clock_fn=Clock(),
                )

    def test_complete_result_tampering_blocks_resume_before_network(self):
        plan = frozen_plan()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = m.acquire_plan(plan, output_root=root, transport=FakeTransport([crossref_response()]), max_units=1, sleep_fn=lambda _: None, clock_fn=Clock())
            result_path = root / first["query_unit_result_paths"][0]
            result = json.loads(result_path.read_text())
            candidate_path = root / result["candidates_path"]
            candidate_path.write_text(candidate_path.read_text() + "{}\n", encoding="utf-8")
            transport = FakeTransport([])
            with self.assertRaisesRegex(ValueError, "candidate file digest mismatch"):
                m.acquire_plan(plan, output_root=root, transport=transport, max_units=1, sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(transport.urls, [])

    def test_incomplete_attempt_is_archived_before_clean_retry(self):
        plan = frozen_plan()
        partial_response = (200, {"message": {"total-results": 2, "items": [{"DOI": "10.1/a", "title": ["A"]}], "next-cursor": "*"}}, {})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = m.acquire_plan(plan, output_root=root, transport=FakeTransport([partial_response]), max_units=1, sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(first["partial_query_units"], 1)
            second = m.acquire_plan(plan, output_root=root, transport=FakeTransport([crossref_response()]), max_units=1, sleep_fn=lambda _: None, clock_fn=Clock())
            self.assertEqual(second["complete_query_units"], 1)
            archives = list((root / "units").rglob("attempt.json"))
            self.assertEqual(len(archives), 1)
            archived = json.loads(archives[0].read_text())
            self.assertEqual(archived["archived_status"], "PARTIAL")
            self.assertTrue((root / archived["candidate_snapshot_path"]).is_file())
            self.assertTrue((root / "runs" / first["run_id"] / "run-manifest.json").is_file())

    def test_live_transport_user_agent_drift_is_rejected_before_network(self):
        transport = m.UrllibTransport(user_agent="different-client")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "User-Agent differs"):
                m.acquire_plan(frozen_plan(), output_root=Path(tmp), transport=transport, max_units=1, sleep_fn=lambda _: None, clock_fn=Clock())

    def test_repository_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the Git repository"):
            m.validate_output_root(ROOT / "acquisition-output")


if __name__ == "__main__":
    unittest.main()
