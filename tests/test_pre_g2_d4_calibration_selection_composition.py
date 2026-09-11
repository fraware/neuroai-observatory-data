from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_pre_g2_d4_pilot_readiness_aggregate import (
    build_pilot_readiness_aggregate,
)
from scripts.evaluate_pre_g2_d4_pilot_readiness import (
    evaluate_pilot_readiness,
)
from scripts.execute_pre_g2_d4_final_selection import (
    PUBLIC_CONTROLLED_FAILURE,
    PUBLIC_INTERNAL_FAILURE,
    execute_composed_selection,
    run_composed_selection,
)
from scripts.select_pre_g2_d4_held_out import (
    candidate_pool_commitment,
    select_candidates,
)
from scripts.validate_pre_g2_d4_calibration_selection_authorization import (
    D4CalibrationAuthorizationError,
    canonical_sha256,
    require_approved_human_calibration_disposition,
    validate_human_calibration_disposition,
    validate_selection_authorization_envelope,
)
from tests.test_pre_g2_d4_pilot_execution import (
    PILOT_KEY,
    POOL_KEY,
    _attestation,
    _candidate_pool,
    _packet,
    _write_pilot,
)


def _disposition_authority() -> dict[str, object]:
    return {
        "reviewer_competence_established": False,
        "benchmark_adequacy_established": False,
        "g0_passed": False,
        "g2_passed": False,
        "g5_passed": False,
        "rights_clearance": False,
        "population_generalization_authority": False,
        "canonical_s2_authority": False,
        "publication_authority": False,
        "phase4_online_first_default_authorized": False,
        "assessment_effect": "NONE",
    }


def _envelope_authority() -> dict[str, object]:
    return {
        "human_identity_established": False,
        "reviewer_competence_established": False,
        "benchmark_adequacy_established": False,
        "g0_passed": False,
        "g2_passed": False,
        "g5_passed": False,
        "rights_clearance": False,
        "population_generalization_authority": False,
        "canonical_s2_authority": False,
        "publication_authority": False,
        "phase4_online_first_default_authorized": False,
        "assessment_effect": "NONE",
    }


def _disposition(
    manifest: dict[str, object],
    aggregate: dict[str, object],
    readiness: dict[str, object],
    *,
    decision: str = "APPROVE",
) -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "disposition_id": "SYNTHETIC-D4-CALIBRATION-001",
        "benchmark_id": "PRE_G2_PRODUCT_V0_1",
        "sampling_protocol_id": "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1",
        "pilot_execution_protocol_id": "PRE_G2_D4_PILOT_EXECUTION_PROTOCOL_2026-09-09_v0.1",
        "pilot_round_id": manifest["pilot_round_id"],
        "pilot_membership_commitment": manifest[
            "pilot_membership_commitment"
        ],
        "pilot_manifest_sha256": canonical_sha256(manifest),
        "pilot_readiness_aggregate_sha256": canonical_sha256(
            aggregate
        ),
        "pilot_readiness_result_sha256": canonical_sha256(readiness),
        "reviewer_training_record_sha256": manifest[
            "reviewer_training_record_sha256"
        ],
        "exposure_register_sha256": manifest[
            "exposure_register_sha256"
        ],
        "prior_exposure_disjointness_audit_sha256": manifest[
            "prior_exposure_disjointness_audit_sha256"
        ],
        "quantitative_gate_passed": True,
        "decision": decision,
        "approval_scope": "FINAL_D4_CHALLENGE_SELECTION_ONLY",
        "governance_ref": "S3-D4-GOVERNANCE-001",
        "governance_role": "D4_HUMAN_CALIBRATION_AUTHORITY",
        "rationale": "Synthetic governance rationale for fail-closed composition testing.",
        "decided_at": "2026-09-11T20:00:00Z",
        "authority": _disposition_authority(),
    }


def _envelope(
    manifest: dict[str, object],
    disposition: dict[str, object],
    pool: dict[str, object],
    attestation: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "envelope_id": "SYNTHETIC-D4-SELECTION-AUTH-001",
        "benchmark_id": "PRE_G2_PRODUCT_V0_1",
        "sampling_protocol_id": "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1",
        "pilot_execution_protocol_id": "PRE_G2_D4_PILOT_EXECUTION_PROTOCOL_2026-09-09_v0.1",
        "scope": "FINAL_D4_CHALLENGE_SELECTION_ONLY",
        "state": "CONTROLLED_COMPOSITION_BINDING_RECORDED",
        "pilot_round_id": manifest["pilot_round_id"],
        "pilot_membership_commitment": manifest[
            "pilot_membership_commitment"
        ],
        "human_calibration_disposition_sha256": canonical_sha256(
            disposition
        ),
        "candidate_pool_id": pool["candidate_pool_id"],
        "candidate_pool_commitment": pool[
            "candidate_pool_commitment"
        ],
        "identity_namespace_attestation_sha256": canonical_sha256(
            attestation
        ),
        "bound_at": "2026-09-11T20:05:00Z",
        "control_ref": "S3-D4-CONTROL-001",
        "authority": _envelope_authority(),
    }


def _prepare_fixture(
    root: Path,
    *,
    decision: str = "APPROVE",
    overlap: bool = False,
) -> dict[str, object]:
    manifest, _ = _write_pilot(root)
    packet_root = root / "packets"
    aggregate = build_pilot_readiness_aggregate(
        manifest,
        packet_root,
        PILOT_KEY,
    )
    readiness = evaluate_pilot_readiness(aggregate)
    disposition = _disposition(
        manifest,
        aggregate,
        readiness,
        decision=decision,
    )
    pool = _candidate_pool(overlap=overlap)
    attestation = _attestation(manifest, pool)
    envelope = _envelope(
        manifest,
        disposition,
        pool,
        attestation,
    )

    paths = {
        "manifest": root / "pilot-manifest.json",
        "disposition": root / "calibration-disposition.json",
        "envelope": root / "selection-authorization.json",
        "pool": root / "candidate-pool.json",
        "attestation": root / "namespace-attestation.json",
        "pilot_key": root / "pilot.key",
        "pool_key": root / "pool.key",
        "controlled": root / "controlled" / "selection.json",
        "controlled_error": root / "controlled" / "error.json",
    }
    paths["manifest"].write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    paths["disposition"].write_text(
        json.dumps(disposition),
        encoding="utf-8",
    )
    paths["envelope"].write_text(
        json.dumps(envelope),
        encoding="utf-8",
    )
    paths["pool"].write_text(
        json.dumps(pool),
        encoding="utf-8",
    )
    paths["attestation"].write_text(
        json.dumps(attestation),
        encoding="utf-8",
    )
    paths["pilot_key"].write_bytes(PILOT_KEY)
    paths["pool_key"].write_bytes(POOL_KEY)

    return {
        "manifest": manifest,
        "packet_root": packet_root,
        "aggregate": aggregate,
        "readiness": readiness,
        "disposition": disposition,
        "pool": pool,
        "attestation": attestation,
        "envelope": envelope,
        "paths": paths,
    }


def _run_fixture(
    fixture: dict[str, object],
) -> tuple[int, dict[str, object] | None, str]:
    paths = fixture["paths"]
    return run_composed_selection(
        pilot_manifest_path=paths["manifest"],
        packet_root=fixture["packet_root"],
        pilot_key_path=paths["pilot_key"],
        calibration_disposition_path=paths["disposition"],
        authorization_envelope_path=paths["envelope"],
        candidate_pool_path=paths["pool"],
        candidate_pool_key_path=paths["pool_key"],
        identity_namespace_attestation_path=paths["attestation"],
        controlled_output=paths["controlled"],
        controlled_error_output=paths["controlled_error"],
    )


class D4CalibrationSelectionCompositionTests(unittest.TestCase):
    def test_valid_disposition_binds_exact_pilot_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            validate_human_calibration_disposition(
                fixture["disposition"],
                pilot_manifest=fixture["manifest"],
                readiness_aggregate=fixture["aggregate"],
                readiness_result=fixture["readiness"],
            )
            digest = require_approved_human_calibration_disposition(
                fixture["disposition"],
                pilot_manifest=fixture["manifest"],
                readiness_aggregate=fixture["aggregate"],
                readiness_result=fixture["readiness"],
            )
            self.assertEqual(
                digest,
                fixture["envelope"][
                    "human_calibration_disposition_sha256"
                ],
            )

    def test_revise_and_reject_cannot_unlock_selection(self) -> None:
        for decision in ("REVISE", "REJECT"):
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as tmp:
                fixture = _prepare_fixture(
                    Path(tmp),
                    decision=decision,
                )
                validate_human_calibration_disposition(
                    fixture["disposition"],
                    pilot_manifest=fixture["manifest"],
                    readiness_aggregate=fixture["aggregate"],
                    readiness_result=fixture["readiness"],
                )
                with self.assertRaises(D4CalibrationAuthorizationError):
                    require_approved_human_calibration_disposition(
                        fixture["disposition"],
                        pilot_manifest=fixture["manifest"],
                        readiness_aggregate=fixture["aggregate"],
                        readiness_result=fixture["readiness"],
                    )
                status, public, message = _run_fixture(fixture)
                self.assertEqual(status, 1)
                self.assertIsNone(public)
                self.assertEqual(
                    message,
                    PUBLIC_CONTROLLED_FAILURE,
                )

    def test_valid_envelope_binds_approval_pool_and_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            envelope_digest = validate_selection_authorization_envelope(
                fixture["envelope"],
                approved_disposition_sha256=canonical_sha256(
                    fixture["disposition"]
                ),
                pilot_manifest=fixture["manifest"],
                candidate_pool=fixture["pool"],
                identity_namespace_attestation=fixture[
                    "attestation"
                ],
            )
            self.assertEqual(
                envelope_digest,
                canonical_sha256(fixture["envelope"]),
            )

    def test_valid_composed_execution_preserves_lower_level_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            expected_controlled, expected_aggregate = select_candidates(
                copy.deepcopy(fixture["pool"]),
                POOL_KEY,
            )
            status, public, message = _run_fixture(fixture)
            self.assertEqual(status, 0)
            self.assertEqual(message, "")
            self.assertIsNotNone(public)

            controlled = json.loads(
                fixture["paths"]["controlled"].read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                controlled["selection"],
                expected_controlled,
            )
            self.assertEqual(
                public["selection"],
                expected_aggregate,
            )
            self.assertTrue(
                public["execution_preconditions"][
                    "human_calibration_approval_verified"
                ]
            )
            self.assertTrue(
                public["execution_preconditions"][
                    "authorization_envelope_verified"
                ]
            )
            self.assertTrue(
                public["execution_preconditions"][
                    "pilot_final_overlap_zero"
                ]
            )
            rendered = json.dumps(public, sort_keys=True)
            self.assertNotIn("selected_candidate_ids", rendered)
            self.assertNotIn("FINAL_ITEM_", rendered)

    def test_disposition_digest_mutations_fail_closed(self) -> None:
        mutations = (
            ("pilot_round_id", "OTHER-ROUND"),
            ("pilot_membership_commitment", "1" * 64),
            ("pilot_manifest_sha256", "2" * 64),
            ("pilot_readiness_aggregate_sha256", "3" * 64),
            ("pilot_readiness_result_sha256", "4" * 64),
        )
        for field, value in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                fixture = _prepare_fixture(Path(tmp))
                disposition = fixture["disposition"]
                disposition[field] = value
                with self.assertRaises(D4CalibrationAuthorizationError):
                    validate_human_calibration_disposition(
                        disposition,
                        pilot_manifest=fixture["manifest"],
                        readiness_aggregate=fixture["aggregate"],
                        readiness_result=fixture["readiness"],
                    )

    def test_quantitative_gate_failure_blocks_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            manifest = fixture["manifest"]
            packet_root = fixture["packet_root"]

            # Convert four exact-agreement packets into unresolved disagreement.
            # Membership is unchanged, so only the derived readiness state changes.
            for index in range(4):
                packet = _packet(
                    index,
                    "DISAGREE_UNADJUDICATED",
                )
                path = packet_root / f"packet-{index:03d}.json"
                raw = (
                    json.dumps(
                        packet,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode("utf-8")
                path.write_bytes(raw)
                manifest["packet_manifest"][index][
                    "packet_sha256"
                ] = hashlib.sha256(raw).hexdigest()

            fixture["paths"]["manifest"].write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            status, public, message = _run_fixture(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_arbitrary_well_formed_calibration_digest_in_envelope_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            envelope = fixture["envelope"]
            envelope["human_calibration_disposition_sha256"] = "f" * 64
            fixture["paths"]["envelope"].write_text(
                json.dumps(envelope),
                encoding="utf-8",
            )
            status, public, _ = _run_fixture(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)

    def test_envelope_candidate_pool_or_attestation_mismatch_fails(self) -> None:
        for field in (
            "candidate_pool_commitment",
            "identity_namespace_attestation_sha256",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                fixture = _prepare_fixture(Path(tmp))
                envelope = fixture["envelope"]
                envelope[field] = "9" * 64
                fixture["paths"]["envelope"].write_text(
                    json.dumps(envelope),
                    encoding="utf-8",
                )
                status, public, _ = _run_fixture(fixture)
                self.assertEqual(status, 1)
                self.assertIsNone(public)

    def test_pilot_candidate_overlap_blocks_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(
                Path(tmp),
                overlap=True,
            )
            status, public, message = _run_fixture(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_wrong_commitment_keys_fail_closed(self) -> None:
        for key_name in ("pilot_key", "pool_key"):
            with self.subTest(key_name=key_name), tempfile.TemporaryDirectory() as tmp:
                fixture = _prepare_fixture(Path(tmp))
                fixture["paths"][key_name].write_bytes(b"wrong-key")
                status, public, _ = _run_fixture(fixture)
                self.assertEqual(status, 1)
                self.assertIsNone(public)

    def test_candidate_pool_shape_violation_fails_before_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            pool = fixture["pool"]
            pool["candidates"][0]["model_score"] = 0.99
            fixture["paths"]["pool"].write_text(
                json.dumps(pool),
                encoding="utf-8",
            )
            status, public, message = _run_fixture(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_output_paths_cannot_alias_inputs_or_packet_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            original_pool = fixture["paths"]["pool"].read_bytes()
            paths = fixture["paths"]

            status, public, _ = run_composed_selection(
                pilot_manifest_path=paths["manifest"],
                packet_root=fixture["packet_root"],
                pilot_key_path=paths["pilot_key"],
                calibration_disposition_path=paths["disposition"],
                authorization_envelope_path=paths["envelope"],
                candidate_pool_path=paths["pool"],
                candidate_pool_key_path=paths["pool_key"],
                identity_namespace_attestation_path=paths["attestation"],
                controlled_output=paths["pool"],
            )
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(
                paths["pool"].read_bytes(),
                original_pool,
            )

            inside_packets = fixture["packet_root"] / "output.json"
            status, public, _ = run_composed_selection(
                pilot_manifest_path=paths["manifest"],
                packet_root=fixture["packet_root"],
                pilot_key_path=paths["pilot_key"],
                calibration_disposition_path=paths["disposition"],
                authorization_envelope_path=paths["envelope"],
                candidate_pool_path=paths["pool"],
                candidate_pool_key_path=paths["pool_key"],
                identity_namespace_attestation_path=paths["attestation"],
                controlled_output=inside_packets,
            )
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertFalse(inside_packets.exists())

    def test_controlled_diagnostic_write_failure_keeps_public_error_generic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(
                Path(tmp),
                decision="REJECT",
            )
            bad_error_path = Path(tmp) / "existing-directory"
            bad_error_path.mkdir()
            paths = fixture["paths"]
            status, public, message = run_composed_selection(
                pilot_manifest_path=paths["manifest"],
                packet_root=fixture["packet_root"],
                pilot_key_path=paths["pilot_key"],
                calibration_disposition_path=paths["disposition"],
                authorization_envelope_path=paths["envelope"],
                candidate_pool_path=paths["pool"],
                candidate_pool_key_path=paths["pool_key"],
                identity_namespace_attestation_path=paths["attestation"],
                controlled_output=paths["controlled"],
                controlled_error_output=bad_error_path,
            )
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_unexpected_internal_exception_is_publicly_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            secret = "SECRET-D4-CONTROLLED-DETAIL"
            with patch(
                "scripts.execute_pre_g2_d4_final_selection.execute_composed_selection",
                side_effect=RuntimeError(secret),
            ):
                status, public, message = _run_fixture(fixture)
            self.assertEqual(status, 70)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_INTERNAL_FAILURE)
            self.assertNotIn(secret, message)

            controlled_error = json.loads(
                fixture["paths"]["controlled_error"].read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                controlled_error["controlled_detail"],
                secret,
            )

    def test_authority_escalation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            disposition = fixture["disposition"]
            disposition["authority"]["g2_passed"] = True
            with self.assertRaises(D4CalibrationAuthorizationError):
                validate_human_calibration_disposition(
                    disposition,
                    pilot_manifest=fixture["manifest"],
                    readiness_aggregate=fixture["aggregate"],
                    readiness_result=fixture["readiness"],
                )

            envelope = copy.deepcopy(fixture["envelope"])
            envelope["authority"]["publication_authority"] = True
            with self.assertRaises(D4CalibrationAuthorizationError):
                validate_selection_authorization_envelope(
                    envelope,
                    approved_disposition_sha256=canonical_sha256(
                        fixture["disposition"]
                    ),
                    pilot_manifest=fixture["manifest"],
                    candidate_pool=fixture["pool"],
                    identity_namespace_attestation=fixture[
                        "attestation"
                    ],
                )

    def test_direct_composed_function_rejects_mismatched_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            envelope = copy.deepcopy(fixture["envelope"])
            envelope["candidate_pool_id"] = "OTHER-POOL"
            with self.assertRaises(Exception):
                execute_composed_selection(
                    pilot_manifest=fixture["manifest"],
                    packet_root=fixture["packet_root"],
                    pilot_commitment_key=PILOT_KEY,
                    calibration_disposition=fixture["disposition"],
                    authorization_envelope=envelope,
                    candidate_pool=fixture["pool"],
                    candidate_pool_commitment_key=POOL_KEY,
                    identity_namespace_attestation=fixture["attestation"],
                )


if __name__ == "__main__":
    unittest.main()
