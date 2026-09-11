from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

PROTOCOL_PATH = Path(
    "curation/PRE_G2_D4_CALIBRATION_SELECTION_COMPOSITION_2026-09-12_v0.1.json"
)
DISPOSITION_SCHEMA_PATH = Path(
    "schemas/pre-g2-d4-human-calibration-disposition-v0.1.schema.json"
)
ENVELOPE_SCHEMA_PATH = Path(
    "schemas/pre-g2-d4-final-selection-authorization-envelope-v0.1.schema.json"
)


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


class D4CalibrationSelectionProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(
            PROTOCOL_PATH.read_text(encoding="utf-8")
        )
        cls.disposition_schema = json.loads(
            DISPOSITION_SCHEMA_PATH.read_text(encoding="utf-8")
        )
        cls.envelope_schema = json.loads(
            ENVELOPE_SCHEMA_PATH.read_text(encoding="utf-8")
        )

    def test_identity_and_parent_main_binding(self) -> None:
        self.assertEqual(
            self.protocol["control_id"],
            "PRE_G2_D4_CALIBRATION_SELECTION_COMPOSITION_2026-09-12_v0.1",
        )
        self.assertEqual(self.protocol["governing_issue"], 240)
        self.assertEqual(self.protocol["umbrella_d4_issue"], 223)
        self.assertEqual(
            self.protocol["parent_main_binding"]["main_commit_sha"],
            "5c8c24f5f2a2af610c8a75cba8ce7b627b732c24",
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

    def test_audit_finding_preserves_historical_artifacts(self) -> None:
        finding = self.protocol["audit_finding"]
        self.assertFalse(
            finding[
                "historical_candidate_pool_schema_binds_human_calibration_disposition"
            ]
        )
        self.assertFalse(
            finding[
                "historical_lower_selector_validates_human_calibration_disposition"
            ]
        )
        self.assertFalse(
            finding["historical_lower_selector_requires_approve_decision"]
        )
        self.assertFalse(
            finding[
                "historical_lower_selector_requires_pilot_final_disjointness_before_selection"
            ]
        )
        self.assertFalse(
            finding["historical_artifact_rewrite_authorized"]
        )
        self.assertTrue(
            finding["append_only_authorization_envelope_required"]
        )
        self.assertEqual(
            finding["required_real_execution_path"],
            "D4_FINAL_SELECTION_COMPOSED_V0_1",
        )
        self.assertEqual(
            finding["lower_selector_status_after_successor"],
            "VALID_DETERMINISTIC_PRIMITIVE_NOT_SUFFICIENT_ALONE_FOR_REAL_FINAL_SELECTION",
        )

    def test_human_disposition_is_local_and_non_authorizing(self) -> None:
        contract = self.protocol["human_calibration_disposition_contract"]
        self.assertEqual(
            contract["decision_domain"],
            ["APPROVE", "REVISE", "REJECT"],
        )
        self.assertTrue(contract["only_approve_unlocks_selection"])
        self.assertEqual(
            contract["approval_scope"],
            "FINAL_D4_CHALLENGE_SELECTION_ONLY",
        )
        self.assertTrue(contract["quantitative_gate_pass_required"])
        self.assertTrue(contract["binds_canonical_pilot_manifest_sha256"])
        self.assertTrue(
            contract["binds_canonical_readiness_aggregate_sha256"]
        )
        self.assertTrue(
            contract["binds_canonical_readiness_result_sha256"]
        )
        self.assertFalse(
            contract["reviewer_competence_established_by_approval"]
        )
        self.assertFalse(
            contract["benchmark_adequacy_established_by_approval"]
        )
        self.assertFalse(
            contract["governance_identity_established_by_software"]
        )

    def test_authorization_envelope_is_only_a_composition_binding(self) -> None:
        contract = self.protocol[
            "selection_authorization_envelope_contract"
        ]
        self.assertEqual(
            contract["scope"],
            "FINAL_D4_CHALLENGE_SELECTION_ONLY",
        )
        self.assertTrue(
            contract["binds_exact_approved_disposition_sha256"]
        )
        self.assertTrue(
            contract["binds_exact_candidate_pool_commitment"]
        )
        self.assertTrue(
            contract["binds_exact_identity_namespace_attestation_sha256"]
        )
        self.assertFalse(
            contract["independent_human_authority_created"]
        )
        self.assertFalse(
            contract["s3_custody_established_by_schema"]
        )

    def test_schema_authority_fields_are_fail_closed(self) -> None:
        disposition_props = self.disposition_schema["properties"]
        self.assertEqual(
            disposition_props["approval_scope"]["const"],
            "FINAL_D4_CHALLENGE_SELECTION_ONLY",
        )
        self.assertTrue(
            disposition_props["quantitative_gate_passed"]["const"]
        )
        disposition_authority = disposition_props[
            "authority"
        ]["$ref"]
        self.assertEqual(disposition_authority, "#/$defs/authority")
        for key, spec in self.disposition_schema["$defs"][
            "authority"
        ]["properties"].items():
            if key == "assessment_effect":
                self.assertEqual(spec["const"], "NONE")
            else:
                self.assertFalse(spec["const"], key)

        envelope_props = self.envelope_schema["properties"]
        self.assertEqual(
            envelope_props["scope"]["const"],
            "FINAL_D4_CHALLENGE_SELECTION_ONLY",
        )
        self.assertEqual(
            envelope_props["state"]["const"],
            "CONTROLLED_COMPOSITION_BINDING_RECORDED",
        )
        for key, spec in self.envelope_schema["$defs"][
            "authority"
        ]["properties"].items():
            if key == "assessment_effect":
                self.assertEqual(spec["const"], "NONE")
            else:
                self.assertFalse(spec["const"], key)

    def test_composed_execution_orders_approval_and_disjointness_before_selection(self) -> None:
        execution = self.protocol["composed_execution_contract"]
        sequence = execution["sequence"]
        select_index = sequence.index(
            "EXECUTE_EXISTING_DETERMINISTIC_SELECTION_SEMANTICS"
        )
        self.assertLess(
            sequence.index("REQUIRE_HUMAN_DECISION_APPROVE"),
            select_index,
        )
        self.assertLess(
            sequence.index("VALIDATE_SELECTION_AUTHORIZATION_ENVELOPE"),
            select_index,
        )
        self.assertLess(
            sequence.index("REQUIRE_ZERO_OVERLAP"),
            select_index,
        )
        self.assertTrue(execution["candidate_pool_hmac_reverified"])
        self.assertTrue(execution["pilot_membership_hmac_reverified"])
        self.assertTrue(
            execution["identity_namespace_attestation_reverified"]
        )
        self.assertTrue(
            execution["valid_success_preserves_lower_level_selection_semantics"]
        )
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
            execution[
                "controlled_outputs_may_be_inside_pilot_packet_root"
            ]
        )

    def test_existing_quantitative_gate_is_preserved_not_silently_changed(self) -> None:
        thresholds = self.protocol[
            "governed_pilot_thresholds_preserved"
        ]
        self.assertFalse(
            thresholds[
                "this_successor_changes_quantitative_gate_semantics"
            ]
        )
        self.assertEqual(
            thresholds[
                "minimum_primary_secondary_exact_four_way_agreement_count"
            ],
            48,
        )
        self.assertEqual(
            thresholds["maximum_unresolved_disagreement_count"],
            3,
        )
        self.assertEqual(thresholds["minimum_resolved_include"], 10)
        self.assertEqual(thresholds["minimum_resolved_exclude"], 10)
        self.assertEqual(
            thresholds["minimum_resolved_borderline"],
            10,
        )
        self.assertFalse(
            thresholds[
                "scientific_appropriateness_of_raw_agreement_gate_reopened_here"
            ]
        )

    def test_statistical_and_authority_boundaries_remain_fail_closed(self) -> None:
        statistical = self.protocol["statistical_boundary"]
        self.assertEqual(
            statistical["evidence_role"],
            "CHALLENGE_CONSTRUCT_COVERAGE",
        )
        self.assertFalse(statistical["population_generalizable"])
        self.assertFalse(
            statistical["population_prevalence_claim_created"]
        )
        self.assertFalse(
            statistical["population_recall_claim_created"]
        )
        self.assertFalse(statistical["market_share_claim_created"])
        self.assertFalse(
            statistical["global_completeness_claim_created"]
        )

        for key, value in self.protocol["current_evidence_state"].items():
            with self.subTest(evidence=key):
                self.assertFalse(value)

        authority = self.protocol["authority"]
        self.assertTrue(authority["g1_approved"])
        for key in (
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "rights_clearance",
            "reviewer_competence_established",
            "identity_resolution_truth_established",
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
