from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_pre_g2_d3_challenge_pilot_readiness import (
    derive_readiness_aggregate,
)
from scripts.execute_pre_g2_d3_challenge_final_selection import (
    PUBLIC_CONTROLLED_FAILURE,
    PUBLIC_INTERNAL_FAILURE,
    execute_composed_selection,
    run_composed_selection,
)
from scripts.select_pre_g2_d3_challenge_held_out import (
    candidate_pool_commitment,
    select_candidates,
)
from scripts.validate_pre_g2_d3_challenge_human_calibration_disposition import (
    D3CalibrationDispositionError,
    calibration_disposition_sha256,
    canonical_sha256,
    require_approved_calibration_disposition,
    validate_calibration_disposition,
)
from tests.test_pre_g2_d3_challenge_sampling_calibration import (
    PILOT_KEY,
    POOL_KEY,
    _attestation,
    _candidate_pool,
    _pilot_packet,
    _write_pilot,
)


def _authority() -> dict[str, object]:
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


def _disposition(
    manifest: dict[str, object],
    aggregate: dict[str, object],
    result: dict[str, object],
    *,
    decision: str = "APPROVE",
) -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "disposition_id": "SYNTHETIC-D3-CALIBRATION-DISPOSITION-001",
        "benchmark_id": "PRE_G2_PATENT_V0_1",
        "protocol_id": "PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1",
        "pilot_round_id": manifest["pilot_round_id"],
        "pilot_membership_commitment": manifest[
            "pilot_membership_commitment"
        ],
        "pilot_manifest_sha256": canonical_sha256(manifest),
        "pilot_readiness_aggregate_sha256": canonical_sha256(
            aggregate
        ),
        "pilot_readiness_result_sha256": canonical_sha256(result),
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
        "approval_scope": "FINAL_CHALLENGE_CANDIDATE_POOL_SELECTION_ONLY",
        "governance_ref": "S3-D3-GOVERNANCE-REF-001",
        "governance_role": "D3_HUMAN_CALIBRATION_AUTHORITY",
        "rationale": "Synthetic governance rationale for composed-control testing.",
        "decided_at": "2026-09-11T15:00:00Z",
        "authority": _authority(),
    }


def _prepare_fixture(
    root: Path,
    *,
    decision: str = "APPROVE",
) -> dict[str, object]:
    manifest, packet_root = _write_pilot(root)
    aggregate, readiness = derive_readiness_aggregate(
        manifest,
        packet_root,
        PILOT_KEY,
    )
    disposition = _disposition(
        manifest,
        aggregate,
        readiness,
        decision=decision,
    )
    disposition_sha = calibration_disposition_sha256(disposition)

    pool = _candidate_pool()
    pool["human_calibration_disposition_sha256"] = disposition_sha
    pool["candidate_pool_commitment"] = candidate_pool_commitment(
        pool,
        POOL_KEY,
    )
    attestation = _attestation(manifest, pool)

    paths = {
        "manifest": root / "pilot-manifest.json",
        "disposition": root / "calibration-disposition.json",
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
        "paths": paths,
    }


def _run_fixture(fixture: dict[str, object]) -> tuple[int, dict[str, object] | None, str]:
    paths = fixture["paths"]
    return run_composed_selection(
        pilot_manifest_path=paths["manifest"],
        packet_root=fixture["packet_root"],
        pilot_key_path=paths["pilot_key"],
        calibration_disposition_path=paths["disposition"],
        candidate_pool_path=paths["pool"],
        pool_key_path=paths["pool_key"],
        identity_namespace_attestation_path=paths["attestation"],
        controlled_output=paths["controlled"],
        controlled_error_output=paths["controlled_error"],
    )


class D3CalibrationSelectionCompositionTests(unittest.TestCase):
    def test_valid_approval_binds_exact_pilot_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            validate_calibration_disposition(
                fixture["disposition"],
                pilot_manifest=fixture["manifest"],
                readiness_aggregate=fixture["aggregate"],
                readiness_result=fixture["readiness"],
            )
            digest = require_approved_calibration_disposition(
                fixture["disposition"],
                pilot_manifest=fixture["manifest"],
                readiness_aggregate=fixture["aggregate"],
                readiness_result=fixture["readiness"],
            )
            self.assertEqual(
                digest,
                fixture["pool"][
                    "human_calibration_disposition_sha256"
                ],
            )

    def test_revise_and_reject_are_structurally_valid_but_cannot_unlock_selection(self) -> None:
        for decision in ("REVISE", "REJECT"):
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as tmp:
                fixture = _prepare_fixture(Path(tmp), decision=decision)
                validate_calibration_disposition(
                    fixture["disposition"],
                    pilot_manifest=fixture["manifest"],
                    readiness_aggregate=fixture["aggregate"],
                    readiness_result=fixture["readiness"],
                )
                with self.assertRaises(D3CalibrationDispositionError):
                    require_approved_calibration_disposition(
                        fixture["disposition"],
                        pilot_manifest=fixture["manifest"],
                        readiness_aggregate=fixture["aggregate"],
                        readiness_result=fixture["readiness"],
                    )
                status, public, message = _run_fixture(fixture)
                self.assertEqual(status, 1)
                self.assertIsNone(public)
                self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_valid_composed_execution_preserves_lower_level_selection_semantics(self) -> None:
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
                    "pilot_final_overlap_zero"
                ]
            )
            rendered = json.dumps(public, sort_keys=True)
            self.assertNotIn("selected_candidate_ids", rendered)
            self.assertNotIn("S3-CANDIDATE-FAMILY-", rendered)

    def test_arbitrary_well_formed_disposition_digest_cannot_unlock_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            pool = fixture["pool"]
            pool["human_calibration_disposition_sha256"] = "f" * 64
            pool["candidate_pool_commitment"] = candidate_pool_commitment(
                pool,
                POOL_KEY,
            )
            fixture["paths"]["pool"].write_text(
                json.dumps(pool),
                encoding="utf-8",
            )
            attestation = _attestation(fixture["manifest"], pool)
            fixture["paths"]["attestation"].write_text(
                json.dumps(attestation),
                encoding="utf-8",
            )
            status, public, message = _run_fixture(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_disposition_must_bind_exact_pilot_and_readiness_digests(self) -> None:
        mutations = (
            ("pilot_round_id", "OTHER-PILOT"),
            ("pilot_membership_commitment", "9" * 64),
            ("pilot_manifest_sha256", "8" * 64),
            ("pilot_readiness_aggregate_sha256", "7" * 64),
            ("pilot_readiness_result_sha256", "6" * 64),
        )
        for field, value in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                fixture = _prepare_fixture(Path(tmp))
                disposition = fixture["disposition"]
                disposition[field] = value
                with self.assertRaises(D3CalibrationDispositionError):
                    validate_calibration_disposition(
                        disposition,
                        pilot_manifest=fixture["manifest"],
                        readiness_aggregate=fixture["aggregate"],
                        readiness_result=fixture["readiness"],
                    )

    def test_quantitative_gate_failure_blocks_composed_selection_before_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = _prepare_fixture(root)
            manifest = fixture["manifest"]
            packet_root = fixture["packet_root"]

            for index in range(7):
                packet = _pilot_packet(
                    index,
                    state="DISAGREE_UNADJUDICATED",
                    primary="INCLUDE",
                    secondary="BORDERLINE",
                    final=None,
                )
                path = packet_root / f"packet-{index:04d}.json"
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
                ] = __import__("hashlib").sha256(raw).hexdigest()

            fixture["paths"]["manifest"].write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            status, public, message = _run_fixture(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_pilot_candidate_overlap_blocks_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            pool = fixture["pool"]
            pool["candidates"][0]["candidate_id"] = (
                "S3-PILOT-FAMILY-0000"
            )
            pool["candidate_pool_commitment"] = candidate_pool_commitment(
                pool,
                POOL_KEY,
            )
            fixture["paths"]["pool"].write_text(
                json.dumps(pool),
                encoding="utf-8",
            )
            attestation = _attestation(fixture["manifest"], pool)
            fixture["paths"]["attestation"].write_text(
                json.dumps(attestation),
                encoding="utf-8",
            )
            status, public, _ = _run_fixture(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)

    def test_namespace_attestation_mutation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            attestation = fixture["attestation"]
            attestation["candidate_pool_commitment"] = "1" * 64
            fixture["paths"]["attestation"].write_text(
                json.dumps(attestation),
                encoding="utf-8",
            )
            status, public, _ = _run_fixture(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)

    def test_wrong_commitment_keys_fail_closed(self) -> None:
        for key_name in ("pilot_key", "pool_key"):
            with self.subTest(key_name=key_name), tempfile.TemporaryDirectory() as tmp:
                fixture = _prepare_fixture(Path(tmp))
                fixture["paths"][key_name].write_bytes(b"wrong-key")
                status, public, _ = _run_fixture(fixture)
                self.assertEqual(status, 1)
                self.assertIsNone(public)

    def test_output_paths_cannot_alias_inputs_or_packet_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            original_pool = fixture["paths"]["pool"].read_bytes()
            status, public, message = run_composed_selection(
                pilot_manifest_path=fixture["paths"]["manifest"],
                packet_root=fixture["packet_root"],
                pilot_key_path=fixture["paths"]["pilot_key"],
                calibration_disposition_path=fixture["paths"]["disposition"],
                candidate_pool_path=fixture["paths"]["pool"],
                pool_key_path=fixture["paths"]["pool_key"],
                identity_namespace_attestation_path=fixture["paths"]["attestation"],
                controlled_output=fixture["paths"]["pool"],
            )
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)
            self.assertEqual(
                fixture["paths"]["pool"].read_bytes(),
                original_pool,
            )

            inside_packets = fixture["packet_root"] / "output.json"
            status, public, _ = run_composed_selection(
                pilot_manifest_path=fixture["paths"]["manifest"],
                packet_root=fixture["packet_root"],
                pilot_key_path=fixture["paths"]["pilot_key"],
                calibration_disposition_path=fixture["paths"]["disposition"],
                candidate_pool_path=fixture["paths"]["pool"],
                pool_key_path=fixture["paths"]["pool_key"],
                identity_namespace_attestation_path=fixture["paths"]["attestation"],
                controlled_output=inside_packets,
            )
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertFalse(inside_packets.exists())

    def test_controlled_diagnostic_write_failure_preserves_generic_public_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp), decision="REJECT")
            bad_error_path = Path(tmp) / "existing-directory"
            bad_error_path.mkdir()
            status, public, message = run_composed_selection(
                pilot_manifest_path=fixture["paths"]["manifest"],
                packet_root=fixture["packet_root"],
                pilot_key_path=fixture["paths"]["pilot_key"],
                calibration_disposition_path=fixture["paths"]["disposition"],
                candidate_pool_path=fixture["paths"]["pool"],
                pool_key_path=fixture["paths"]["pool_key"],
                identity_namespace_attestation_path=fixture["paths"]["attestation"],
                controlled_output=fixture["paths"]["controlled"],
                controlled_error_output=bad_error_path,
            )
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_unexpected_internal_exception_is_publicly_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            secret = "SECRET-CONTROLLED-FAMILY-DETAIL"
            with patch(
                "scripts.execute_pre_g2_d3_challenge_final_selection.execute_composed_selection",
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

    def test_authority_escalation_in_disposition_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            disposition = fixture["disposition"]
            disposition["authority"]["g2_passed"] = True
            with self.assertRaises(D3CalibrationDispositionError):
                validate_calibration_disposition(
                    disposition,
                    pilot_manifest=fixture["manifest"],
                    readiness_aggregate=fixture["aggregate"],
                    readiness_result=fixture["readiness"],
                )

    def test_direct_composed_function_rejects_candidate_pool_bound_to_other_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare_fixture(Path(tmp))
            pool = copy.deepcopy(fixture["pool"])
            pool["human_calibration_disposition_sha256"] = "0" * 64
            pool["candidate_pool_commitment"] = candidate_pool_commitment(
                pool,
                POOL_KEY,
            )
            attestation = _attestation(fixture["manifest"], pool)
            with self.assertRaises(Exception):
                execute_composed_selection(
                    pilot_manifest=fixture["manifest"],
                    packet_root=fixture["packet_root"],
                    pilot_commitment_key=PILOT_KEY,
                    calibration_disposition=fixture["disposition"],
                    candidate_pool=pool,
                    candidate_pool_commitment_key=POOL_KEY,
                    identity_namespace_attestation=attestation,
                )


if __name__ == "__main__":
    unittest.main()
