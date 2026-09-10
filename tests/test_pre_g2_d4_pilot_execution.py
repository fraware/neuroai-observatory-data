from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_pre_g2_d4_pilot_readiness_aggregate import (
    COMMITMENT_SCHEME,
    D4PilotExecutionError,
    build_pilot_readiness_aggregate,
    pilot_membership_commitment,
)
from scripts.check_pre_g2_d4_pilot_final_disjointness import (
    D4DisjointnessError,
    compute_disjointness_audit,
)
from scripts.select_pre_g2_d4_held_out import candidate_pool_commitment

PILOT_KEY = b"synthetic-pilot-key"
POOL_KEY = b"synthetic-pool-key"
SHA = "a" * 64
STRATA = (
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


def _object_binding(index: int) -> dict[str, object]:
    evidence_id = f"EVIDENCE-{index:03d}"
    return {
        "object_name": f"Synthetic product {index:03d}",
        "organization_identity": "Synthetic organization",
        "object_type": "DEVICE",
        "version_status": "KNOWN",
        "version_or_release": "v1",
        "observed_at": "2026-09-01T00:00:00+00:00",
        "jurisdiction_context": ["SYNTH-JURISDICTION"],
        "language_context": ["en"],
        "identity_resolution_state": "RESOLVED",
        "identity_basis_refs": [evidence_id],
    }


def _packet(index: int, state: str, decision: str = "INCLUDE") -> dict[str, object]:
    binding = _object_binding(index)
    evidence_id = binding["identity_basis_refs"][0]
    evidence_packet = {
        "evidence_refs": [
            {
                "evidence_id": evidence_id,
                "source_class": "FIRST_PARTY",
                "observed_at": "2026-09-01T00:00:00+00:00",
                "content_sha256": SHA,
                "claim_scopes": ["EXISTENCE_IDENTITY"],
                "source_identity_ref": "SYNTHETIC-SOURCE",
                "source_language": "en",
                "review_language": "en",
                "translation_status": "SOURCE_LANGUAGE_REVIEWED",
                "translation_provenance_ref": None,
            }
        ],
        "observation_cutoff": "2026-09-02T00:00:00+00:00",
        "identity_evidence_present": True,
        "stronger_claims_require_independent_support": True,
    }
    evidence_sha = _canonical_sha256(evidence_packet)

    if state == "AGREE":
        primary_decision = decision
        secondary_decision = decision
        final_disposition: str | None = decision
        final_rationale: str | None = "Independent reviewers agree."
    elif state == "ADJUDICATED":
        primary_decision = "INCLUDE"
        secondary_decision = "EXCLUDE"
        final_disposition = decision
        final_rationale = "Synthetic adjudication rationale."
    elif state == "DISAGREE_UNADJUDICATED":
        primary_decision = "INCLUDE"
        secondary_decision = "EXCLUDE"
        final_disposition = None
        final_rationale = None
    else:
        raise AssertionError(state)

    def reviewer(ref: str, role: str, reviewer_decision: str, timestamp: str, rationale: str) -> dict[str, object]:
        return {
            "reviewer_ref": ref,
            "evidence_packet_sha256": evidence_sha,
            "decision": reviewer_decision,
            "rationale": rationale,
            "adjudicator_role": role,
            "timestamp": timestamp,
            "exact_object_binding": copy.deepcopy(binding),
        }

    reviewer_records = [
        reviewer(f"PRIMARY-{index:03d}", "PRIMARY_REVIEWER", primary_decision, "2026-09-03T00:00:00+00:00", "Primary rationale."),
        reviewer(f"SECONDARY-{index:03d}", "SECONDARY_REVIEWER", secondary_decision, "2026-09-04T00:00:00+00:00", "Secondary rationale."),
    ]
    if state == "ADJUDICATED":
        reviewer_records.append(
            reviewer(
                f"ADJUDICATOR-{index:03d}",
                "FINAL_ADJUDICATOR",
                decision,
                "2026-09-05T00:00:00+00:00",
                final_rationale or "",
            )
        )

    return {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PRODUCT_V0_1",
        "benchmark_kind": "PRODUCT",
        "item_id": f"PILOT_ITEM_{index:03d}",
        "candidate_role": "PILOT_DEVELOPMENT",
        "exact_object_binding": binding,
        "evidence_packet": evidence_packet,
        "construct_strata": [STRATA[index % len(STRATA)]],
        "review_design": {
            "double_label_required": True,
            "model_output_blinding_state": "BLINDED_TO_MODEL_OUTPUT",
            "blinding_exception_rationale": None,
        },
        "reviewer_records": reviewer_records,
        "adjudication": {
            "state": state,
            "final_disposition": final_disposition,
            "final_rationale": final_rationale,
        },
        "exposure_control": {
            "exposure_status": "NO_KNOWN_EXPOSURE_REVIEWED",
            "exposure_register_ref": "SYNTHETIC-EXPOSURE-REGISTER",
            "held_out_eligible": False,
        },
        "rights_containment": {
            "custody": "S3_CONTROLLED",
            "redistribution_authority_claimed": False,
        },
    }


def _pilot_packets() -> list[dict[str, object]]:
    packets: list[dict[str, object]] = []
    dispositions = ("INCLUDE", "EXCLUDE", "BORDERLINE")
    for index in range(48):
        packets.append(_packet(index, "AGREE", dispositions[index % 3]))
    for index in range(48, 57):
        packets.append(_packet(index, "ADJUDICATED", "BORDERLINE"))
    for index in range(57, 60):
        packets.append(_packet(index, "DISAGREE_UNADJUDICATED"))
    return packets


def _write_pilot(root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    packet_root = root / "packets"
    packet_root.mkdir()
    packets = _pilot_packets()
    entries: list[dict[str, str]] = []
    item_ids: list[str] = []
    for index, packet in enumerate(packets):
        filename = f"packet-{index:03d}.json"
        raw = (json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        (packet_root / filename).write_bytes(raw)
        entries.append({"controlled_packet_ref": filename, "packet_sha256": hashlib.sha256(raw).hexdigest()})
        item_ids.append(str(packet["item_id"]))

    pilot_round_id = "SYNTHETIC-PILOT-ROUND"
    manifest: dict[str, object] = {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PRODUCT_V0_1",
        "sampling_protocol_id": "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1",
        "execution_protocol_id": "PRE_G2_D4_PILOT_EXECUTION_PROTOCOL_2026-09-09_v0.1",
        "pilot_round_id": pilot_round_id,
        "state": "COMPLETE_ROUND_NO_EXTENSION",
        "pilot_membership_commitment": pilot_membership_commitment(pilot_round_id, item_ids, PILOT_KEY),
        "pilot_membership_commitment_scheme": COMMITMENT_SCHEME,
        "reviewer_training_record_sha256": "b" * 64,
        "exposure_register_sha256": "c" * 64,
        "prior_exposure_disjointness_audit_sha256": "d" * 64,
        "packet_manifest": entries,
    }
    return manifest, packets


def _candidate_pool(overlap: bool = False) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for index in range(240):
        candidate_id = f"FINAL_ITEM_{index:03d}"
        if overlap and index == 0:
            candidate_id = "PILOT_ITEM_000"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "construct_strata": list(STRATA),
                "source_languages": ["en", "fr", "de", "es", "ja", "ko", "zh"],
                "jurisdictions": ["US", "FR", "DE", "JP", "KR", "CN"],
                "exact_object_identity_resolved": True,
                "exposure_status": "NO_KNOWN_EXPOSURE_REVIEWED",
                "semantic_validation_passed": True,
                "human_confirmed_construct_tags": True,
                "pilot_or_development_exposed": False,
            }
        )
    pool: dict[str, object] = {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PRODUCT_V0_1",
        "protocol_id": "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1",
        "candidate_pool_id": "SYNTHETIC-FINAL-POOL",
        "candidate_pool_commitment": "0" * 64,
        "candidate_pool_commitment_scheme": COMMITMENT_SCHEME,
        "candidate_pool_frozen": True,
        "candidates": candidates,
    }
    pool["candidate_pool_commitment"] = candidate_pool_commitment(pool, POOL_KEY)
    return pool


def _attestation(manifest: dict[str, object], pool: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "namespace_id": "D4_CONTROLLED_ITEM_ID_V1",
        "state": "HUMAN_CONTROLLED_NAMESPACE_BINDING_RECORDED",
        "pilot_round_id": manifest["pilot_round_id"],
        "pilot_membership_commitment": manifest["pilot_membership_commitment"],
        "candidate_pool_id": pool["candidate_pool_id"],
        "candidate_pool_commitment": pool["candidate_pool_commitment"],
        "human_identity_resolution_provenance_sha256": "e" * 64,
        "authority": {
            "identity_resolution_truth_established": False,
            "g2_passed": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "assessment_effect": "NONE",
        },
    }


class D4PilotAggregateExecutionTests(unittest.TestCase):
    def test_valid_exact_threshold_pilot_derives_readiness_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            aggregate = build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)
            self.assertEqual(aggregate["total_items"], 60)
            self.assertEqual(aggregate["primary_secondary_exact_agreement_count"], 48)
            self.assertEqual(aggregate["adjudicated_disagreement_count"], 9)
            self.assertEqual(aggregate["unresolved_disagreement_count"], 3)
            self.assertGreaterEqual(aggregate["resolved_disposition_counts"]["INCLUDE"], 10)
            self.assertGreaterEqual(aggregate["resolved_disposition_counts"]["EXCLUDE"], 10)
            self.assertGreaterEqual(aggregate["resolved_disposition_counts"]["BORDERLINE"], 10)
            self.assertTrue(all(value == 6 for value in aggregate["required_stratum_counts"].values()))
            self.assertFalse(aggregate["authority"]["g2_passed"])

    def test_manifest_order_does_not_change_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            first = build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)
            reversed_manifest = copy.deepcopy(manifest)
            reversed_manifest["packet_manifest"] = list(reversed(reversed_manifest["packet_manifest"]))
            second = build_pilot_readiness_aggregate(reversed_manifest, root / "packets", PILOT_KEY)
            self.assertEqual(first, second)

    def test_packet_mutation_is_detected_by_raw_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            path = root / "packets" / "packet-000.json"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(D4PilotExecutionError):
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)

    def test_missing_packet_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            (root / "packets" / "packet-000.json").unlink()
            with self.assertRaises(D4PilotExecutionError):
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)

    def test_wrong_membership_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            with self.assertRaises(D4PilotExecutionError):
                build_pilot_readiness_aggregate(manifest, root / "packets", b"wrong-key")

    def test_duplicate_item_id_is_rejected_even_with_updated_packet_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            path = root / "packets" / "packet-001.json"
            packet = json.loads(path.read_text(encoding="utf-8"))
            packet["item_id"] = "PILOT_ITEM_000"
            raw = (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()
            path.write_bytes(raw)
            manifest["packet_manifest"][1]["packet_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaises(D4PilotExecutionError):
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)

    def test_semantic_invalid_packet_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            path = root / "packets" / "packet-000.json"
            packet = json.loads(path.read_text(encoding="utf-8"))
            packet["reviewer_records"][0]["evidence_packet_sha256"] = "f" * 64
            raw = (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()
            path.write_bytes(raw)
            manifest["packet_manifest"][0]["packet_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaises(D4PilotExecutionError):
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)

    def test_held_out_eligibility_and_wrong_role_fail_closed(self) -> None:
        for mutation in ("held_out", "role"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest, _ = _write_pilot(root)
                path = root / "packets" / "packet-000.json"
                packet = json.loads(path.read_text(encoding="utf-8"))
                if mutation == "held_out":
                    packet["exposure_control"]["held_out_eligible"] = True
                else:
                    packet["candidate_role"] = "HELD_OUT_CANDIDATE"
                raw = (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()
                path.write_bytes(raw)
                manifest["packet_manifest"][0]["packet_sha256"] = hashlib.sha256(raw).hexdigest()
                with self.assertRaises(D4PilotExecutionError):
                    build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)

    def test_forbidden_model_development_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            path = root / "packets" / "packet-000.json"
            packet = json.loads(path.read_text(encoding="utf-8"))
            packet["evidence_packet"]["model_score"] = 0.9
            raw = (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()
            path.write_bytes(raw)
            manifest["packet_manifest"][0]["packet_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaises(D4PilotExecutionError):
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)

    def test_public_aggregate_contains_no_controlled_item_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            aggregate = build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)
            serialized = json.dumps(aggregate, sort_keys=True)
            self.assertNotIn("PILOT_ITEM_", serialized)
            self.assertNotIn("EVIDENCE-", serialized)
            self.assertNotIn("PRIMARY-", serialized)


class D4PilotFinalDisjointnessTests(unittest.TestCase):
    def test_disjoint_memberships_produce_aggregate_only_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            pool = _candidate_pool()
            attestation = _attestation(manifest, pool)
            raw = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
            controlled, public = compute_disjointness_audit(
                manifest,
                root / "packets",
                PILOT_KEY,
                pool,
                POOL_KEY,
                attestation,
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(public["overlap_count"], 0)
            self.assertTrue(public["overlap_zero"])
            self.assertNotIn("overlap_item_ids", public)
            self.assertEqual(controlled["overlap_item_ids"], [])
            self.assertFalse(public["identity_resolution_truth_established"])
            self.assertFalse(public["authority"]["final_selection_authorized"])

    def test_overlap_is_visible_only_as_count_in_public_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            pool = _candidate_pool(overlap=True)
            attestation = _attestation(manifest, pool)
            raw = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
            controlled, public = compute_disjointness_audit(
                manifest,
                root / "packets",
                PILOT_KEY,
                pool,
                POOL_KEY,
                attestation,
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(public["overlap_count"], 1)
            self.assertFalse(public["overlap_zero"])
            self.assertEqual(controlled["overlap_item_ids"], ["PILOT_ITEM_000"])
            self.assertNotIn("PILOT_ITEM_000", json.dumps(public, sort_keys=True))

    def test_candidate_pool_commitment_mismatch_fails_closed_without_identifier_in_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            pool = _candidate_pool()
            pool["candidate_pool_commitment"] = "0" * 64
            attestation = _attestation(manifest, pool)
            with self.assertRaises(D4DisjointnessError) as caught:
                compute_disjointness_audit(manifest, root / "packets", PILOT_KEY, pool, POOL_KEY, attestation, "f" * 64)
            self.assertNotIn("FINAL_ITEM_", str(caught.exception))

    def test_candidate_validation_failure_does_not_leak_candidate_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            pool = _candidate_pool()
            pool["candidates"][0]["pilot_or_development_exposed"] = True
            pool["candidate_pool_commitment"] = candidate_pool_commitment(pool, POOL_KEY)
            attestation = _attestation(manifest, pool)
            with self.assertRaises(D4DisjointnessError) as caught:
                compute_disjointness_audit(manifest, root / "packets", PILOT_KEY, pool, POOL_KEY, attestation, "f" * 64)
            self.assertNotIn("FINAL_ITEM_000", str(caught.exception))

    def test_namespace_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            pool = _candidate_pool()
            attestation = _attestation(manifest, pool)
            attestation["namespace_id"] = "WRONG"
            with self.assertRaises(D4DisjointnessError):
                compute_disjointness_audit(manifest, root / "packets", PILOT_KEY, pool, POOL_KEY, attestation, "f" * 64)

    def test_attestation_digest_argument_must_bind_attestation_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            pool = _candidate_pool()
            attestation = _attestation(manifest, pool)
            with self.assertRaises(D4DisjointnessError):
                compute_disjointness_audit(
                    manifest,
                    root / "packets",
                    PILOT_KEY,
                    pool,
                    POOL_KEY,
                    attestation,
                    "0" * 64,
                )


if __name__ == "__main__":
    unittest.main()
