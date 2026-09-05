from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-05_G1_APPROVED_SUCCESSOR.json"
PREDECESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-05_D1_D2_CONSTRUCT_VALIDITY_SUCCESSOR.json"
POINTER = ROOT / "curation" / "CURRENT_EXECUTION_CONTROL.json"
DISPOSITION = ROOT / "curation" / "HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json"
REVIEW_BINDING = ROOT / "curation" / "PRE_G1_D1_D2_REVIEW_BINDING_D1_CONSTRUCT_VALIDITY_2026-09-05_v0.1.json"
D1 = ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json"
D2 = ROOT / "curation" / "CAPABILITY_CONTEXT_TAXONOMY_v0.1.json"
HISTORICAL_G1 = ROOT / "curation" / "HUMAN_G1_DISPOSITION_PACKET_OBSERVATORY_RECOVERY_2026-09-03_v0.1.json"
PATSTAT_RIGHTS = ROOT / "curation" / "PATSTAT_PUBLIC_EXTRACT_RIGHTS_REVIEW_2026-09-05_v0.1.json"
D1_VALIDATOR = ROOT / "scripts" / "validate_landscape_research_contract.py"

EXPECTED_SUCCESSOR_PATH = "curation/PROGRAMME_EXECUTION_STATE_2026-09-05_G1_APPROVED_SUCCESSOR.json"
EXPECTED_DISPOSITION_PATH = "curation/HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json"
EXPECTED_PREDECESSOR_BLOB = "bcce43681e0419836cc22249322dcfb712d1e729"
EXPECTED_REVIEW_BINDING_BLOB = "28e69f53f9b475a2ee474e9fa886d9660db7f7b0"
EXPECTED_HISTORICAL_G1_BLOB = "9b61daa3f0f3c43fa4a1451c07b675a0dbbebbaa"
EXPECTED_D1_BLOB = "6aacb9d9bfba570121484b1e214b02ac824d645e"
EXPECTED_D2_BLOB = "f8d4943da5c0659ba775b3f6227e8a21a7bcb03a"
EXPECTED_D1_CANONICAL = "7d270002094dcdecb703d5b70ef2268e4869005c284ffd98db3eb936641a78cb"
EXPECTED_D2_CANONICAL = "bd9451a5084485ef7a36251b0bc39d486fe0c2174636171a29ec03d7010cbf1d"
EXPECTED_COMMENT_BODY_SHA256 = "b332349811dcdf48accc1c2e596cc1deaa34aeb3957421d7e18a3dca9f8c2554"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return hashlib.sha1(payload).hexdigest()


def load_d1_validator():
    spec = importlib.util.spec_from_file_location("g1_successor_d1_validator", D1_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to import D1 validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class G1ApprovedSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.successor = load_json(SUCCESSOR)
        cls.predecessor = load_json(PREDECESSOR)
        cls.pointer = load_json(POINTER)
        cls.disposition = load_json(DISPOSITION)
        cls.review_binding = load_json(REVIEW_BINDING)
        cls.d1 = load_json(D1)
        cls.d2 = load_json(D2)
        cls.patstat = load_json(PATSTAT_RIGHTS)
        cls.d1_validator = load_d1_validator()

    def test_pointer_targets_exact_g1_successor_and_disposition(self) -> None:
        self.assertEqual(self.pointer["status"], "CURRENT_CONTROL_POINTER_NONCANONICAL")
        self.assertEqual(self.pointer["as_of"], "2026-09-05")
        self.assertEqual(self.pointer["current_programme_execution_state"], EXPECTED_SUCCESSOR_PATH)
        self.assertEqual(self.pointer["current_g1_disposition"], EXPECTED_DISPOSITION_PATH)

    def test_predecessor_and_historical_records_are_byte_immutable(self) -> None:
        self.assertEqual(git_blob_sha(PREDECESSOR), EXPECTED_PREDECESSOR_BLOB)
        self.assertEqual(git_blob_sha(REVIEW_BINDING), EXPECTED_REVIEW_BINDING_BLOB)
        self.assertEqual(git_blob_sha(HISTORICAL_G1), EXPECTED_HISTORICAL_G1_BLOB)
        self.assertFalse(self.successor["predecessor"]["predecessor_is_modified_by_this_successor"])
        historical = self.successor["historical_record_boundary"]
        self.assertFalse(historical["predecessor_execution_state_modified"])
        self.assertFalse(historical["historical_g1_packet_modified_by_this_successor"])
        self.assertFalse(historical["review_binding_modified_by_this_successor"])

    def test_disposition_is_exact_attributable_approval(self) -> None:
        d = self.disposition
        self.assertEqual(d["record_type"], "HUMAN_G1_DISPOSITION")
        self.assertEqual(d["decision"], "APPROVE")
        self.assertTrue(d["scope"]["g1_approved"])
        self.assertTrue(d["scope"]["substantive_change_requires_new_human_disposition"])
        attribution = d["attribution"]
        self.assertEqual(attribution["source"], "GITHUB_ISSUE_COMMENT")
        self.assertEqual(attribution["issue_number"], 218)
        self.assertEqual(attribution["comment_id"], 5552118979)
        self.assertEqual(attribution["github_login"], "fraware")
        self.assertEqual(attribution["github_user_id"], 113530345)
        self.assertEqual(attribution["author_association"], "OWNER")
        self.assertEqual(attribution["comment_created_at"], "2026-09-05T13:24:50Z")
        self.assertEqual(attribution["comment_updated_at_at_recording"], "2026-09-05T13:24:50Z")
        self.assertEqual(attribution["comment_body_sha256_utf8"], EXPECTED_COMMENT_BODY_SHA256)

    def test_disposition_binds_exact_review_and_d1_d2_identities(self) -> None:
        self.assertEqual(self.disposition["review_binding"]["git_blob_sha"], EXPECTED_REVIEW_BINDING_BLOB)
        self.assertEqual(git_blob_sha(D1), EXPECTED_D1_BLOB)
        self.assertEqual(git_blob_sha(D2), EXPECTED_D2_BLOB)
        d1_digest = self.d1_validator.sha256_bytes(self.d1_validator.canonical_json_bytes(self.d1))
        d2_digest = self.d1_validator.sha256_bytes(self.d1_validator.canonical_json_bytes(self.d2))
        self.assertEqual(d1_digest, EXPECTED_D1_CANONICAL)
        self.assertEqual(d2_digest, EXPECTED_D2_CANONICAL)
        self.assertEqual(self.disposition["d1"]["canonical_json_sha256"], d1_digest)
        self.assertEqual(self.disposition["d2"]["canonical_json_sha256"], d2_digest)
        self.assertEqual(self.successor["g1_disposition"]["d1"]["canonical_json_sha256"], d1_digest)
        self.assertEqual(self.successor["g1_disposition"]["d2"]["canonical_json_sha256"], d2_digest)
        self.assertEqual(self.review_binding["d1"]["canonical_json_sha256"], d1_digest)
        self.assertEqual(self.review_binding["d2"]["canonical_json_sha256"], d2_digest)

    def test_approval_is_external_to_immutable_pre_g1_artifacts(self) -> None:
        self.assertFalse(self.d1["governance"]["g1_approved"])
        self.assertFalse(self.d2["governance"]["g1_approved"])
        self.assertFalse(self.review_binding["governance"]["g1_approved"])
        self.assertTrue(self.disposition["authority"]["g1_approved"])
        self.assertTrue(self.successor["gate_state"]["g1"]["g1_approved"])

    def test_only_g1_transitions(self) -> None:
        gates = self.successor["gate_state"]
        self.assertEqual(gates["g0"]["decision"], "BLOCKED_NOT_PASSED")
        self.assertFalse(gates["g0"]["passed"])
        self.assertFalse(gates["g0"]["re_adjudicated_by_this_successor"])
        self.assertEqual(gates["g1"]["decision"], "APPROVE")
        self.assertTrue(gates["g1"]["approved"])
        self.assertTrue(gates["g1"]["human_disposition_recorded"])
        self.assertFalse(gates["g2"]["g2_passed"])
        self.assertFalse(gates["g2"]["re_adjudicated_by_this_successor"])

    def test_pre_g2_work_is_unlocked_without_claiming_g2(self) -> None:
        boundary = self.successor["pre_g2_execution_boundary"]
        self.assertTrue(boundary["construction_against_approved_d1_d2_may_proceed"])
        self.assertTrue(boundary["technical_scaffold_presence_does_not_pass_g2"])
        self.assertTrue(boundary["actual_heldout_membership_labels_and_adjudication_remain_s3_controlled"])
        self.assertFalse(boundary["g2_freeze_or_passage_recorded_by_this_successor"])
        self.assertFalse(boundary["publication_or_s2_authority_created_by_this_successor"])

    def test_independent_blockers_remain_fail_closed(self) -> None:
        matters = self.successor["independent_unresolved_matters"]
        patstat = matters["patstat_public_extract_rights_review"]
        self.assertEqual(patstat["issue"], 210)
        self.assertEqual(patstat["state"], "OPEN")
        self.assertFalse(patstat["rights_clearance"])
        self.assertFalse(self.patstat["authority"]["rights_clearance"])
        phase3 = matters["online_first_phase3_external_proof"]
        self.assertEqual(phase3["workbench_issue"], 287)
        self.assertEqual(phase3["state"], "INCOMPLETE_EXTERNAL_PROOF_NOT_EXECUTED")
        self.assertFalse(phase3["phase4_default_transition_authorized"])

    def test_no_unrelated_authority_is_created(self) -> None:
        authority = self.successor["authority"]
        self.assertFalse(authority["g0_passed"])
        self.assertTrue(authority["g1_approved"])
        self.assertFalse(authority["g2_passed"])
        self.assertFalse(authority["canonical_s2_authority"])
        self.assertFalse(authority["publication_authority"])
        self.assertFalse(authority["mutation_authority"])
        self.assertFalse(authority["patstat_rights_clearance"])
        self.assertFalse(authority["phase4_online_first_default_authorized"])
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
