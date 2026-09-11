from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

PROTOCOL_PATH = Path(
    "curation/PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1.json"
)


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


class D3ChallengeSamplingProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(
            PROTOCOL_PATH.read_text(encoding="utf-8")
        )

    def test_identity_and_parent_bindings(self) -> None:
        self.assertEqual(
            self.protocol["control_id"],
            "PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1",
        )
        self.assertEqual(self.protocol["governing_issue"], 236)
        self.assertEqual(self.protocol["umbrella_d3_issue"], 222)
        self.assertEqual(self.protocol["baseline_a_audit_issue"], 220)
        self.assertEqual(self.protocol["patstat_rights_issue"], 210)
        self.assertEqual(
            self.protocol["parent_main_binding"]["main_commit_sha"],
            "c55f7615384d13dcb5c14a2d18f347fb18554cfe",
        )
        self.assertEqual(
            self.protocol["parent_d3_challenge_binding"]["git_blob_sha"],
            "0b66a1f5242e9c6020935b2d25e2da068b76c8c1",
        )
        self.assertEqual(
            self.protocol["parent_review_packet_binding"]["schema_git_blob_sha"],
            "5e47501690efd3aa272d1a163da80d6393685664",
        )
        self.assertEqual(
            self.protocol["parent_review_packet_binding"]["validator_git_blob_sha"],
            "496bf9f143694f25602ba86f6dff91a79e13dda3",
        )

    def test_all_bound_artifacts_are_exact(self) -> None:
        for name, binding in self.protocol["artifact_bindings"].items():
            with self.subTest(name=name):
                path = Path(binding["path"])
                self.assertTrue(path.is_file(), path)
                self.assertEqual(
                    _git_blob_sha(path),
                    binding["git_blob_sha"],
                    path,
                )

    def test_pilot_gate_deliberately_excludes_raw_agreement_threshold(self) -> None:
        pilot = self.protocol["pilot_design"]
        self.assertEqual(pilot["pilot_n"], 60)
        self.assertEqual(pilot["minimum_per_required_stratum"], 10)
        self.assertEqual(pilot["minimum_resolved_include"], 10)
        self.assertEqual(pilot["minimum_resolved_exclude"], 10)
        self.assertEqual(pilot["minimum_resolved_borderline"], 10)
        self.assertEqual(pilot["maximum_unresolved_disagreement"], 6)
        self.assertFalse(pilot["raw_four_way_agreement_is_automated_gate"])
        self.assertTrue(pilot["raw_four_way_agreement_reporting_required"])
        self.assertTrue(
            pilot["human_calibration_disposition_required_after_quantitative_gate"]
        )
        self.assertFalse(pilot["failed_round_extension_permitted"])
        self.assertTrue(pilot["replacement_round_must_be_disjoint"])

    def test_final_allocation_is_challenge_resolution_not_population_power(self) -> None:
        role = self.protocol["statistical_role"]
        self.assertEqual(
            role["evidence_role"],
            "CHALLENGE_CONSTRUCT_COVERAGE",
        )
        self.assertFalse(role["population_generalizable"])
        self.assertFalse(role["sample_size_is_population_power_calculation"])
        self.assertFalse(role["confidence_interval_claim_created"])
        final = self.protocol["final_challenge_design"]
        self.assertEqual(final["final_n"], 240)
        self.assertEqual(final["minimum_per_required_stratum"], 40)
        self.assertEqual(
            final["single_item_descriptive_stratum_rate_increment_max"],
            0.025,
        )
        self.assertEqual(final["non_english_language_target_count"], 8)
        self.assertEqual(final["minimum_per_counted_non_english_language"], 4)
        self.assertEqual(final["jurisdiction_target_count"], 8)
        self.assertEqual(final["minimum_per_counted_jurisdiction"], 4)
        self.assertEqual(final["missing_abstract_minimum"], 16)
        self.assertEqual(final["short_abstract_minimum"], 16)
        self.assertEqual(final["outside_query_pool_challenge_minimum"], 40)
        self.assertFalse(
            final["outside_query_pool_is_population_recall_denominator"]
        )
        self.assertFalse(
            final[
                "selection_may_use_model_predictions_scores_prompts_thresholds_or_final_errors"
            ]
        )

    def test_anti_cherry_picking_and_disjointness_boundaries(self) -> None:
        anti = self.protocol["anti_cherry_picking"]
        self.assertTrue(anti["human_calibration_disposition_digest_required"])
        self.assertTrue(anti["candidate_pool_frozen_before_selection"])
        self.assertTrue(anti["candidate_pool_hmac_required"])
        self.assertTrue(anti["deterministic_tie_break_bound_to_pool_commitment"])
        self.assertTrue(anti["final_human_d1_labels_forbidden_from_selector_input"])
        self.assertTrue(
            anti["historical_machine_label_fields_forbidden_from_selector_input"]
        )
        self.assertEqual(
            anti["selected_membership_custody"],
            "S3_CONTROLLED",
        )
        self.assertEqual(
            anti["public_output"],
            "AGGREGATE_ONLY_PLUS_OPAQUE_DIGESTS",
        )

        disjoint = self.protocol["pilot_final_disjointness"]
        self.assertEqual(
            disjoint["namespace_id"],
            "D3_DOCDB_SIMPLE_PATENT_FAMILY_ID_V1",
        )
        self.assertTrue(disjoint["identity_namespace_attestation_required"])
        self.assertFalse(
            disjoint["family_resolution_truth_established_by_software"]
        )
        self.assertTrue(disjoint["overlap_blocks_final_selection"])
        self.assertFalse(disjoint["public_zero_knowledge_proof_claimed"])

    def test_probability_and_rights_boundaries_remain_fail_closed(self) -> None:
        probability = self.protocol["probability_audit_boundary"]
        self.assertFalse(probability["implemented_by_this_protocol"])
        self.assertFalse(probability["roman_second_stage_estimator_certified"])
        self.assertFalse(probability["roman_reported_population_total_validated"])
        self.assertFalse(probability["roman_reported_query_recall_validated"])
        self.assertFalse(probability["challenge_counts_create_population_inference"])

        rights = self.protocol["rights_boundary"]
        self.assertEqual(rights["patstat_rights_issue"], 210)
        self.assertFalse(rights["patstat_rights_clearance"])
        self.assertTrue(rights["patstat_controlled_evidence_remains_s3"])

    def test_current_evidence_and_authority_are_non_authorizing(self) -> None:
        evidence = self.protocol["current_evidence_state"]
        for key, value in evidence.items():
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
