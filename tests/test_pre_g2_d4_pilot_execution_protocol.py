from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "curation" / "PRE_G2_D4_PILOT_EXECUTION_PROTOCOL_2026-09-09_v0.1.json"

PARENT_MAIN = "41b4f3e3663e6538bdeeb1d3de4b0e479c080fa5"
EXPECTED_PARENT_BLOBS = {
    "d4_product_challenge_protocol": "ec472ac66264e34343c97544d8da597014a9d80e",
    "d4_sampling_calibration_protocol": "feedbc5587b0de8a548d41efd49fc66c24cde271",
    "d4_review_packet_schema": "d0511d994bb65c5027b7a341a42a4b5e30ed72e2",
    "d4_review_packet_semantic_validator": "6365d7667744e1a45fa5da71a044158896036903",
    "d4_pilot_readiness_schema": "869863518051020618d03e4b07f7d475ce63cda4",
    "d4_pilot_readiness_evaluator": "ffdcdee9cb35fbfc26c619a18aa1d728124c8e3d",
    "d4_candidate_pool_schema": "c36857c378e7ccbd432d88a3a44fe194a1ec0f18",
    "d4_selector_v0_1": "1adfc08ddc57d0f77e24870eb839cc513d5fbb65",
}
EXPECTED_EXECUTION_BLOBS = {
    "pilot_execution_manifest_schema": "79308a46724e566980d1fed5a83c0579be68406b",
    "pilot_aggregate_builder": "2a59f0c7160b3692f4f68cbceafc2b94e51ab04b",
    "identity_namespace_attestation_schema": "8a138f6c2c72c62bea964986da9117d30a18329b",
    "pilot_final_disjointness_checker": "2f4c6e4707ed253078560df36a90bfbaff6b09e9",
    "pilot_final_disjointness_public_summary_schema": "396722a91d11917c7eb1e69283178d5481ef4c16",
}


def git_blob_sha1(path: Path) -> str:
    payload = path.read_bytes()
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(framed).hexdigest()  # noqa: S324 - Git object identity only


class PreG2D4PilotExecutionProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))

    def test_protocol_identity_and_parent_main_are_exact(self) -> None:
        self.assertEqual(
            self.protocol["protocol_id"],
            "PRE_G2_D4_PILOT_EXECUTION_PROTOCOL_2026-09-09_v0.1",
        )
        self.assertEqual(self.protocol["benchmark_id"], "PRE_G2_PRODUCT_V0_1")
        self.assertEqual(self.protocol["state"], "SOFTWARE_CONTROL_PROTOCOL_ONLY_NO_REAL_PILOT")
        self.assertEqual(self.protocol["parent_main_binding"]["main_commit_sha"], PARENT_MAIN)

    def test_parent_artifacts_are_exactly_blob_bound(self) -> None:
        bindings = self.protocol["parent_artifact_bindings"]
        for name, expected_blob in EXPECTED_PARENT_BLOBS.items():
            with self.subTest(name=name):
                self.assertEqual(bindings[name]["git_blob_sha"], expected_blob)
                self.assertEqual(git_blob_sha1(ROOT / bindings[name]["path"]), expected_blob)

    def test_execution_artifacts_are_exactly_blob_bound(self) -> None:
        bindings = self.protocol["execution_artifact_bindings"]
        for name, expected_blob in EXPECTED_EXECUTION_BLOBS.items():
            with self.subTest(name=name):
                self.assertEqual(bindings[name]["git_blob_sha"], expected_blob)
                self.assertEqual(git_blob_sha1(ROOT / bindings[name]["path"]), expected_blob)

    def test_pilot_contract_is_fail_closed_and_aggregate_derived(self) -> None:
        contract = self.protocol["pilot_execution_contract"]
        self.assertEqual(contract["pilot_size"], 60)
        self.assertEqual(contract["all_items_must_be_candidate_role"], "PILOT_DEVELOPMENT")
        self.assertTrue(contract["all_items_double_labeled"])
        self.assertFalse(contract["all_items_held_out_eligible"])
        self.assertTrue(contract["packet_bytes_bound_by_sha256"])
        self.assertTrue(contract["unique_packet_references_required"])
        self.assertTrue(contract["unique_item_ids_required"])
        self.assertEqual(contract["pilot_membership_commitment_scheme"], "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1")
        self.assertEqual(contract["commitment_key_custody"], "S3_CONTROLLED_NEVER_PUBLIC_GIT")
        self.assertTrue(contract["review_packet_structure_enforced_before_semantic_validation"])
        self.assertTrue(contract["merged_semantic_validator_required"])
        self.assertTrue(contract["model_development_fields_rejected_recursively"])
        self.assertTrue(contract["aggregate_counts_derived_from_packets_not_operator_supplied"])
        self.assertFalse(contract["controlled_identifiers_permitted_in_public_output"])
        self.assertTrue(contract["semantic_validation_diagnostics_sanitized_at_public_boundary"])

    def test_disjointness_contract_does_not_overclaim_cryptographic_or_identity_truth(self) -> None:
        contract = self.protocol["later_final_pool_disjointness_contract"]
        self.assertTrue(contract["shared_namespace_attestation_required"])
        self.assertEqual(contract["identity_namespace_attestation_digest_semantics"], "SHA256_CANONICAL_JSON_V1")
        self.assertTrue(contract["attestation_digest_recomputed_and_verified"])
        self.assertEqual(contract["comparison_semantics"], "SHARED_CONTROLLED_ITEM_ID_NAMESPACE_EXACT_EQUALITY")
        self.assertTrue(contract["controlled_overlap_ids_remain_s3"])
        self.assertFalse(contract["public_summary_contains_overlap_ids"])
        self.assertFalse(contract["public_zero_knowledge_proof"])
        self.assertFalse(contract["independently_verifiable_without_s3_inputs"])
        self.assertFalse(contract["identity_resolution_truth_established_by_software"])
        self.assertTrue(contract["nonzero_overlap_blocks_final_selection"])

    def test_parent_selector_diagnostic_defect_is_explicitly_contained(self) -> None:
        selector = self.protocol["parent_artifact_bindings"]["d4_selector_v0_1"]
        self.assertEqual(selector["known_diagnostic_containment_issue"], 232)
        self.assertFalse(selector["real_s3_cli_execution_approved"])
        self.assertTrue(selector["use_inside_disjointness_wrapper_only_with_sanitized_external_errors"])

    def test_current_software_stage_does_not_remove_later_governance_boundary(self) -> None:
        governance = self.protocol["current_stage_governance"]
        self.assertFalse(governance["human_governance_required_to_merge_software_controls"])
        self.assertFalse(governance["human_calibration_disposition_executed"])
        self.assertFalse(governance["human_calibration_requirement_for_later_real_final_selection_removed"])

    def test_current_evidence_state_and_authority_remain_non_authorizing(self) -> None:
        state = self.protocol["current_evidence_state"]
        for field, value in state.items():
            with self.subTest(field=field):
                self.assertFalse(value)

        authority = self.protocol["authority"]
        self.assertTrue(authority["g1_approved"])
        for field in (
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "reviewer_competence_established",
            "identity_resolution_truth_established",
            "benchmark_adequacy_established",
            "rights_clearance",
            "population_generalization_authority",
            "canonical_s2_authority",
            "publication_authority",
            "phase4_online_first_default_authorized",
        ):
            with self.subTest(field=field):
                self.assertFalse(authority[field])
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
