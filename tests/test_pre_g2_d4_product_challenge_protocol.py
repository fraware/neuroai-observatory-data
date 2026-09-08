from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "curation" / "PRE_G2_D4_PRODUCT_CHALLENGE_PROTOCOL_2026-09-08_v0.1.json"
SCHEMA_PATH = ROOT / "schemas" / "pre-g2-d4-product-review-packet-v0.1.schema.json"
VALIDATOR_PATH = ROOT / "scripts" / "validate_pre_g2_d4_review_packet_semantics.py"

D1_SHA = "7d270002094dcdecb703d5b70ef2268e4869005c284ffd98db3eb936641a78cb"
D2_SHA = "bd9451a5084485ef7a36251b0bc39d486fe0c2174636171a29ec03d7010cbf1d"
G1_ID = "HUMAN_G1_DISPOSITION_2026-09-05_D1_D2_v0.1"
G1_SHA = "ed6489fe1085b5aec1b594970dd1c574b57bd6bbd25a659643e9bd1b7b72d8ef"
WORKBENCH_SHA = "854cc9d1c8e24a9e8ae8b21d871329bc3c24c118"
WORKBENCH_PRODUCT_CONTRACT_BLOB = "2d01f0bbc72eaa4f4e9aac55ad01bbe3185cfe1d"
WORKBENCH_EVIDENCE_ROLE_BLOB = "a79c92dd3c3419ef97b38c62fea8b850b6f02c23"
REVIEW_SCHEMA_BLOB = "385762f930fa4e0251a7f5c2c2045c01ca8a0b1f"
SEMANTIC_VALIDATOR_BLOB = "7384b35cbce89faa5abc0e3af127b1674e2ddded"

REQUIRED_STRATA = {
    "AMBIGUOUS_BIOSIGNAL",
    "CLINICAL",
    "CONSUMER",
    "ENTERTAINMENT_XR",
    "MULTI_JURISDICTION",
    "MULTILINGUAL",
    "NONTRADITIONAL_FORM_FACTOR",
    "RESEARCH",
    "WELLNESS",
    "WORKPLACE",
}
D1_DISPOSITIONS = {"ABSTAIN", "BORDERLINE", "EXCLUDE", "INCLUDE"}
REQUIRED_G2_DISPOSITIONS = {"BORDERLINE", "EXCLUDE", "INCLUDE"}
ADJUDICATION_STATES = {"ADJUDICATED", "AGREE", "DISAGREE_UNADJUDICATED"}
PERMITTED_CHALLENGE_METRICS = {
    "ABSTENTION",
    "BINARY_CLASSIFICATION",
    "CALIBRATION",
    "FOUR_WAY_ROUTING",
    "SUBGROUP_DIAGNOSTIC",
}


def git_blob_sha1(path: Path) -> str:
    payload = path.read_bytes()
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(framed).hexdigest()  # noqa: S324 - Git object identity, not cryptographic security


class PreG2D4ProductChallengeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_protocol_is_pre_g2_only_and_binds_exact_approved_semantics(self) -> None:
        self.assertEqual(self.protocol["status"], "PRE_G2_PROTOCOL_ONLY_NO_MEMBERSHIP_OR_LABELS")
        self.assertEqual(self.protocol["governing_issue"], 223)
        semantics = self.protocol["governing_semantics"]
        self.assertEqual(semantics["d1_canonical_json_sha256"], D1_SHA)
        self.assertEqual(semantics["d2_canonical_json_sha256"], D2_SHA)
        self.assertEqual(semantics["g1_disposition_id"], G1_ID)
        self.assertEqual(semantics["g1_disposition_sha256"], G1_SHA)
        self.assertEqual(semantics["g1_decision"], "APPROVE")
        self.assertEqual(semantics["g1_scope"], "EXACT_D1_D2_IDENTITIES_ONLY")

    def test_protocol_binds_exact_current_workbench_contract_lineage(self) -> None:
        binding = self.protocol["workbench_contract_binding"]
        self.assertEqual(binding["repository"], "fraware/neuroai-workbench")
        self.assertEqual(binding["commit_sha"], WORKBENCH_SHA)
        self.assertEqual(binding["product_public_contract_git_blob_sha"], WORKBENCH_PRODUCT_CONTRACT_BLOB)
        self.assertEqual(binding["evaluation_evidence_roles_git_blob_sha"], WORKBENCH_EVIDENCE_ROLE_BLOB)
        self.assertEqual(binding["benchmark_id"], "PRE_G2_PRODUCT_V0_1")
        self.assertEqual(binding["benchmark_kind"], "PRODUCT")
        self.assertEqual(binding["public_contract_schema_version"], "0.2")
        self.assertEqual(binding["public_contract_state"], "DRAFT_UNFROZEN")
        self.assertEqual(binding["evaluation_plan_schema_version"], "0.1")
        self.assertEqual(binding["evidence_binding_schema_version"], "0.3")
        self.assertEqual(binding["binary_projection_id"], "D1_INCLUDE_EXCLUDE_BINARY_V1")

    def test_d4_is_challenge_evidence_and_cannot_claim_population_inference(self) -> None:
        role = self.protocol["statistical_evidence_role"]
        self.assertEqual(role["role"], "CHALLENGE_CONSTRUCT_COVERAGE")
        self.assertEqual(role["sampling_design_type"], "NONPROBABILITY_CHALLENGE")
        self.assertFalse(role["population_generalizable"])
        self.assertTrue(role["challenge_enrichment"])
        self.assertEqual(role["component_pooling_policy"], "NO_CROSS_ROLE_POOLING")
        for field in (
            "population_frame_id",
            "inclusion_probability_manifest_sha256",
            "estimator_id",
            "uncertainty_method_id",
        ):
            self.assertIsNone(role[field])
        for field in (
            "prevalence_reporting_allowed",
            "population_recall_reporting_allowed",
            "market_share_reporting_allowed",
            "global_completeness_reporting_allowed",
        ):
            self.assertFalse(role[field])
        self.assertEqual(set(role["permitted_metric_families"]), PERMITTED_CHALLENGE_METRICS)
        self.assertNotIn("PREVALENCE", role["permitted_metric_families"])
        self.assertNotIn("RETRIEVAL_RECALL", role["permitted_metric_families"])

    def test_required_product_strata_and_construct_questions_are_exact(self) -> None:
        self.assertEqual(set(self.protocol["required_construct_strata"]), REQUIRED_STRATA)
        self.assertEqual(set(self.protocol["construct_coverage_questions"]), REQUIRED_STRATA)
        for question in self.protocol["construct_coverage_questions"].values():
            self.assertIsInstance(question, str)
            self.assertGreater(len(question.strip()), 20)

    def test_d1_four_way_boundary_and_unresolved_disagreement_are_preserved(self) -> None:
        boundary = self.protocol["boundary_semantics"]
        self.assertEqual(set(boundary["allowed_dispositions"]), D1_DISPOSITIONS)
        self.assertEqual(set(boundary["required_g2_coverage_dispositions"]), REQUIRED_G2_DISPOSITIONS)
        self.assertEqual(set(boundary["resolved_adjudication_states"]), {"ADJUDICATED", "AGREE"})
        self.assertEqual(boundary["unresolved_adjudication_state"], "DISAGREE_UNADJUDICATED")
        self.assertTrue(boundary["human_abstain_is_resolved_governed_disposition"])
        self.assertTrue(boundary["unresolved_disagreement_must_not_be_coerced"])
        self.assertTrue(boundary["unresolved_disagreement_excluded_from_binary_reference_denominators"])
        self.assertTrue(boundary["rationale_required_for_resolved_gold_rows"])

    def test_selection_protocol_does_not_reverse_engineer_or_invent_counts(self) -> None:
        selection = self.protocol["candidate_selection_protocol"]
        self.assertEqual(
            selection["selection_time_boundary"],
            "BEFORE_FINAL_HELD_OUT_MODEL_PROMPT_THRESHOLD_PERFORMANCE",
        )
        self.assertFalse(selection["candidate_membership_chosen_from_final_model_errors"])
        self.assertTrue(selection["development_pilot_required"])
        self.assertFalse(selection["development_pilot_is_held_out"])
        self.assertTrue(selection["pilot_items_permanently_excluded_or_exposure_marked_from_final_held_out"])
        self.assertTrue(selection["selection_provenance_required"])
        self.assertTrue(selection["deliberate_enrichment_must_be_recorded"])
        self.assertIsNone(selection["minimum_final_sample_size"])
        self.assertIsNone(selection["minimum_per_stratum_counts"])
        self.assertIn("COUNTS_MUST_BE_PREDECLARED", selection["count_policy"])
        self.assertIn("DOES NOT INVENT", selection["count_policy"])
        self.assertEqual(selection["real_candidate_membership_location"], "S3_CONTROLLED")

    def test_identity_and_evidence_scope_are_fail_closed(self) -> None:
        identity = self.protocol["exact_object_identity_protocol"]
        self.assertTrue(identity["unknown_version_must_remain_explicit"])
        self.assertTrue(identity["ambiguous_identity_must_remain_explicit"])
        self.assertTrue(identity["model_inference_may_not_repair_identity_ambiguity"])
        self.assertFalse(identity["ambiguous_object_identity_held_out_eligible"])
        self.assertTrue(identity["company_level_statement_may_not_silently_bind_different_product_or_release"])
        self.assertTrue(identity["observation_time_required"])

        evidence = self.protocol["evidence_scope_protocol"]
        for field in (
            "stronger_claims_require_independent_support",
            "product_existence_does_not_establish_effectiveness",
            "product_existence_does_not_establish_regulatory_authorization",
            "product_existence_does_not_establish_deployment",
            "patent_ownership_does_not_establish_product_identity_or_commercialization",
            "marketing_claim_does_not_establish_effectiveness",
            "jurisdiction_specific_status_must_not_be_globalized",
            "translation_provenance_required_for_translated_evidence",
        ):
            self.assertTrue(evidence[field])

    def test_human_reference_standard_and_leakage_boundary_are_explicit(self) -> None:
        review = self.protocol["human_review_protocol"]
        self.assertTrue(review["human_reference_standard_required"])
        self.assertFalse(review["model_consensus_may_be_reference_standard"])
        self.assertTrue(review["reviewers_blinded_to_model_predictions_scores_and_machine_labels_where_practical"])
        self.assertTrue(review["blinding_exception_requires_recorded_rationale"])
        self.assertEqual(
            set(review["required_review_field_names"]),
            {"decision", "rationale", "adjudicator_role", "timestamp", "exact_object_binding"},
        )
        self.assertTrue(review["double_label_subset_required"])
        self.assertTrue(review["double_label_all_final_held_out_candidates"])
        self.assertIsNone(review["double_label_subset_count"])
        self.assertIn("EVERY FINAL HELD-OUT D4 CANDIDATE", review["double_label_count_policy"])
        self.assertTrue(review["adjudication_protocol_required"])
        self.assertTrue(review["agreement_requires_matching_primary_secondary_dispositions"])
        self.assertTrue(review["adjudication_requires_real_primary_secondary_disagreement_and_final_adjudicator"])
        self.assertTrue(review["unresolved_disagreement_cannot_be_held_out_eligible"])
        self.assertTrue(review["reviewer_training_and_calibration_record_required"])

        leakage = self.protocol["leakage_and_contamination_protocol"]
        for field in (
            "held_out_membership_location",
            "held_out_labels_location",
            "review_records_location",
            "adjudication_records_location",
        ):
            self.assertEqual(leakage[field], "S3_CONTROLLED")
        self.assertFalse(leakage["model_prompt_threshold_development_access_to_final_membership_or_labels"])
        self.assertTrue(leakage["exposure_register_required"])
        self.assertTrue(leakage["held_out_eligibility_requires_no_known_exposure_reviewed"])
        self.assertFalse(leakage["unknown_exposure_status_held_out_eligible"])
        self.assertFalse(leakage["public_git_may_contain_real_held_out_membership_or_labels"])

    def test_review_packet_schema_and_semantic_validator_are_exactly_blob_bound(self) -> None:
        binding = self.protocol["review_packet_schema"]
        self.assertEqual(binding["git_blob_sha"], REVIEW_SCHEMA_BLOB)
        self.assertEqual(git_blob_sha1(SCHEMA_PATH), REVIEW_SCHEMA_BLOB)
        self.assertEqual(binding["custody_of_real_packets"], "S3_CONTROLLED")
        self.assertFalse(binding["public_repository_may_contain_real_packets"])

        semantic = self.protocol["semantic_validator"]
        self.assertEqual(semantic["git_blob_sha"], SEMANTIC_VALIDATOR_BLOB)
        self.assertEqual(git_blob_sha1(VALIDATOR_PATH), SEMANTIC_VALIDATOR_BLOB)
        self.assertTrue(semantic["structural_json_schema_validation_is_separate"])
        self.assertFalse(semantic["validator_establishes_source_truth_or_reviewer_competence"])

        self.assertEqual(self.schema["$id"], "urn:neuroai:observatory:d4-product-review-packet:0.1")
        self.assertFalse(self.schema["additionalProperties"])
        self.assertIn("review_design", self.schema["required"])
        strata_enum = set(self.schema["properties"]["construct_strata"]["items"]["enum"])
        self.assertEqual(strata_enum, REQUIRED_STRATA)
        reviewer_decisions = set(self.schema["$defs"]["reviewer_record"]["properties"]["decision"]["enum"])
        self.assertEqual(reviewer_decisions, D1_DISPOSITIONS)
        adjudication_states = set(self.schema["$defs"]["adjudication"]["properties"]["state"]["enum"])
        self.assertEqual(adjudication_states, ADJUDICATION_STATES)
        rights = self.schema["properties"]["rights_containment"]["properties"]
        self.assertEqual(rights["custody"]["const"], "S3_CONTROLLED")
        self.assertFalse(rights["redistribution_authority_claimed"]["const"])

    def test_future_freeze_requires_real_evidence_without_claiming_it_exists(self) -> None:
        freeze = self.protocol["freeze_requirements"]
        self.assertEqual(freeze["future_public_contract_state"], "FROZEN_COMMITMENTS_ONLY")
        self.assertEqual(freeze["commitment_scheme"], "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1")
        self.assertEqual(
            set(freeze["required_boundary_count_keys"]),
            {"ABSTAIN", "BORDERLINE", "EXCLUDE", "INCLUDE", "UNRESOLVED_ADJUDICATION"},
        )
        self.assertEqual(set(freeze["required_nonzero_boundary_coverage"]), REQUIRED_G2_DISPOSITIONS)
        for field in (
            "boundary_coverage_report_digest_required",
            "strata_coverage_report_digest_required",
            "sampling_protocol_id_and_digest_required",
            "human_review_provenance_digest_required",
            "adjudication_protocol_id_and_digest_required",
            "adjudication_accounting_digest_required",
            "double_label_subset_count_required",
            "rights_containment_review_required",
            "contamination_review_and_exposure_register_required",
            "evaluation_plan_digest_binding_required",
        ):
            self.assertTrue(freeze[field])
        self.assertEqual(freeze["evaluation_plan_role"], "CHALLENGE_CONSTRUCT_COVERAGE")
        self.assertFalse(freeze["cross_role_pooling_permitted"])

        state = self.protocol["current_evidence_state"]
        self.assertFalse(state["real_candidate_membership_selected"])
        self.assertFalse(state["real_human_labels_present_in_public_repo"])
        self.assertFalse(state["real_d4_frozen"])
        self.assertFalse(state["benchmark_adequacy_established"])
        self.assertFalse(state["g2_human_disposition_recorded"])

    def test_protocol_confers_no_scientific_release_or_assessment_authority(self) -> None:
        authority = self.protocol["authority"]
        self.assertFalse(authority["g0_passed"])
        self.assertTrue(authority["g1_approved"])
        for field in (
            "g2_passed",
            "g5_passed",
            "canonical_s2_authority",
            "publication_authority",
            "product_effectiveness_authority",
            "regulatory_status_authority",
            "global_completeness_claim",
            "population_generalization_authority",
            "rights_clearance",
            "phase4_online_first_default_authorized",
        ):
            self.assertFalse(authority[field])
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
