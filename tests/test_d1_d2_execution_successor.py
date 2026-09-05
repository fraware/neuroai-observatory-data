from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-05_D1_D2_CONSTRUCT_VALIDITY_SUCCESSOR.json"
CURRENT_SUCCESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-05_G1_APPROVED_SUCCESSOR.json"
POINTER = ROOT / "curation" / "CURRENT_EXECUTION_CONTROL.json"
D1 = ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json"
D2 = ROOT / "curation" / "CAPABILITY_CONTEXT_TAXONOMY_v0.1.json"
REVIEW_BINDING = ROOT / "curation" / "PRE_G1_D1_D2_REVIEW_BINDING_D1_CONSTRUCT_VALIDITY_2026-09-05_v0.1.json"
PREDECESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-03_SRC14021_DISPOSITION_C_SUCCESSOR.json"
HISTORICAL_G1 = ROOT / "curation" / "HUMAN_G1_DISPOSITION_PACKET_OBSERVATORY_RECOVERY_2026-09-03_v0.1.json"
HISTORICAL_PRE_G2 = ROOT / "curation" / "PUBLIC_PRE_G2_S2_BINDINGS_OBSERVATORY_RECOVERY_2026-09-03_BOUND_v0.1.json"
D1_VALIDATOR = ROOT / "scripts" / "validate_landscape_research_contract.py"

EXPECTED_D1_CANONICAL_SHA256 = "7d270002094dcdecb703d5b70ef2268e4869005c284ffd98db3eb936641a78cb"
EXPECTED_D2_CANONICAL_SHA256 = "bd9451a5084485ef7a36251b0bc39d486fe0c2174636171a29ec03d7010cbf1d"
EXPECTED_D1_GIT_BLOB = "6aacb9d9bfba570121484b1e214b02ac824d645e"
EXPECTED_D2_GIT_BLOB = "f8d4943da5c0659ba775b3f6227e8a21a7bcb03a"
EXPECTED_PREDECESSOR_GIT_BLOB = "10a141ebe52e3d66512ed8d9313c4a10f427dd70"
EXPECTED_HISTORICAL_G1_GIT_BLOB = "9b61daa3f0f3c43fa4a1451c07b675a0dbbebbaa"
EXPECTED_HISTORICAL_PRE_G2_GIT_BLOB = "e4796fb88900a2d31e6a75569c39778606be63cf"
EXPECTED_OBSERVATORY_MERGE_SHA = "021096b724bb66198e4470c5c5f77840cc856858"
EXPECTED_SUCCESSOR_PATH = "curation/PROGRAMME_EXECUTION_STATE_2026-09-05_D1_D2_CONSTRUCT_VALIDITY_SUCCESSOR.json"
CURRENT_SUCCESSOR_PATH = "curation/PROGRAMME_EXECUTION_STATE_2026-09-05_G1_APPROVED_SUCCESSOR.json"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return hashlib.sha1(payload).hexdigest()


def load_d1_validator():
    spec = importlib.util.spec_from_file_location("d1_execution_successor_validator", D1_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to import D1 validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class D1D2ExecutionSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.successor = load_json(SUCCESSOR)
        cls.current_successor = load_json(CURRENT_SUCCESSOR)
        cls.pointer = load_json(POINTER)
        cls.d1 = load_json(D1)
        cls.d2 = load_json(D2)
        cls.review_binding = load_json(REVIEW_BINDING)
        cls.d1_validator = load_d1_validator()

    def test_pointer_advanced_through_append_only_g1_successor(self) -> None:
        self.assertEqual(self.pointer["status"], "CURRENT_CONTROL_POINTER_NONCANONICAL")
        self.assertEqual(self.pointer["as_of"], "2026-09-05")
        self.assertEqual(self.pointer["current_programme_execution_state"], CURRENT_SUCCESSOR_PATH)
        self.assertEqual(self.current_successor["predecessor"]["path"], EXPECTED_SUCCESSOR_PATH)
        self.assertFalse(self.current_successor["predecessor"]["predecessor_is_modified_by_this_successor"])

    def test_predecessor_and_historical_records_are_byte_immutable(self) -> None:
        self.assertEqual(git_blob_sha(PREDECESSOR), EXPECTED_PREDECESSOR_GIT_BLOB)
        self.assertEqual(git_blob_sha(HISTORICAL_G1), EXPECTED_HISTORICAL_G1_GIT_BLOB)
        self.assertEqual(git_blob_sha(HISTORICAL_PRE_G2), EXPECTED_HISTORICAL_PRE_G2_GIT_BLOB)
        pred = self.successor["predecessor"]
        self.assertFalse(pred["predecessor_is_modified_by_this_successor"])
        boundary = self.successor["historical_record_boundary"]
        self.assertFalse(boundary["historical_g1_packet_modified_by_this_successor"])
        self.assertFalse(boundary["historical_pre_g2_bound_modified_by_this_successor"])

    def test_current_d1_d2_exact_identities_match_successor(self) -> None:
        self.assertEqual(git_blob_sha(D1), EXPECTED_D1_GIT_BLOB)
        self.assertEqual(git_blob_sha(D2), EXPECTED_D2_GIT_BLOB)
        d1_digest = self.d1_validator.sha256_bytes(self.d1_validator.canonical_json_bytes(self.d1))
        d2_digest = self.d1_validator.sha256_bytes(self.d1_validator.canonical_json_bytes(self.d2))
        self.assertEqual(d1_digest, EXPECTED_D1_CANONICAL_SHA256)
        self.assertEqual(d2_digest, EXPECTED_D2_CANONICAL_SHA256)
        recorded = self.successor["d1_d2_construct_validity"]
        self.assertEqual(recorded["d1"]["canonical_json_sha256"], d1_digest)
        self.assertEqual(recorded["d2"]["canonical_json_sha256"], d2_digest)

    def test_review_binding_matches_current_artifacts(self) -> None:
        recorded = self.successor["d1_d2_construct_validity"]
        self.assertEqual(recorded["review_binding_path"], str(REVIEW_BINDING.relative_to(ROOT)))
        self.assertEqual(self.review_binding["d1"]["canonical_json_sha256"], EXPECTED_D1_CANONICAL_SHA256)
        self.assertEqual(self.review_binding["d2"]["canonical_json_sha256"], EXPECTED_D2_CANONICAL_SHA256)
        self.assertEqual(
            self.review_binding["d2"]["d1_contract_binding"]["canonical_json_sha256"],
            EXPECTED_D1_CANONICAL_SHA256,
        )

    def test_observatory_and_workflow_evidence_is_exact_and_technical_only(self) -> None:
        context = self.successor["observatory_authoring_context"]
        self.assertEqual(context["main_sha_after_d1_d2_remediation_merge"], EXPECTED_OBSERVATORY_MERGE_SHA)
        self.assertEqual(context["post_merge_d1_workflow"]["run_id"], 33960778043)
        self.assertEqual(context["post_merge_d2_workflow"]["run_id"], 33960777944)
        self.assertEqual(context["post_merge_d1_workflow"]["conclusion"], "success")
        self.assertEqual(context["post_merge_d2_workflow"]["conclusion"], "success")
        self.assertIn("does_not_prove", context["post_merge_d1_workflow"])
        self.assertIn("does_not_prove", context["post_merge_d2_workflow"])

    def test_historical_successor_gate_state_remains_unchanged(self) -> None:
        inherited = self.successor["inherited_execution_state"]
        self.assertFalse(inherited["re_adjudicated_by_this_successor"])
        self.assertFalse(inherited["new_operational_proof_claimed"])
        self.assertEqual(inherited["g0"]["decision"], "BLOCKED_NOT_PASSED")
        self.assertFalse(inherited["g0"]["passed"])
        self.assertFalse(inherited["g1"]["g1_approved"])
        self.assertFalse(inherited["g1"]["human_disposition_recorded"])
        self.assertFalse(inherited["g2"]["g2_passed"])
        self.assertFalse(inherited["workbench_g0_transport_pin"]["reverified_by_this_successor"])
        self.assertFalse(inherited["workbench_g0_transport_pin"]["updated_by_this_successor"])

    def test_historical_successor_authority_flags_remain_false(self) -> None:
        authority = self.successor["authority"]
        self.assertFalse(authority["canonical_s2_authority"])
        self.assertFalse(authority["publication_authority"])
        self.assertFalse(authority["mutation_authority"])
        self.assertEqual(authority["assessment_effect"], "NONE")
        self.assertFalse(authority["g0_passed"])
        self.assertFalse(authority["g1_approved"])
        self.assertFalse(authority["g2_passed"])
        self.assertFalse(self.review_binding["governance"]["g1_approved"])
        self.assertFalse(self.review_binding["governance"]["g2_passed"])

    def test_patstat_rights_review_remains_separate_and_unresolved(self) -> None:
        patstat = self.successor["separate_unresolved_matters"]["patstat_public_extract_rights_review"]
        self.assertEqual(patstat["issue"], 210)
        self.assertEqual(patstat["state_at_authoring"], "OPEN")
        self.assertFalse(patstat["disposed_by_this_successor"])
        self.assertFalse(patstat["rights_finding_made_by_this_successor"])
        self.assertIn("PATSTAT redistribution rights", self.successor["boundary"])
        self.assertIn("PATSTAT redistribution rights", self.pointer["boundary"])


if __name__ == "__main__":
    unittest.main()
