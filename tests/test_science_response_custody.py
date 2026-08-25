from __future__ import annotations

import importlib.util
import json
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


compiler = _load_module(
    "compile_science_queries_for_response_custody_tests",
    SCRIPTS / "compile_science_queries.py",
)
acquisition = _load_module(
    "acquire_science_candidates_for_response_custody_tests",
    SCRIPTS / "acquire_science_candidates.py",
)

PROTOCOL = json.loads(
    (ROOT / "science" / "discovery-protocol-v0.1.json").read_text()
)
COMPILATION = json.loads(
    (ROOT / "science" / "query-compilation-v0.2.json").read_text()
)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)

    def fetch(self, _url):
        if not self.responses:
            raise RuntimeError("unexpected transport call")
        item = self.responses.pop(0)
        if isinstance(item, bytes):
            body = item
        else:
            body = json.dumps(item).encode("utf-8")
        return acquisition.HttpResult(
            status=200,
            headers={"content-type": "application/json"},
            body=body,
        )


class Clock:
    def __init__(self):
        self.second = 0

    def __call__(self):
        value = f"2026-08-25T05:00:{self.second:02d}Z"
        self.second += 1
        return value


def crossref_unit():
    plan = compiler.compile_plan(PROTOCOL, COMPILATION)
    unit = dict(
        next(row for row in plan["query_units"] if row["provider"] == "CROSSREF")
    )
    unit["evidence_cutoff"] = plan["evidence_cutoff"]
    return unit


class ScienceResponseCustodyTests(unittest.TestCase):
    def test_invalid_json_response_remains_in_content_addressed_failure_custody(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = acquisition.acquire_query_unit(
                crossref_unit(),
                output_root=root,
                transport=FakeTransport([b"not-json"]),
                sleep_fn=lambda _: None,
                clock_fn=Clock(),
            )
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(len(result["response_manifest"]), 1)
            self.assertEqual(result["page_manifest"], [])
            self.assertIsNone(result["coverage"])
            response = result["response_manifest"][0]
            raw_path = root / response["raw_custody_pointer"]
            self.assertTrue(raw_path.is_file())
            self.assertEqual(
                acquisition._sha256_bytes(raw_path.read_bytes()),
                response["content_sha256"],
            )
            self.assertEqual(
                result["freeze"]["raw_response_manifest_sha256"],
                acquisition._sha256_json(result["response_manifest"]),
            )
            self.assertIn("invalid JSON", result["freeze"]["failure_reason"])

    def test_denominator_drift_preserves_both_provider_responses(self):
        responses = [
            {
                "message": {
                    "total-results": 3,
                    "items": [{"DOI": "10.1/a", "title": ["A"]}],
                    "next-cursor": "cursor-2",
                }
            },
            {
                "message": {
                    "total-results": 4,
                    "items": [{"DOI": "10.1/b", "title": ["B"]}],
                    "next-cursor": "cursor-3",
                }
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = acquisition.acquire_query_unit(
                crossref_unit(),
                output_root=root,
                transport=FakeTransport(responses),
                sleep_fn=lambda _: None,
                clock_fn=Clock(),
            )
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(
                result["freeze"]["failure_reason"],
                "PROVIDER_TOTAL_CHANGED_DURING_TRAVERSAL",
            )
            self.assertEqual(len(result["response_manifest"]), 2)
            self.assertEqual(len(result["page_manifest"]), 2)
            self.assertEqual(
                [page["provider_total"] for page in result["page_manifest"]],
                [3, 4],
            )
            self.assertEqual(
                len(list((root / "raw" / "sha256").rglob("*.json"))), 2
            )
            self.assertEqual(
                result["freeze"]["raw_response_manifest_sha256"],
                acquisition._sha256_json(result["response_manifest"]),
            )
            self.assertIsNone(result["coverage"])


if __name__ == "__main__":
    unittest.main()
