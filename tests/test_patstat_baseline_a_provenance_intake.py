from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.validate_patstat_baseline_a_provenance_intake import (
    PatstatProvenanceIntakeError,
    validate_intake_status,
)

REQUIREMENTS_PATH = Path(
    "curation/PATSTAT_BASELINE_A_PROVENANCE_INTAKE_REQUIREMENTS_2026-09-12_v0.1.json"
)
STATUS_PATH = Path(
    "curation/PATSTAT_BASELINE_A_PROVENANCE_INTAKE_STATUS_2026-09-12_v0.1.json"
)


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _fully_provided(
    status: dict[str, object],
    requirements: dict[str, object],
) -> dict[str, object]:
    result = copy.deepcopy(status)
    result["response_binding"] = {
        "state": "RESPONSE_RECEIVED",
        "controlled_response_sha256": "a" * 64,
        "received_at": "2026-09-12T00:00:00Z",
        "source_ref": "S3-ROMAN-PROVENANCE-RESPONSE-001",
    }
    for index, component_id in enumerate(
        requirements["component_requirements"]
    ):
        component = result["components"][component_id]
        component["state"] = "PROVIDED_UNVERIFIED"
        component["evidence_manifest_sha256"] = (
            f"{index + 1:x}" * 64
        )
        component["independent_verification_sha256"] = None
        for field in component["required_evidence"]:
            component["required_evidence"][field] = True
    result["declared_readiness"] = "READY_FOR_SCIENTIFIC_AUDIT"
    return result


class PatstatBaselineAProvenanceIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.requirements = _load(REQUIREMENTS_PATH)
        cls.status = _load(STATUS_PATH)

    def test_current_status_is_waiting_and_non_authorizing(self) -> None:
        result = validate_intake_status(
            copy.deepcopy(self.status),
            requirements=self.requirements,
        )
        self.assertEqual(
            result["readiness"],
            "WAITING_FOR_PROVENANCE",
        )
        self.assertFalse(result["ready_for_scientific_audit"])
        self.assertEqual(
            result["mandatory_component_count"],
            6,
        )
        self.assertEqual(
            len(result["missing_components"]),
            6,
        )
        self.assertFalse(result["scientific_validity_established"])
        self.assertFalse(result["roman_49671_validated"])
        self.assertFalse(
            result["roman_67_percent_retrieval_recall_validated"]
        )
        self.assertFalse(result["rights_clearance"])
        self.assertFalse(result["g2_passed"])
        self.assertFalse(result["g5_passed"])
        self.assertEqual(result["assessment_effect"], "NONE")

    def test_complete_supplied_provenance_means_ready_to_audit_only(self) -> None:
        status = _fully_provided(
            self.status,
            self.requirements,
        )
        result = validate_intake_status(
            status,
            requirements=self.requirements,
        )
        self.assertEqual(
            result["readiness"],
            "READY_FOR_SCIENTIFIC_AUDIT",
        )
        self.assertTrue(result["ready_for_scientific_audit"])
        self.assertEqual(result["missing_components"], [])
        self.assertEqual(
            result["verified_reconstructible_component_count"],
            0,
        )
        self.assertFalse(result["scientific_validity_established"])
        self.assertFalse(result["roman_49671_validated"])
        self.assertFalse(
            result["roman_67_percent_retrieval_recall_validated"]
        )

    def test_missing_second_stage_inclusion_probability_evidence_blocks_readiness(self) -> None:
        status = _fully_provided(
            self.status,
            self.requirements,
        )
        component = status["components"]["SECOND_STAGE_333_DESIGN"]
        component["state"] = "MISSING"
        component["required_evidence"][
            "inclusion_probability_manifest_bound"
        ] = False
        component["evidence_manifest_sha256"] = None
        status["declared_readiness"] = "WAITING_FOR_PROVENANCE"

        result = validate_intake_status(
            status,
            requirements=self.requirements,
        )
        self.assertFalse(result["ready_for_scientific_audit"])
        self.assertEqual(
            result["missing_components"],
            ["SECOND_STAGE_333_DESIGN"],
        )

    def test_missing_estimator_or_uncertainty_evidence_blocks_component(self) -> None:
        for field in (
            "full_estimator_implementation_bound",
            "second_stage_uncertainty_method_bound",
            "retrieval_recall_ratio_uncertainty_method_bound",
        ):
            with self.subTest(field=field):
                status = _fully_provided(
                    self.status,
                    self.requirements,
                )
                component = status["components"][
                    "ESTIMATOR_AND_UNCERTAINTY"
                ]
                component["required_evidence"][field] = False
                with self.assertRaises(
                    PatstatProvenanceIntakeError
                ):
                    validate_intake_status(
                        status,
                        requirements=self.requirements,
                    )

    def test_missing_judge_model_human_provenance_fails_closed(self) -> None:
        status = _fully_provided(
            self.status,
            self.requirements,
        )
        component = status["components"][
            "HISTORICAL_JUDGES_AND_RUBRIC"
        ]
        component["required_evidence"][
            "historical_labels_confirmed_machine_generated"
        ] = False
        with self.assertRaises(PatstatProvenanceIntakeError):
            validate_intake_status(
                status,
                requirements=self.requirements,
            )

    def test_missing_seed_or_query_definition_fails_closed(self) -> None:
        mutations = (
            (
                "FIRST_STAGE_PROBABILITY_DESIGN",
                "seed_randomization_procedure_bound",
            ),
            (
                "SECOND_STAGE_333_DESIGN",
                "seed_randomization_procedure_bound",
            ),
            (
                "RETRIEVAL_POOL_CONSTRUCTION",
                "exact_query_definitions_bound",
            ),
        )
        for component_id, field in mutations:
            with self.subTest(component=component_id, field=field):
                status = _fully_provided(
                    self.status,
                    self.requirements,
                )
                status["components"][component_id][
                    "required_evidence"
                ][field] = False
                with self.assertRaises(
                    PatstatProvenanceIntakeError
                ):
                    validate_intake_status(
                        status,
                        requirements=self.requirements,
                    )

    def test_verified_state_requires_independent_verification_digest(self) -> None:
        status = _fully_provided(
            self.status,
            self.requirements,
        )
        component = status["components"][
            "SECOND_STAGE_333_DESIGN"
        ]
        component["state"] = "VERIFIED_RECONSTRUCTIBLE"
        with self.assertRaises(PatstatProvenanceIntakeError):
            validate_intake_status(
                status,
                requirements=self.requirements,
            )

        component["independent_verification_sha256"] = "f" * 64
        result = validate_intake_status(
            status,
            requirements=self.requirements,
        )
        self.assertEqual(
            result["verified_reconstructible_component_count"],
            1,
        )
        self.assertFalse(result["scientific_validity_established"])

    def test_awaiting_response_cannot_hide_supplied_component(self) -> None:
        status = copy.deepcopy(self.status)
        component = status["components"][
            "EXPORT_CLARIFICATION"
        ]
        component["state"] = "PROVIDED_UNVERIFIED"
        component["evidence_manifest_sha256"] = "1" * 64
        for field in component["required_evidence"]:
            component["required_evidence"][field] = True
        with self.assertRaises(PatstatProvenanceIntakeError):
            validate_intake_status(
                status,
                requirements=self.requirements,
            )

    def test_ready_declaration_cannot_hide_missing_component(self) -> None:
        status = copy.deepcopy(self.status)
        status["declared_readiness"] = "READY_FOR_SCIENTIFIC_AUDIT"
        with self.assertRaises(PatstatProvenanceIntakeError):
            validate_intake_status(
                status,
                requirements=self.requirements,
            )

    def test_human_gold_global_claim_and_authority_escalation_fail_closed(self) -> None:
        mutations = [
            (
                "fixed_scientific_boundaries",
                "historical_labels_authority",
                "HUMAN_GOLD",
            ),
            (
                "fixed_scientific_boundaries",
                "global_population_claim_allowed",
                True,
            ),
            (
                "fixed_scientific_boundaries",
                "roman_49671_validated",
                True,
            ),
            (
                "rights_boundary",
                "rights_clearance",
                True,
            ),
            (
                "authority",
                "g5_passed",
                True,
            ),
            (
                "authority",
                "publication_authority",
                True,
            ),
        ]
        for section, field, value in mutations:
            with self.subTest(section=section, field=field):
                status = copy.deepcopy(self.status)
                status[section][field] = value
                with self.assertRaises(
                    PatstatProvenanceIntakeError
                ):
                    validate_intake_status(
                        status,
                        requirements=self.requirements,
                    )

    def test_requirements_component_shape_is_exact(self) -> None:
        status = copy.deepcopy(self.status)
        status["components"][
            "SECOND_STAGE_333_DESIGN"
        ]["required_evidence"]["invented_field"] = False
        with self.assertRaises(PatstatProvenanceIntakeError):
            validate_intake_status(
                status,
                requirements=self.requirements,
            )


if __name__ == "__main__":
    unittest.main()
