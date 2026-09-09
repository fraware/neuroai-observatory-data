from __future__ import annotations

import copy
import unittest

from scripts.evaluate_pre_g2_d4_pilot_readiness import (
    D4PilotReadinessError,
    NOT_READY_STATE,
    READY_STATE,
    REQUIRED_STRATA,
    evaluate_pilot_readiness,
)
from scripts.select_pre_g2_d4_held_out import (
    D4SelectionError,
    candidate_pool_commitment,
    select_candidates,
)

COMMITMENT_KEY = b"synthetic-test-key-never-used-for-real-d4"
LANGUAGES = ("fr", "de", "es", "zh", "ja", "ko")
JURISDICTIONS = ("US", "FR", "DE", "JP", "KR", "CN")


def _authority() -> dict[str, object]:
    return {
        "reviewer_competence_established": False,
        "benchmark_adequacy_established": False,
        "g2_passed": False,
        "canonical_s2_authority": False,
        "publication_authority": False,
        "assessment_effect": "NONE",
    }


def _pilot_report() -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PRODUCT_V0_1",
        "protocol_id": "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1",
        "pilot_round_id": "SYNTHETIC-PILOT-001",
        "state": "COMPLETE_ROUND_NO_EXTENSION",
        "total_items": 60,
        "double_labeled_items": 60,
        "primary_secondary_exact_agreement_count": 48,
        "adjudicated_disagreement_count": 9,
        "unresolved_disagreement_count": 3,
        "resolved_disposition_counts": {
            "ABSTAIN": 0,
            "BORDERLINE": 19,
            "EXCLUDE": 19,
            "INCLUDE": 19,
        },
        "required_stratum_counts": {stratum: 6 for stratum in REQUIRED_STRATA},
        "per_stratum_disagreement_counts": {stratum: 1 for stratum in REQUIRED_STRATA},
        "semantic_validation_failure_count": 0,
        "reviewer_reference_collision_count": 0,
        "evidence_binding_failure_count": 0,
        "blinding_exception_count": 2,
        "blinding_exception_with_rationale_count": 2,
        "pilot_items_held_out_eligible_count": 0,
        "pilot_membership_commitment": "1" * 64,
        "reviewer_training_record_sha256": "2" * 64,
        "exposure_register_sha256": "3" * 64,
        "pilot_disjointness_proof_sha256": "4" * 64,
        "authority": _authority(),
    }


def _candidate(index: int) -> dict[str, object]:
    return {
        "candidate_id": f"SYNTHETIC-CANDIDATE-{index:04d}",
        "construct_strata": [REQUIRED_STRATA[index % len(REQUIRED_STRATA)]],
        "source_languages": [LANGUAGES[index % len(LANGUAGES)]],
        "jurisdictions": [JURISDICTIONS[index % len(JURISDICTIONS)]],
        "exact_object_identity_resolved": True,
        "exposure_status": "NO_KNOWN_EXPOSURE_REVIEWED",
        "semantic_validation_passed": True,
        "human_confirmed_construct_tags": True,
        "pilot_or_development_exposed": False,
    }


def _candidate_pool(size: int = 300) -> dict[str, object]:
    pool: dict[str, object] = {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PRODUCT_V0_1",
        "protocol_id": "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1",
        "candidate_pool_id": "SYNTHETIC-POOL-001",
        "candidate_pool_commitment": "0" * 64,
        "candidate_pool_frozen": True,
        "candidates": [_candidate(index) for index in range(size)],
    }
    pool["candidate_pool_commitment"] = candidate_pool_commitment(pool, COMMITMENT_KEY)
    return pool


def _recommit(pool: dict[str, object]) -> None:
    pool["candidate_pool_commitment"] = candidate_pool_commitment(pool, COMMITMENT_KEY)


class D4PilotReadinessTests(unittest.TestCase):
    def test_exact_threshold_pilot_is_ready_only_for_human_disposition(self) -> None:
        result = evaluate_pilot_readiness(_pilot_report())
        self.assertTrue(result["quantitative_gate_passed"])
        self.assertEqual(result["state"], READY_STATE)
        self.assertTrue(result["human_calibration_disposition_required"])
        self.assertEqual(result["agreement_rate"], 0.8)
        self.assertEqual(result["unresolved_disagreement_rate"], 0.05)
        self.assertFalse(result["authority"]["reviewer_competence_established"])
        self.assertFalse(result["authority"]["g2_passed"])

    def test_agreement_below_threshold_requires_new_disjoint_round(self) -> None:
        report = _pilot_report()
        report["primary_secondary_exact_agreement_count"] = 47
        report["adjudicated_disagreement_count"] = 10
        result = evaluate_pilot_readiness(report)
        self.assertFalse(result["quantitative_gate_passed"])
        self.assertEqual(result["state"], NOT_READY_STATE)
        self.assertIn("PRIMARY_SECONDARY_EXACT_AGREEMENT_BELOW_48_OF_60", result["violations"])

    def test_unresolved_disagreement_above_threshold_fails(self) -> None:
        report = _pilot_report()
        report["adjudicated_disagreement_count"] = 8
        report["unresolved_disagreement_count"] = 4
        report["resolved_disposition_counts"]["BORDERLINE"] = 18
        result = evaluate_pilot_readiness(report)
        self.assertIn("UNRESOLVED_DISAGREEMENT_ABOVE_3_OF_60", result["violations"])

    def test_boundary_disposition_floor_is_enforced_without_coercing_abstain(self) -> None:
        report = _pilot_report()
        report["resolved_disposition_counts"] = {
            "ABSTAIN": 10,
            "BORDERLINE": 9,
            "EXCLUDE": 19,
            "INCLUDE": 19,
        }
        result = evaluate_pilot_readiness(report)
        self.assertIn("RESOLVED_BORDERLINE_BELOW_10", result["violations"])
        self.assertNotIn("RESOLVED_ABSTAIN_BELOW_10", result["violations"])

    def test_each_controlled_stratum_requires_six_pilot_items(self) -> None:
        report = _pilot_report()
        report["required_stratum_counts"]["WORKPLACE"] = 5
        result = evaluate_pilot_readiness(report)
        self.assertIn("STRATUM_WORKPLACE_BELOW_6", result["violations"])

    def test_zero_failure_and_blinding_accounting_are_fail_closed(self) -> None:
        report = _pilot_report()
        report["semantic_validation_failure_count"] = 1
        report["reviewer_reference_collision_count"] = 1
        report["evidence_binding_failure_count"] = 1
        report["blinding_exception_with_rationale_count"] = 1
        report["pilot_items_held_out_eligible_count"] = 1
        result = evaluate_pilot_readiness(report)
        self.assertIn("SEMANTIC_VALIDATION_FAILURE_COUNT_NONZERO", result["violations"])
        self.assertIn("REVIEWER_REFERENCE_COLLISION_COUNT_NONZERO", result["violations"])
        self.assertIn("EVIDENCE_BINDING_FAILURE_COUNT_NONZERO", result["violations"])
        self.assertIn("BLINDING_EXCEPTION_RATIONALE_ACCOUNTING_MISMATCH", result["violations"])
        self.assertIn("PILOT_ITEM_HELD_OUT_ELIGIBILITY_NONZERO", result["violations"])

    def test_accounting_inconsistency_is_invalid_not_a_failed_scientific_round(self) -> None:
        report = _pilot_report()
        report["adjudicated_disagreement_count"] = 8
        with self.assertRaisesRegex(D4PilotReadinessError, "account for all 60"):
            evaluate_pilot_readiness(report)

    def test_authority_escalation_is_rejected(self) -> None:
        report = _pilot_report()
        report["authority"]["reviewer_competence_established"] = True
        with self.assertRaisesRegex(D4PilotReadinessError, "must remain false"):
            evaluate_pilot_readiness(report)


class D4DeterministicSelectionTests(unittest.TestCase):
    def test_valid_pool_selects_exact_240_and_satisfies_all_frozen_quotas(self) -> None:
        controlled, aggregate = select_candidates(_candidate_pool(), COMMITMENT_KEY)
        self.assertEqual(controlled["selected_count"], 240)
        self.assertEqual(len(controlled["selected_candidate_ids"]), 240)
        self.assertEqual(len(set(controlled["selected_candidate_ids"])), 240)
        self.assertTrue(aggregate["quota_satisfaction_established_for_selected_membership"])
        self.assertFalse(aggregate["population_generalizable"])
        self.assertFalse(aggregate["global_pool_feasibility_solver_used"])
        for stratum in REQUIRED_STRATA:
            self.assertGreaterEqual(aggregate["stratum_counts"][stratum], 24)
        self.assertEqual(len(aggregate["non_english_language_targets"]), 6)
        for language in aggregate["non_english_language_targets"]:
            self.assertGreaterEqual(aggregate["non_english_language_counts"][language], 3)
        self.assertEqual(len(aggregate["jurisdiction_targets"]), 6)
        for jurisdiction in aggregate["jurisdiction_targets"]:
            self.assertGreaterEqual(aggregate["jurisdiction_counts"][jurisdiction], 3)
        self.assertFalse(controlled["selection_used_final_human_labels"])
        self.assertFalse(controlled["selection_used_model_outputs_scores_prompts_thresholds_or_final_errors"])
        self.assertEqual(controlled["custody"], "S3_CONTROLLED")
        self.assertFalse(controlled["authority"]["g2_passed"])

    def test_selection_is_deterministic_for_same_committed_pool(self) -> None:
        pool = _candidate_pool()
        first, first_aggregate = select_candidates(pool, COMMITMENT_KEY)
        second, second_aggregate = select_candidates(copy.deepcopy(pool), COMMITMENT_KEY)
        self.assertEqual(first["selected_candidate_ids"], second["selected_candidate_ids"])
        self.assertEqual(first["selected_membership_sha256"], second["selected_membership_sha256"])
        self.assertEqual(first_aggregate, second_aggregate)

    def test_pool_commitment_and_selection_are_input_order_invariant(self) -> None:
        pool = _candidate_pool()
        reversed_pool = copy.deepcopy(pool)
        reversed_pool["candidates"].reverse()
        self.assertEqual(
            candidate_pool_commitment(pool, COMMITMENT_KEY),
            candidate_pool_commitment(reversed_pool, COMMITMENT_KEY),
        )
        reversed_pool["candidate_pool_commitment"] = pool["candidate_pool_commitment"]
        first, _ = select_candidates(pool, COMMITMENT_KEY)
        second, _ = select_candidates(reversed_pool, COMMITMENT_KEY)
        self.assertEqual(first["selected_candidate_ids"], second["selected_candidate_ids"])

    def test_mutation_after_commitment_is_detected(self) -> None:
        pool = _candidate_pool()
        pool["candidates"][0]["jurisdictions"] = ["CA"]
        with self.assertRaisesRegex(D4SelectionError, "does not match the exact frozen"):
            select_candidates(pool, COMMITMENT_KEY)

    def test_wrong_commitment_key_is_rejected(self) -> None:
        pool = _candidate_pool()
        with self.assertRaisesRegex(D4SelectionError, "supplied key"):
            select_candidates(pool, b"wrong-key")

    def test_final_labels_or_model_outputs_are_not_permitted_input_fields(self) -> None:
        for field in ("decision", "prediction", "model_score", "threshold", "final_model_error"):
            pool = _candidate_pool()
            pool["candidates"][0][field] = "FORBIDDEN"
            _recommit(pool)
            with self.assertRaisesRegex(D4SelectionError, "keys mismatch"):
                select_candidates(pool, COMMITMENT_KEY)

    def test_pilot_exposure_or_unresolved_identity_fails_closed(self) -> None:
        pool = _candidate_pool()
        pool["candidates"][0]["pilot_or_development_exposed"] = True
        _recommit(pool)
        with self.assertRaisesRegex(D4SelectionError, "pilot/development exposed"):
            select_candidates(pool, COMMITMENT_KEY)

        pool = _candidate_pool()
        pool["candidates"][0]["exact_object_identity_resolved"] = False
        _recommit(pool)
        with self.assertRaisesRegex(D4SelectionError, "resolved exact-object identity"):
            select_candidates(pool, COMMITMENT_KEY)

    def test_insufficient_construct_support_fails_closed(self) -> None:
        pool = _candidate_pool()
        for candidate in pool["candidates"]:
            if "WORKPLACE" in candidate["construct_strata"]:
                candidate["construct_strata"] = ["CONSUMER"]
        _recommit(pool)
        with self.assertRaisesRegex(D4SelectionError, "STRATUM:WORKPLACE"):
            select_candidates(pool, COMMITMENT_KEY)

    def test_insufficient_non_english_language_diversity_fails_closed(self) -> None:
        pool = _candidate_pool()
        for index, candidate in enumerate(pool["candidates"]):
            candidate["source_languages"] = [LANGUAGES[index % 5]]
        _recommit(pool)
        with self.assertRaisesRegex(D4SelectionError, "fewer than 6 non-English"):
            select_candidates(pool, COMMITMENT_KEY)

    def test_candidate_pool_smaller_than_final_n_is_invalid(self) -> None:
        pool = _candidate_pool(239)
        with self.assertRaisesRegex(D4SelectionError, "at least 240"):
            select_candidates(pool, COMMITMENT_KEY)


if __name__ == "__main__":
    unittest.main()
