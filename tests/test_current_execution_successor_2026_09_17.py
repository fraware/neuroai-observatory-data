from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-17_CONTROL_DELTA_SUCCESSOR.json"
PREDECESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-14_PRE_G3_REPLAY_REBIND_SUCCESSOR.json"
POINTER = ROOT / "curation" / "CURRENT_EXECUTION_CONTROL.json"
G1 = ROOT / "curation" / "HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json"
PATSTAT_STATUS = ROOT / "curation" / "PATSTAT_BASELINE_A_PROVENANCE_INTAKE_STATUS_2026-09-17_ROMAN_RESPONSE_v0.1.json"
PATSTAT_RIGHTS = ROOT / "curation" / "PATSTAT_PUBLIC_EXTRACT_RIGHTS_REVIEW_2026-09-17_ROMAN_ANALYSIS_SUCCESSOR_v0.1.json"

EXPECTED_SUCCESSOR_PATH = "curation/PROGRAMME_EXECUTION_STATE_2026-09-17_CONTROL_DELTA_SUCCESSOR.json"
EXPECTED_OBSERVATORY_MAIN = "b450a5109a784924c53cbdc75adb57b6f67df9ba"
EXPECTED_WORKBENCH_MAIN = "854cc9d1c8e24a9e8ae8b21d871329bc3c24c118"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return hashlib.sha1(payload).hexdigest()


class CurrentExecutionSuccessor20260917Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.successor = load_json(SUCCESSOR)
        cls.pointer = load_json(POINTER)

    def test_pointer_advances_to_exact_successor(self) -> None:
        self.assertEqual(self.pointer["status"], "CURRENT_CONTROL_POINTER_NONCANONICAL")
        self.assertEqual(self.pointer["as_of"], "2026-09-17")
        self.assertEqual(self.pointer["current_programme_execution_state"], EXPECTED_SUCCESSOR_PATH)
        self.assertEqual(
            self.pointer["current_g1_disposition"],
            "curation/HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json",
        )

    def test_predecessor_g1_and_patstat_artifacts_are_exactly_blob_bound(self) -> None:
        self.assertEqual(self.successor["predecessor"]["git_blob_sha"], git_blob_sha(PREDECESSOR))
        self.assertFalse(self.successor["predecessor"]["predecessor_is_modified_by_this_successor"])
        self.assertEqual(self.successor["inherited_gate_state"]["g1"]["git_blob_sha"], git_blob_sha(G1))
        patstat = self.successor["current_control_deltas"]["patstat_roman_provenance"]
        self.assertEqual(patstat["provenance_status_git_blob_sha"], git_blob_sha(PATSTAT_STATUS))
        self.assertEqual(patstat["rights_control_git_blob_sha"], git_blob_sha(PATSTAT_RIGHTS))

    def test_repository_binding_is_exact_current_state(self) -> None:
        binding = self.successor["repository_binding"]
        self.assertEqual(binding["observatory_main_sha"], EXPECTED_OBSERVATORY_MAIN)
        self.assertEqual(binding["workbench_main_sha"], EXPECTED_WORKBENCH_MAIN)

    def test_ctgov_software_controls_do_not_claim_real_execution(self) -> None:
        onboarding = self.successor["current_control_deltas"]["ctgov_monitor_onboarding"]
        self.assertEqual(onboarding["pull_request"], 261)
        self.assertEqual(onboarding["final_pr_head_sha"], "cef486f6472ad8a713259975ad00fbdca238f95e")
        self.assertEqual(onboarding["exact_head_workflow_run_id"], 34972211820)
        self.assertEqual(onboarding["exact_head_workflow_conclusion"], "success")
        self.assertTrue(onboarding["software_control_available"])
        self.assertFalse(onboarding["real_human_monitor_review_performed"])
        self.assertFalse(onboarding["network_execution_performed"])
        self.assertFalse(onboarding["monitor_registry_successor_created"])
        self.assertFalse(onboarding["canonical_s2_mutation_performed"])

        capture = self.successor["current_control_deltas"]["ctgov_first_capture"]
        self.assertEqual(capture["pull_request"], 263)
        self.assertEqual(capture["final_pr_head_sha"], "28c132308fa860d1bab7a6bbff041e541e535537")
        self.assertEqual(capture["exact_head_workflow_run_id"], 34972907102)
        self.assertEqual(capture["exact_head_workflow_conclusion"], "success")
        self.assertTrue(capture["software_control_available"])
        self.assertFalse(capture["real_first_capture_authorization_created"])
        self.assertFalse(capture["live_clinicaltrials_capture_executed"])
        self.assertFalse(capture["quarantine_approval_performed"])
        self.assertFalse(capture["monitor_registry_successor_created"])
        self.assertFalse(capture["canonical_s2_mutation_performed"])

    def test_roman_response_is_partial_and_rights_remain_unresolved(self) -> None:
        patstat = self.successor["current_control_deltas"]["patstat_roman_provenance"]
        self.assertEqual(patstat["roman_direct_main_commit"], "bb6df60f31e76936fa9957bbac545994b96b2e34")
        self.assertEqual(patstat["intake_pull_request"], 264)
        self.assertEqual(patstat["merged_main_sha"], EXPECTED_OBSERVATORY_MAIN)
        self.assertEqual(patstat["provenance_readiness"], "WAITING_FOR_PROVENANCE")
        self.assertFalse(patstat["mandatory_components_complete"])
        self.assertTrue(patstat["all_mandatory_components_still_incomplete"])
        self.assertFalse(patstat["rights_clearance"])
        self.assertFalse(patstat["scientific_validity_established"])
        self.assertFalse(patstat["human_reference_standard_created"])
        self.assertTrue(patstat["reported_interval_conflict_unresolved"])
        self.assertEqual(patstat["all_recorded_workflows_conclusion"], "success")

    def test_phase3_and_gate_state_remain_fail_closed(self) -> None:
        phase3 = self.successor["workbench_phase3"]
        self.assertEqual(phase3["workflow_dispatch_runs_observed_at_recording"], 0)
        self.assertFalse(phase3["external_live_proof_executed"])
        self.assertFalse(phase3["external_live_proof_reviewed"])
        self.assertFalse(phase3["phase4_online_first_default_authorized"])

        gates = self.successor["inherited_gate_state"]
        self.assertEqual(gates["g0"]["decision"], "BLOCKED_NOT_PASSED")
        self.assertFalse(gates["g0"]["passed"])
        self.assertEqual(gates["g0"]["blocking_source_ids"], ["SRC-14-021"])
        self.assertFalse(gates["g0"]["re_adjudicated_by_this_successor"])
        self.assertTrue(gates["g1"]["approved"])
        self.assertFalse(gates["g2"]["passed"])
        self.assertFalse(gates["g3"]["passed"])
        self.assertFalse(gates["g5"]["passed"])

    def test_real_human_benchmarks_and_authority_remain_false(self) -> None:
        human = self.successor["human_benchmark_state"]
        self.assertFalse(human["d3_real_human_benchmark_frozen"])
        self.assertFalse(human["d4_real_human_benchmark_frozen"])
        self.assertFalse(human["roman_model_generated_labels_count_as_d3_human_gold"])
        self.assertFalse(human["g2_human_disposition_completed"])

        authority = self.successor["authority"]
        self.assertTrue(authority["g1_approved"])
        for field in (
            "g0_passed",
            "g2_passed",
            "g3_passed",
            "g5_passed",
            "patstat_rights_clearance",
            "canonical_s2_authority",
            "publication_authority",
            "mutation_authority",
            "population_generalization_authority",
            "phase4_online_first_default_authorized",
        ):
            with self.subTest(field=field):
                self.assertFalse(authority[field])
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
