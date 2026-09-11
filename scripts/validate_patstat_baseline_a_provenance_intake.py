from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIREMENTS_CONTROL_ID = (
    "PATSTAT_BASELINE_A_PROVENANCE_INTAKE_REQUIREMENTS_2026-09-12_v0.1"
)
REQUIREMENTS_GIT_BLOB_SHA = "19178e12b28f2f10729a7ff3cb92261e83bbcb81"
ROMAN_SOURCE_COMMIT = "2a09c02f7ec313a1da929c94a2b4ed6e0e88beb8"
SCIENTIFIC_STATUS_BLOB_SHA = "18c3b4b44f5f5d5381032236d1a696b7c3495fd7"
PATSTAT_EDITION = "Autumn 2025"
POPULATION_UNIT = "DOCDB_SIMPLE_PATENT_FAMILY"

WAITING = "WAITING_FOR_PROVENANCE"
READY = "READY_FOR_SCIENTIFIC_AUDIT"
MISSING = "MISSING"
PROVIDED = "PROVIDED_UNVERIFIED"
VERIFIED = "VERIFIED_RECONSTRUCTIBLE"
COMPONENT_STATES = {MISSING, PROVIDED, VERIFIED}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

TOP_LEVEL_KEYS = {
    "schema_version",
    "intake_id",
    "requirements_control_id",
    "requirements_git_blob_sha",
    "baseline_binding",
    "response_binding",
    "declared_readiness",
    "components",
    "fixed_scientific_boundaries",
    "rights_boundary",
    "authority",
}
BASELINE_KEYS = {
    "roman_source_commit",
    "scientific_status_git_blob_sha",
    "patstat_edition",
    "population_unit",
}
RESPONSE_KEYS = {
    "state",
    "controlled_response_sha256",
    "received_at",
    "source_ref",
}
COMPONENT_KEYS = {
    "state",
    "evidence_manifest_sha256",
    "independent_verification_sha256",
    "required_evidence",
}
FIXED_BOUNDARY = {
    "historical_labels_authority": "MODEL_GENERATED_NOT_HUMAN_GOLD",
    "english_abstract_frame_is_global_patent_population": False,
    "global_population_claim_allowed": False,
    "roman_49671_validated": False,
    "roman_67_percent_retrieval_recall_validated": False,
    "design_unbiasedness_validated": False,
    "reported_interval_validated": False,
    "human_reference_standard_created": False,
}
RIGHTS_BOUNDARY = {
    "rights_issue": 210,
    "rights_clearance": False,
    "scientific_readiness_implies_rights_clearance": False,
}
AUTHORITY = {
    "g0_passed": False,
    "g2_passed": False,
    "g5_passed": False,
    "rights_clearance": False,
    "canonical_scientific_finding": False,
    "benchmark_adequacy_established": False,
    "population_generalization_authority": False,
    "canonical_s2_authority": False,
    "publication_authority": False,
    "phase4_online_first_default_authorized": False,
    "assessment_effect": "NONE",
}


class PatstatProvenanceIntakeError(ValueError):
    """Raised when a sanitized PATSTAT provenance intake status is invalid."""


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PatstatProvenanceIntakeError(f"{field} must be an object")
    return value


def _require_exact_keys(
    value: dict[str, Any],
    expected: set[str],
    field: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PatstatProvenanceIntakeError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PatstatProvenanceIntakeError(
            f"{field} must be a non-empty string"
        )
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PatstatProvenanceIntakeError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def _require_aware_timestamp(value: Any, field: str) -> datetime:
    text = _require_nonempty_string(value, field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PatstatProvenanceIntakeError(
            f"{field} must be an ISO-8601 date-time"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PatstatProvenanceIntakeError(
            f"{field} must include an explicit timezone"
        )
    return parsed


def _load_requirements(
    requirements: dict[str, Any],
) -> dict[str, list[str]]:
    if requirements.get("control_id") != REQUIREMENTS_CONTROL_ID:
        raise PatstatProvenanceIntakeError(
            "requirements control_id mismatch"
        )
    components = _require_mapping(
        requirements.get("component_requirements"),
        "requirements.component_requirements",
    )
    normalized: dict[str, list[str]] = {}
    for component_id, raw_fields in components.items():
        if not isinstance(raw_fields, list) or not raw_fields:
            raise PatstatProvenanceIntakeError(
                f"requirements for {component_id} must be a non-empty list"
            )
        if any(
            not isinstance(item, str) or not item
            for item in raw_fields
        ):
            raise PatstatProvenanceIntakeError(
                f"requirements for {component_id} contain invalid field names"
            )
        if len(raw_fields) != len(set(raw_fields)):
            raise PatstatProvenanceIntakeError(
                f"requirements for {component_id} contain duplicates"
            )
        normalized[component_id] = list(raw_fields)
    if not normalized:
        raise PatstatProvenanceIntakeError(
            "requirements must define at least one component"
        )
    return normalized


def validate_intake_status(
    status: dict[str, Any],
    *,
    requirements: dict[str, Any],
) -> dict[str, Any]:
    """Validate provenance completeness without asserting scientific validity.

    READY_FOR_SCIENTIFIC_AUDIT means only that every mandatory provenance
    component has been supplied and digest-bound. It does not establish that
    the estimator, sampling probabilities, uncertainty calculation, labels,
    rights or headline findings are scientifically valid.
    """

    requirement_fields = _load_requirements(requirements)
    _require_exact_keys(status, TOP_LEVEL_KEYS, "status")
    if status["schema_version"] != "0.1":
        raise PatstatProvenanceIntakeError(
            "status.schema_version must be 0.1"
        )
    _require_nonempty_string(status["intake_id"], "status.intake_id")
    if status["requirements_control_id"] != REQUIREMENTS_CONTROL_ID:
        raise PatstatProvenanceIntakeError(
            "status requirements_control_id mismatch"
        )
    if status["requirements_git_blob_sha"] != REQUIREMENTS_GIT_BLOB_SHA:
        raise PatstatProvenanceIntakeError(
            "status requirements_git_blob_sha mismatch"
        )

    baseline = _require_mapping(
        status["baseline_binding"],
        "status.baseline_binding",
    )
    _require_exact_keys(
        baseline,
        BASELINE_KEYS,
        "status.baseline_binding",
    )
    expected_baseline = {
        "roman_source_commit": ROMAN_SOURCE_COMMIT,
        "scientific_status_git_blob_sha": SCIENTIFIC_STATUS_BLOB_SHA,
        "patstat_edition": PATSTAT_EDITION,
        "population_unit": POPULATION_UNIT,
    }
    if baseline != expected_baseline:
        raise PatstatProvenanceIntakeError(
            "baseline_binding does not match the exact controlled Baseline A lineage"
        )

    components = _require_mapping(
        status["components"],
        "status.components",
    )
    if set(components) != set(requirement_fields):
        raise PatstatProvenanceIntakeError(
            "status components must match the exact requirements component set"
        )

    states: dict[str, str] = {}
    verified_components: list[str] = []
    for component_id, required_fields in requirement_fields.items():
        component = _require_mapping(
            components[component_id],
            f"status.components.{component_id}",
        )
        _require_exact_keys(
            component,
            COMPONENT_KEYS,
            f"status.components.{component_id}",
        )
        state = component["state"]
        if state not in COMPONENT_STATES:
            raise PatstatProvenanceIntakeError(
                f"{component_id}.state is unsupported"
            )
        states[component_id] = state

        evidence = _require_mapping(
            component["required_evidence"],
            f"{component_id}.required_evidence",
        )
        if set(evidence) != set(required_fields):
            raise PatstatProvenanceIntakeError(
                f"{component_id}.required_evidence does not match the requirement contract"
            )
        if any(type(value) is not bool for value in evidence.values()):
            raise PatstatProvenanceIntakeError(
                f"{component_id}.required_evidence values must be booleans"
            )

        evidence_sha = component["evidence_manifest_sha256"]
        verification_sha = component[
            "independent_verification_sha256"
        ]
        all_required_present = all(evidence.values())

        if state == MISSING:
            if all_required_present:
                raise PatstatProvenanceIntakeError(
                    f"{component_id} cannot be MISSING when every required evidence flag is true"
                )
            if evidence_sha is not None:
                _require_sha256(
                    evidence_sha,
                    f"{component_id}.evidence_manifest_sha256",
                )
            if verification_sha is not None:
                raise PatstatProvenanceIntakeError(
                    f"{component_id} MISSING state cannot carry independent verification"
                )
        elif state == PROVIDED:
            if not all_required_present:
                raise PatstatProvenanceIntakeError(
                    f"{component_id} PROVIDED_UNVERIFIED requires every mandatory evidence flag"
                )
            _require_sha256(
                evidence_sha,
                f"{component_id}.evidence_manifest_sha256",
            )
            if verification_sha is not None:
                raise PatstatProvenanceIntakeError(
                    f"{component_id} PROVIDED_UNVERIFIED cannot claim independent verification"
                )
        else:
            if not all_required_present:
                raise PatstatProvenanceIntakeError(
                    f"{component_id} VERIFIED_RECONSTRUCTIBLE requires every mandatory evidence flag"
                )
            _require_sha256(
                evidence_sha,
                f"{component_id}.evidence_manifest_sha256",
            )
            _require_sha256(
                verification_sha,
                f"{component_id}.independent_verification_sha256",
            )
            verified_components.append(component_id)

    response = _require_mapping(
        status["response_binding"],
        "status.response_binding",
    )
    _require_exact_keys(
        response,
        RESPONSE_KEYS,
        "status.response_binding",
    )
    response_state = response["state"]
    if response_state not in {"AWAITING_RESPONSE", "RESPONSE_RECEIVED"}:
        raise PatstatProvenanceIntakeError(
            "response_binding.state is unsupported"
        )
    any_supplied = any(state != MISSING for state in states.values())
    if response_state == "AWAITING_RESPONSE":
        if any_supplied:
            raise PatstatProvenanceIntakeError(
                "AWAITING_RESPONSE cannot coexist with supplied provenance components"
            )
        for field in (
            "controlled_response_sha256",
            "received_at",
            "source_ref",
        ):
            if response[field] is not None:
                raise PatstatProvenanceIntakeError(
                    f"AWAITING_RESPONSE requires response_binding.{field}=null"
                )
    else:
        _require_sha256(
            response["controlled_response_sha256"],
            "response_binding.controlled_response_sha256",
        )
        _require_aware_timestamp(
            response["received_at"],
            "response_binding.received_at",
        )
        _require_nonempty_string(
            response["source_ref"],
            "response_binding.source_ref",
        )

    all_supplied = all(state != MISSING for state in states.values())
    derived_readiness = READY if all_supplied else WAITING
    if status["declared_readiness"] != derived_readiness:
        raise PatstatProvenanceIntakeError(
            "declared_readiness does not match mandatory provenance completeness"
        )

    if status["fixed_scientific_boundaries"] != FIXED_BOUNDARY:
        raise PatstatProvenanceIntakeError(
            "fixed_scientific_boundaries must remain fail-closed"
        )
    if status["rights_boundary"] != RIGHTS_BOUNDARY:
        raise PatstatProvenanceIntakeError(
            "rights_boundary must remain fail-closed"
        )
    if status["authority"] != AUTHORITY:
        raise PatstatProvenanceIntakeError(
            "authority must remain fail-closed"
        )

    return {
        "intake_id": status["intake_id"],
        "readiness": derived_readiness,
        "ready_for_scientific_audit": all_supplied,
        "verified_reconstructible_component_count": len(
            verified_components
        ),
        "mandatory_component_count": len(states),
        "missing_components": sorted(
            component_id
            for component_id, state in states.items()
            if state == MISSING
        ),
        "scientific_validity_established": False,
        "roman_49671_validated": False,
        "roman_67_percent_retrieval_recall_validated": False,
        "rights_clearance": False,
        "g2_passed": False,
        "g5_passed": False,
        "publication_authority": False,
        "assessment_effect": "NONE",
    }


def _load_object(path: Path, field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PatstatProvenanceIntakeError(
            f"{field} root must be an object"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate sanitized PATSTAT Baseline A provenance intake completeness"
    )
    parser.add_argument("status", type=Path)
    parser.add_argument("requirements", type=Path)
    args = parser.parse_args()
    try:
        status = _load_object(args.status, "status")
        requirements = _load_object(args.requirements, "requirements")
        result = validate_intake_status(
            status,
            requirements=requirements,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        PatstatProvenanceIntakeError,
    ) as exc:
        print(f"INVALID: {exc}")
        return 1

    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
