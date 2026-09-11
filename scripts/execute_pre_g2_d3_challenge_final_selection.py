from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from scripts.build_pre_g2_d3_challenge_pilot_readiness import (
    D3ChallengePilotExecutionError,
    derive_readiness_aggregate,
)
from scripts.check_pre_g2_d3_challenge_pilot_final_disjointness import (
    D3ChallengeDisjointnessError,
    compute_disjointness_audit,
)
from scripts.select_pre_g2_d3_challenge_held_out import (
    D3ChallengeSelectionError,
    select_candidates,
)
from scripts.validate_pre_g2_d3_challenge_human_calibration_disposition import (
    D3CalibrationDispositionError,
    PROTOCOL_ID,
    calibration_disposition_sha256,
    canonical_sha256,
    require_approved_calibration_disposition,
)

BENCHMARK_ID = "PRE_G2_PATENT_V0_1"
EXECUTION_TYPE = "D3_CHALLENGE_FINAL_SELECTION_COMPOSED_V0_1"
PUBLIC_CONTROLLED_FAILURE = (
    "INVALID: controlled D3 final-selection preconditions or execution failed under the composed S3 boundary"
)
PUBLIC_INTERNAL_FAILURE = (
    "INVALID: internal D3 final-selection failure contained under the composed S3 boundary"
)

AUTHORITY = {
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


class D3ComposedFinalSelectionError(ValueError):
    """Raised when the composed real-execution path must fail closed."""


def _load_object(path: Path, field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise D3ComposedFinalSelectionError(
            f"{field} root must be an object"
        )
    return payload


def _normalized(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _validate_output_paths(
    *,
    pilot_manifest_path: Path,
    candidate_pool_path: Path,
    disposition_path: Path,
    attestation_path: Path,
    pilot_key_path: Path,
    pool_key_path: Path,
    packet_root: Path,
    controlled_output: Path,
    controlled_error_output: Path | None,
) -> None:
    inputs = {
        _normalized(pilot_manifest_path),
        _normalized(candidate_pool_path),
        _normalized(disposition_path),
        _normalized(attestation_path),
        _normalized(pilot_key_path),
        _normalized(pool_key_path),
    }
    packet_directory = _normalized(packet_root)
    outputs = [_normalized(controlled_output)]
    if controlled_error_output is not None:
        outputs.append(_normalized(controlled_error_output))

    if len(outputs) != len(set(outputs)):
        raise D3ComposedFinalSelectionError(
            "controlled success and error outputs must be distinct"
        )
    if any(output in inputs for output in outputs):
        raise D3ComposedFinalSelectionError(
            "controlled outputs must be distinct from all direct execution inputs"
        )
    if any(_is_within(output, packet_directory) for output in outputs):
        raise D3ComposedFinalSelectionError(
            "controlled outputs must not be written inside the pilot packet directory"
        )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


def _controlled_diagnostic(
    error: BaseException,
    *,
    failure_class: str,
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "execution_type": EXECUTION_TYPE,
        "protocol_id": PROTOCOL_ID,
        "failure_class": failure_class,
        "exception_type": type(error).__name__,
        "controlled_detail": str(error),
        "custody": "S3_CONTROLLED",
        "public_output_authority": False,
        "authority": AUTHORITY,
    }


def execute_composed_selection(
    *,
    pilot_manifest: dict[str, Any],
    packet_root: Path,
    pilot_commitment_key: bytes,
    calibration_disposition: dict[str, Any],
    candidate_pool: dict[str, Any],
    candidate_pool_commitment_key: bytes,
    identity_namespace_attestation: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute all challenge-selection prerequisites before deterministic selection.

    Success verifies one exact quantitative pilot result, one exact human APPROVE
    disposition, the candidate pool's binding to that disposition, and exact
    pilot/pool disjointness from controlled S3 inputs. It still creates no G2,
    benchmark-adequacy, population, publication, or assessment authority.
    """

    readiness_aggregate, readiness_result = derive_readiness_aggregate(
        pilot_manifest,
        packet_root,
        pilot_commitment_key,
    )
    if readiness_result.get("quantitative_gate_passed") is not True:
        raise D3ComposedFinalSelectionError(
            "pilot quantitative gate did not pass"
        )

    disposition_sha = require_approved_calibration_disposition(
        calibration_disposition,
        pilot_manifest=pilot_manifest,
        readiness_aggregate=readiness_aggregate,
        readiness_result=readiness_result,
    )
    if (
        candidate_pool.get("human_calibration_disposition_sha256")
        != disposition_sha
    ):
        raise D3ComposedFinalSelectionError(
            "candidate pool does not bind the exact approved human calibration disposition"
        )

    attestation_sha = canonical_sha256(
        identity_namespace_attestation
    )
    controlled_disjointness, public_disjointness = (
        compute_disjointness_audit(
            pilot_manifest,
            packet_root,
            pilot_commitment_key,
            candidate_pool,
            candidate_pool_commitment_key,
            identity_namespace_attestation,
            attestation_sha,
        )
    )
    if public_disjointness.get("overlap_zero") is not True:
        raise D3ComposedFinalSelectionError(
            "pilot/final candidate-pool overlap is nonzero"
        )

    controlled_selection, selection_aggregate = select_candidates(
        candidate_pool,
        candidate_pool_commitment_key,
    )

    pilot_manifest_sha = canonical_sha256(pilot_manifest)
    readiness_aggregate_sha = canonical_sha256(
        readiness_aggregate
    )
    readiness_result_sha = canonical_sha256(readiness_result)

    controlled_execution = {
        "schema_version": "0.1",
        "execution_type": EXECUTION_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "pilot_round_id": pilot_manifest["pilot_round_id"],
        "pilot_membership_commitment": pilot_manifest[
            "pilot_membership_commitment"
        ],
        "pilot_manifest_sha256": pilot_manifest_sha,
        "pilot_readiness_aggregate_sha256": readiness_aggregate_sha,
        "pilot_readiness_result_sha256": readiness_result_sha,
        "human_calibration_disposition_sha256": disposition_sha,
        "identity_namespace_attestation_sha256": attestation_sha,
        "pilot_final_disjointness_controlled_audit_sha256": public_disjointness[
            "controlled_audit_sha256"
        ],
        "candidate_pool_id": candidate_pool["candidate_pool_id"],
        "candidate_pool_commitment": candidate_pool[
            "candidate_pool_commitment"
        ],
        "execution_preconditions": {
            "pilot_quantitative_gate_verified": True,
            "human_calibration_approval_verified": True,
            "candidate_pool_binds_exact_approval": True,
            "pilot_final_disjointness_verified": True,
            "pilot_final_overlap_zero": True,
        },
        "selection": controlled_selection,
        "disjointness_audit": controlled_disjointness,
        "custody": "S3_CONTROLLED",
        "authority": AUTHORITY,
    }
    controlled_execution_sha = canonical_sha256(
        controlled_execution
    )

    public_summary = {
        "schema_version": "0.1",
        "execution_type": EXECUTION_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "pilot_round_id": pilot_manifest["pilot_round_id"],
        "pilot_membership_commitment": pilot_manifest[
            "pilot_membership_commitment"
        ],
        "pilot_manifest_sha256": pilot_manifest_sha,
        "pilot_readiness_aggregate_sha256": readiness_aggregate_sha,
        "pilot_readiness_result_sha256": readiness_result_sha,
        "human_calibration_disposition_sha256": disposition_sha,
        "identity_namespace_attestation_sha256": attestation_sha,
        "pilot_final_disjointness_controlled_audit_sha256": public_disjointness[
            "controlled_audit_sha256"
        ],
        "controlled_execution_sha256": controlled_execution_sha,
        "candidate_pool_commitment": candidate_pool[
            "candidate_pool_commitment"
        ],
        "execution_preconditions": {
            "pilot_quantitative_gate_verified": True,
            "human_calibration_approval_verified": True,
            "candidate_pool_binds_exact_approval": True,
            "pilot_final_disjointness_verified": True,
            "pilot_final_overlap_zero": True,
        },
        "selection": selection_aggregate,
        "population_generalizable": False,
        "benchmark_adequacy_established": False,
        "g2_passed": False,
        "authority": AUTHORITY,
    }
    return controlled_execution, public_summary


def run_composed_selection(
    *,
    pilot_manifest_path: Path,
    packet_root: Path,
    pilot_key_path: Path,
    calibration_disposition_path: Path,
    candidate_pool_path: Path,
    pool_key_path: Path,
    identity_namespace_attestation_path: Path,
    controlled_output: Path,
    controlled_error_output: Path | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    try:
        _validate_output_paths(
            pilot_manifest_path=pilot_manifest_path,
            candidate_pool_path=candidate_pool_path,
            disposition_path=calibration_disposition_path,
            attestation_path=identity_namespace_attestation_path,
            pilot_key_path=pilot_key_path,
            pool_key_path=pool_key_path,
            packet_root=packet_root,
            controlled_output=controlled_output,
            controlled_error_output=controlled_error_output,
        )
    except D3ComposedFinalSelectionError:
        return 1, None, PUBLIC_CONTROLLED_FAILURE

    try:
        pilot_manifest = _load_object(
            pilot_manifest_path,
            "pilot_manifest",
        )
        calibration_disposition = _load_object(
            calibration_disposition_path,
            "calibration_disposition",
        )
        candidate_pool = _load_object(
            candidate_pool_path,
            "candidate_pool",
        )
        attestation = _load_object(
            identity_namespace_attestation_path,
            "identity_namespace_attestation",
        )
        pilot_key = pilot_key_path.read_bytes()
        pool_key = pool_key_path.read_bytes()
        if not pilot_key or not pool_key:
            raise D3ComposedFinalSelectionError(
                "commitment key files must not be empty"
            )

        controlled, public = execute_composed_selection(
            pilot_manifest=pilot_manifest,
            packet_root=packet_root,
            pilot_commitment_key=pilot_key,
            calibration_disposition=calibration_disposition,
            candidate_pool=candidate_pool,
            candidate_pool_commitment_key=pool_key,
            identity_namespace_attestation=attestation,
        )
        _atomic_write_json(controlled_output, controlled)
        return 0, public, ""
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        D3ChallengePilotExecutionError,
        D3CalibrationDispositionError,
        D3ChallengeDisjointnessError,
        D3ChallengeSelectionError,
        D3ComposedFinalSelectionError,
    ) as exc:
        if controlled_error_output is not None:
            try:
                _atomic_write_json(
                    controlled_error_output,
                    _controlled_diagnostic(
                        exc,
                        failure_class="CONTROLLED_PRECONDITION_OR_SELECTION_FAILURE",
                    ),
                )
            except OSError:
                pass
        return 1, None, PUBLIC_CONTROLLED_FAILURE
    except Exception as exc:
        if controlled_error_output is not None:
            try:
                _atomic_write_json(
                    controlled_error_output,
                    _controlled_diagnostic(
                        exc,
                        failure_class="UNEXPECTED_INTERNAL_FAILURE",
                    ),
                )
            except OSError:
                pass
        return 70, None, PUBLIC_INTERNAL_FAILURE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute the composed PRE-G2 D3 challenge final-selection path"
    )
    parser.add_argument("pilot_manifest", type=Path)
    parser.add_argument("calibration_disposition", type=Path)
    parser.add_argument("candidate_pool", type=Path)
    parser.add_argument("identity_namespace_attestation", type=Path)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument(
        "--pilot-commitment-key-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--candidate-pool-commitment-key-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--controlled-output",
        type=Path,
        required=True,
        help="Required explicit controlled path for membership plus execution audit.",
    )
    parser.add_argument(
        "--controlled-error-output",
        type=Path,
        default=None,
        help="Optional controlled path for detailed failure diagnostics.",
    )
    args = parser.parse_args()

    status, public, public_message = run_composed_selection(
        pilot_manifest_path=args.pilot_manifest,
        packet_root=args.packet_root,
        pilot_key_path=args.pilot_commitment_key_file,
        calibration_disposition_path=args.calibration_disposition,
        candidate_pool_path=args.candidate_pool,
        pool_key_path=args.candidate_pool_commitment_key_file,
        identity_namespace_attestation_path=args.identity_namespace_attestation,
        controlled_output=args.controlled_output,
        controlled_error_output=args.controlled_error_output,
    )
    if public is None:
        print(public_message)
        return status
    print(
        json.dumps(
            public,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
