#!/usr/bin/env python3
"""Validate evidence-bound source lifecycle overlays used by development monitoring."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTE_POLICY = ROOT / "curation" / "source_route_resilience_v0.1.json"
DEFAULT_LIFECYCLE_OVERLAY = ROOT / "curation" / "source_lifecycle_monitoring_overlay_v0.1.json"
STATUS = "DEVELOPMENT_LIFECYCLE_MONITORING_OVERLAY_NOT_CANONICAL"
LIFECYCLE_STATE = "NO_LONGER_LISTED"
MONITORING_STATE = "LIFECYCLE_RESOLVED_ARCHIVAL"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _require_sha256(value: Any, field: str) -> str:
    token = str(value or "")
    if not _HEX64.fullmatch(token):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
    return token


def _require_commit_sha(value: Any, field: str) -> str:
    token = str(value or "")
    if not _HEX40.fullmatch(token):
        raise ValueError(f"{field} must be a lowercase 40-character commit SHA")
    return token


def verify_lifecycle_overlay(
    overlay: dict[str, Any],
    route_policy: dict[str, Any],
    *,
    effective_source_ids: set[str] | None = None,
    governing_monitor_source_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    metadata = overlay.get("metadata")
    transitions = overlay.get("transitions")
    if not isinstance(metadata, dict) or not isinstance(transitions, list):
        raise ValueError("Lifecycle overlay requires metadata and transitions")
    if metadata.get("status") != STATUS:
        raise ValueError("Lifecycle overlay lost its explicit noncanonical status")
    if metadata.get("automatic_source_mutation") is not False or metadata.get("automatic_assessment_mutation") is not False:
        raise ValueError("Lifecycle overlay must forbid automatic source and assessment mutation")
    if metadata.get("transition_count") != len(transitions):
        raise ValueError("Lifecycle overlay transition_count mismatch")

    route_policy_sha = sha256(route_policy)
    if metadata.get("route_policy_sha256") != route_policy_sha:
        raise ValueError("Lifecycle overlay route-policy hash mismatch")

    route_sources_raw = route_policy.get("sources")
    if not isinstance(route_sources_raw, list):
        raise ValueError("Route policy requires a sources array")
    route_sources: dict[str, dict[str, Any]] = {}
    for item in route_sources_raw:
        if not isinstance(item, dict) or not isinstance(item.get("source_id"), str):
            raise ValueError("Route policy source must be an object with source_id")
        source_id = str(item["source_id"])
        if source_id in route_sources:
            raise ValueError(f"Duplicate route-policy source_id {source_id!r}")
        route_sources[source_id] = item

    by_source: dict[str, dict[str, Any]] = {}
    for transition in transitions:
        if not isinstance(transition, dict):
            raise ValueError("Lifecycle transition must be an object")
        source_id = str(transition.get("source_id") or "")
        if not source_id:
            raise ValueError("Lifecycle transition requires source_id")
        if source_id in by_source:
            raise ValueError(f"Duplicate lifecycle transition for {source_id}")
        if effective_source_ids is not None and source_id not in effective_source_ids:
            raise ValueError(f"Lifecycle transition references unknown effective source {source_id}")
        if governing_monitor_source_ids is not None and source_id in governing_monitor_source_ids:
            raise ValueError(f"Lifecycle overlay cannot suppress governing predecessor monitor {source_id}")

        source_policy = route_sources.get(source_id)
        if source_policy is None:
            raise ValueError(f"Lifecycle transition {source_id} lacks route-policy source")
        lifecycle = source_policy.get("lifecycle_resolution")
        if not isinstance(lifecycle, dict):
            raise ValueError(f"Lifecycle transition {source_id} lacks route-policy lifecycle assertion")

        if transition.get("lifecycle_state") != LIFECYCLE_STATE:
            raise ValueError(f"Lifecycle transition {source_id} has unsupported lifecycle state")
        if transition.get("monitoring_state") != MONITORING_STATE:
            raise ValueError(f"Lifecycle transition {source_id} has unsupported monitoring state")
        if transition.get("source_active_expected") is not False:
            raise ValueError(f"Lifecycle transition {source_id} must mark source inactive")
        if transition.get("evidence_substitution_allowed") is not False:
            raise ValueError(f"Lifecycle transition {source_id} must forbid evidence substitution")
        if transition.get("source_url") != source_policy.get("url"):
            raise ValueError(f"Lifecycle transition {source_id} source URL drift")
        if transition.get("route_source_sha256") != sha256(source_policy):
            raise ValueError(f"Lifecycle transition {source_id} route-source hash mismatch")
        if transition.get("lifecycle_assertion_sha256") != sha256(lifecycle):
            raise ValueError(f"Lifecycle transition {source_id} lifecycle-assertion hash mismatch")
        if transition.get("expected_identity") != lifecycle.get("expected_identity"):
            raise ValueError(f"Lifecycle transition {source_id} identity drift")
        if transition.get("primary_route_id") != lifecycle.get("primary_route_id"):
            raise ValueError(f"Lifecycle transition {source_id} primary route drift")
        if transition.get("publisher_listing_route_id") != lifecycle.get("publisher_listing_route_id"):
            raise ValueError(f"Lifecycle transition {source_id} publisher-listing route drift")
        if not str(transition.get("successor_discovery_watch_id") or ""):
            raise ValueError(f"Lifecycle transition {source_id} requires successor discovery watch binding")

        evidence = transition.get("live_evidence")
        if not isinstance(evidence, dict):
            raise ValueError(f"Lifecycle transition {source_id} requires live_evidence")
        if not isinstance(evidence.get("workflow_run_id"), int) or evidence["workflow_run_id"] <= 0:
            raise ValueError(f"Lifecycle transition {source_id} requires positive workflow_run_id")
        _require_commit_sha(evidence.get("workflow_head_sha"), f"{source_id}.workflow_head_sha")
        if not str(evidence.get("observed_at") or ""):
            raise ValueError(f"Lifecycle transition {source_id} requires observed_at")
        if evidence.get("route_policy_sha256") != route_policy_sha:
            raise ValueError(f"Lifecycle transition {source_id} live evidence policy hash mismatch")
        _require_sha256(evidence.get("route_report_sha256"), f"{source_id}.route_report_sha256")
        _require_sha256(evidence.get("lifecycle_report_sha256"), f"{source_id}.lifecycle_report_sha256")
        if evidence.get("primary_http_status") not in {404, 410}:
            raise ValueError(f"Lifecycle transition {source_id} requires primary 404/410 evidence")
        equivalent = evidence.get("identity_equivalent_http_statuses")
        if not isinstance(equivalent, list) or not equivalent or any(status not in {404, 410} for status in equivalent):
            raise ValueError(f"Lifecycle transition {source_id} requires identity-equivalent 404/410 evidence")
        if evidence.get("publisher_listing_http_status") != 200:
            raise ValueError(f"Lifecycle transition {source_id} requires successful publisher listing evidence")
        if evidence.get("publisher_listing_identity_present") is not False:
            raise ValueError(f"Lifecycle transition {source_id} requires exact identity absence")
        if evidence.get("resolution_state") != "RESOLVED_LIFECYCLE_CHANGE":
            raise ValueError(f"Lifecycle transition {source_id} requires resolved lifecycle evidence")

        observed_transition_sha = transition.get("transition_sha256")
        unsigned_transition = json.loads(json.dumps(transition))
        unsigned_transition.pop("transition_sha256", None)
        if observed_transition_sha != sha256(unsigned_transition):
            raise ValueError(f"Lifecycle transition {source_id} hash mismatch")
        by_source[source_id] = transition

    observed_overlay_sha = overlay.get("overlay_sha256")
    unsigned_overlay = json.loads(json.dumps(overlay))
    unsigned_overlay.pop("overlay_sha256", None)
    if observed_overlay_sha != sha256(unsigned_overlay):
        raise ValueError("Lifecycle overlay hash mismatch")
    return by_source


def load_verified_lifecycle_overlay(
    *,
    route_policy_path: Path = DEFAULT_ROUTE_POLICY,
    overlay_path: Path = DEFAULT_LIFECYCLE_OVERLAY,
    effective_source_ids: set[str] | None = None,
    governing_monitor_source_ids: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    route_policy = load_json(route_policy_path.resolve())
    overlay = load_json(overlay_path.resolve())
    transitions = verify_lifecycle_overlay(
        overlay,
        route_policy,
        effective_source_ids=effective_source_ids,
        governing_monitor_source_ids=governing_monitor_source_ids,
    )
    return route_policy, overlay, transitions


def build_active_route_policy(
    route_policy: dict[str, Any],
    lifecycle_transitions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    raw_sources = route_policy.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("Route policy requires sources")
    active_sources = [
        json.loads(json.dumps(item))
        for item in raw_sources
        if isinstance(item, dict) and str(item.get("source_id") or "") not in lifecycle_transitions
    ]
    metadata = dict(route_policy.get("metadata") or {})
    metadata.update(
        {
            "title": "Derived active source-route policy",
            "status": "DERIVED_ACTIVE_ROUTE_POLICY_NOT_CANONICAL",
            "source_count": len(active_sources),
            "derived_from_policy_sha256": sha256(route_policy),
            "excluded_lifecycle_source_ids": sorted(lifecycle_transitions),
        }
    )
    return {"metadata": metadata, "sources": active_sources}
