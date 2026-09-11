from __future__ import annotations

import copy
import hashlib
import json
import unittest
from typing import Any

from scripts.validate_pre_g2_d3_patent_review_packet_semantics import (
    D3PatentReviewPacketSemanticError,
    validate_packet_semantics,
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _binding() -> dict[str, Any]:
    return {
        "controlled_family_ref": "S3-FAMILY-0001",
        "unit_of_observation": "DOCDB_SIMPLE_PATENT_FAMILY",
        "family_identity_state": "RESOLVED",
        "publication_identity_refs": ["E-PUB"],
        "family_years": [2020, 2022],
        "jurisdictions": ["US", "EP"],
        "source_languages": ["en", "fr"],
        "text_availability": "SHORT_ABSTRACT",
        "observed_at": "2026-09-10T10:00:00Z",
        "identity_basis_refs": ["E-PUB"],
    }


def _evidence_packet() -> dict[str, Any]:
    return {
        "evidence_refs": [
            {
                "evidence_id": "E-PUB",
                "source_class": "EPO_OPS_BIBLIOGRAPHIC",
                "observed_at": "2026-09-10T09:00:00Z",
                "content_sha256": "a" * 64,
                "claim_scopes": [
                    "FAMILY_IDENTITY",
                    "PUBLICATION_IDENTITY",
                    "JURISDICTION",
                    "TEMPORAL",
                ],
                "source_identity_ref": "EPO-OPS",
                "source_language": "en",
                "review_language": "en",
                "translation_status": "SOURCE_LANGUAGE_REVIEWED",
                "translation_provenance_ref": None,
                "custody": "PUBLIC_REPRODUCIBLE",
                "rights_state": "PUBLIC_SOURCE_TERMS_APPLY",
            },
            {
                "evidence_id": "E-FR",
                "source_class": "PATENT_OFFICE_PUBLIC",
                "observed_at": "2026-09-10T09:05:00Z",
                "content_sha256": "b" * 64,
                "claim_scopes": [
                    "PATENT_TEXT",
                    "CAPABILITY_CONTEXT",
                    "NEGATIVE_CONTROL_CONTEXT",
                ],
                "source_identity_ref": "SYNTHETIC-PATENT-OFFICE",
                "source_language": "fr",
                "review_language": "en",
                "translation_status": "TRANSLATED_FOR_REVIEW",
                "translation_provenance_ref": "S3-TRANSLATION-0001",
                "custody": "PUBLIC_REPRODUCIBLE",
                "rights_state": "PUBLIC_SOURCE_TERMS_APPLY",
            },
            {
                "evidence_id": "E-PATSTAT",
                "source_class": "PATSTAT_CONTROLLED",
                "observed_at": "2026-09-10T09:10:00Z",
                "content_sha256": "c" * 64,
                "claim_scopes": ["PATENT_TEXT"],
                "source_identity_ref": "PATSTAT-AUTUMN-2025",
                "source_language": "en",
                "review_language": "en",
                "translation_status": "SOURCE_LANGUAGE_REVIEWED",
                "translation_provenance_ref": None,
                "custody": "S3_CONTROLLED",
                "rights_state": "S3_LICENSED_RIGHTS_UNRESOLVED",
            },
        ],
        "observation_cutoff": "2026-09-10T12:00:00Z",
        "historical_machine_labels_included": False,
        "population_weights_included": False,
    }


def _annotations() -> list[dict[str, Any]]:
    return [
        {
            "stratum": "GRAY_CAPABILITY",
            "human_confirmed": True,
            "rationale": "Synthetic gray-capability construct annotation.",
            "evidence_refs": ["E-FR"],
        },
        {
            "stratum": "MISSING_OR_SHORT_ABSTRACT",
            "human_confirmed": True,
            "rationale": "Synthetic short-abstract construct annotation.",
            "evidence_refs": ["E-PATSTAT"],
        },
        {
            "stratum": "MULTI_JURISDICTION",
            "human_confirmed": True,
            "rationale": "Synthetic multi-jurisdiction construct annotation.",
            "evidence_refs": ["E-PUB"],
        },
        {
            "stratum": "MULTI_YEAR",
            "human_confirmed": True,
            "rationale": "Synthetic multi-year construct annotation.",
            "evidence_refs": ["E-PUB"],
        },
        {
            "stratum": "MULTILINGUAL",
            "human_confirmed": True,
            "rationale": "Synthetic multilingual construct annotation.",
            "evidence_refs": ["E-FR"],
        },
        {
            "stratum": "SEMANTICALLY_DECEPTIVE_NEGATIVE",
            "human_confirmed": True,
            "rationale": "Synthetic deceptive-negative construct annotation.",
            "evidence_refs": ["E-FR"],
        },
    ]


def _packet(
    *,
    candidate_role: str = "HELD_OUT_CANDIDATE",
    state: str = "AGREE",
    primary: str = "INCLUDE",
    secondary: str = "INCLUDE",
    final: str | None = "INCLUDE",
    held_out_eligible: bool = True,
) -> dict[str, Any]:
    binding = _binding()
    evidence = _evidence_packet()
    evidence_digest = _canonical_sha256(evidence)
    reviewers: list[dict[str, Any]] = [
        {
            "reviewer_ref": "S3-REVIEWER-PRIMARY",
            "evidence_packet_sha256": evidence_digest,
            "decision": primary,
            "rationale": "Synthetic primary rationale.",
            "adjudicator_role": "PRIMARY_REVIEWER",
            "timestamp": "2026-09-10T13:00:00Z",
            "exact_patent_binding": copy.deepcopy(binding),
        },
        {
            "reviewer_ref": "S3-REVIEWER-SECONDARY",
            "evidence_packet_sha256": evidence_digest,
            "decision": secondary,
            "rationale": "Synthetic secondary rationale.",
            "adjudicator_role": "SECONDARY_REVIEWER",
            "timestamp": "2026-09-10T13:05:00Z",
            "exact_patent_binding": copy.deepcopy(binding),
        },
    ]
    final_rationale: str | None
    if state == "ADJUDICATED":
        final_rationale = "Synthetic final adjudication rationale."
        reviewers.append(
            {
                "reviewer_ref": "S3-REVIEWER-FINAL",
                "evidence_packet_sha256": evidence_digest,
                "decision": final,
                "rationale": final_rationale,
                "adjudicator_role": "FINAL_ADJUDICATOR",
                "timestamp": "2026-09-10T14:00:00Z",
                "exact_patent_binding": copy.deepcopy(binding),
            }
        )
    elif state == "DISAGREE_UNADJUDICATED":
        final = None
        final_rationale = None
    else:
        final_rationale = "Synthetic agreed final rationale."

    return {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PATENT_V0_1",
        "benchmark_kind": "PATENT",
        "evidence_role": "CHALLENGE_CONSTRUCT_COVERAGE",
        "candidate_role": candidate_role,
        "exact_patent_binding": binding,
        "evidence_packet": evidence,
        "construct_annotations": _annotations(),
        "review_design": {
            "double_label_required": True,
            "model_output_blinding_state": "BLINDED_TO_MODEL_OUTPUT",
            "blinding_exception_rationale": None,
        },
        "reviewer_records": reviewers,
        "adjudication": {
            "state": state,
            "final_disposition": final,
            "final_rationale": final_rationale,
        },
        "exposure_control": {
            "exposure_status": "NO_KNOWN_EXPOSURE_REVIEWED",
            "exposure_register_ref": "S3-EXPOSURE-REGISTER",
            "held_out_eligible": held_out_eligible,
        },
        "sampling_provenance": {
            "baseline_a_used_for_candidate_discovery": True,
            "historical_machine_labels_visible_to_reviewers": False,
            "query_pool_provenance": "IN_QUERY_POOL",
            "population_weight": None,
            "inclusion_probability": None,
        },
        "rights_containment": {
            "packet_custody": "S3_CONTROLLED",
            "patstat_rights_issue": 210,
            "patstat_rights_clearance": False,
            "redistribution_authority_claimed": False,
        },
        "authority": {
            "g2_passed": False,
            "benchmark_adequacy_established": False,
            "population_generalization_authority": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "assessment_effect": "NONE",
        },
    }


def _refresh_digest(packet: dict[str, Any]) -> None:
    digest = _canonical_sha256(packet["evidence_packet"])
    for record in packet["reviewer_records"]:
        record["evidence_packet_sha256"] = digest


class D3PatentReviewPacketSemanticTests(unittest.TestCase):
    def test_valid_challenge_packet(self) -> None:
        validate_packet_semantics(_packet())

    def test_valid_adjudicated_disagreement(self) -> None:
        packet = _packet(
            state="ADJUDICATED",
            primary="INCLUDE",
            secondary="BORDERLINE",
            final="BORDERLINE",
        )
        validate_packet_semantics(packet)

    def test_valid_unresolved_disagreement_is_not_held_out_eligible(self) -> None:
        packet = _packet(
            state="DISAGREE_UNADJUDICATED",
            primary="INCLUDE",
            secondary="BORDERLINE",
            final=None,
            held_out_eligible=False,
        )
        validate_packet_semantics(packet)

    def test_patstat_evidence_must_remain_s3_rights_unresolved(self) -> None:
        for field, value in (
            ("custody", "PUBLIC_REPRODUCIBLE"),
            ("rights_state", "PUBLIC_SOURCE_TERMS_APPLY"),
        ):
            with self.subTest(field=field):
                packet = _packet()
                patstat = packet["evidence_packet"]["evidence_refs"][2]
                patstat[field] = value
                _refresh_digest(packet)
                with self.assertRaises(D3PatentReviewPacketSemanticError):
                    validate_packet_semantics(packet)

    def test_forbidden_model_fields_are_rejected_recursively(self) -> None:
        for field in ("model_score", "historical_machine_label", "probability_include", "prompt"):
            with self.subTest(field=field):
                packet = _packet()
                packet["construct_annotations"][0][field] = "forbidden"
                with self.assertRaises(D3PatentReviewPacketSemanticError):
                    validate_packet_semantics(packet)

    def test_historical_labels_and_population_weights_fail_closed(self) -> None:
        mutations = (
            ("historical_machine_labels_included", True),
            ("population_weights_included", True),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                packet = _packet()
                packet["evidence_packet"][field] = value
                _refresh_digest(packet)
                with self.assertRaises(D3PatentReviewPacketSemanticError):
                    validate_packet_semantics(packet)

        packet = _packet()
        packet["sampling_provenance"]["population_weight"] = 2.0
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["sampling_provenance"]["inclusion_probability"] = 0.25
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_identity_and_publication_refs_must_resolve_inside_packet(self) -> None:
        packet = _packet()
        packet["exact_patent_binding"]["identity_basis_refs"] = ["MISSING"]
        for record in packet["reviewer_records"]:
            record["exact_patent_binding"] = copy.deepcopy(packet["exact_patent_binding"])
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["evidence_packet"]["evidence_refs"][0]["claim_scopes"].remove("PUBLICATION_IDENTITY")
        _refresh_digest(packet)
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_evidence_and_object_times_cannot_exceed_cutoff(self) -> None:
        packet = _packet()
        packet["evidence_packet"]["evidence_refs"][0]["observed_at"] = "2026-09-10T12:01:00Z"
        _refresh_digest(packet)
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["exact_patent_binding"]["observed_at"] = "2026-09-10T12:01:00Z"
        for record in packet["reviewer_records"]:
            record["exact_patent_binding"] = copy.deepcopy(packet["exact_patent_binding"])
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_translation_semantics_are_fail_closed(self) -> None:
        packet = _packet()
        translated = packet["evidence_packet"]["evidence_refs"][1]
        translated["review_language"] = "fr"
        _refresh_digest(packet)
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        translated = packet["evidence_packet"]["evidence_refs"][1]
        translated["translation_provenance_ref"] = None
        _refresh_digest(packet)
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_mechanical_construct_invariants(self) -> None:
        mutations = (
            ("MULTI_YEAR", lambda p: p["exact_patent_binding"].update({"family_years": [2020]})),
            (
                "MULTI_JURISDICTION",
                lambda p: p["exact_patent_binding"].update({"jurisdictions": ["US"]}),
            ),
            (
                "MISSING_OR_SHORT_ABSTRACT",
                lambda p: p["exact_patent_binding"].update({"text_availability": "ENGLISH_ABSTRACT"}),
            ),
        )
        for stratum, mutate in mutations:
            with self.subTest(stratum=stratum):
                packet = _packet()
                mutate(packet)
                for record in packet["reviewer_records"]:
                    record["exact_patent_binding"] = copy.deepcopy(packet["exact_patent_binding"])
                with self.assertRaises(D3PatentReviewPacketSemanticError):
                    validate_packet_semantics(packet)

        packet = _packet()
        packet["exact_patent_binding"]["source_languages"] = ["en"]
        for record in packet["reviewer_records"]:
            record["exact_patent_binding"] = copy.deepcopy(packet["exact_patent_binding"])
        translated = packet["evidence_packet"]["evidence_refs"][1]
        translated["source_language"] = "en"
        translated["review_language"] = "en"
        translated["translation_status"] = "SOURCE_LANGUAGE_REVIEWED"
        translated["translation_provenance_ref"] = None
        _refresh_digest(packet)
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_construct_annotations_require_human_confirmation_and_bound_evidence(self) -> None:
        packet = _packet()
        packet["construct_annotations"][0]["human_confirmed"] = False
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["construct_annotations"][0]["evidence_refs"] = ["MISSING"]
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["construct_annotations"].append(copy.deepcopy(packet["construct_annotations"][0]))
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_held_out_requires_independent_double_review(self) -> None:
        packet = _packet()
        packet["review_design"]["double_label_required"] = False
        packet["reviewer_records"] = packet["reviewer_records"][:1]
        packet["adjudication"] = {
            "state": "AGREE",
            "final_disposition": "INCLUDE",
            "final_rationale": "Synthetic agreed final rationale.",
        }
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_reviewer_evidence_digest_and_exact_binding_are_enforced(self) -> None:
        packet = _packet()
        packet["reviewer_records"][0]["evidence_packet_sha256"] = "0" * 64
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["reviewer_records"][0]["exact_patent_binding"]["controlled_family_ref"] = "OTHER"
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_reviewer_refs_and_roles_must_be_distinct(self) -> None:
        packet = _packet()
        packet["reviewer_records"][1]["reviewer_ref"] = packet["reviewer_records"][0]["reviewer_ref"]
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["reviewer_records"][1]["adjudicator_role"] = "PRIMARY_REVIEWER"
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_agree_and_adjudicated_states_are_consistent(self) -> None:
        packet = _packet()
        packet["reviewer_records"][1]["decision"] = "BORDERLINE"
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet(
            state="ADJUDICATED",
            primary="INCLUDE",
            secondary="BORDERLINE",
            final="BORDERLINE",
        )
        packet["reviewer_records"][2]["timestamp"] = "2026-09-10T13:00:00Z"
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_unresolved_disagreement_cannot_be_held_out_eligible(self) -> None:
        packet = _packet(
            state="DISAGREE_UNADJUDICATED",
            primary="INCLUDE",
            secondary="BORDERLINE",
            final=None,
            held_out_eligible=True,
        )
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_pilot_and_ambiguous_identity_cannot_be_held_out_eligible(self) -> None:
        packet = _packet(candidate_role="PILOT_DEVELOPMENT", held_out_eligible=True)
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["exact_patent_binding"]["family_identity_state"] = "AMBIGUOUS_REVIEW_REQUIRED"
        for record in packet["reviewer_records"]:
            record["exact_patent_binding"] = copy.deepcopy(packet["exact_patent_binding"])
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

    def test_rights_and_authority_escalation_fail_closed(self) -> None:
        packet = _packet()
        packet["rights_containment"]["patstat_rights_clearance"] = True
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        packet = _packet()
        packet["rights_containment"]["redistribution_authority_claimed"] = True
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)

        for field in (
            "g2_passed",
            "benchmark_adequacy_established",
            "population_generalization_authority",
            "canonical_s2_authority",
            "publication_authority",
        ):
            with self.subTest(field=field):
                packet = _packet()
                packet["authority"][field] = True
                with self.assertRaises(D3PatentReviewPacketSemanticError):
                    validate_packet_semantics(packet)

    def test_exact_top_level_shape_rejects_smuggled_fields(self) -> None:
        packet = _packet()
        packet["population_estimate"] = 123
        with self.assertRaises(D3PatentReviewPacketSemanticError):
            validate_packet_semantics(packet)


if __name__ == "__main__":
    unittest.main()
