from __future__ import annotations
import copy, importlib.util, json, unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]
SPEC=importlib.util.spec_from_file_location("validate_source_universes", ROOT/"scripts"/"validate_source_universes.py")
m=importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)
REG=json.loads((ROOT/"source-universes"/"p0-registry-v0.1.json").read_text())

class SourceUniverseContractTests(unittest.TestCase):
    def test_registry_passes(self):
        self.assertTrue(m.validate_registry(copy.deepcopy(REG)))

    def test_all_required_domains_present(self):
        self.assertEqual({r["domain"] for r in REG["records"] if r["priority"]=="P0"},
            {"SCIENCE","CLINICAL","REGULATORY","PUBLIC_FUNDING","PATENT_IP","CAPITAL","NEURAL_DATA"})

    def test_duplicate_id_fails(self):
        x=copy.deepcopy(REG); x["records"].append(copy.deepcopy(x["records"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            m.validate_registry(x)

    def test_open_world_cannot_claim_completeness(self):
        x=copy.deepcopy(REG["records"][0]); x["closure"]["closure_type"]="OPEN_WORLD_DISCOVERY"
        with self.assertRaisesRegex(ValueError,"open-world"):
            m.validate_universe(x)

    def test_license_and_access_remain_separate(self):
        x=next(copy.deepcopy(r) for r in REG["records"] if r["universe_id"]=="SU-CAP-PRIVATE-LICENSED")
        self.assertEqual(x["interface"]["authentication_class"],"LICENSE_REQUIRED")
        self.assertEqual(x["rights"]["redistribution_rights_class"],"NO_REDISSEMINATION")
        self.assertTrue(m.validate_universe(x))

    def test_verified_interface_requires_base_url(self):
        x=copy.deepcopy(REG["records"][0]); x["interface"]["base_url"]=None
        with self.assertRaisesRegex(ValueError,"base_url"):
            m.validate_universe(x)

    def coverage(self):
        return {
          "coverage_id":"COV-TEST-001","schema_version":"0.1.0","universe_id":"SU-SCI-CROSSREF",
          "frozen_at":"2026-08-20T08:30:00Z","denominator":{"eligible":100,"method":"API_TOTAL"},
          "states":{"discovered":100,"resolved":90,"sourced":88,"temporally_verified":80,"linked":75,"stale":5,"conflicted":2,"inaccessible":3,"excluded":4},
          "rates":{"discovery":1.0,"resolution":0.9,"sourcing":0.88,"temporal_verification":0.8,"linkage":0.75},
          "exclusions":[{"reason":"outside frozen NeuroAI inclusion criteria","count":4}],
          "authority_boundary":"Coverage metrics measure processing state only and establish no substantive truth or assessment conclusion."
        }

    def test_verified_interface_rejects_unknown_rights(self):
        x=copy.deepcopy(REG["records"][0]); x["rights"]["redistribution_rights_class"]="UNKNOWN_PENDING_REVIEW"
        with self.assertRaisesRegex(ValueError,"unknown rights"):
            m.validate_universe(x)

    def test_zero_denominator_requires_null_rates(self):
        x=self.coverage(); x["denominator"]["eligible"]=0; x["denominator"]["method"]="NO_GLOBAL_DENOMINATOR"
        x["states"]={k:0 for k in x["states"]}; x["rates"]={k:None for k in x["rates"]}; x["exclusions"]=[]
        self.assertTrue(m.validate_coverage(x))

    def test_coverage_reconciles(self):
        u=next(r for r in REG["records"] if r["universe_id"]=="SU-SCI-CROSSREF")
        self.assertTrue(m.validate_coverage(self.coverage(),u))

    def test_bad_rate_fails(self):
        x=self.coverage(); x["rates"]["resolution"]=0.91
        with self.assertRaisesRegex(ValueError,"rate does not reconcile"):
            m.validate_coverage(x)

    def test_bad_exclusion_total_fails(self):
        x=self.coverage(); x["exclusions"][0]["count"]=3
        with self.assertRaisesRegex(ValueError,"exclusion detail"):
            m.validate_coverage(x)

    def test_bad_denominator_method_fails_against_universe(self):
        x=self.coverage(); x["denominator"]["method"]="REGISTRY_RECORD_COUNT"
        u=next(r for r in REG["records"] if r["universe_id"]=="SU-SCI-CROSSREF")
        with self.assertRaisesRegex(ValueError,"denominator method"):
            m.validate_coverage(x,u)

if __name__=="__main__":
    unittest.main()
