from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("compile_science_queries", ROOT / "scripts" / "compile_science_queries.py")
m = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)

PROTOCOL = json.loads((ROOT / "science" / "discovery-protocol-v0.1.json").read_text())
COMPILATION = json.loads((ROOT / "science" / "query-compilation-v0.1.json").read_text())


class ScienceQueryCompilationTests(unittest.TestCase):
    def test_valid_plan_is_deterministic(self):
        first = m.compile_plan(copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION))
        second = m.compile_plan(copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION))
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "FROZEN_QUERY_PLAN_NO_ACQUISITION_EXECUTED")
        self.assertEqual(first["unit_count"], 768)
        self.assertEqual(first["provider_counts"], {"CROSSREF": 384, "EUROPE_PMC": 384})
        self.assertEqual(len(first["plan_sha256"]), 64)

    def test_calendar_windows_end_at_cutoff_window(self):
        windows = m._year_windows("2015-01-01", "2026-08-20")
        self.assertEqual(len(windows), 12)
        self.assertEqual(windows[0], ("2015-01-01", "2015-12-31"))
        self.assertEqual(windows[-1], ("2026-01-01", "2026-08-20"))

    def test_crossref_query_unit_contract(self):
        plan = m.compile_plan(copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION))
        unit = plan["query_units"][0]
        self.assertEqual(unit["provider"], "CROSSREF")
        self.assertEqual(unit["query_family_id"], "QF-NEURAL-INTERFACE")
        self.assertEqual(unit["term"], "brain-computer interface")
        self.assertEqual(unit["window"], {"from": "2015-01-01", "through": "2015-12-31"})
        self.assertEqual(unit["parameters"]["query.title"], "brain-computer interface")
        self.assertEqual(
            unit["parameters"]["filter"],
            "from-pub-date:2015-01-01,until-pub-date:2015-12-31",
        )
        self.assertEqual(unit["parameters"]["rows"], "1000")
        self.assertEqual(unit["parameters"]["cursor"], "*")
        self.assertEqual(unit["coverage_denominator_method"], "API_TOTAL")

    def test_europe_pmc_query_unit_contract(self):
        plan = m.compile_plan(copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION))
        unit = next(row for row in plan["query_units"] if row["provider"] == "EUROPE_PMC")
        self.assertEqual(
            unit["parameters"]["query"],
            '(TITLE:"brain-computer interface" OR ABSTRACT:"brain-computer interface") '
            'AND FIRST_PDATE:[2015-01-01 TO 2015-12-31]',
        )
        self.assertEqual(unit["parameters"]["resultType"], "core")
        self.assertEqual(unit["parameters"]["format"], "json")
        self.assertEqual(unit["parameters"]["pageSize"], "1000")
        self.assertEqual(unit["parameters"]["cursorMark"], "*")

    def test_client_identity_is_hash_bound_to_every_query_unit(self):
        plan = m.compile_plan(copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION))
        expected = {
            "access_class": "PUBLIC",
            "user_agent": m.EXPECTED_USER_AGENT,
        }
        self.assertTrue(all(unit["client_identity"] == expected for unit in plan["query_units"]))
        x = copy.deepcopy(COMPILATION)
        x["providers"]["CROSSREF"]["client_identity"]["user_agent"] = "different-client"
        with self.assertRaisesRegex(ValueError, "unexpected client user_agent"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_query_unit_ids_are_unique(self):
        plan = m.compile_plan(copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION))
        ids = [row["query_unit_id"] for row in plan["query_units"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_compilation_must_match_protocol_window(self):
        x = copy.deepcopy(COMPILATION)
        x["partitioning"]["through"] = "2026-08-19"
        with self.assertRaisesRegex(ValueError, "partition does not match"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_provider_order_is_frozen(self):
        x = copy.deepcopy(COMPILATION)
        x["provider_scope"] = ["EUROPE_PMC", "CROSSREF"]
        with self.assertRaisesRegex(ValueError, "provider order"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_plan_does_not_claim_acquisition(self):
        plan = m.compile_plan(copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION))
        self.assertIn("proves no provider request was sent", plan["authority_boundary"])
        self.assertEqual(
            plan["coverage_semantics"]["aggregate_union_denominator"],
            "NOT_CLAIMED_DUE_TO_OVERLAP_ACROSS_TERMS_AND_WINDOWS",
        )


if __name__ == "__main__":
    unittest.main()
