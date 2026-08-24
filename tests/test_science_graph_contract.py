from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("validate_science_graph", ROOT / "scripts" / "validate_science_graph.py")
m = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)

PROTOCOL = json.loads((ROOT / "science" / "discovery-protocol-v0.1.json").read_text())
ADAPTERS = json.loads((ROOT / "science" / "adapters-v0.1.json").read_text())
UNIVERSES = json.loads((ROOT / "source-universes" / "p0" / "science-v0.1.json").read_text())
BUNDLE = json.loads((ROOT / "fixtures" / "vnext" / "science-acquisition.synthetic.json").read_text())


def adapters():
    return m.validate_adapters(copy.deepcopy(ADAPTERS), copy.deepcopy(UNIVERSES))


class ScienceGraphContractTests(unittest.TestCase):
    def test_valid_repository_state(self):
        self.assertTrue(m.validate_repository_state())

    def test_protocol_requires_relevance_adjudication(self):
        x = copy.deepcopy(PROTOCOL)
        x["candidate_inclusion"]["relevance_adjudication_required"] = False
        with self.assertRaisesRegex(ValueError, "relevance adjudication"):
            m.validate_protocol(x)

    def test_protocol_forbids_automatic_canonical_inclusion(self):
        x = copy.deepcopy(PROTOCOL)
        x["candidate_inclusion"]["automatic_canonical_inclusion"] = True
        with self.assertRaisesRegex(ValueError, "automatic canonical inclusion"):
            m.validate_protocol(x)

    def test_protocol_identifier_precedence_is_frozen(self):
        x = copy.deepcopy(PROTOCOL)
        x["deduplication"]["exact_identifier_precedence"] = ["PMID", "DOI", "PMCID", "OPENALEX"]
        with self.assertRaisesRegex(ValueError, "identifier precedence"):
            m.validate_protocol(x)

    def test_protocol_fuzzy_matching_remains_candidate_only(self):
        x = copy.deepcopy(PROTOCOL)
        x["deduplication"]["fuzzy_title_author_matching"] = "CANONICAL_MATCH"
        with self.assertRaisesRegex(ValueError, "candidate-only"):
            m.validate_protocol(x)

    def test_adapter_provider_universe_mismatch_fails(self):
        x = copy.deepcopy(ADAPTERS)
        x["records"][0]["source_universe_id"] = "SU-SCI-EUROPEPMC"
        with self.assertRaisesRegex(ValueError, "provider/universe mismatch"):
            m.validate_adapters(x, copy.deepcopy(UNIVERSES))

    def test_adapter_base_url_must_match_source_universe(self):
        x = copy.deepcopy(ADAPTERS)
        x["records"][0]["transport"]["base_url"] = "https://example.org/works"
        with self.assertRaisesRegex(ValueError, "base_url differs"):
            m.validate_adapters(x, copy.deepcopy(UNIVERSES))

    def test_duplicate_adapter_provider_fails(self):
        x = copy.deepcopy(ADAPTERS)
        x["records"][1]["provider"] = "CROSSREF"
        x["records"][1]["source_universe_id"] = "SU-SCI-CROSSREF"
        with self.assertRaises(ValueError):
            m.validate_adapters(x, copy.deepcopy(UNIVERSES))

    def test_credential_required_state_is_fail_closed(self):
        x = copy.deepcopy(ADAPTERS)
        openalex = next(r for r in x["records"] if r["provider"] == "OPENALEX")
        openalex["state"] = "READY"
        with self.assertRaisesRegex(ValueError, "credentialed adapter cannot be READY"):
            m.validate_adapters(x, copy.deepcopy(UNIVERSES))

    def test_freeze_unknown_query_family_fails(self):
        x = copy.deepcopy(BUNDLE)
        x["freezes"][0]["query_family_ids"] = ["QF-NOT-DECLARED"]
        with self.assertRaisesRegex(ValueError, "unknown query families"):
            m.validate_acquisition_bundle(x, adapters(), copy.deepcopy(PROTOCOL))

    def test_freeze_cutoff_must_match_protocol(self):
        x = copy.deepcopy(BUNDLE)
        x["freezes"][0]["retrieval_cutoff"] = "2026-08-19T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "retrieval cutoff differs"):
            m.validate_acquisition_bundle(x, adapters(), copy.deepcopy(PROTOCOL))

    def test_complete_freeze_cannot_retain_continuation(self):
        x = copy.deepcopy(BUNDLE)
        x["freezes"][0]["continuation_state"] = "cursor-next"
        with self.assertRaisesRegex(ValueError, "complete freeze cannot retain continuation"):
            m.validate_acquisition_bundle(x, adapters(), copy.deepcopy(PROTOCOL))

    def test_candidate_dangling_freeze_fails(self):
        x = copy.deepcopy(BUNDLE)
        x["candidates"][0]["acquisition_freeze_id"] = "AF-SCI-CROSSREF-MISSING"
        with self.assertRaisesRegex(ValueError, "dangling acquisition freeze"):
            m.validate_acquisition_bundle(x, adapters(), copy.deepcopy(PROTOCOL))

    def test_candidate_provider_must_match_adapter(self):
        x = copy.deepcopy(BUNDLE)
        x["candidates"][0]["provider"] = "EUROPE_PMC"
        with self.assertRaisesRegex(ValueError, "provider does not match"):
            m.validate_acquisition_bundle(x, adapters(), copy.deepcopy(PROTOCOL))

    def test_candidate_query_family_must_be_in_freeze(self):
        x = copy.deepcopy(BUNDLE)
        x["candidates"][0]["discovery_query_family_ids"] = ["QF-NEURAL-DECODING"]
        with self.assertRaisesRegex(ValueError, "query family not present"):
            m.validate_acquisition_bundle(x, adapters(), copy.deepcopy(PROTOCOL))

    def test_complete_freeze_count_must_reconcile(self):
        x = copy.deepcopy(BUNDLE)
        x["freezes"][0]["records_observed"] = 2
        with self.assertRaisesRegex(ValueError, "records_observed does not reconcile"):
            m.validate_acquisition_bundle(x, adapters(), copy.deepcopy(PROTOCOL))


if __name__ == "__main__":
    unittest.main()
