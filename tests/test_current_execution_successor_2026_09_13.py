from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-13_PRE_G2_CURRENT_SUCCESSOR.json"
PREDECESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-08_SCHEDULED_G0_EVIDENCE_SUCCESSOR.json"
POINTER = ROOT / "curation" / "CURRENT_EXECUTION_CONTROL.json"
G1 = ROOT / "curation" / "HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json"
SOURCE_STATE = ROOT / "curation" / "source_universe_execution_state_2026-09-03_SRC14021_DISPOSITION_C_SUCCESSOR.json"
D3 = ROOT / "curation" / "PRE_G2_D3_CALIBRATION_SELECTION_COMPOSITION_2026-09-11_v0.1.json"
D4 = ROOT / "curation" / "PRE_G2_D4_PILOT_READINESS_POLICY_2026-09-12_v0.2.json"
PATSTAT = ROOT / "curation" / "PATSTAT_BASELINE_A_PROVENANCE_INTAKE_STATUS_2026-09-12_v0.1.json"

EXPECTED_SUCCESSOR_PATH = "curation/PROGRAMME_EXECUTION_STATE_2026-09-13_PRE_G2_CURRENT_SUCCESSOR.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return hashlib.sha1(payload).hexdigest()


class CurrentExecutionSuccessor20260913Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.successor = load_json(SUCCESSOR)
        cls.pointer = load_json(POINTER)

    def test_pointer_is_atomically_advanced_to_exact_successor(self) -> None:
        self.assertEqual(self.pointer["status"], "CURRENT_CONTROL_POINTER_NONCANONICAL")
        self.assertEqual(self.pointer["as_of"], "2026-09-13")
        self.assertEqual(self.pointer["current_programme_execution_state"], EXPECTED_SUCCESSOR_PATH)
        self.assertEqual(self.pointer["current_g1_disposition"], "curation/HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json")

    def test_predecessor_and_inherited_controls_are_exactly_blob_bound(self) -> None:
        pred = self.successor["predecessor"]
        self.assertEqual(pred["git_blob_sha"], git_blob_sha(PREDECESSOR))
        self.assertFalse(pred["predecessor_is_modified_by_this_successor"])
        self.assertEqual(self.successor["inherited_gate_state"]["g1"]["git_blob_sha"], git_blob_sha(G1))
        self.assertEqual(self.successor["source_universe_state"]["git_blob_sha"], git_blob_sha(SOURCE_STATE))
        self.assertEqual(self.successor["pre_g2_state"]["d3"]["challenge_composition_git_blob_sha"], git_blob_sha(D3))
        self.assertEqual(self.successor["pre_g2_state"]["d4"]["readiness_policy_git_blob_sha"], git_blob_sha(D4))
        self.assertEqual(self.successor["pre_g2_state"]["patstat_baseline_a"]["provenance_status_git_blob_sha"], git_blob_sha(PATSTAT))

    def test_gate_state_is_preserved_without_readjudication(self) -> None:
        gates = self.successor["inherited_gate_state"]
        self.assertEqual(gates["g0"]["decision"], "BLOCKED_NOT_PASSED")
        self.assertFalse(gates["g0"]["passed"])
        self.assertEqual(gates["g0"]["blocking_source_id"], "SRC-14-021")
        self.assertFalse(gates["g0"]["re_adjudicated_by_this_successor"])
        self.assertEqual(gates["g1"]["decision"], "APPROVE")
        self.assertTrue(gates["g1"]["approved"])
        self.assertFalse(gates["g1"]["re_adjudicated_by_this_successor"])
        self.assertFalse(gates["g2"]["passed"])
        self.assertFalse(gates["g2"]["re_adjudicated_by_this_successor"])

    def test_pre_g2_state_records_real_evidence_gaps(self) -> None:
        d3 = self.successor["pre_g2_state"]["d3"]
        self.assertTrue(d3["challenge_software_control_composed"])
        self.assertFalse(d3["real_pilot_executed"])
        self.assertFalse(d3["real_final_membership_selected"])
        self.assertFalse(d3["frozen"])
        self.assertFalse(d3["probability_audit_ready"])

        d4 = self.successor["pre_g2_state"]["d4"]
        self.assertFalse(d4["raw_exact_agreement_automated_gate"])
        self.assertTrue(d4["raw_exact_agreement_retained_as_human_review_diagnostic"])
        self.assertFalse(d4["real_pilot_executed"])
        self.assertFalse(d4["frozen"])

        patstat = self.successor["pre_g2_state"]["patstat_baseline_a"]
        self.assertEqual(patstat["provenance_readiness"], "WAITING_FOR_PROVENANCE")
        self.assertFalse(patstat["roman_49671_validated"])
        self.assertFalse(patstat["roman_67_percent_retrieval_recall_validated"])
        self.assertFalse(patstat["rights_clearance"])

    def test_workbench_phase3_remains_incomplete_and_phase4_unauthorized(self) -> None:
        phase3 = self.successor["workbench_phase3"]
        self.assertEqual(phase3["workbench_main_sha"], "854cc9d1c8e24a9e8ae8b21d871329bc3c24c118")
        self.assertEqual(phase3["workflow_git_blob_sha"], "aa75dfaa1559b35377af64a775a7285278faad6e")
        self.assertTrue(phase3["execution_readiness_merged"])
        self.assertFalse(phase3["external_live_proof_executed"])
        self.assertFalse(phase3["external_live_proof_reviewed_complete"])
        self.assertFalse(phase3["phase4_online_first_default_authorized"])

    def test_authority_boundary_remains_fail_closed(self) -> None:
        authority = self.successor["authority"]
        self.assertTrue(authority["g1_approved"])
        for field in (
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "canonical_s2_authority",
            "publication_authority",
            "mutation_authority",
            "patstat_rights_clearance",
            "population_generalization_authority",
            "phase4_online_first_default_authorized",
        ):
            with self.subTest(field=field):
                self.assertFalse(authority[field])
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
