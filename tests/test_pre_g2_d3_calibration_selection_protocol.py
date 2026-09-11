from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

PROTOCOL_PATH = Path(
    "curation/PRE_G2_D3_CALIBRATION_SELECTION_COMPOSITION_2026-09-11_v0.1.json"
)
DISPOSITION_SCHEMA_PATH = Path(
    "schemas/pre-g2-d3-challenge-human-calibration-disposition-v0.1.schema.json"
)


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


class D3CalibrationSelectionProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(
            PROTOCOL_PATH.read_text(encoding="utf-8")
        )
        cls.schema = json.loads(
            DISPOSITION_SCHEMA_PATH.read_text(encoding="utf-8")
        )

    def test_identity_and_parent_main_are_exact(self) -> None:
        self.assertEqual(
            self.protocol["control_id"],
            "PRE_G2_D3_CALIBRATION_SELECTION_COMPOSITION_2026-09-11_v0.1",
        )
        self.assertEqual(self.protocol["governing_issue"], 238)
        self.assertEqual(self.protocol["umbrella_d3_issue"], 222)
        self.assertEqual(self.protocol["baseline_a_audit_issue"], 220)
        self.assertEqual(self.protocol["patstat_rights_issue"], 210)
        self.assertEqual(
            self.protocol["parent_main_binding"]["main_commit_sha"],
            "a2d7af14eaadd44c140a29846696dfce99a884a0",
        )

    def test_all_parent_and_successor_artifacts_are_exactly_blob_bound(self) -> None:
        for group in (
            "parent_artifact_bindings",
            "successor_artifact_bindings",
        ):
            for name, binding in self.protocol[group].items():
                with self.subTest(group=group, name=name):
                    path = Path(binding["path"])
                    self.assertTrue(path.is_file(), path)
                    self.assertEqual(
                        _git_blob_sha(path),
                        binding["git_blob_sha"],
                        path,
                    )

    def test_audit_finding_does_not_rewrite_lower_level_selector(self) -> None:
        finding = self.protocol["audit_finding"]
        self.assertTrue(
            finding[
                "v0_1_candidate_pool_binds_calibration_disposition_digest"
            ]
        )
        self.assertFalse(
            finding[
                "v0_1_lower_selector_validates_disposition_object_semantics"
            ]
        )
        self.assertFalse(
            finding["v0_1_lower_selector_requires_approve_decision"]
        )
        self.assertFalse(
            finding[
                "v0_1_lower_selector_requires_pilot_disjointness_before_selection"
            ]
        )
        self.assertEqual(
            finding["v0_1_lower_selector_status_after_successor"],
            "VALID_DETERMINISTIC_PRIMITIVE_NOT_SUFFICIENT_ALONE_FOR_REAL_FINAL_SELECTION",
        )
        self.assertFalse(finding["historical_v0_1_rewrite_authorized"])
        self.assertEqual(
            finding["required_real_execution_path"],
            "COMPOSED_FINAL_SELECTION_ENTRYPOINT",
        )

    def test_human_disposition_contract_is_local_and_fail_closed(self) -> None:
        contract = self.protocol["human_calibration_disposition_contract"]
        self.assertEqual(
            contract["decision_domain"],
            ["APPROVE", "REVISE", "REJECT"],
        )
        self.assertTrue(contract["only_approve_unlocks_selection"])
        self.assertEqual(
            contract["approval_scope"],
            "FINAL_CHALLENGE_CANDIDATE_POOL_SELECTION_ONLY",
        )
        self.assertTrue(contract["quantitative_gate_passed_required"])
        self.assertTrue(contract["binds_canonical_pilot_manifest_sha256"])
        self.assertTrue(
            contract["binds_canonical_readiness_aggregate_sha256"]
        )
        self.assertTrue(
            contract["binds_canonical_readiness_result_sha256"]
        )
        self.assertFalse(
            contract["governance_identity_or_competence_established_by_software"]
        )
        self.assertFalse(
            contract["reviewer_competence_established_by_approval"]
        )
        self.assertFalse(
            contract["benchmark_adequacy_established_by_approval"]
        )

    def test_disposition_schema_cannot_claim_broader_authority(self) -> None:
        props = self.schema["properties"]
        self.assertEqual(
            props["benchmark_id"]["const"],
            "PRE_G2_PATENT_V0_1",
        )
        self.assertEqual(
            props["approval_scope"]["const"],
            "FINAL_CHALLENGE_CANDIDATE_POOL_SELECTION_ONLY",
        )
        self.assertEqual(
            props["governance_role"]["const"],
            "D3_HUMAN_CALIBRATION_AUTHORITY",
        )
        self.assertTrue(props["quantitative_gate_passed"]["const"])
        authority = props["authority"]["properties"]
        for key in (
            "reviewer_competence_established",
            "benchmark_adequacy_established",
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "rights_clearance",
            "population_generalization_authority",
            "canonical_s2_authority",
            "publication_authority",
            "phase4_online_first_default_authorized",
        ):
            self.assertFalse(authority[key]["const"], key)
        self.assertEqual(authority["assessment_effect"]["const"], "NONE")

    def test_composed_execution_requires_all_prerequisites_before_selection(self) -> None:
        execution = self.protocol["composed_execution_contract"]
        sequence = execution["sequence"]
        self.assertLess(
            sequence.index("REQUIRE_HUMAN_DECISION_APPROVE"),
            sequence.index("EXECUTE_DETERMINISTIC_LOWER_LEVEL_SELECTION"),
        )
        self.assertLess(
            sequence.index("REQUIRE_ZERO_OVERLAP"),
            sequence.index("EXECUTE_DETERMINISTIC_LOWER_LEVEL_SELECTION"),
        )
        self.assertTrue(
            execution[
                "valid_success_preserves_lower_level_selected_membership_semantics"
            ]
        )
        self.assertTrue(execution["candidate_pool_hmac_reverified"])
        self.assertTrue(execution["pilot_membership_hmac_reverified"])
        self.assertEqual(
            execution["public_failure_diagnostics"],
            "FIXED_GENERIC_MESSAGES_ONLY",
        )
        self.assertFalse(
            execution["unexpected_exception_detail_publicly_permitted"]
        )
        self.assertFalse(
            execution["controlled_outputs_may_alias_direct_inputs"]
        )
        self.assertFalse(
            execution["controlled_outputs_may_be_inside_pilot_packet_directory"]
        )
        self.assertFalse(
            execution["runtime_s3_custody_established_by_filesystem_path_alone"]
        )

    def test_current_evidence_and_authority_remain_non_authorizing(self) -> None:
        for key, value in self.protocol["current_evidence_state"].items():
            with self.subTest(key=key):
                self.assertFalse(value)

        authority = self.protocol["authority"]
        self.assertTrue(authority["g1_approved"])
        for key in (
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "rights_clearance",
            "reviewer_competence_established",
            "benchmark_adequacy_established",
            "population_generalization_authority",
            "canonical_s2_authority",
            "publication_authority",
            "phase4_online_first_default_authorized",
        ):
            self.assertFalse(authority[key], key)
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
