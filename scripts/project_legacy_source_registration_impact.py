#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from source_namespace_eligibility import (
    DEFAULT_POLICY,
    SAFE_RAW_ACTIONS,
    evaluate_manifest,
    file_sha256,
    load_policy,
    validate_policy,
)
from validate_legacy_source_registration import validate_manifest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"
DEFAULT_SCHEMA = ROOT / "schemas" / "legacy-source-registration-proposals.schema.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "legacy-source-registration-impact"

SAFE_IDENTITY_ACTIONS = SAFE_RAW_ACTIONS
SOURCE_DELTA_ACTIONS = frozenset({"REGISTER_NEW_SOURCE", "REGISTER_MISSING_EXPLICIT_SOURCE"})
REVIEW_DISPOSITIONS = frozenset({"READY_FOR_IDENTITY_REVIEW", "CURATION_REQUIRED"})
MONITORING_DISPOSITION = "UNCLASSIFIED_PENDING_SEPARATE_MONITORING_REVIEW"


class ProjectionError(ValueError):
    pass


def _evidence_key(row: dict[str, Any]) -> str:
    return "::".join(
        (
            str(row.get("system") or "UNRESOLVED_SYSTEM"),
            str(row.get("assessment_version") or "UNRESOLVED_VERSION"),
            str(row.get("evidence_id") or "UNRESOLVED_EVIDENCE"),
        )
    )


def _manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_projection(
    manifest: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    manifest_sha256: str | None = None,
    policy_sha256: str | None = None,
) -> dict[str, Any]:
    if policy is None:
        policy = load_policy()
    validate_policy(policy)
    evaluations = {row["proposal_id"]: row for row in evaluate_manifest(manifest, policy)}

    checkpoint = manifest["derived_from"]
    proposals = manifest["proposals"]
    total_evidence = int(checkpoint["assessment_evidence_count"])
    current_matched = int(checkpoint["deterministic_matched_evidence_count"])
    current_unresolved = int(checkpoint["unresolved_evidence_count"])
    current_sources = int(checkpoint["source_universe_count"])

    all_evidence: dict[str, dict[str, Any]] = {}
    safe_evidence: dict[str, dict[str, Any]] = {}
    unresolved_after: dict[str, dict[str, Any]] = {}
    unresolved_reasons: dict[str, str] = {}
    packet: list[dict[str, Any]] = []

    for proposal in proposals:
        proposal_id = str(proposal["proposal_id"])
        evaluation = evaluations[proposal_id]
        raw_action = str(proposal["action"])
        effective_action = str(evaluation["effective_action"])
        linked = proposal["linked_evidence"]
        proposal_evidence_keys: list[str] = []
        for row in linked:
            key = _evidence_key(row)
            if key in all_evidence:
                raise ProjectionError(f"Evidence {key} appears in more than one proposal")
            all_evidence[key] = row
            proposal_evidence_keys.append(key)
            if effective_action in SAFE_IDENTITY_ACTIONS:
                safe_evidence[key] = row
            else:
                unresolved_after[key] = row
                unresolved_reasons[key] = str(evaluation["eligibility_reason"])

        if effective_action in SAFE_IDENTITY_ACTIONS:
            disposition = "READY_FOR_IDENTITY_REVIEW"
        elif effective_action == "CURATION_REQUIRED":
            disposition = "CURATION_REQUIRED"
        else:
            raise ProjectionError(f"Unsupported effective proposal action {effective_action!r}")

        packet.append(
            {
                "proposal_id": proposal_id,
                "action": raw_action,
                "raw_action": raw_action,
                "effective_action": effective_action,
                "source_namespace_eligible": bool(evaluation["source_namespace_eligible"]),
                "eligibility_rule": evaluation["eligibility_rule"],
                "eligibility_reason": evaluation["eligibility_reason"],
                "matched_ineligible_markers": evaluation["matched_ineligible_markers"],
                "checksum_is_provenance_only": evaluation["checksum_is_provenance_only"],
                "review_disposition": disposition,
                "monitoring_disposition": MONITORING_DISPOSITION,
                "projected_source_universe_delta": 1 if effective_action in SOURCE_DELTA_ACTIONS else 0,
                "projected_newly_joinable_evidence_count": (
                    len(linked) if effective_action in SAFE_IDENTITY_ACTIONS else 0
                ),
                "linked_evidence_keys": proposal_evidence_keys,
                "linked_evidence_ids": [row["evidence_id"] for row in linked],
                "systems": sorted({str(row["system"]) for row in linked}),
                "requested_source_id": proposal.get("requested_source_id"),
                "existing_source_id": proposal.get("existing_source_id"),
                "identity_rule": proposal["identity_rule"],
                "normalized_public_url": proposal.get("normalized_public_url"),
                "checksum": proposal.get("checksum"),
                "impacted_requirement_count": proposal["impacted_requirement_count"],
                "impacted_requirement_ids": proposal["impacted_requirement_ids"],
                "source_boundary_note": proposal["source_boundary_note"],
            }
        )

    if len(all_evidence) != current_unresolved:
        raise ProjectionError(
            f"Proposal manifest represents {len(all_evidence)} unresolved evidence records; checkpoint says {current_unresolved}"
        )

    newly_joinable = len(safe_evidence)
    projected_matched = current_matched + newly_joinable
    if projected_matched > total_evidence:
        raise ProjectionError("Projected matched evidence exceeds assessment evidence total")
    projected_unresolved = total_evidence - projected_matched
    if projected_unresolved != len(unresolved_after):
        raise ProjectionError(
            f"Projected unresolved count {projected_unresolved} does not match curation remainder {len(unresolved_after)}"
        )

    added_sources = sum(1 for row in packet if row["effective_action"] in SOURCE_DELTA_ACTIONS)
    projected_sources = current_sources + added_sources
    raw_action_counts = Counter(str(proposal["action"]) for proposal in proposals)
    effective_action_counts = Counter(str(row["effective_action"]) for row in packet)
    disposition_counts = Counter(str(row["review_disposition"]) for row in packet)
    remaining = [
        {
            "evidence_key": key,
            "system": row.get("system"),
            "assessment_version": row.get("assessment_version"),
            "evidence_id": row.get("evidence_id"),
            "title": row.get("title"),
            "reason": unresolved_reasons[key],
        }
        for key, row in sorted(unresolved_after.items())
    ]

    projection = {
        "schema_version": "0.2.0",
        "artifact": "legacy_assessment_source_registration_impact",
        "status": "NONCANONICAL_PROJECTION",
        "scenario_only": True,
        "source_manifest": {
            "artifact": manifest["artifact"],
            "status": manifest["status"],
            "sha256": manifest_sha256,
            "interpretation": "MECHANICAL_EXACT_IDENTITY_CANDIDATE_LAYER",
        },
        "source_namespace_policy": {
            "artifact": policy["artifact"],
            "status": policy["status"],
            "precedence": policy["precedence"],
            "sha256": policy_sha256,
        },
        "current_state": {
            "effective_source_count": current_sources,
            "assessment_evidence_count": total_evidence,
            "deterministically_matched_evidence_count": current_matched,
            "unresolved_evidence_count": current_unresolved,
        },
        "candidate_state": {
            "exact_key_candidate_evidence_count": int(checkpoint["registration_eligible_evidence_count"]),
            "source_namespace_eligible_exact_key_evidence_count": sum(
                len(row["linked_evidence_ids"])
                for row in packet
                if row["raw_action"] == "REGISTER_NEW_SOURCE" and row["source_namespace_eligible"]
            ),
        },
        "proposal_state": {
            "proposal_count": len(proposals),
            "raw_action_counts": {key: raw_action_counts[key] for key in sorted(raw_action_counts)},
            "effective_action_counts": {key: effective_action_counts[key] for key in sorted(effective_action_counts)},
            "review_disposition_counts": {key: disposition_counts[key] for key in sorted(disposition_counts)},
            "identity_safe_proposal_count": sum(
                1 for row in packet if row["review_disposition"] == "READY_FOR_IDENTITY_REVIEW"
            ),
            "curation_required_proposal_count": sum(
                1 for row in packet if row["review_disposition"] == "CURATION_REQUIRED"
            ),
        },
        "full_identity_safe_acceptance_scenario": {
            "scenario_label": "IF_ALL_IDENTITY_SAFE_PROPOSALS_ARE_LATER_ACCEPTED_BY_AUTHORIZED_REVIEW",
            "newly_joinable_evidence_count": newly_joinable,
            "projected_deterministically_matched_evidence_count": projected_matched,
            "projected_unresolved_evidence_count": projected_unresolved,
            "projected_joinability": {"numerator": projected_matched, "denominator": total_evidence},
            "projected_added_source_identity_count": added_sources,
            "projected_effective_source_count": projected_sources,
            "canonical_status": "SCENARIO_ONLY_NOT_CURRENT_CANONICAL_DATA",
        },
        "remaining_unresolved_evidence": remaining,
        "review_packet": packet,
        "monitoring_boundary": (
            "Source registration and source identity review do not classify monitoring cadence. Every proposal remains "
            f"{MONITORING_DISPOSITION} until a separate monitoring review is performed."
        ),
        "authority_boundary": (
            "READY_FOR_IDENTITY_REVIEW is a technical review disposition only. Source-namespace eligibility is evaluated "
            "after exact artifact identity. This projection does not approve, accept, publish, or canonically register any "
            "source and does not modify historical assessments."
        ),
    }
    validate_projection(projection)
    return projection


def validate_projection(projection: dict[str, Any]) -> None:
    if projection.get("status") != "NONCANONICAL_PROJECTION" or projection.get("scenario_only") is not True:
        raise ProjectionError("Projection must remain explicitly noncanonical and scenario-only")
    policy = projection.get("source_namespace_policy")
    if not isinstance(policy, dict) or policy.get("status") != "NONCANONICAL_POLICY":
        raise ProjectionError("Projection must carry a noncanonical source-namespace policy")
    if policy.get("precedence") != "SOURCE_NAMESPACE_ELIGIBILITY_OVERRIDES_MECHANICAL_REGISTRATION_ACTION":
        raise ProjectionError("Projection does not enforce source-namespace policy precedence")
    packet = projection.get("review_packet")
    if not isinstance(packet, list) or not packet:
        raise ProjectionError("Projection review packet must be a non-empty list")
    dispositions = {str(row.get("review_disposition")) for row in packet}
    if not dispositions.issubset(REVIEW_DISPOSITIONS):
        raise ProjectionError(f"Unsupported review disposition(s): {sorted(dispositions - REVIEW_DISPOSITIONS)}")
    if any(row.get("monitoring_disposition") != MONITORING_DISPOSITION for row in packet):
        raise ProjectionError("Monitoring cadence must remain unclassified in identity review")
    requested_ids = sorted({str(row["requested_source_id"]) for row in packet if row.get("requested_source_id")})
    if requested_ids != ["SRC-PR-011"]:
        raise ProjectionError(f"Unexpected requested source IDs in projection: {requested_ids}")
    for row in packet:
        if row["raw_action"] == "REGISTER_NEW_SOURCE" and (
            row.get("requested_source_id") or row.get("existing_source_id")
        ):
            raise ProjectionError("New-source candidate received a canonical source identity")
        if row["effective_action"] == "CURATION_REQUIRED" and row["projected_source_universe_delta"] != 0:
            raise ProjectionError("Curation-required proposal must not increase the projected source universe")

    scenario = projection.get("full_identity_safe_acceptance_scenario")
    current = projection.get("current_state")
    if not isinstance(scenario, dict) or not isinstance(current, dict):
        raise ProjectionError("Projection missing current/scenario state")
    if scenario.get("canonical_status") != "SCENARIO_ONLY_NOT_CURRENT_CANONICAL_DATA":
        raise ProjectionError("Projected source/evidence counts must be labelled scenario-only")
    expected = int(current["deterministically_matched_evidence_count"]) + int(scenario["newly_joinable_evidence_count"])
    if int(scenario["projected_deterministically_matched_evidence_count"]) != expected:
        raise ProjectionError("Projected matched evidence is not derived from current + newly joinable evidence")
    if int(scenario["projected_effective_source_count"]) != int(current["effective_source_count"]) + int(
        scenario["projected_added_source_identity_count"]
    ):
        raise ProjectionError("Projected source universe is not derived from current + proposed source delta")


def render_markdown(projection: dict[str, Any]) -> str:
    current = projection["current_state"]
    candidates = projection["candidate_state"]
    scenario = projection["full_identity_safe_acceptance_scenario"]
    lines = [
        "# Legacy source-registration impact projection",
        "",
        "**NONCANONICAL PROJECTION — scenario only. No source registration is approved or published by this artifact.**",
        "",
        "## Current state",
        "",
        f"- Effective source universe: {current['effective_source_count']}",
        f"- Assessment evidence: {current['assessment_evidence_count']}",
        f"- Deterministically joined: {current['deterministically_matched_evidence_count']}",
        f"- Unresolved: {current['unresolved_evidence_count']}",
        "",
        "## Candidate vs namespace-eligible evidence",
        "",
        f"- Exact-key candidate evidence: {candidates['exact_key_candidate_evidence_count']}",
        f"- Source-namespace-eligible exact-key evidence: {candidates['source_namespace_eligible_exact_key_evidence_count']}",
        "",
        "## Full identity-safe acceptance scenario",
        "",
        f"- Newly joinable evidence: {scenario['newly_joinable_evidence_count']}",
        f"- Projected deterministic joinability: {scenario['projected_deterministically_matched_evidence_count']}/{scenario['projected_joinability']['denominator']}",
        f"- Projected unresolved evidence: {scenario['projected_unresolved_evidence_count']}",
        f"- Projected added source identities: {scenario['projected_added_source_identity_count']}",
        f"- Projected effective source universe: {scenario['projected_effective_source_count']} (scenario only)",
        "",
        "## Review packet",
        "",
        "| Proposal | Raw action | Effective action | Namespace eligible | Review disposition | Evidence unlocked | Systems | Requested source ID | Monitoring |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for row in projection["review_packet"]:
        lines.append(
            f"| {row['proposal_id']} | {row['raw_action']} | {row['effective_action']} | "
            f"{row['source_namespace_eligible']} | {row['review_disposition']} | "
            f"{row['projected_newly_joinable_evidence_count']} | {', '.join(row['systems'])} | "
            f"{row.get('requested_source_id') or '—'} | {row['monitoring_disposition']} |"
        )
    lines.extend(["", "## Remaining unresolved evidence", ""])
    for row in projection["remaining_unresolved_evidence"]:
        lines.append(f"- {row['system']} {row['evidence_id']}: {row['reason']}")
    lines.extend(["", projection["authority_boundary"], "", projection["monitoring_boundary"], ""])
    return "\n".join(lines)


def write_outputs(projection: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "legacy-source-registration-impact.json"
    markdown_path = output_dir / "legacy-source-registration-impact.md"
    json_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(projection), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project noncanonical impact of identity-safe legacy source registrations")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--namespace-policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_manifest(manifest, schema)
    policy = load_policy(args.namespace_policy)
    projection = build_projection(
        manifest,
        policy=policy,
        manifest_sha256=_manifest_sha256(args.manifest),
        policy_sha256=file_sha256(args.namespace_policy),
    )
    outputs = write_outputs(projection, args.output_dir)
    scenario = projection["full_identity_safe_acceptance_scenario"]
    print(
        "projected joinability: "
        f"{scenario['projected_deterministically_matched_evidence_count']}/"
        f"{scenario['projected_joinability']['denominator']} | "
        f"remaining unresolved: {scenario['projected_unresolved_evidence_count']} | "
        f"projected sources: {scenario['projected_effective_source_count']} (scenario only)"
    )
    print(f"JSON: {outputs['json']}")
    print(f"Markdown: {outputs['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
