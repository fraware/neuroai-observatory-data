#!/usr/bin/env python3
"""Build a noncanonical human-review queue for legacy source remediation.

This queue composes three already-separated technical layers:

1. exact artifact/source-identity proposals;
2. source-namespace eligibility;
3. prospective monitoring classification.

It does not approve a source, assign a new canonical source ID, create a monitor,
or publish a successor source universe. Human/institutional decisions remain
outside this generator.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from project_legacy_source_monitoring import (
    DEFAULT_MANIFEST,
    DEFAULT_SCHEMA,
    build_projection as build_monitoring_projection,
)
from source_namespace_eligibility import DEFAULT_POLICY, evaluate_manifest, file_sha256, load_policy
from validate_legacy_source_registration import validate_manifest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "legacy-source-promotion-readiness"

STATIC_LANE = "STATIC_IDENTITY_AND_METADATA_REVIEW"
LIVE_LANE = "LIVE_SOURCE_REFRESH_REQUIRED"
CURATION_LANE = "CURATION_REQUIRED"
LANES = frozenset({STATIC_LANE, LIVE_LANE, CURATION_LANE})
APPROVAL_STATUS = "NOT_APPROVED"
CANONICAL_STATUS = "NOT_CANONICAL"
HUMAN_REVIEW_STATUS = "UNREVIEWED"
EXPECTED_QUEUE_ROWS = 35
EXPECTED_LANE_COUNTS = {
    STATIC_LANE: 22,
    LIVE_LANE: 11,
    CURATION_LANE: 2,
}
EXPECTED_MONITORING_COUNTS = {
    "ARCHIVAL_STATIC": 22,
    "ON_CHANGE": 7,
    "RECURRING": 4,
}


class PromotionReadinessError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _linked_identity(proposal: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    linked = proposal.get("linked_evidence")
    if not isinstance(linked, list) or not linked or any(not isinstance(row, dict) for row in linked):
        raise PromotionReadinessError(f"Proposal {proposal.get('proposal_id')!r} has invalid linked evidence")
    systems = sorted({_text(row.get("system")) for row in linked if _text(row.get("system"))})
    evidence_ids = [_text(row.get("evidence_id")) for row in linked]
    scoped_evidence_ids = [f"{_text(row.get('system'))}:{_text(row.get('evidence_id'))}" for row in linked]
    if any(not value for value in evidence_ids) or any(value.startswith(":") or value.endswith(":") for value in scoped_evidence_ids):
        raise PromotionReadinessError(f"Proposal {proposal.get('proposal_id')!r} has incomplete evidence identity")
    if len(scoped_evidence_ids) != len(set(scoped_evidence_ids)):
        raise PromotionReadinessError(f"Proposal {proposal.get('proposal_id')!r} repeats assessment-scoped evidence")
    return systems, evidence_ids, scoped_evidence_ids


def _lane_for(*, eligible: bool, monitoring_mode: str | None) -> tuple[str, str, str]:
    if not eligible:
        if monitoring_mode is not None:
            raise PromotionReadinessError("Source-namespace-ineligible proposal cannot carry monitoring classification")
        return (
            CURATION_LANE,
            "NOT_APPLICABLE",
            "Human curation must resolve source-namespace eligibility or missing deterministic identity before any promotion or monitoring decision.",
        )
    if monitoring_mode == "ARCHIVAL_STATIC":
        return (
            STATIC_LANE,
            "NOT_REQUIRED",
            "Review exact captured artifact identity, metadata, source class, claim boundary, and provenance for future successor-source promotion.",
        )
    if monitoring_mode in {"ON_CHANGE", "RECURRING"}:
        return (
            LIVE_LANE,
            "REQUIRED",
            "Perform a fresh retrieval/capture and review current metadata, source class, claim boundary, and provenance before any successor-source promotion decision.",
        )
    raise PromotionReadinessError(f"Eligible proposal has unsupported monitoring mode {monitoring_mode!r}")


def build_queue(
    manifest: dict[str, Any],
    policy: dict[str, Any],
    *,
    manifest_sha256: str | None = None,
    policy_sha256: str | None = None,
) -> dict[str, Any]:
    if manifest.get("artifact") != "legacy_assessment_source_registration_proposals":
        raise PromotionReadinessError("Unexpected legacy source-registration manifest")
    proposals = manifest.get("proposals")
    if not isinstance(proposals, list) or len(proposals) != EXPECTED_QUEUE_ROWS:
        raise PromotionReadinessError(f"Expected exactly {EXPECTED_QUEUE_ROWS} remediation proposals")

    namespace_rows = evaluate_manifest(manifest, policy)
    namespace_by_id = {row["proposal_id"]: row for row in namespace_rows}
    if len(namespace_by_id) != EXPECTED_QUEUE_ROWS:
        raise PromotionReadinessError("Namespace evaluation does not cover all remediation proposals exactly once")

    monitoring_projection = build_monitoring_projection(
        manifest,
        policy,
        manifest_sha256=manifest_sha256,
        policy_sha256=policy_sha256,
    )
    monitoring_rows = monitoring_projection["sources"]
    if not isinstance(monitoring_rows, list):
        raise PromotionReadinessError("Prospective monitoring projection has invalid source rows")
    monitoring_by_id = {row["proposal_id"]: row for row in monitoring_rows}
    if len(monitoring_by_id) != len(monitoring_rows):
        raise PromotionReadinessError("Prospective monitoring projection contains duplicate proposal IDs")

    excluded_by_id = {
        row["proposal_id"]: row for row in monitoring_projection.get("excluded_curation_holds", [])
    }
    if set(monitoring_by_id) & set(excluded_by_id):
        raise PromotionReadinessError("Proposal appears in both monitoring and curation-hold populations")
    if set(monitoring_by_id) | set(excluded_by_id) != set(namespace_by_id):
        raise PromotionReadinessError("Identity, namespace, and monitoring layers disagree on proposal population")

    queue_rows: list[dict[str, Any]] = []
    seen_scoped_evidence: set[str] = set()
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise PromotionReadinessError("Proposal entries must be objects")
        proposal_id = _text(proposal.get("proposal_id"))
        if not proposal_id or proposal_id not in namespace_by_id:
            raise PromotionReadinessError(f"Missing namespace evaluation for {proposal_id!r}")
        namespace = namespace_by_id[proposal_id]
        eligible = bool(namespace["source_namespace_eligible"])
        monitoring = monitoring_by_id.get(proposal_id)
        if eligible != (monitoring is not None):
            raise PromotionReadinessError(
                f"Namespace/monitoring disagreement for {proposal_id}: eligible={eligible} monitoring={monitoring is not None}"
            )
        if not eligible and proposal_id not in excluded_by_id:
            raise PromotionReadinessError(f"Ineligible proposal {proposal_id} is missing from monitoring curation holds")

        systems, evidence_ids, scoped_evidence_ids = _linked_identity(proposal)
        overlap = seen_scoped_evidence.intersection(scoped_evidence_ids)
        if overlap:
            raise PromotionReadinessError(f"Assessment-scoped evidence appears across multiple proposals: {sorted(overlap)}")
        seen_scoped_evidence.update(scoped_evidence_ids)

        raw_action = _text(proposal.get("action"))
        effective_action = _text(namespace.get("effective_action"))
        monitoring_mode = _text(monitoring.get("monitoring_mode")) if monitoring else None
        lane, refresh_status, next_action = _lane_for(eligible=eligible, monitoring_mode=monitoring_mode)

        requested_source_id = proposal.get("requested_source_id")
        existing_source_id = proposal.get("existing_source_id")
        if effective_action == "REGISTER_NEW_SOURCE" and (requested_source_id or existing_source_id):
            raise PromotionReadinessError(f"New-source proposal {proposal_id} carries a canonical source ID")
        if requested_source_id and requested_source_id != "SRC-PR-011":
            raise PromotionReadinessError(f"Unexpected requested source ID {requested_source_id!r}")

        impacted_requirement_ids = proposal.get("impacted_requirement_ids")
        if not isinstance(impacted_requirement_ids, list) or any(not isinstance(item, str) for item in impacted_requirement_ids):
            raise PromotionReadinessError(f"Proposal {proposal_id} has invalid impacted requirement IDs")
        impacted_requirement_count = proposal.get("impacted_requirement_count")
        if impacted_requirement_count != len(impacted_requirement_ids):
            raise PromotionReadinessError(f"Proposal {proposal_id} impacted requirement count disagrees with IDs")

        queue_rows.append(
            {
                "proposal_id": proposal_id,
                "systems": systems,
                "linked_evidence_ids": evidence_ids,
                "assessment_scoped_evidence_ids": scoped_evidence_ids,
                "raw_source_action": raw_action,
                "effective_source_action": effective_action,
                "source_namespace_eligible": eligible,
                "source_namespace_rule": namespace.get("eligibility_rule"),
                "source_namespace_reason": namespace.get("eligibility_reason"),
                "matched_ineligible_markers": namespace.get("matched_ineligible_markers", []),
                "prospective_source_identity_key": (
                    monitoring.get("prospective_source_identity_key") if monitoring else None
                ),
                "existing_source_id": existing_source_id,
                "requested_source_id": requested_source_id,
                "normalized_public_url": proposal.get("normalized_public_url"),
                "checksum": proposal.get("checksum"),
                "identity_rule": proposal.get("identity_rule"),
                "identity_rationale": proposal.get("identity_rationale"),
                "monitoring_mode": monitoring_mode,
                "recommended_interval": monitoring.get("recommended_interval") if monitoring else None,
                "monitoring_priority": monitoring.get("priority") if monitoring else None,
                "monitoring_rule": monitoring.get("rule") if monitoring else None,
                "monitoring_reason": monitoring.get("reason") if monitoring else None,
                "review_lane": lane,
                "refresh_status": refresh_status,
                "required_next_action": next_action,
                "impacted_requirement_count": impacted_requirement_count,
                "impacted_requirement_ids": impacted_requirement_ids,
                "source_boundary_note": proposal.get("source_boundary_note"),
                "approval_status": APPROVAL_STATUS,
                "canonical_status": CANONICAL_STATUS,
                "human_review_status": HUMAN_REVIEW_STATUS,
                "reviewer_identity": None,
                "decision_record_id": None,
            }
        )

    queue_rows.sort(key=lambda row: row["proposal_id"])
    lane_counts = Counter(row["review_lane"] for row in queue_rows)
    monitoring_counts = Counter(row["monitoring_mode"] for row in queue_rows if row["monitoring_mode"])
    payload = {
        "schema_version": "0.1.0",
        "artifact": "legacy_source_promotion_readiness_queue",
        "status": "NONCANONICAL_REVIEW_QUEUE",
        "approval_status": APPROVAL_STATUS,
        "canonical_status": CANONICAL_STATUS,
        "human_review_status": HUMAN_REVIEW_STATUS,
        "source_manifest": {
            "artifact": manifest.get("artifact"),
            "status": manifest.get("status"),
            "sha256": manifest_sha256,
        },
        "source_namespace_policy": {
            "artifact": policy.get("artifact"),
            "status": policy.get("status"),
            "sha256": policy_sha256,
        },
        "current_canonical_checkpoint": {
            "effective_source_count": 248,
            "monitor_registry_source_count": 224,
            "unmonitored_effective_source_count": 24,
            "mutated_by_this_queue": False,
        },
        "queue_checkpoint": {
            "queue_row_count": len(queue_rows),
            "linked_unresolved_evidence_row_count": len(seen_scoped_evidence),
            "lane_counts": dict(sorted(lane_counts.items())),
            "eligible_monitoring_mode_counts": dict(sorted(monitoring_counts.items())),
        },
        "rows": queue_rows,
        "authority_boundary": (
            "This artifact is a technical promotion-readiness queue only. It records no approval, acceptance, "
            "canonical publication, source registration, monitor creation, reviewer identity, or institutional decision."
        ),
    }
    validate_queue(payload)
    return payload


def validate_queue(payload: dict[str, Any]) -> None:
    if payload.get("status") != "NONCANONICAL_REVIEW_QUEUE":
        raise PromotionReadinessError("Promotion-readiness queue must remain explicitly noncanonical")
    if payload.get("approval_status") != APPROVAL_STATUS or payload.get("canonical_status") != CANONICAL_STATUS:
        raise PromotionReadinessError("Promotion-readiness queue crossed approval/canonical authority boundary")
    if payload.get("human_review_status") != HUMAN_REVIEW_STATUS:
        raise PromotionReadinessError("Promotion-readiness queue cannot fabricate completed human review")
    if payload.get("current_canonical_checkpoint") != {
        "effective_source_count": 248,
        "monitor_registry_source_count": 224,
        "unmonitored_effective_source_count": 24,
        "mutated_by_this_queue": False,
    }:
        raise PromotionReadinessError("Promotion-readiness queue changed the canonical data/monitoring checkpoint")

    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_QUEUE_ROWS:
        raise PromotionReadinessError(f"Promotion-readiness queue must contain {EXPECTED_QUEUE_ROWS} rows")
    if len({row.get("proposal_id") for row in rows}) != EXPECTED_QUEUE_ROWS:
        raise PromotionReadinessError("Promotion-readiness queue proposal IDs are not unique")
    if any(row.get("review_lane") not in LANES for row in rows):
        raise PromotionReadinessError("Promotion-readiness queue contains an unsupported lane")

    lane_counts = Counter(row["review_lane"] for row in rows)
    if dict(lane_counts) != EXPECTED_LANE_COUNTS:
        raise PromotionReadinessError(f"Unexpected review-lane counts: {dict(lane_counts)}")
    monitoring_counts = Counter(row["monitoring_mode"] for row in rows if row.get("monitoring_mode"))
    if dict(monitoring_counts) != EXPECTED_MONITORING_COUNTS:
        raise PromotionReadinessError(f"Unexpected monitoring-mode counts: {dict(monitoring_counts)}")

    for row in rows:
        lane = row["review_lane"]
        if row.get("approval_status") != APPROVAL_STATUS or row.get("canonical_status") != CANONICAL_STATUS:
            raise PromotionReadinessError(f"Queue row {row.get('proposal_id')} contains approval/canonical state")
        if row.get("human_review_status") != HUMAN_REVIEW_STATUS:
            raise PromotionReadinessError(f"Queue row {row.get('proposal_id')} fabricates human review state")
        if row.get("reviewer_identity") is not None or row.get("decision_record_id") is not None:
            raise PromotionReadinessError(f"Queue row {row.get('proposal_id')} fabricates reviewer/decision identity")
        if row.get("effective_source_action") == "REGISTER_NEW_SOURCE" and (
            row.get("requested_source_id") or row.get("existing_source_id")
        ):
            raise PromotionReadinessError(f"Queue row {row.get('proposal_id')} mints/attaches a source ID")
        if lane == STATIC_LANE:
            if row.get("source_namespace_eligible") is not True or row.get("monitoring_mode") != "ARCHIVAL_STATIC":
                raise PromotionReadinessError("Static-review lane disagrees with namespace/monitoring layers")
            if row.get("refresh_status") != "NOT_REQUIRED":
                raise PromotionReadinessError("Static-review lane cannot require freshness retrieval")
        elif lane == LIVE_LANE:
            if row.get("source_namespace_eligible") is not True or row.get("monitoring_mode") not in {
                "ON_CHANGE",
                "RECURRING",
            }:
                raise PromotionReadinessError("Live-refresh lane disagrees with namespace/monitoring layers")
            if row.get("refresh_status") != "REQUIRED":
                raise PromotionReadinessError("Live-refresh lane must require a fresh capture")
        else:
            if row.get("source_namespace_eligible") is not False or row.get("monitoring_mode") is not None:
                raise PromotionReadinessError("Curation lane cannot carry eligible monitoring classification")
            if row.get("refresh_status") != "NOT_APPLICABLE":
                raise PromotionReadinessError("Curation lane must keep refresh status not applicable")

    requested = sorted(row["requested_source_id"] for row in rows if row.get("requested_source_id"))
    if requested != ["SRC-PR-011"]:
        raise PromotionReadinessError(f"Unexpected historically explicit requested source IDs: {requested}")
    curation_evidence = {
        scoped
        for row in rows
        if row["review_lane"] == CURATION_LANE
        for scoped in row["assessment_scoped_evidence_ids"]
    }
    if curation_evidence != {"BrainGate2 T15:EV-T15-012", "FDA adaptive DBS:EV-15"}:
        raise PromotionReadinessError(f"Unexpected curation-hold evidence: {sorted(curation_evidence)}")


def render_markdown(payload: dict[str, Any]) -> str:
    checkpoint = payload["queue_checkpoint"]
    current = payload["current_canonical_checkpoint"]
    lines = [
        "# Legacy source promotion-readiness queue",
        "",
        "**NONCANONICAL REVIEW QUEUE — no approval, source registration, monitor creation, or canonical publication is recorded.**",
        "",
        "## Checkpoint",
        "",
        f"- Queue rows: {checkpoint['queue_row_count']}",
        f"- Linked unresolved evidence rows: {checkpoint['linked_unresolved_evidence_row_count']}",
        f"- Current canonical sources: {current['effective_source_count']}",
        f"- Current monitored sources: {current['monitor_registry_source_count']}",
        f"- Current unmonitored effective sources: {current['unmonitored_effective_source_count']}",
    ]
    for lane, count in checkpoint["lane_counts"].items():
        lines.append(f"- {lane}: {count}")
    lines.extend(
        [
            "",
            "## Queue",
            "",
            "| Proposal | Systems | Evidence | Lane | Refresh | Monitoring | Next action | Requested source ID |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in payload["rows"]:
        lines.append(
            f"| {row['proposal_id']} | {', '.join(row['systems'])} | {', '.join(row['assessment_scoped_evidence_ids'])} | "
            f"{row['review_lane']} | {row['refresh_status']} | {row['monitoring_mode'] or '—'} | "
            f"{row['required_next_action']} | {row.get('requested_source_id') or '—'} |"
        )
    lines.extend(["", "## Authority boundary", "", payload["authority_boundary"], ""])
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "legacy-source-promotion-readiness.json"
    csv_path = output_dir / "legacy-source-promotion-readiness.csv"
    md_path = output_dir / "legacy-source-promotion-readiness.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    fields = (
        "proposal_id",
        "systems",
        "assessment_scoped_evidence_ids",
        "raw_source_action",
        "effective_source_action",
        "source_namespace_eligible",
        "source_namespace_reason",
        "prospective_source_identity_key",
        "existing_source_id",
        "requested_source_id",
        "normalized_public_url",
        "checksum",
        "monitoring_mode",
        "recommended_interval",
        "monitoring_priority",
        "monitoring_rule",
        "review_lane",
        "refresh_status",
        "required_next_action",
        "impacted_requirement_count",
        "impacted_requirement_ids",
        "source_boundary_note",
        "approval_status",
        "canonical_status",
        "human_review_status",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in payload["rows"]:
            flat = {field: row.get(field) for field in fields}
            flat["systems"] = "|".join(row["systems"])
            flat["assessment_scoped_evidence_ids"] = "|".join(row["assessment_scoped_evidence_ids"])
            flat["impacted_requirement_ids"] = "|".join(row["impacted_requirement_ids"])
            writer.writerow(flat)
    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--namespace-policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_manifest(manifest, schema)
    policy = load_policy(args.namespace_policy)
    payload = build_queue(
        manifest,
        policy,
        manifest_sha256=file_sha256(args.manifest),
        policy_sha256=file_sha256(args.namespace_policy),
    )
    outputs = write_outputs(payload, args.output_dir.resolve())
    checkpoint = payload["queue_checkpoint"]
    print(f"rows={checkpoint['queue_row_count']} evidence={checkpoint['linked_unresolved_evidence_row_count']}")
    for lane, count in checkpoint["lane_counts"].items():
        print(f"{lane}={count}")
    print(f"json={outputs['json']} csv={outputs['csv']} markdown={outputs['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
