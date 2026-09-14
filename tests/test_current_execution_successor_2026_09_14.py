from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = (
    ROOT
    / "curation"
    / "PROGRAMME_EXECUTION_STATE_2026-09-14_G0_ROUTE_REMEDIATION_SUCCESSOR.json"
)
PREDECESSOR = (
    ROOT
    / "curation"
    / "PROGRAMME_EXECUTION_STATE_2026-09-13_PRE_G2_CURRENT_SUCCESSOR.json"
)
POINTER = ROOT / "curation" / "CURRENT_EXECUTION_CONTROL.json"
G1 = ROOT / "curation" / "HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json"
SOURCE_STATE = (
    ROOT
    / "curation"
    / "source_universe_execution_state_2026-09-03_SRC14021_DISPOSITION_C_SUCCESSOR.json"
)
D3 = (
    ROOT
    / "curation"
    / "PRE_G2_D3_CALIBRATION_SELECTION_COMPOSITION_2026-09-11_v0.1.json"
)
D4 = ROOT / "curation" / "PRE_G2_D4_PILOT_READINESS_POLICY_2026-09-12_v0.2.json"
PATSTAT = (
    ROOT
    / "curation"
    / "PATSTAT_BASELINE_A_PROVENANCE_INTAKE_STATUS_2026-09-12_v0.1.json"
)
ROUTES = ROOT / "curation" / "source_route_resilience_v0.1.json"

EXPECTED_SUCCESSOR_PATH = (
    "curation/PROGRAMME_EXECUTION_STATE_2026-09-14_G0_ROUTE_REMEDIATION_SUCCESSOR.json"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return hashlib.sha1(payload).hexdigest()


class CurrentExecutionSuccessor20260914Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.successor = load_json(SUCCESSOR)
        cls.pointer = load_json(POINTER)

    def test_historical_successor_remains_valid_after_pointer_advances(self) -> None:
        self.assertEqual(self.pointer["status"], "CURRENT_CONTROL_POINTER_NONCANONICAL")
        self.assertGreaterEqual(self.pointer["as_of"], "2026-09-14")
        current_path = ROOT / self.pointer["current_programme_execution_state"]
        self.assertTrue(current_path.exists())
        self.assertTrue(Path(EXPECTED_SUCCESSOR_PATH).name)
        self.assertEqual(
            self.pointer["current_g1_disposition"],
            "curation/HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json",
        )

    def test_predecessor_and_controls_are_exactly_blob_bound(self) -> None:
        self.assertEqual(
            self.successor["predecessor"]["git_blob_sha"],
            git_blob_sha(PREDECESSOR),
        )
        self.assertFalse(
            self.successor["predecessor"]["predecessor_is_modified_by_this_successor"]
        )
        self.assertEqual(
            self.successor["inherited_gate_state"]["g1"]["git_blob_sha"],
            git_blob_sha(G1),
        )
        self.assertEqual(
            self.successor["source_universe_state"]["git_blob_sha"],
            git_blob_sha(SOURCE_STATE),
        )
        self.assertEqual(
            self.successor["pre_g2_state"]["d3"]["challenge_composition_git_blob_sha"],
            git_blob_sha(D3),
        )
        self.assertEqual(
            self.successor["pre_g2_state"]["d4"]["readiness_policy_git_blob_sha"],
            git_blob_sha(D4),
        )
        self.assertEqual(
            self.successor["pre_g2_state"]["patstat_baseline_a"][
                "provenance_status_git_blob_sha"
            ],
            git_blob_sha(PATSTAT),
        )
        self.assertEqual(
            self.successor["g0_operational_evidence"]["src_14_014_route_remediation"][
                "route_policy_git_blob_sha"
            ],
            git_blob_sha(ROUTES),
        )

    def test_newest_schedule_is_recorded_without_false_g0_pass(self) -> None:
        g0 = self.successor["g0_operational_evidence"]
        scheduled = g0["newest_normal_scheduled_due_cycle"]
        self.assertEqual(scheduled["workflow_run_id"], 34833993578)
        self.assertEqual(scheduled["event"], "schedule")
        self.assertEqual(scheduled["conclusion"], "failure")
        self.assertEqual(scheduled["source_accountability_coverage"], 1.0)
        self.assertEqual(scheduled["target_execution_coverage"], 1.0)
        self.assertEqual(scheduled["resume_additional_transport_sends"], 0)
        self.assertEqual(
            scheduled["unresolved_failed_source_ids"],
            ["SRC-14-014", "SRC-14-021"],
        )
        self.assertFalse(scheduled["qualifies_as_g0_pass"])
        self.assertFalse(g0["g0_passed"])

    def test_aotearoa_remediation_is_narrow_and_live_corroborated(self) -> None:
        g0 = self.successor["g0_operational_evidence"]
        remediation = g0["src_14_014_route_remediation"]
        self.assertEqual(remediation["pull_request"], 252)
        self.assertFalse(remediation["source_universe_expanded"])
        self.assertFalse(remediation["canonical_source_registration_created"])
        self.assertFalse(remediation["source_identity_truth_created"])
        self.assertEqual(remediation["primary_route_id"], "SRC-14-014:apex")
        self.assertEqual(
            remediation["identity_equivalent_route_id"],
            "SRC-14-014:www",
        )

        push = g0["post_merge_push_corroboration"]
        self.assertEqual(push["workflow_run_id"], 34846817313)
        self.assertEqual(push["event"], "push")
        self.assertEqual(push["source_accountability_coverage"], 1.0)
        self.assertEqual(push["target_execution_coverage"], 1.0)
        self.assertFalse(push["src_14_014_unresolved_after_remediation"])
        self.assertEqual(push["unresolved_failed_source_ids"], ["SRC-14-021"])
        self.assertFalse(push["normal_schedule_criterion_satisfied"])

    def test_gate_and_authority_state_remain_fail_closed(self) -> None:
        gates = self.successor["inherited_gate_state"]
        self.assertEqual(gates["g0"]["decision"], "BLOCKED_NOT_PASSED")
        self.assertFalse(gates["g0"]["passed"])
        self.assertEqual(gates["g0"]["blocking_source_ids"], ["SRC-14-021"])
        self.assertTrue(gates["g1"]["approved"])
        self.assertFalse(gates["g2"]["passed"])

        phase3 = self.successor["workbench_phase3"]
        self.assertEqual(phase3["workflow_dispatch_runs_observed_at_recording"], 0)
        self.assertFalse(phase3["external_live_proof_executed"])
        self.assertFalse(phase3["phase4_online_first_default_authorized"])

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
