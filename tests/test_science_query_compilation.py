from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compile_science_queries",
    ROOT / "scripts" / "compile_science_queries.py",
)
m = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)

PROTOCOL = json.loads(
    (ROOT / "science" / "discovery-protocol-v0.1.json").read_text()
)
COMPILATION_V01 = json.loads(
    (ROOT / "science" / "query-compilation-v0.1.json").read_text()
)
COMPILATION_V02 = json.loads(
    (ROOT / "science" / "query-compilation-v0.2.json").read_text()
)
EXPECTED_V01_PLAN_SHA256 = (
    "ce2a8d1c0377a2e960b31eab194bf93bd87f350be2f788abc315a079092c504e"
)
EXPECTED_V02_PLAN_SHA256 = (
    "a9b8b8999861882c4bc78b27f40f48e476f7cafbbb347b00a0a6cd897406db56"
)


class ScienceQueryCompilationTests(unittest.TestCase):
    def test_current_plan_is_deterministic_and_hash_frozen(self):
        first = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V02)
        )
        second = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V02)
        )
        self.assertEqual(first, second)
        self.assertEqual(first["compilation_id"], "SCIENCE-QUERY-COMPILATION-V0.2")
        self.assertEqual(first["status"], "FROZEN_QUERY_PLAN_NO_ACQUISITION_EXECUTED")
        self.assertEqual(first["unit_count"], 768)
        self.assertEqual(
            first["provider_counts"], {"CROSSREF": 384, "EUROPE_PMC": 384}
        )
        self.assertEqual(first["plan_sha256"], EXPECTED_V02_PLAN_SHA256)
        self.assertEqual(
            first["plan_id"], "SCIENCE-QUERY-PLAN-A9B8B8999861882C4BC7"
        )

    def test_predecessor_plan_remains_independently_reproducible(self):
        plan = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V01)
        )
        self.assertEqual(plan["compilation_id"], "SCIENCE-QUERY-COMPILATION-V0.1")
        self.assertEqual(plan["unit_count"], 768)
        self.assertEqual(
            plan["provider_counts"], {"CROSSREF": 384, "EUROPE_PMC": 384}
        )
        self.assertEqual(plan["plan_sha256"], EXPECTED_V01_PLAN_SHA256)
        self.assertEqual(
            plan["plan_id"], "SCIENCE-QUERY-PLAN-CE2A8D1C0377A2E960B3"
        )

    def test_current_and_predecessor_plan_identities_are_distinct(self):
        predecessor = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V01)
        )
        current = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V02)
        )
        self.assertNotEqual(predecessor["plan_sha256"], current["plan_sha256"])
        self.assertNotEqual(predecessor["plan_id"], current["plan_id"])
        self.assertEqual(predecessor["unit_count"], current["unit_count"])
        self.assertEqual(predecessor["provider_counts"], current["provider_counts"])

    def test_calendar_windows_end_at_cutoff_window(self):
        windows = m._year_windows("2015-01-01", "2026-08-20")
        self.assertEqual(len(windows), 12)
        self.assertEqual(windows[0], ("2015-01-01", "2015-12-31"))
        self.assertEqual(windows[-1], ("2026-01-01", "2026-08-20"))

    def test_current_crossref_query_unit_is_minimized(self):
        plan = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V02)
        )
        unit = plan["query_units"][0]
        self.assertEqual(unit["provider"], "CROSSREF")
        self.assertEqual(unit["query_family_id"], "QF-NEURAL-INTERFACE")
        self.assertEqual(unit["term"], "brain-computer interface")
        self.assertEqual(
            unit["window"], {"from": "2015-01-01", "through": "2015-12-31"}
        )
        self.assertEqual(
            unit["parameters"]["query.title"], "brain-computer interface"
        )
        self.assertEqual(
            unit["parameters"]["filter"],
            "from-pub-date:2015-01-01,until-pub-date:2015-12-31",
        )
        self.assertEqual(unit["parameters"]["rows"], "1000")
        self.assertEqual(unit["parameters"]["select"], "DOI,title,published")
        self.assertEqual(unit["parameters"]["cursor"], "*")
        self.assertEqual(unit["coverage_denominator_method"], "API_TOTAL")

    def test_current_europe_pmc_query_unit_is_minimized(self):
        plan = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V02)
        )
        unit = next(
            row for row in plan["query_units"] if row["provider"] == "EUROPE_PMC"
        )
        self.assertEqual(
            unit["parameters"]["query"],
            '(TITLE:"brain-computer interface" OR ABSTRACT:"brain-computer interface") '
            'AND FIRST_PDATE:[2015-01-01 TO 2015-12-31]',
        )
        self.assertEqual(unit["parameters"]["resultType"], "lite")
        self.assertEqual(unit["parameters"]["format"], "json")
        self.assertEqual(unit["parameters"]["pageSize"], "1000")
        self.assertEqual(unit["parameters"]["cursorMark"], "*")

    def test_predecessor_request_shape_is_preserved(self):
        plan = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V01)
        )
        crossref = plan["query_units"][0]
        europe_pmc = next(
            row for row in plan["query_units"] if row["provider"] == "EUROPE_PMC"
        )
        self.assertNotIn("select", crossref["parameters"])
        self.assertEqual(europe_pmc["parameters"]["resultType"], "core")

    def test_client_identity_is_hash_bound_to_every_query_unit(self):
        plan = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V02)
        )
        expected = {
            "access_class": "PUBLIC",
            "user_agent": m.EXPECTED_USER_AGENT,
        }
        self.assertTrue(
            all(unit["client_identity"] == expected for unit in plan["query_units"])
        )
        x = copy.deepcopy(COMPILATION_V02)
        x["providers"]["CROSSREF"]["client_identity"]["user_agent"] = (
            "different-client"
        )
        with self.assertRaisesRegex(ValueError, "unexpected client user_agent"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_query_unit_ids_are_unique(self):
        plan = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V02)
        )
        ids = [row["query_unit_id"] for row in plan["query_units"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_compilation_must_match_protocol_window(self):
        x = copy.deepcopy(COMPILATION_V02)
        x["partitioning"]["through"] = "2026-08-19"
        with self.assertRaisesRegex(ValueError, "partition does not match"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_provider_order_is_frozen(self):
        x = copy.deepcopy(COMPILATION_V02)
        x["provider_scope"] = ["EUROPE_PMC", "CROSSREF"]
        with self.assertRaisesRegex(ValueError, "provider order"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_current_compilation_requires_pre_acquisition_supersession_state(self):
        x = copy.deepcopy(COMPILATION_V02)
        x["supersedes"]["acquisition_state"] = "PROVIDER_ACQUISITION_EXECUTED"
        with self.assertRaisesRegex(ValueError, "cannot be superseded after provider acquisition"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_current_crossref_minimization_cannot_drift(self):
        x = copy.deepcopy(COMPILATION_V02)
        x["providers"]["CROSSREF"]["fixed_parameters"]["select"] = (
            "DOI,title,published,abstract"
        )
        with self.assertRaisesRegex(ValueError, "Crossref request fields must remain minimized"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_current_europe_pmc_minimization_cannot_drift(self):
        x = copy.deepcopy(COMPILATION_V02)
        x["providers"]["EUROPE_PMC"]["fixed_parameters"]["resultType"] = "core"
        with self.assertRaisesRegex(ValueError, "Europe PMC response contract must remain lite"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_unsupported_compilation_id_fails_closed(self):
        x = copy.deepcopy(COMPILATION_V02)
        x["compilation_id"] = "SCIENCE-QUERY-COMPILATION-V9.9"
        with self.assertRaisesRegex(ValueError, "unsupported query compilation"):
            m.compile_plan(copy.deepcopy(PROTOCOL), x)

    def test_plan_does_not_claim_acquisition(self):
        plan = m.compile_plan(
            copy.deepcopy(PROTOCOL), copy.deepcopy(COMPILATION_V02)
        )
        self.assertIn("proves no provider request was sent", plan["authority_boundary"])
        self.assertEqual(
            plan["coverage_semantics"]["aggregate_union_denominator"],
            "NOT_CLAIMED_DUE_TO_OVERLAP_ACROSS_TERMS_AND_WINDOWS",
        )


if __name__ == "__main__":
    unittest.main()
