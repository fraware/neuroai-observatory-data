#!/usr/bin/env python3
"""Project monitoring eligibility for namespace-safe legacy source proposals.

This module is intentionally noncanonical. It consumes the mechanical legacy
source-registration proposal manifest plus the source-namespace eligibility
policy and emits monitoring recommendations only for proposals that pass the
namespace gate. It never registers a source, creates a monitor, or changes the
canonical monitoring registry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from source_namespace_eligibility import (
    DEFAULT_POLICY,
    SAFE_RAW_ACTIONS,
    evaluate_manifest,
    file_sha256,
    load_policy,
)
from validate_legacy_source_registration import validate_manifest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"
DEFAULT_SCHEMA = ROOT / "schemas" / "legacy-source-registration-proposals.schema.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "legacy-source-monitoring"

MONITORING_MODES = frozenset({"RECURRING", "ON_CHANGE", "ARCHIVAL_STATIC"})
REGISTRATION_STATUS = "NOT_REGISTERED"
MONITOR_STATUS = "PROSPECTIVE_ONLY"
EXPECTED_PROSPECTIVE_SOURCE_COUNT = 33
_GIT_OBJECT_RE = re.compile(r"/(?:blob|tree|commit)/[0-9a-f]{7,64}(?:/|$)", re.IGNORECASE)


class ProspectiveMonitoringError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _url_parts(value: Any) -> tuple[str, str]:
    raw = _text(value)
    if not raw:
        return "", ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "", ""
    return parsed.netloc.casefold(), parsed.path.casefold()


def _signals(proposal: dict[str, Any]) -> dict[str, Any]:
    linked = proposal.get("linked_evidence")
    if not isinstance(linked, list) or not linked or any(not isinstance(row, dict) for row in linked):
        raise ProspectiveMonitoringError(f"Proposal {proposal.get('proposal_id')!r} has no valid linked evidence")

    evidence_types = sorted({_text(row.get("evidence_type")) for row in linked if _text(row.get("evidence_type"))})
    evidence_classes = sorted({_text(row.get("evidence_class")) for row in linked if _text(row.get("evidence_class"))})
    source_labels = sorted({_text(row.get("source_label")) for row in linked if _text(row.get("source_label"))})
    publication_states = sorted(
        {_text(row.get("publication_state")) for row in linked if _text(row.get("publication_state"))}
    )
    titles = sorted({_text(row.get("title")) for row in linked if _text(row.get("title"))})
    combined = " ".join(
        _upper(value)
        for group in (evidence_types, evidence_classes, source_labels, publication_states, titles)
        for value in group
    )
    url = _text(proposal.get("normalized_public_url"))
    host, path = _url_parts(url)
    return {
        "evidence_types": evidence_types,
        "evidence_classes": evidence_classes,
        "source_labels": source_labels,
        "publication_states": publication_states,
        "titles": titles,
        "combined": combined,
        "url": url or None,
        "url_host": host or None,
        "url_path": path or None,
    }


def classify_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """Classify one already namespace-eligible proposal by source mutability."""
    signals = _signals(proposal)
    token = str(signals["combined"])
    url = _text(signals["url"])
    host = _text(signals["url_host"])
    path = _text(signals["url_path"])

    # Exact immutable artifacts take precedence over host-level rules. A filed
    # PDF or commit-pinned repository object should not be polled simply because
    # it lives on a mutable website.
    if url and _GIT_OBJECT_RE.search(url):
        return {
            "monitoring_mode": "ARCHIVAL_STATIC",
            "recommended_interval": None,
            "priority": "LOW",
            "rule": "IMMUTABLE_GIT_OBJECT",
            "reason": "Commit-pinned Git content is an immutable evidence artifact; monitor the upstream project separately.",
            "signals": signals,
        }

    static_document_tokens = (
        "SUMMARY OF SAFETY",
        "SSED",
        "STATISTICAL ANALYSIS PLAN",
        "CLINICAL INVESTIGATION PLAN",
        "PROTOCOL",
        "PATIENT USER GUIDE",
        "USER GUIDE",
        "MANUAL",
        "LABELING",
        "LABEL",
    )
    if path.endswith(".pdf") or any(marker in token for marker in static_document_tokens):
        return {
            "monitoring_mode": "ARCHIVAL_STATIC",
            "recommended_interval": None,
            "priority": "LOW",
            "rule": "STATIC_FILE_OR_VERSIONED_DOCUMENT",
            "reason": "The evidence object is a fixed filed/versioned document; discovery of a successor is a separate task.",
            "signals": signals,
        }

    trial_hosts = (
        "clinicaltrials.gov",
        "clinicaltrialsregister.eu",
        "ctis.eu",
        "who.int",
    )
    if "TRIAL REGISTRY" in token or "CLINICALTRIAL" in token or any(marker in host for marker in trial_hosts):
        return {
            "monitoring_mode": "RECURRING",
            "recommended_interval": "MONTHLY",
            "priority": "HIGH",
            "rule": "LIVE_TRIAL_REGISTRY",
            "reason": "Living trial-registry metadata can change through recruitment, protocol updates, follow-up, and results posting.",
            "signals": signals,
        }

    publication_tokens = (
        "PEER-REVIEWED",
        "PEER REVIEWED",
        "PREPRINT",
        "PUBLICATION",
        "ARTICLE",
        "PRESS RELEASE",
        "PRESS_RELEASE",
        "SYNDICATION",
        "MEDIA",
        "NEWS",
        "CONFERENCE PAPER",
    )
    publication_hosts = (
        "nature.com",
        "nejm.org",
        "sciencedirect.com",
        "pubmed.ncbi.nlm.nih.gov",
        "arxiv.org",
        "medrxiv.org",
        "biorxiv.org",
        "businesswire.com",
    )
    if any(marker in token for marker in publication_tokens) or any(marker in host for marker in publication_hosts):
        return {
            "monitoring_mode": "ARCHIVAL_STATIC",
            "recommended_interval": None,
            "priority": "LOW",
            "rule": "DATED_PUBLICATION_OR_EVENT_ARTIFACT",
            "reason": "The cited publication/event record is fixed; later programme developments should enter as distinct sources.",
            "signals": signals,
        }

    # Live regulatory database pages can acquire supplements, corrections, or
    # changed status. Static filed PDFs were already caught above.
    fda_live_markers = (
        "accessdata.fda.gov",
        "fda.gov/medical-devices",
        "fda.gov/safety/recalls",
    )
    if any(marker in f"{host}{path}" for marker in fda_live_markers) or any(
        marker in token for marker in ("PMA SUPPLEMENT", "RECALL", "REGULATORY DATABASE", "REGULATORY RECORD")
    ):
        return {
            "monitoring_mode": "ON_CHANGE",
            "recommended_interval": "QUARTERLY_REVIEW",
            "priority": "HIGH",
            "rule": "LIVE_REGULATORY_DATABASE",
            "reason": "The regulatory/database record can acquire supplements, corrections, recalls, or status updates.",
            "signals": signals,
        }

    normative_tokens = ("GUIDANCE", "LEGAL TEXT", "REGULATION", "PROCEDURAL")
    if any(marker in token for marker in normative_tokens):
        return {
            "monitoring_mode": "ON_CHANGE",
            "recommended_interval": "QUARTERLY_REVIEW",
            "priority": "NORMAL",
            "rule": "NORMATIVE_OR_PROCEDURAL_SOURCE",
            "reason": "Normative/procedural material changes infrequently but can alter interpretation or obligations.",
            "signals": signals,
        }

    live_project_tokens = (
        "OFFICIAL PROJECT PAGE",
        "PROJECT PAGE",
        "PRODUCT PAGE",
        "TECHNOLOGY PAGE",
        "REPOSITORY LANDING",
        "REPOSITORY METADATA",
    )
    if (host == "github.com" and not _GIT_OBJECT_RE.search(url)) or any(
        marker in token for marker in live_project_tokens
    ):
        return {
            "monitoring_mode": "ON_CHANGE",
            "recommended_interval": "MONTHLY_REVIEW",
            "priority": "NORMAL",
            "rule": "LIVE_PROJECT_OR_REPOSITORY_PAGE",
            "reason": "The landing page is mutable and can surface releases, repository changes, or current programme state.",
            "signals": signals,
        }

    # Fail conservatively: insufficient metadata does not justify recurring
    # polling, but also does not justify declaring the source immutable.
    return {
        "monitoring_mode": "ON_CHANGE",
        "recommended_interval": None,
        "priority": "NORMAL",
        "rule": "CONSERVATIVE_ON_CHANGE_FALLBACK",
        "reason": "Available metadata is insufficient to justify recurring polling or an immutable-source classification.",
        "signals": signals,
    }


def build_projection(
    manifest: dict[str, Any],
    policy: dict[str, Any],
    *,
    manifest_sha256: str | None = None,
    policy_sha256: str | None = None,
) -> dict[str, Any]:
    validate_manifest_contract = manifest.get("artifact") == "legacy_assessment_source_registration_proposals"
    if not validate_manifest_contract:
        raise ProspectiveMonitoringError("Unexpected legacy source-registration manifest")

    evaluations = {row["proposal_id"]: row for row in evaluate_manifest(manifest, policy)}
    proposals = manifest.get("proposals")
    if not isinstance(proposals, list):
        raise ProspectiveMonitoringError("Proposal manifest proposals must be a list")

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen_proposals: set[str] = set()
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ProspectiveMonitoringError("Proposal entries must be objects")
        proposal_id = _text(proposal.get("proposal_id"))
        if not proposal_id or proposal_id in seen_proposals:
            raise ProspectiveMonitoringError(f"Invalid or duplicate proposal ID {proposal_id!r}")
        seen_proposals.add(proposal_id)
        evaluation = evaluations[proposal_id]
        effective_action = _text(evaluation["effective_action"])

        linked = proposal.get("linked_evidence")
        if not isinstance(linked, list) or not linked:
            raise ProspectiveMonitoringError(f"Proposal {proposal_id} has no linked evidence")
        evidence_ids = [_text(item.get("evidence_id")) for item in linked if isinstance(item, dict)]
        systems = sorted({_text(item.get("system")) for item in linked if isinstance(item, dict) and _text(item.get("system"))})

        if not evaluation["source_namespace_eligible"] or effective_action not in SAFE_RAW_ACTIONS:
            excluded.append(
                {
                    "proposal_id": proposal_id,
                    "effective_action": effective_action,
                    "linked_evidence_ids": evidence_ids,
                    "systems": systems,
                    "eligibility_reason": evaluation["eligibility_reason"],
                }
            )
            continue

        classification = classify_proposal(proposal)
        requested_source_id = proposal.get("requested_source_id")
        existing_source_id = proposal.get("existing_source_id")
        if effective_action == "REGISTER_NEW_SOURCE" and (requested_source_id or existing_source_id):
            raise ProspectiveMonitoringError(f"New-source proposal {proposal_id} already carries a source ID")
        if requested_source_id and requested_source_id != "SRC-PR-011":
            raise ProspectiveMonitoringError(f"Unexpected requested source ID {requested_source_id!r}")

        rows.append(
            {
                "proposal_id": proposal_id,
                "prospective_source_identity_key": f"proposal:{proposal_id}",
                "effective_source_action": effective_action,
                "systems": systems,
                "linked_evidence_ids": evidence_ids,
                "normalized_public_url": proposal.get("normalized_public_url"),
                "checksum": proposal.get("checksum"),
                "requested_source_id": requested_source_id,
                "existing_source_id": existing_source_id,
                "source_namespace_eligible": True,
                "registration_status": REGISTRATION_STATUS,
                "monitor_status": MONITOR_STATUS,
                "monitoring_mode": classification["monitoring_mode"],
                "recommended_interval": classification["recommended_interval"],
                "priority": classification["priority"],
                "rule": classification["rule"],
                "reason": classification["reason"],
                "classification_signals": classification["signals"],
            }
        )

    rows.sort(key=lambda row: str(row["proposal_id"]))
    excluded.sort(key=lambda row: str(row["proposal_id"]))
    if len(rows) != EXPECTED_PROSPECTIVE_SOURCE_COUNT:
        raise ProspectiveMonitoringError(
            f"Expected {EXPECTED_PROSPECTIVE_SOURCE_COUNT} namespace-eligible prospective source identities; got {len(rows)}"
        )
    if len(excluded) != 2:
        raise ProspectiveMonitoringError(f"Expected exactly two curation holds; got {len(excluded)}")

    modes = Counter(str(row["monitoring_mode"]) for row in rows)
    rules = Counter(str(row["rule"]) for row in rows)
    projection = {
        "schema_version": "0.1.0",
        "artifact": "legacy_source_prospective_monitoring",
        "status": "NONCANONICAL_PROJECTION",
        "scenario_only": True,
        "registration_status": REGISTRATION_STATUS,
        "monitor_status": MONITOR_STATUS,
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
        "current_canonical_monitoring_checkpoint": {
            "effective_source_count": 248,
            "monitor_registry_source_count": 224,
            "unmonitored_effective_source_count": 24,
            "mutated_by_this_projection": False,
        },
        "prospective_population": {
            "source_identity_count": len(rows),
            "excluded_curation_hold_count": len(excluded),
            "mode_counts": dict(sorted(modes.items())),
            "rule_counts": dict(sorted(rules.items())),
        },
        "excluded_curation_holds": excluded,
        "sources": rows,
        "authority_boundary": (
            "Monitoring recommendations apply only to prospective namespace-eligible source identities. "
            "They do not approve source registration, create monitor records, assign canonical source IDs, "
            "or alter current canonical monitoring cadence."
        ),
    }
    validate_projection(projection)
    return projection


def validate_projection(projection: dict[str, Any]) -> None:
    if projection.get("status") != "NONCANONICAL_PROJECTION" or projection.get("scenario_only") is not True:
        raise ProspectiveMonitoringError("Prospective monitoring output must remain noncanonical and scenario-only")
    if projection.get("registration_status") != REGISTRATION_STATUS:
        raise ProspectiveMonitoringError("Prospective monitoring output cannot register sources")
    if projection.get("monitor_status") != MONITOR_STATUS:
        raise ProspectiveMonitoringError("Prospective monitoring output cannot create monitor records")
    checkpoint = projection.get("current_canonical_monitoring_checkpoint")
    if checkpoint != {
        "effective_source_count": 248,
        "monitor_registry_source_count": 224,
        "unmonitored_effective_source_count": 24,
        "mutated_by_this_projection": False,
    }:
        raise ProspectiveMonitoringError("Canonical monitoring checkpoint changed in prospective projection")
    rows = projection.get("sources")
    if not isinstance(rows, list) or len(rows) != EXPECTED_PROSPECTIVE_SOURCE_COUNT:
        raise ProspectiveMonitoringError("Prospective monitoring population must contain exactly 33 rows")
    if len({row.get("proposal_id") for row in rows}) != len(rows):
        raise ProspectiveMonitoringError("Prospective monitoring rows contain duplicate proposal IDs")
    for row in rows:
        if row.get("source_namespace_eligible") is not True:
            raise ProspectiveMonitoringError("Ineligible source proposal entered prospective monitoring output")
        if row.get("effective_source_action") not in SAFE_RAW_ACTIONS:
            raise ProspectiveMonitoringError("Unsafe source action entered prospective monitoring output")
        if row.get("registration_status") != REGISTRATION_STATUS or row.get("monitor_status") != MONITOR_STATUS:
            raise ProspectiveMonitoringError("Prospective row crossed registration or monitoring authority boundary")
        if row.get("monitoring_mode") not in MONITORING_MODES:
            raise ProspectiveMonitoringError(f"Unsupported monitoring mode {row.get('monitoring_mode')!r}")
        if row.get("effective_source_action") == "REGISTER_NEW_SOURCE" and (
            row.get("requested_source_id") or row.get("existing_source_id")
        ):
            raise ProspectiveMonitoringError("New-source prospective row carries a canonical source identity")
    requested = sorted(row["requested_source_id"] for row in rows if row.get("requested_source_id"))
    if requested != ["SRC-PR-011"]:
        raise ProspectiveMonitoringError(f"Unexpected requested source IDs: {requested}")
    excluded = projection.get("excluded_curation_holds")
    if not isinstance(excluded, list) or len(excluded) != 2:
        raise ProspectiveMonitoringError("Exactly two curation holds must remain excluded")
    excluded_evidence = {evidence_id for row in excluded for evidence_id in row.get("linked_evidence_ids", [])}
    if excluded_evidence != {"EV-15", "EV-T15-012"}:
        raise ProspectiveMonitoringError(f"Unexpected curation hold evidence set: {sorted(excluded_evidence)}")


def render_markdown(projection: dict[str, Any]) -> str:
    population = projection["prospective_population"]
    checkpoint = projection["current_canonical_monitoring_checkpoint"]
    lines = [
        "# Prospective monitoring classification for legacy source identities",
        "",
        "**NONCANONICAL PROJECTION — no source registration or monitor creation is authorized.**",
        "",
        "## Current canonical checkpoint",
        "",
        f"- Effective sources: {checkpoint['effective_source_count']}",
        f"- Existing monitored sources: {checkpoint['monitor_registry_source_count']}",
        f"- Current unmonitored effective sources: {checkpoint['unmonitored_effective_source_count']}",
        "",
        "## Prospective population",
        "",
        f"- Namespace-eligible source identities: {population['source_identity_count']}",
        f"- Excluded curation holds: {population['excluded_curation_hold_count']}",
    ]
    for mode, count in population["mode_counts"].items():
        lines.append(f"- {mode}: {count}")
    lines.extend(
        [
            "",
            "## Recommendations",
            "",
            "| Proposal | Systems | Evidence | Mode | Interval | Priority | Rule | Requested source ID |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in projection["sources"]:
        lines.append(
            f"| {row['proposal_id']} | {', '.join(row['systems'])} | {', '.join(row['linked_evidence_ids'])} | "
            f"{row['monitoring_mode']} | {row['recommended_interval'] or '—'} | {row['priority']} | {row['rule']} | "
            f"{row.get('requested_source_id') or '—'} |"
        )
    lines.extend(["", "## Authority boundary", "", projection["authority_boundary"], ""])
    return "\n".join(lines)


def write_outputs(projection: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "legacy-source-prospective-monitoring.json"
    csv_path = output_dir / "legacy-source-prospective-monitoring.csv"
    md_path = output_dir / "legacy-source-prospective-monitoring.md"
    json_path.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(projection), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fields = (
            "proposal_id",
            "prospective_source_identity_key",
            "effective_source_action",
            "systems",
            "linked_evidence_ids",
            "normalized_public_url",
            "checksum",
            "requested_source_id",
            "existing_source_id",
            "registration_status",
            "monitor_status",
            "monitoring_mode",
            "recommended_interval",
            "priority",
            "rule",
            "reason",
        )
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in projection["sources"]:
            flat = {field: row.get(field) for field in fields}
            flat["systems"] = "|".join(row["systems"])
            flat["linked_evidence_ids"] = "|".join(row["linked_evidence_ids"])
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
    projection = build_projection(
        manifest,
        policy,
        manifest_sha256=file_sha256(args.manifest),
        policy_sha256=file_sha256(args.namespace_policy),
    )
    outputs = write_outputs(projection, args.output_dir.resolve())
    population = projection["prospective_population"]
    print(f"prospective={population['source_identity_count']} excluded={population['excluded_curation_hold_count']}")
    for mode, count in population["mode_counts"].items():
        print(f"{mode}={count}")
    print(f"json={outputs['json']} csv={outputs['csv']} markdown={outputs['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
