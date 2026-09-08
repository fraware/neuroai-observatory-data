from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-08_SCHEDULED_G0_EVIDENCE_SUCCESSOR.json"
PREDECESSOR = ROOT / "curation" / "PROGRAMME_EXECUTION_STATE_2026-09-05_G1_APPROVED_SUCCESSOR.json"
POINTER = ROOT / "curation" / "CURRENT_EXECUTION_CONTROL.json"
DISPOSITION = ROOT / "curation" / "HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json"
PATSTAT_RIGHTS = ROOT / "curation" / "PATSTAT_PUBLIC_EXTRACT_RIGHTS_REVIEW_2026-09-05_v0.1.json"

EXPECTED_SUCCESSOR_PATH = "curation/PROGRAMME_EXECUTION_STATE_2026-09-08_SCHEDULED_G0_EVIDENCE_SUCCESSOR.json"
EXPECTED_PREDECESSOR_PATH = "curation/PROGRAMME_EXECUTION_STATE_2026-09-05_G1_APPROVED_SUCCESSOR.json"
EXPECTED_PREDECESSOR_BLOB = "1f902dbe8776495d2e4bd2e90ba88a09ffaa913d"
EXPECTED_DISPOSITION_PATH = "curation/HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1.json"
EXPECTED_D1_CANONICAL = "7d270002094dcdecb703d5b70ef2268e4869005c284ffd98db3eb936641a78cb"
EXPECTED_D2_CANONICAL = "bd9451a5084485ef7a36251b0bc39d486fe0c2174636171a29ec03d7010cbf1d"
EXPECTED_RUN_ID = 34110413357
EXPECTED_RUN_NUMBER = 55
EXPECTED_OBSERVATORY_SHA = "e208a5361fbf57610a10d760266458a75b7505c1"
EXPECTED_WORKBENCH_SHA = "685f1597a2a63f2e2217f65f115a67ac3e35cc55"
EXPECTED_ARTIFACT_ID = 10014107494
EXPECTED_ARTIFACT_DIGEST = "8086464058b2eedc7b24b147c35034587cf2f12c7fef59d77f01ab711cbe602b"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return hashlib.sha1(payload).hexdigest()


class ScheduledG0EvidenceSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.successor = load_json(SUCCESSOR)
        cls.predecessor = load_json(PREDECESSOR)
        cls.pointer = load_json(POINTER)
        cls.disposition = load_json(DISPOSITION)
        cls.patstat = load_json(PATSTAT_RIGHTS)

    def test_pointer_advances_to_exact_new_successor(self) -> None:
        self.assertEqual(self.pointer["status"], "CURRENT_CONTROL_POINTER_NONCANONICAL")
        self.assertEqual(self.pointer["as_of"], "2026-09-08")
        self.assertEqual(self.pointer["current_programme_execution_state"], EXPECTED_SUCCESSOR_PATH)
        self.assertEqual(self.pointer["current_g1_disposition"], EXPECTED_DISPOSITION_PATH)

    def test_predecessor_is_exact_and_byte_immutable(self) -> None:
        predecessor = self.successor["predecessor"]
        self.assertEqual(predecessor["path"], EXPECTED_PREDECESSOR_PATH)
        self.assertEqual(predecessor["git_blob_sha"], EXPECTED_PREDECESSOR_BLOB)
        self.assertEqual(git_blob_sha(PREDECESSOR), EXPECTED_PREDECESSOR_BLOB)
        self.assertFalse(predecessor["predecessor_is_modified_by_this_successor"])
        self.assertFalse(self.successor["historical_record_boundary"]["predecessor_execution_state_modified"])

    def test_exact_normal_schedule_run_identity_is_bound(self) -> None:
        evidence = self.successor["scheduled_g0_evidence"]
        run = evidence["workflow_run"]
        self.assertEqual(evidence["evidence_class"], "NORMAL_SCHEDULED_OPERATIONAL_DUE_CYCLE")
        self.assertEqual(run["workflow_path"], ".github/workflows/operational-live-cycle.yml")
        self.assertEqual(run["event"], "schedule")
        self.assertEqual(run["run_id"], EXPECTED_RUN_ID)
        self.assertEqual(run["run_number"], EXPECTED_RUN_NUMBER)
        self.assertEqual(run["head_sha"], EXPECTED_OBSERVATORY_SHA)
        self.assertEqual(run["conclusion"], "failure")

    def test_runtime_pairing_and_jobs_are_exact(self) -> None:
        evidence = self.successor["scheduled_g0_evidence"]
        pairing = evidence["runtime_pairing"]
        self.assertEqual(pairing["observatory_head_sha"], EXPECTED_OBSERVATORY_SHA)
        self.assertEqual(pairing["workbench_checked_out_sha"], EXPECTED_WORKBENCH_SHA)
        self.assertFalse(pairing["workbench_pin_updated_by_this_successor"])
        jobs = evidence["jobs"]
        self.assertEqual(jobs["validation"], {"job_id": 101705081004, "conclusion": "success"})
        self.assertEqual(jobs["live"]["job_id"], 101705112713)
        self.assertEqual(jobs["live"]["conclusion"], "failure")
        self.assertEqual(jobs["live"]["due_cycle_and_exact_resume_step_conclusion"], "success")
        self.assertEqual(jobs["live"]["post_transition_invariants_step_conclusion"], "failure")
        self.assertEqual(jobs["live"]["sanitized_artifact_retention_step_conclusion"], "success")

    def test_sanitized_artifact_identity_is_exact_and_non_authorizing(self) -> None:
        artifact = self.successor["scheduled_g0_evidence"]["retained_sanitized_artifact"]
        self.assertEqual(artifact["artifact_id"], EXPECTED_ARTIFACT_ID)
        self.assertEqual(artifact["name"], "operational-live-proof-34110413357-1")
        self.assertEqual(artifact["size_in_bytes"], 3509)
        self.assertEqual(artifact["github_artifact_digest_sha256"], EXPECTED_ARTIFACT_DIGEST)
        self.assertFalse(artifact["expired_at_observation"])
        self.assertFalse(artifact["contains_protected_capture_bytes"])
        self.assertIn("does not reinterpret", artifact["note"])

    def test_reported_operational_facts_preserve_failure_locus(self) -> None:
        facts = self.successor["scheduled_g0_evidence"]["reported_execution_facts"]
        self.assertEqual(facts["execution_status"], "COMPLETE_WITH_SOURCE_FAILURES")
        self.assertEqual(facts["transport_security"], "DNS_PINNED_VALIDATED_ADDRESS_SET")
        self.assertEqual(facts["source_accountability_coverage"], 1.0)
        self.assertEqual(facts["target_execution_coverage"], 1.0)
        self.assertEqual(facts["resume_additional_transport_sends"], 0)
        self.assertEqual(facts["engineering_state"], "READY")
        self.assertEqual(facts["top_level_health"], "DEGRADED")
        self.assertEqual(facts["source_resolution_state"], "DEGRADED")
        self.assertEqual(facts["failed_source_ids"], ["SRC-0064", "SRC-14-019", "SRC-14-021"])
        self.assertEqual(facts["route_resolved_failed_source_ids"], ["SRC-0064", "SRC-14-019"])
        self.assertEqual(facts["unresolved_failed_source_ids"], ["SRC-14-021"])
        self.assertEqual(
            facts["src_14_021_failure"],
            {"failure_class": "NETWORK_ERROR", "retryable": True, "attempt_count": 3},
        )

    def test_scheduled_criterion_is_executed_but_not_satisfied(self) -> None:
        interpretation = self.successor["scheduled_g0_evidence"]["criterion_interpretation"]
        self.assertTrue(interpretation["normal_schedule_event_observed"])
        self.assertFalse(interpretation["scheduled_operational_live_criterion_satisfied"])
        self.assertEqual(interpretation["state"], "EXECUTED_NOT_SATISFIED")
        self.assertEqual(interpretation["blocking_source_id"], "SRC-14-021")
        self.assertEqual(interpretation["blocking_issue"], 224)
        gates = self.successor["gate_state"]
        self.assertEqual(gates["g0"]["decision"], "BLOCKED_NOT_PASSED")
        self.assertFalse(gates["g0"]["passed"])
        self.assertTrue(gates["g0"]["scheduled_event_observed"])
        self.assertFalse(gates["g0"]["scheduled_operational_live_criterion_satisfied"])

    def test_g1_is_inherited_exactly_and_g2_remains_unpassed(self) -> None:
        inherited = self.successor["g1_disposition_inheritance"]
        self.assertEqual(inherited["record_path"], EXPECTED_DISPOSITION_PATH)
        self.assertEqual(inherited["decision"], "APPROVE")
        self.assertTrue(inherited["g1_approved"])
        self.assertTrue(inherited["human_disposition_recorded"])
        self.assertEqual(inherited["d1_canonical_json_sha256"], EXPECTED_D1_CANONICAL)
        self.assertEqual(inherited["d2_canonical_json_sha256"], EXPECTED_D2_CANONICAL)
        self.assertFalse(inherited["re_adjudicated_by_this_successor"])
        self.assertEqual(self.disposition["decision"], "APPROVE")
        self.assertFalse(self.successor["gate_state"]["g2"]["g2_passed"])

    def test_independent_blockers_and_authority_remain_fail_closed(self) -> None:
        matters = self.successor["independent_unresolved_matters"]
        sona = matters["src_14_021_successor_domain_verification"]
        self.assertEqual(sona["issue"], 224)
        self.assertEqual(sona["state"], "OPEN")
        self.assertFalse(sona["verified_successor_route_registered"])
        self.assertFalse(sona["sonafrica_net_promoted_by_this_successor"])
        patstat = matters["patstat_public_extract_rights_review"]
        self.assertEqual(patstat["issue"], 210)
        self.assertFalse(patstat["rights_clearance"])
        self.assertFalse(self.patstat["authority"]["rights_clearance"])
        phase3 = matters["online_first_phase3_external_proof"]
        self.assertEqual(phase3["workbench_issue"], 287)
        self.assertEqual(phase3["state"], "INCOMPLETE_EXTERNAL_PROOF_NOT_EXECUTED")
        self.assertFalse(phase3["phase4_default_transition_authorized"])
        authority = self.successor["authority"]
        self.assertFalse(authority["g0_passed"])
        self.assertTrue(authority["g1_approved"])
        self.assertFalse(authority["g2_passed"])
        self.assertFalse(authority["canonical_s2_authority"])
        self.assertFalse(authority["publication_authority"])
        self.assertFalse(authority["mutation_authority"])
        self.assertEqual(authority["assessment_effect"], "NONE")
        self.assertFalse(authority["patstat_rights_clearance"])
        self.assertFalse(authority["phase4_online_first_default_authorized"])


if __name__ == "__main__":
    unittest.main()
