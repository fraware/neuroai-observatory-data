from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "curation" / "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1.json"
PILOT_SCHEMA_PATH = ROOT / "schemas" / "pre-g2-d4-pilot-readiness-aggregate-v0.1.schema.json"
POOL_SCHEMA_PATH = ROOT / "schemas" / "pre-g2-d4-selection-candidate-pool-v0.1.schema.json"
PILOT_EVALUATOR_PATH = ROOT / "scripts" / "evaluate_pre_g2_d4_pilot_readiness.py"
SELECTOR_PATH = ROOT / "scripts" / "select_pre_g2_d4_held_out.py"
PARENT_PROTOCOL_PATH = ROOT / "curation" / "PRE_G2_D4_PRODUCT_CHALLENGE_PROTOCOL_2026-09-08_v0.1.json"

PARENT_MAIN_SHA = "92d56c0b7f9ea776a9e616e769407ee7b4b37296"
PARENT_PROTOCOL_BLOB = "ec472ac66264e34343c97544d8da597014a9d80e"
PILOT_SCHEMA_BLOB = "869863518051020618d03e4b07f7d475ce63cda4"
POOL_SCHEMA_BLOB = "c36857c378e7ccbd432d88a3a44fe194a1ec0f18"
PILOT_EVALUATOR_BLOB = "ffdcdee9cb35fbfc26c619a18aa1d728124c8e3d"
SELECTOR_BLOB = "1adfc08ddc57d0f77e24870eb839cc513d5fbb65"
COMMITMENT_SCHEME = "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1"

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


def git_blob_sha1(path: Path) -> str:
    payload = path.read_bytes()
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(framed).hexdigest()  # noqa: S324 - Git object identity, not cryptographic security


class PreG2D4SamplingCalibrationProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.pilot_schema = json.loads(PILOT_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.pool_schema = json.loads(POOL_SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_parent_d4_protocol_binding_is_exact(self) -> None:
        parent = self.protocol["parent_d4_protocol_binding"]
        self.assertEqual(parent["main_commit_sha"], PARENT_MAIN_SHA)
        self.assertEqual(parent["git_blob_sha"], PARENT_PROTOCOL_BLOB)
        self.assertEqual(git_blob_sha1(PARENT_PROTOCOL_PATH), PARENT_PROTOCOL_BLOB)
        self.assertEqual(parent["benchmark_id"], "PRE_G2_PRODUCT_V0_1")
        self.assertEqual(parent["statistical_evidence_role"], "CHALLENGE_CONSTRUCT_COVERAGE")
        self.assertEqual(parent["sampling_design_type"], "NONPROBABILITY_CHALLENGE")
        self.assertFalse(parent["population_generalizable"])
        self.assertEqual(parent["component_pooling_policy"], "NO_CROSS_ROLE_POOLING")

    def test_pilot_artifacts_are_exactly_blob_bound(self) -> None:
        artifacts = self.protocol["pilot_readiness_artifacts"]
        self.assertEqual(artifacts["aggregate_schema_git_blob_sha"], PILOT_SCHEMA_BLOB)
        self.assertEqual(artifacts["evaluator_git_blob_sha"], PILOT_EVALUATOR_BLOB)
        self.assertEqual(git_blob_sha1(PILOT_SCHEMA_PATH), PILOT_SCHEMA_BLOB)
        self.assertEqual(git_blob_sha1(PILOT_EVALUATOR_PATH), PILOT_EVALUATOR_BLOB)
        self.assertTrue(artifacts["aggregate_only_public_reporting"])
        self.assertFalse(artifacts["real_item_identities_in_public_aggregate"])
        self.assertFalse(artifacts["real_reviewer_identities_in_public_aggregate"])
        self.assertFalse(artifacts["real_source_evidence_in_public_aggregate"])
        self.assertFalse(artifacts["human_rationales_in_public_aggregate"])

    def test_candidate_pool_and_selector_are_exactly_blob_bound(self) -> None:
        pool = self.protocol["controlled_candidate_pool"]
        selection = self.protocol["deterministic_selection"]
        self.assertEqual(pool["schema_git_blob_sha"], POOL_SCHEMA_BLOB)
        self.assertEqual(selection["selector_git_blob_sha"], SELECTOR_BLOB)
        self.assertEqual(git_blob_sha1(POOL_SCHEMA_PATH), POOL_SCHEMA_BLOB)
        self.assertEqual(git_blob_sha1(SELECTOR_PATH), SELECTOR_BLOB)
        self.assertEqual(pool["commitment_scheme"], COMMITMENT_SCHEME)
        self.assertEqual(pool["commitment_key_location"], "S3_CONTROLLED_NEVER_PUBLIC_GIT")
        self.assertFalse(pool["public_git_may_contain_real_candidate_identities"])
        self.assertFalse(pool["public_git_may_contain_commitment_key"])
        self.assertFalse(pool["final_label_fields_permitted_in_selection_input"])
        self.assertFalse(pool["model_output_score_prompt_threshold_or_final_error_fields_permitted_in_selection_input"])
        self.assertFalse(selection["global_optimization_solver_used"])
        self.assertIn("not a proof", selection["failure_semantics"])
        self.assertFalse(selection["candidate_ids_printed_to_stdout"])
        self.assertTrue(selection["controlled_membership_output_requires_explicit_path"])
        self.assertEqual(selection["controlled_membership_output_custody"], "S3_CONTROLLED")

    def test_pilot_gate_is_fixed_before_execution_without_claiming_competence(self) -> None:
        pilot = self.protocol["pilot_calibration_round"]
        self.assertEqual(pilot["round_size"], 60)
        self.assertTrue(pilot["every_item_double_labeled"])
        self.assertTrue(pilot["pilot_items_permanently_excluded_from_final_held_out"])
        self.assertFalse(pilot["failed_round_extension_permitted"])
        self.assertEqual(pilot["pilot_membership_commitment_scheme"], COMMITMENT_SCHEME)
        self.assertEqual(pilot["minimum_items_per_controlled_stratum"], 6)
        self.assertEqual(pilot["minimum_resolved_include"], 10)
        self.assertEqual(pilot["minimum_resolved_exclude"], 10)
        self.assertEqual(pilot["minimum_resolved_borderline"], 10)
        self.assertTrue(pilot["abstain_remains_valid_without_minimum"])
        self.assertEqual(pilot["minimum_primary_secondary_exact_four_way_agreement_count"], 48)
        self.assertEqual(pilot["minimum_primary_secondary_exact_four_way_agreement_rate"], 0.8)
        self.assertEqual(pilot["maximum_unresolved_disagreement_count"], 3)
        self.assertEqual(pilot["maximum_unresolved_disagreement_rate"], 0.05)
        self.assertEqual(pilot["semantic_validation_failure_count_required"], 0)
        self.assertEqual(pilot["reviewer_reference_collision_count_required"], 0)
        self.assertEqual(pilot["evidence_binding_failure_count_required"], 0)
        self.assertEqual(pilot["pilot_items_held_out_eligible_count_required"], 0)
        self.assertFalse(pilot["automated_pass_establishes_reviewer_competence"])
        self.assertTrue(pilot["human_calibration_disposition_required_after_automated_pass"])

    def test_final_allocation_is_prelabel_challenge_coverage_not_population_power(self) -> None:
        allocation = self.protocol["final_held_out_allocation"]
        self.assertTrue(allocation["selection_allowed_only_after_quantitative_pilot_pass_and_human_calibration_approval"])
        self.assertEqual(allocation["exact_final_unique_membership_count"], 240)
        self.assertEqual(allocation["minimum_items_per_controlled_stratum"], 24)
        self.assertEqual(allocation["multilingual_minimum_items"], 24)
        self.assertEqual(allocation["minimum_distinct_non_english_source_languages"], 6)
        self.assertEqual(allocation["minimum_items_per_counted_non_english_source_language"], 3)
        self.assertEqual(allocation["multi_jurisdiction_minimum_items"], 24)
        self.assertEqual(allocation["minimum_distinct_jurisdictions"], 6)
        self.assertEqual(allocation["minimum_items_per_counted_jurisdiction"], 3)
        self.assertTrue(allocation["selection_occurs_before_final_human_d1_dispositions"])
        self.assertTrue(allocation["final_human_labels_collected_only_after_exact_membership_is_frozen"])
        self.assertTrue(allocation["final_membership_may_not_be_repaired_after_labels_by_cherry_picking"])
        self.assertTrue(allocation["g2_boundary_coverage_still_requires_nonzero_include_exclude_borderline"])
        self.assertFalse(allocation["allocation_is_population_power_calculation"])
        self.assertFalse(allocation["allocation_is_prevalence_precision_calculation"])

    def test_controlled_strata_are_exact(self) -> None:
        self.assertEqual(set(self.protocol["controlled_product_strata"]), REQUIRED_STRATA)
        candidate_enum = set(self.pool_schema["$defs"]["candidate"]["properties"]["construct_strata"]["items"]["enum"])
        self.assertEqual(candidate_enum, REQUIRED_STRATA)

    def test_public_schemas_bind_keyed_commitment_and_prohibit_label_fields(self) -> None:
        self.assertEqual(
            self.pilot_schema["properties"]["pilot_membership_commitment_scheme"]["const"],
            COMMITMENT_SCHEME,
        )
        self.assertEqual(self.pilot_schema["properties"]["total_items"]["const"], 60)
        self.assertEqual(self.pilot_schema["properties"]["double_labeled_items"]["const"], 60)
        self.assertEqual(
            self.pool_schema["properties"]["candidate_pool_commitment_scheme"]["const"],
            COMMITMENT_SCHEME,
        )
        self.assertEqual(self.pool_schema["properties"]["candidate_pool_frozen"]["const"], True)
        self.assertEqual(self.pool_schema["properties"]["candidates"]["minItems"], 240)
        candidate_properties = set(self.pool_schema["$defs"]["candidate"]["properties"])
        for forbidden in ("decision", "label", "prediction", "model_score", "threshold", "final_model_error"):
            self.assertNotIn(forbidden, candidate_properties)

    def test_human_calibration_disposition_cannot_be_replaced_by_thresholds(self) -> None:
        governance = self.protocol["human_governance_after_pilot"]
        self.assertTrue(governance["required"])
        self.assertFalse(governance["automated_thresholds_may_substitute_for_human_calibration_disposition"])
        self.assertIn("REVIEWER_TRAINING_AND_QUALIFICATION_PROVENANCE", governance["must_review"])
        self.assertIn("RATIONALE_QUALITY", governance["must_review"])

    def test_current_state_and_authority_remain_fail_closed(self) -> None:
        state = self.protocol["current_evidence_state"]
        for field in (
            "real_pilot_round_exists",
            "pilot_quantitative_gate_passed",
            "human_calibration_disposition_approved",
            "real_final_candidate_pool_frozen",
            "real_final_membership_selected",
            "real_final_human_labels_collected",
            "real_d4_frozen",
            "benchmark_adequacy_established",
        ):
            self.assertFalse(state[field])

        authority = self.protocol["authority"]
        self.assertTrue(authority["g1_approved"])
        for field in (
            "reviewer_competence_established",
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "canonical_s2_authority",
            "publication_authority",
            "population_generalization_authority",
            "rights_clearance",
            "phase4_online_first_default_authorized",
        ):
            self.assertFalse(authority[field])
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
