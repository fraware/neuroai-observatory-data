from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-14_PRE_G3_REPLAY_REBIND_SUCCESSOR.json"
PREDECESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-14_G0_ROUTE_REMEDIATION_SUCCESSOR.json"
POINTER = ROOT / "curation" / "CURRENT_EXECUTION_CONTROL.json"
G1 = ROOT / "curation" / "HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json"

EXPECTED_SUCCESSOR_PATH = "curation/PROGRAMME_EXECUTION_STATE_2026-09-14_PRE_G3_REPLAY_REBIND_SUCCESSOR.json"
EXPECTED_OBSERVATORY_MAIN = "111e2002e9fc03de8b6c3e8f5698f2087014d682"
EXPECTED_WORKBENCH_MAIN = "854cc9d1c8e24a9e8ae8b21d871329bc3c24c118"
EXPECTED_PR_HEAD = "c4b7865a51c2d5eb48db620ab0f662a418ef8d6e"
EXPECTED_RUN_IDS = {
    34856581254,
    34856581258,
    34856580586,
    34856580611,
    34856580634,
    34856580596,
    34856580460,
    34856580493,
    34856580482,
    34856580543,
    34856580637,
    34856580608,
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return hashlib.sha1(payload).hexdigest()


class CurrentExecutionSuccessor20260914PreG3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.successor = load_json(SUCCESSOR)
        cls.pointer = load_json(POINTER)

    def test_historical_successor_remains_valid_after_pointer_advances(self) -> None:
        self.assertEqual(self.pointer["status"], "CURRENT_CONTROL_POINTER_NONCANONICAL")
        self.assertGreaterEqual(self.pointer["as_of"], "2026-09-14")
        current_path = ROOT / self.pointer["current_programme_execution_state"]
        self.assertTrue(current_path.is_file())
        self.assertTrue((ROOT / EXPECTED_SUCCESSOR_PATH).is_file())
        self.assertEqual(
            self.pointer["current_g1_disposition"],
            "curation/HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json",
        )

    def test_predecessor_and_g1_are_exactly_blob_bound(self) -> None:
        self.assertEqual(self.successor["predecessor"]["git_blob_sha"], git_blob_sha(PREDECESSOR))
        self.assertFalse(self.successor["predecessor"]["predecessor_is_modified_by_this_successor"])
        self.assertEqual(
            self.successor["inherited_gate_state"]["g1"]["git_blob_sha"],
            git_blob_sha(G1),
        )

    def test_repository_binding_is_current_for_historical_successor(self) -> None:
        binding = self.successor["repository_binding"]
        self.assertEqual(binding["observatory_main_sha"], EXPECTED_OBSERVATORY_MAIN)
        self.assertEqual(binding["workbench_main_sha"], EXPECTED_WORKBENCH_MAIN)

    def test_exact_pr_head_has_complete_green_replay_matrix(self) -> None:
        state = self.successor["pre_g3_structured_replay_compatibility"]
        self.assertEqual(state["pull_request"], 250)
        self.assertEqual(state["final_pr_head_sha"], EXPECTED_PR_HEAD)
        self.assertEqual(state["merged_main_sha"], EXPECTED_OBSERVATORY_MAIN)
        self.assertEqual(state["target_count"], 12)
        self.assertTrue(state["all_target_replays_passed_on_exact_pr_head"])
        runs = state["replay_workflows"]
        self.assertEqual(len(runs), 12)
        self.assertEqual({row["workflow_run_id"] for row in runs}, EXPECTED_RUN_IDS)
        self.assertTrue(all(row["conclusion"] == "success" for row in runs))
        self.assertFalse(state["live_provider_execution_performed"])
        self.assertFalse(state["g3_passed"])

    def test_gate_and_authority_state_remain_fail_closed(self) -> None:
        gates = self.successor["inherited_gate_state"]
        self.assertEqual(gates["g0"]["decision"], "BLOCKED_NOT_PASSED")
        self.assertFalse(gates["g0"]["passed"])
        self.assertEqual(gates["g0"]["blocking_source_ids"], ["SRC-14-021"])
        self.assertTrue(gates["g1"]["approved"])
        self.assertFalse(gates["g2"]["passed"])
        self.assertFalse(gates["g3"]["passed"])
        self.assertFalse(gates["g5"]["passed"])

        deps = self.successor["inherited_external_dependencies"]
        self.assertFalse(deps["workbench_phase3_external_live_proof_executed"])
        self.assertFalse(deps["d3_real_human_benchmark_frozen"])
        self.assertFalse(deps["d4_real_human_benchmark_frozen"])
        self.assertFalse(deps["roman_patstat_track_touched_by_this_successor"])

        authority = self.successor["authority"]
        self.assertTrue(authority["g1_approved"])
        for field in (
            "g0_passed",
            "g2_passed",
            "g3_passed",
            "g5_passed",
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
