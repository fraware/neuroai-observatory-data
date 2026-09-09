from __future__ import annotations

import copy
import hashlib
import json
import unittest

from scripts.validate_pre_g2_d4_review_packet_semantics import (
    D4ReviewPacketSemanticError,
    validate_packet_semantics,
)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _object_binding() -> dict[str, object]:
    return {
        "object_name": "Synthetic neuro product",
        "organization_identity": "Synthetic organization",
        "object_type": "DEVICE",
        "version_status": "KNOWN",
        "version_or_release": "v1",
        "observed_at": "2026-09-07T12:00:00Z",
        "jurisdiction_context": ["US"],
        "language_context": ["en"],
        "identity_resolution_state": "RESOLVED",
        "identity_basis_refs": ["EVIDENCE-IDENTITY-1"],
    }


def _evidence_packet() -> dict[str, object]:
    return {
        "evidence_refs": [
            {
                "evidence_id": "EVIDENCE-IDENTITY-1",
                "source_class": "FIRST_PARTY",
                "observed_at": "2026-09-07T12:00:00Z",
                "content_sha256": "1" * 64,
                "claim_scopes": ["EXISTENCE_IDENTITY", "CAPABILITY_DESCRIPTION"],
                "source_identity_ref": "SYNTHETIC-SOURCE-1",
            }
        ],
        "observation_cutoff": "2026-09-08T00:00:00Z",
        "identity_evidence_present": True,
        "stronger_claims_require_independent_support": True,
    }


def _review(
    role: str,
    decision: str,
    *,
    evidence_packet_sha256: str,
    timestamp: str = "2026-09-08T01:00:00Z",
) -> dict[str, object]:
    return {
        "reviewer_ref": f"REVIEWER-{role}",
        "evidence_packet_sha256": evidence_packet_sha256,
        "decision": decision,
        "rationale": f"Synthetic rationale for {role}",
        "adjudicator_role": role,
        "timestamp": timestamp,
        "exact_object_binding": _object_binding(),
    }


def _valid_agree_packet() -> dict[str, object]:
    evidence_packet = _evidence_packet()
    evidence_digest = _canonical_sha256(evidence_packet)
    return {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PRODUCT_V0_1",
        "benchmark_kind": "PRODUCT",
        "item_id": "D4-SYNTHETIC-001",
        "candidate_role": "HELD_OUT_CANDIDATE",
        "exact_object_binding": _object_binding(),
        "evidence_packet": evidence_packet,
        "construct_strata": ["CONSUMER", "AMBIGUOUS_BIOSIGNAL"],
        "review_design": {
            "double_label_required": True,
            "model_output_blinding_state": "BLINDED_TO_MODEL_OUTPUT",
            "blinding_exception_rationale": None,
        },
        "reviewer_records": [
            _review("PRIMARY_REVIEWER", "INCLUDE", evidence_packet_sha256=evidence_digest),
            _review(
                "SECONDARY_REVIEWER",
                "INCLUDE",
                evidence_packet_sha256=evidence_digest,
                timestamp="2026-09-08T01:10:00Z",
            ),
        ],
        "adjudication": {
            "state": "AGREE",
            "final_disposition": "INCLUDE",
            "final_rationale": "Synthetic agreement rationale",
        },
        "exposure_control": {
            "exposure_status": "NO_KNOWN_EXPOSURE_REVIEWED",
            "exposure_register_ref": "S3-EXPOSURE-SYNTHETIC",
            "held_out_eligible": True,
        },
        "rights_containment": {
            "custody": "S3_CONTROLLED",
            "redistribution_authority_claimed": False,
        },
    }


def _append_final_adjudicator(
    packet: dict[str, object],
    decision: str,
    *,
    timestamp: str,
) -> None:
    evidence_digest = _canonical_sha256(packet["evidence_packet"])
    packet["reviewer_records"].append(
        _review(
            "FINAL_ADJUDICATOR",
            decision,
            evidence_packet_sha256=evidence_digest,
            timestamp=timestamp,
        )
    )


class PreG2D4ReviewPacketSemanticTests(unittest.TestCase):
    def assert_invalid(self, packet: dict[str, object], message: str) -> None:
        with self.assertRaisesRegex(D4ReviewPacketSemanticError, message):
            validate_packet_semantics(packet)

    def test_valid_double_review_agreement(self) -> None:
        validate_packet_semantics(_valid_agree_packet())

    def test_every_reviewer_must_bind_exact_same_object(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["exact_object_binding"]["version_or_release"] = "v2"
        self.assert_invalid(packet, "exact same object")

    def test_reviewer_roles_are_unique(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["adjudicator_role"] = "PRIMARY_REVIEWER"
        self.assert_invalid(packet, "duplicate reviewer role")

    def test_reviewer_refs_are_distinct_across_roles(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["reviewer_ref"] = packet["reviewer_records"][0]["reviewer_ref"]
        self.assert_invalid(packet, "reviewer_ref values must be distinct")

    def test_reviewer_digest_must_bind_exact_evidence_packet(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][0]["evidence_packet_sha256"] = "0" * 64
        self.assert_invalid(packet, "exact canonical evidence_packet SHA-256")

    def test_evidence_mutation_after_review_is_detected(self) -> None:
        packet = _valid_agree_packet()
        packet["evidence_packet"]["evidence_refs"][0]["content_sha256"] = "2" * 64
        self.assert_invalid(packet, "exact canonical evidence_packet SHA-256")

    def test_held_out_candidate_cannot_disable_double_label(self) -> None:
        packet = _valid_agree_packet()
        packet["review_design"]["double_label_required"] = False
        self.assert_invalid(packet, "all held-out D4 candidates require independent double labeling")

    def test_double_label_requires_secondary_reviewer(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"] = [packet["reviewer_records"][0]]
        self.assert_invalid(packet, "SECONDARY_REVIEWER is required")

    def test_agreement_requires_matching_primary_secondary_decisions(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["decision"] = "BORDERLINE"
        self.assert_invalid(packet, "AGREE requires matching")

    def test_agreement_final_disposition_must_equal_reviewers(self) -> None:
        packet = _valid_agree_packet()
        packet["adjudication"]["final_disposition"] = "EXCLUDE"
        self.assert_invalid(packet, "final_disposition must equal")

    def test_adjudication_requires_real_disagreement_and_final_adjudicator(self) -> None:
        packet = _valid_agree_packet()
        packet["adjudication"] = {
            "state": "ADJUDICATED",
            "final_disposition": "INCLUDE",
            "final_rationale": "Synthetic adjudication rationale",
        }
        self.assert_invalid(packet, "requires a real primary/secondary disagreement")

        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["decision"] = "EXCLUDE"
        packet["adjudication"] = {
            "state": "ADJUDICATED",
            "final_disposition": "INCLUDE",
            "final_rationale": "Synthetic adjudication rationale",
        }
        self.assert_invalid(packet, "requires a FINAL_ADJUDICATOR")

    def test_adjudicator_decision_must_equal_final_disposition(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["decision"] = "EXCLUDE"
        _append_final_adjudicator(packet, "BORDERLINE", timestamp="2026-09-08T02:00:00Z")
        packet["adjudication"] = {
            "state": "ADJUDICATED",
            "final_disposition": "INCLUDE",
            "final_rationale": "Synthetic adjudication rationale",
        }
        self.assert_invalid(packet, "FINAL_ADJUDICATOR decision must equal")

    def test_final_adjudicator_must_bind_same_evidence_packet(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["decision"] = "EXCLUDE"
        _append_final_adjudicator(packet, "BORDERLINE", timestamp="2026-09-08T02:00:00Z")
        packet["reviewer_records"][2]["evidence_packet_sha256"] = "0" * 64
        packet["adjudication"] = {
            "state": "ADJUDICATED",
            "final_disposition": "BORDERLINE",
            "final_rationale": "Synthetic adjudication rationale",
        }
        self.assert_invalid(packet, "exact canonical evidence_packet SHA-256")

    def test_adjudicator_must_follow_primary_and_secondary_review(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["decision"] = "EXCLUDE"
        _append_final_adjudicator(packet, "BORDERLINE", timestamp="2026-09-08T01:05:00Z")
        packet["adjudication"] = {
            "state": "ADJUDICATED",
            "final_disposition": "BORDERLINE",
            "final_rationale": "Synthetic adjudication rationale",
        }
        self.assert_invalid(packet, "timestamp cannot precede primary/secondary")

    def test_valid_adjudicated_disagreement(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["decision"] = "EXCLUDE"
        _append_final_adjudicator(packet, "BORDERLINE", timestamp="2026-09-08T02:00:00Z")
        packet["adjudication"] = {
            "state": "ADJUDICATED",
            "final_disposition": "BORDERLINE",
            "final_rationale": "Synthetic adjudication rationale",
        }
        validate_packet_semantics(packet)

    def test_unresolved_disagreement_cannot_be_held_out_eligible(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][1]["decision"] = "EXCLUDE"
        packet["adjudication"] = {
            "state": "DISAGREE_UNADJUDICATED",
            "final_disposition": None,
            "final_rationale": None,
        }
        self.assert_invalid(packet, "unresolved disagreement cannot be held-out eligible")
        packet["exposure_control"]["held_out_eligible"] = False
        validate_packet_semantics(packet)

    def test_unresolved_state_requires_actual_disagreement(self) -> None:
        packet = _valid_agree_packet()
        packet["adjudication"] = {
            "state": "DISAGREE_UNADJUDICATED",
            "final_disposition": None,
            "final_rationale": None,
        }
        packet["exposure_control"]["held_out_eligible"] = False
        self.assert_invalid(packet, "requires differing reviewer dispositions")

    def test_unknown_or_known_exposure_blocks_held_out_eligibility(self) -> None:
        for status in ("UNKNOWN_REVIEW_REQUIRED", "EXPOSED_EXCLUDE_FROM_HELD_OUT"):
            packet = _valid_agree_packet()
            packet["exposure_control"]["exposure_status"] = status
            self.assert_invalid(packet, "held-out eligibility requires completed no-known-exposure review")

    def test_ambiguous_object_identity_blocks_held_out_eligibility(self) -> None:
        packet = _valid_agree_packet()
        packet["exact_object_binding"]["identity_resolution_state"] = "AMBIGUOUS"
        for record in packet["reviewer_records"]:
            record["exact_object_binding"]["identity_resolution_state"] = "AMBIGUOUS"
        self.assert_invalid(packet, "ambiguous object identity cannot be held-out eligible")

    def test_identity_basis_refs_must_resolve_inside_exact_evidence_packet(self) -> None:
        packet = _valid_agree_packet()
        packet["exact_object_binding"]["identity_basis_refs"] = ["MISSING-EVIDENCE"]
        for record in packet["reviewer_records"]:
            record["exact_object_binding"]["identity_basis_refs"] = ["MISSING-EVIDENCE"]
        self.assert_invalid(packet, "identity_basis_refs must resolve")

    def test_identity_basis_must_explicitly_support_existence_identity(self) -> None:
        packet = _valid_agree_packet()
        packet["evidence_packet"]["evidence_refs"][0]["claim_scopes"] = ["CAPABILITY_DESCRIPTION"]
        self.assert_invalid(packet, "must explicitly support EXISTENCE_IDENTITY")

    def test_pilot_material_cannot_be_held_out_eligible(self) -> None:
        packet = _valid_agree_packet()
        packet["candidate_role"] = "PILOT_DEVELOPMENT"
        self.assert_invalid(packet, "pilot/development material cannot be held-out eligible")

    def test_evidence_and_object_observations_cannot_postdate_cutoff(self) -> None:
        packet = _valid_agree_packet()
        packet["evidence_packet"]["evidence_refs"][0]["observed_at"] = "2026-09-08T00:00:01Z"
        self.assert_invalid(packet, "evidence observation cannot be later")

        packet = _valid_agree_packet()
        packet["exact_object_binding"]["observed_at"] = "2026-09-08T00:00:01Z"
        for record in packet["reviewer_records"]:
            record["exact_object_binding"]["observed_at"] = "2026-09-08T00:00:01Z"
        self.assert_invalid(packet, "exact object observation cannot be later")

    def test_review_cannot_precede_evidence_cutoff(self) -> None:
        packet = _valid_agree_packet()
        packet["reviewer_records"][0]["timestamp"] = "2026-09-07T23:59:59Z"
        self.assert_invalid(packet, "review timestamp cannot precede")

    def test_identity_evidence_must_exist_before_reference_review(self) -> None:
        packet = _valid_agree_packet()
        packet["evidence_packet"]["identity_evidence_present"] = False
        self.assert_invalid(packet, "identity_evidence_present must be true")

    def test_duplicate_evidence_ids_are_rejected(self) -> None:
        packet = _valid_agree_packet()
        duplicate = copy.deepcopy(packet["evidence_packet"]["evidence_refs"][0])
        duplicate["content_sha256"] = "2" * 64
        packet["evidence_packet"]["evidence_refs"].append(duplicate)
        self.assert_invalid(packet, "evidence_id values must be unique")

    def test_blinding_exception_requires_recorded_rationale(self) -> None:
        packet = _valid_agree_packet()
        packet["review_design"]["model_output_blinding_state"] = "BLINDING_NOT_PRACTICABLE_RECORDED"
        self.assert_invalid(packet, "blinding_exception_rationale must be a non-empty string")
        packet["review_design"]["blinding_exception_rationale"] = "Synthetic documented exception"
        validate_packet_semantics(packet)

    def test_rights_boundary_cannot_be_escalated(self) -> None:
        packet = _valid_agree_packet()
        packet["rights_containment"]["redistribution_authority_claimed"] = True
        self.assert_invalid(packet, "cannot claim redistribution authority")


if __name__ == "__main__":
    unittest.main()
