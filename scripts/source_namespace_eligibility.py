#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "curation" / "source_namespace_eligibility_policy_v0.1.json"
SAFE_RAW_ACTIONS = frozenset({"REGISTER_NEW_SOURCE", "REGISTER_MISSING_EXPLICIT_SOURCE", "REUSE_EXISTING_SOURCE"})
EFFECTIVE_ACTIONS = frozenset({*SAFE_RAW_ACTIONS, "CURATION_REQUIRED"})


class NamespaceEligibilityError(ValueError):
    pass


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    validate_policy(policy)
    return policy


def _normalized_markers(row: dict[str, Any]) -> set[str]:
    markers: set[str] = set()
    for field in ("evidence_type", "evidence_class", "source_label", "publication_state"):
        value = row.get(field)
        if value:
            markers.add(str(value).strip().upper())
    return markers


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema_version") != "0.1.0":
        raise NamespaceEligibilityError("Unsupported source-namespace policy schema version")
    if policy.get("artifact") != "source_namespace_eligibility_policy":
        raise NamespaceEligibilityError("Unexpected source-namespace policy artifact")
    if policy.get("status") != "NONCANONICAL_POLICY":
        raise NamespaceEligibilityError("Source-namespace eligibility policy must remain noncanonical")
    if policy.get("precedence") != "SOURCE_NAMESPACE_ELIGIBILITY_OVERRIDES_MECHANICAL_REGISTRATION_ACTION":
        raise NamespaceEligibilityError("Source-namespace policy precedence is not explicit")
    markers = policy.get("ineligible_evidence_markers")
    if not isinstance(markers, list) or not markers or any(not isinstance(item, str) or not item.strip() for item in markers):
        raise NamespaceEligibilityError("Source-namespace policy requires non-empty ineligible evidence markers")
    overrides = policy.get("action_overrides")
    if not isinstance(overrides, dict):
        raise NamespaceEligibilityError("Source-namespace policy action_overrides must be an object")
    for proposal_id, override in overrides.items():
        if not isinstance(proposal_id, str) or not isinstance(override, dict):
            raise NamespaceEligibilityError("Invalid source-namespace action override")
        if override.get("effective_action") not in EFFECTIVE_ACTIONS:
            raise NamespaceEligibilityError(f"Unsupported effective action for {proposal_id}")
        if not override.get("reason"):
            raise NamespaceEligibilityError(f"Missing source-namespace override reason for {proposal_id}")
    checkpoint = policy.get("expected_checkpoint")
    if not isinstance(checkpoint, dict):
        raise NamespaceEligibilityError("Source-namespace policy requires expected_checkpoint")
    if checkpoint.get("exact_key_candidate_evidence_count") != 35:
        raise NamespaceEligibilityError("Exact-key candidate checkpoint must preserve the verified count of 35")
    if checkpoint.get("source_namespace_eligible_exact_key_evidence_count") != 34:
        raise NamespaceEligibilityError("Source-namespace-eligible exact-key checkpoint must be 34")


def evaluate_proposal(proposal: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    validate_policy(policy)
    proposal_id = str(proposal.get("proposal_id") or "")
    raw_action = str(proposal.get("action") or "")
    if raw_action not in EFFECTIVE_ACTIONS:
        raise NamespaceEligibilityError(f"Unsupported raw proposal action {raw_action!r} for {proposal_id}")
    linked = proposal.get("linked_evidence")
    if not isinstance(linked, list) or not linked or any(not isinstance(row, dict) for row in linked):
        raise NamespaceEligibilityError(f"Proposal {proposal_id} has no valid linked evidence")

    configured_markers = {str(item).strip().upper() for item in policy["ineligible_evidence_markers"]}
    matched_markers = sorted(
        marker
        for row in linked
        for marker in configured_markers
        if any(marker in candidate for candidate in _normalized_markers(row))
    )
    override = policy["action_overrides"].get(proposal_id)

    # Namespace eligibility is a monotone safety gate: it can demote a mechanically
    # registerable candidate, but it cannot promote a record that the mechanical
    # layer already sent to curation. Preserve the original causal reason in that
    # case even if the evidence also carries an ineligible namespace marker.
    if raw_action == "CURATION_REQUIRED":
        if override is not None and override.get("effective_action") != "CURATION_REQUIRED":
            raise NamespaceEligibilityError(
                f"Policy override for {proposal_id} cannot promote mechanical curation into the source namespace"
            )
        effective_action = "CURATION_REQUIRED"
        rule = "MECHANICAL_CURATION_REMAINS_CURATION"
        reason = "MECHANICAL_CURATION_REQUIRED"
    elif matched_markers:
        effective_action = "CURATION_REQUIRED"
        rule = "INELIGIBLE_ASSESSMENT_LOCAL_EVIDENCE_CLASS"
        reason = "ASSESSMENT_LOCAL_CONTROLLED_ADJUDICATION"
        if override is not None:
            if override.get("effective_action") != effective_action:
                raise NamespaceEligibilityError(
                    f"Policy override for {proposal_id} conflicts with ineligible evidence marker"
                )
            reason = str(override["reason"])
    elif override is not None:
        effective_action = str(override["effective_action"])
        rule = "EXPLICIT_POLICY_OVERRIDE"
        reason = str(override["reason"])
    else:
        effective_action = raw_action
        rule = "MECHANICAL_ACTION_PASSES_NAMESPACE_GATE"
        reason = "SOURCE_NAMESPACE_ELIGIBLE_BY_POLICY"

    source_namespace_eligible = effective_action in SAFE_RAW_ACTIONS
    return {
        "proposal_id": proposal_id,
        "raw_action": raw_action,
        "effective_action": effective_action,
        "source_namespace_eligible": source_namespace_eligible,
        "eligibility_rule": rule,
        "eligibility_reason": reason,
        "matched_ineligible_markers": sorted(set(matched_markers)),
        "checksum_is_provenance_only": bool(override and override.get("checksum_is_provenance_only")),
    }


def evaluate_manifest(manifest: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    validate_policy(policy)
    proposals = manifest.get("proposals")
    if not isinstance(proposals, list) or not proposals:
        raise NamespaceEligibilityError("Proposal manifest must contain proposals")
    evaluations = [evaluate_proposal(proposal, policy) for proposal in proposals]
    ids = [row["proposal_id"] for row in evaluations]
    if len(ids) != len(set(ids)):
        raise NamespaceEligibilityError("Proposal manifest contains duplicate proposal IDs")
    return evaluations


if __name__ == "__main__":
    loaded = load_policy()
    print(json.dumps(loaded, indent=2, sort_keys=True))
