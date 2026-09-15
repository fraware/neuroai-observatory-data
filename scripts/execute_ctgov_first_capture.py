#!/usr/bin/env python3
"""Execute explicitly authorized CT.gov first captures into Workbench quarantine.

This module implements only the pre-registry first-capture boundary. It verifies an exact
noncanonical onboarding package, requires an explicit local authorization packet, derives one
fixed collector profile, executes only each plan's PRIMARY ClinicalTrials.gov single-study
route, and writes sanitized receipts under an operations root outside this repository.

A successful receipt proves bounded retrieval + exact NCT identity matching only. It does not
approve quarantine, create a monitor, publish a Source, create Trial/site graph state, mutate an
assessment, or authorize canonical/publication state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from neuroai_workbench.collector import (
    ClinicalTrialsGovAdapter,
    CollectorConfig,
    EvidenceCollectionService,
    HttpCollector,
    PinnedSocketHttpTransport,
)
from neuroai_workbench.collector.authorization import build_authorization_packet
from neuroai_workbench.collector.dns import DnsGuard
from neuroai_workbench.collector.schemas import REQUEST_SCHEMA, validate_or_raise

WORKBENCH_COMMIT = "854cc9d1c8e24a9e8ae8b21d871329bc3c24c118"
PROFILE_ID = "CTGOV_FIRST_CAPTURE_V0_1"
REPO_ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
NCT = re.compile(r"^NCT[0-9]{8}$")
DMON = re.compile(r"^DMON-[0-9a-f]{32}$")
CREQ = re.compile(r"^CREQ-[0-9a-f]{32}$")

AUTHORITY_FALSE = (
    "fallback_capture_authorized",
    "quarantine_approval_authorized",
    "monitor_registry_successor_authorized",
    "source_namespace_publication_authorized",
    "trial_entity_creation_authorized",
    "trial_site_relationship_creation_authorized",
    "assessment_mutation_authorized",
    "canonical_publication_authorized",
)

COLLECTOR_PROFILE: dict[str, Any] = {
    "profile_id": PROFILE_ID,
    "workbench_commit": WORKBENCH_COMMIT,
    "method": "GET",
    "transport": "PinnedSocketHttpTransport",
    "allowed_content_types": ["application/json"],
    "max_response_bytes": 2 * 1024 * 1024,
    "max_redirects": 0,
    "max_decompression_ratio": 20,
    "connect_timeout_seconds": 10.0,
    "read_timeout_seconds": 30.0,
    "total_timeout_seconds": 60.0,
    "max_attempts": 1,
    "requests_per_host_per_minute": 10,
    "user_agent": "NeuroAI-Observatory-CTGov-FirstCapture/0.1 (+https://github.com/fraware/neuroai-observatory-data)",
    "boundary": (
        "One-attempt pre-registry ClinicalTrials.gov PRIMARY-route capture into controlled "
        "quarantine. The profile creates no quarantine approval, monitor, canonical Source, "
        "assessment effect, or publication authority."
    ),
}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _sha_bytes(_canonical_bytes(value))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _inside_repo(path: Path) -> bool:
    resolved = path.resolve()
    root = REPO_ROOT.resolve()
    return resolved == root or root in resolved.parents


def _require_operations_boundary(operations_root: Path, authorization_path: Path) -> Path:
    root = operations_root.resolve()
    if _inside_repo(root):
        raise ValueError("OPERATIONS_ROOT_INSIDE_REPOSITORY_REFUSED")
    if _inside_repo(authorization_path.resolve()):
        raise ValueError("FIRST_CAPTURE_AUTHORIZATION_INSIDE_REPOSITORY_REFUSED")
    root.mkdir(parents=True, exist_ok=True)
    return root


def collector_profile() -> dict[str, Any]:
    return dict(COLLECTOR_PROFILE)


def collector_configuration_hash() -> str:
    return _digest(COLLECTOR_PROFILE)


def verify_onboarding(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("CT.gov onboarding manifest.json missing")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("CT.gov onboarding manifest must be an object")
    if manifest.get("schema_version") != "0.1.0" or manifest.get("status") != "NONCANONICAL_CT_GOV_MONITOR_ONBOARDING":
        raise ValueError("CT.gov onboarding manifest contract/status mismatch")
    for key in (
        "network_execution_performed",
        "quarantine_approval_performed",
        "monitor_registry_successor_created",
        "monitor_creation_performed",
        "source_namespace_publication_performed",
        "trial_entity_creation_performed",
        "trial_site_relationship_creation_performed",
        "assessment_mutation_performed",
        "canonical_successor_ready",
    ):
        if manifest.get(key) is not False:
            raise ValueError(f"CT.gov onboarding authority boundary weakened: {key}")

    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("file_count") != len(entries):
        raise ValueError("CT.gov onboarding manifest file list/count invalid")
    paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    expected = {"monitor-review-summary.json", "ctgov-monitor-onboarding.json"}
    if set(paths) != expected or len(paths) != len(set(paths)):
        raise ValueError("First capture requires an approved CT.gov onboarding package")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("CT.gov onboarding manifest entry must be an object")
        relative = entry.get("path")
        expected_sha = entry.get("sha256")
        if not isinstance(relative, str) or Path(relative).name != relative:
            raise ValueError("Unsafe CT.gov onboarding manifest path")
        if not isinstance(expected_sha, str) or not HEX64.fullmatch(expected_sha):
            raise ValueError(f"Invalid CT.gov onboarding digest for {relative!r}")
        path = root / relative
        if not path.is_file():
            raise ValueError(f"CT.gov onboarding file missing: {relative}")
        payload = path.read_bytes()
        if _sha_bytes(payload) != expected_sha or entry.get("bytes") != len(payload):
            raise ValueError(f"CT.gov onboarding manifest mismatch: {relative}")

    package = _load_object(root / "ctgov-monitor-onboarding.json", label="CT.gov onboarding package")
    if package.get("schema_version") != "0.1.0" or package.get("artifact") != "ctgov_monitor_onboarding_package":
        raise ValueError("CT.gov onboarding package identity mismatch")
    if package.get("status") != "DRAFT_NONCANONICAL_MONITOR_ONBOARDING":
        raise ValueError("CT.gov onboarding package is not a draft noncanonical onboarding package")
    for key in (
        "network_execution_performed",
        "quarantine_approval_performed",
        "monitor_registry_successor_created",
        "monitor_creation_performed",
        "source_namespace_publication_performed",
        "trial_entity_creation_performed",
        "trial_site_relationship_creation_performed",
        "assessment_mutation_performed",
        "canonical_successor_ready",
    ):
        if package.get(key) is not False:
            raise ValueError(f"CT.gov onboarding package authority boundary weakened: {key}")

    plans = package.get("plans")
    if not isinstance(plans, list) or not plans or package.get("approved_plan_count") != len(plans):
        raise ValueError("CT.gov onboarding approved plan set invalid")
    by_monitor: dict[str, dict[str, Any]] = {}
    source_ids: set[str] = set()
    nct_ids: set[str] = set()
    request_ids: set[str] = set()
    for plan in plans:
        if not isinstance(plan, dict):
            raise ValueError("CT.gov onboarding plan must be an object")
        monitor_id = plan.get("draft_monitor_id")
        source_id = plan.get("source_id")
        nct_id = plan.get("nct_id")
        if not isinstance(monitor_id, str) or not DMON.fullmatch(monitor_id) or monitor_id in by_monitor:
            raise ValueError("CT.gov onboarding draft monitor identity invalid/duplicate")
        if not isinstance(source_id, str) or not source_id or source_id in source_ids:
            raise ValueError(f"{monitor_id}: Source identity invalid/duplicate")
        if not isinstance(nct_id, str) or not NCT.fullmatch(nct_id) or nct_id in nct_ids:
            raise ValueError(f"{monitor_id}: NCT identity invalid/duplicate")
        if plan.get("adapter_id") != "clinicaltrials_gov":
            raise ValueError(f"{monitor_id}: wrong adapter")
        if (
            plan.get("approved_mode") != "RECURRING"
            or plan.get("approved_cadence") != "MONTHLY"
            or plan.get("priority") != "HIGH"
        ):
            raise ValueError(f"{monitor_id}: approved monitoring recommendation drift")
        if plan.get("monitor_registry_state") != "NOT_CREATED":
            raise ValueError(f"{monitor_id}: pre-registry state changed")

        routes = plan.get("routes")
        if not isinstance(routes, list) or len(routes) != 3:
            raise ValueError(f"{monitor_id}: route set invalid")
        primary = [route for route in routes if isinstance(route, dict) and route.get("role") == "PRIMARY"]
        if len(primary) != 1:
            raise ValueError(f"{monitor_id}: exactly one PRIMARY route is required")
        primary_route = primary[0]
        expected_url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
        if (
            primary_route.get("route_class") != "PRIMARY"
            or primary_route.get("priority") != 0
            or primary_route.get("url") != expected_url
            or primary_route.get("accept") != "application/json"
        ):
            raise ValueError(f"{monitor_id}: PRIMARY route drift")
        if plan.get("initial_capture_route_id") != primary_route.get("route_id"):
            raise ValueError(f"{monitor_id}: initial capture must bind the PRIMARY route")

        template = plan.get("first_capture_request_template")
        if not isinstance(template, dict):
            raise ValueError(f"{monitor_id}: first-capture request template missing")
        request_id = template.get("request_id")
        if not isinstance(request_id, str) or not CREQ.fullmatch(request_id) or request_id in request_ids:
            raise ValueError(f"{monitor_id}: request identity invalid/duplicate")
        if (
            template.get("source_id") != source_id
            or template.get("monitor_id") != monitor_id
            or template.get("requested_url") != expected_url
            or template.get("execution_state") != "TEMPLATE_NOT_EXECUTED"
        ):
            raise ValueError(f"{monitor_id}: first-capture request template drift")
        if template.get("required_execution_fields") != [
            "requested_at",
            "onboarding_manifest_sha256",
            "collector_version",
            "configuration_hash",
            "boundary",
        ]:
            raise ValueError(f"{monitor_id}: pre-registry execution fields changed")

        source_ids.add(source_id)
        nct_ids.add(nct_id)
        request_ids.add(request_id)
        by_monitor[monitor_id] = plan

    return {
        "root": root,
        "manifest": manifest,
        "manifest_sha256": _sha_bytes(manifest_bytes),
        "package": package,
        "plans": by_monitor,
    }


def load_first_capture_authorization(path: Path, onboarding: Mapping[str, Any]) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("First-capture authorization packet must be an object")
    if (
        value.get("schema_version") != "0.1.0"
        or value.get("artifact") != "ctgov_first_capture_authorization_packet"
        or value.get("status") != "EXPLICIT_LOCAL_FIRST_CAPTURE_AUTHORIZATION"
    ):
        raise ValueError("First-capture authorization packet identity/status mismatch")
    if value.get("onboarding_manifest_sha256") != onboarding["manifest_sha256"]:
        raise ValueError("First-capture authorization onboarding-manifest binding mismatch")
    if value.get("workbench_commit") != WORKBENCH_COMMIT:
        raise ValueError("First-capture authorization Workbench commit mismatch")
    if value.get("collector_profile_id") != PROFILE_ID:
        raise ValueError("First-capture authorization collector profile mismatch")
    if value.get("collector_configuration_sha256") != collector_configuration_hash():
        raise ValueError("First-capture authorization collector configuration mismatch")
    if value.get("identity_boundary") != "LOCAL_UNAUTHENTICATED_ATTRIBUTION":
        raise ValueError("First-capture authorization identity boundary mismatch")
    for key in ("authorized_by", "authorized_at", "rationale", "authority_boundary"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"First-capture authorization field {key} must be non-empty")
    if value.get("network_execution_authorized") is not True:
        raise ValueError("First-capture authorization must explicitly authorize bounded network execution")
    if value.get("primary_route_only") is not True:
        raise ValueError("First-capture authorization must remain PRIMARY-route-only")
    for key in AUTHORITY_FALSE:
        if value.get(key) is not False:
            raise ValueError(f"First-capture authorization authority escalation: {key}")

    decisions = value.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("First-capture authorization decisions are required")
    by_monitor: dict[str, dict[str, Any]] = {}
    for row in decisions:
        if not isinstance(row, dict):
            raise ValueError("First-capture authorization decision must be an object")
        monitor_id = row.get("draft_monitor_id")
        if monitor_id not in onboarding["plans"] or monitor_id in by_monitor:
            raise ValueError(f"First-capture authorization unknown/duplicate monitor {monitor_id!r}")
        plan = onboarding["plans"][monitor_id]
        expected = {
            "source_id": plan["source_id"],
            "nct_id": plan["nct_id"],
            "request_id": plan["first_capture_request_template"]["request_id"],
            "primary_route_id": plan["initial_capture_route_id"],
            "primary_url": plan["first_capture_request_template"]["requested_url"],
        }
        for key, expected_value in expected.items():
            if row.get(key) != expected_value:
                raise ValueError(f"{monitor_id}: first-capture authorization binding mismatch: {key}")
        if row.get("decision") not in {"AUTHORIZE_PRIMARY_CAPTURE", "DEFER"}:
            raise ValueError(f"{monitor_id}: unsupported first-capture disposition")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            raise ValueError(f"{monitor_id}: first-capture decision rationale required")
        by_monitor[monitor_id] = row
    if set(by_monitor) != set(onboarding["plans"]):
        missing = sorted(set(onboarding["plans"]) - set(by_monitor))
        raise ValueError(f"First-capture authorization must dispose every onboarding plan; missing={missing}")

    return {
        "record": value,
        "sha256": _sha_bytes(raw),
        "decisions": by_monitor,
    }


def build_collection_request(plan: Mapping[str, Any], onboarding_sha: str, *, requested_at: str) -> dict[str, Any]:
    template = plan["first_capture_request_template"]
    request = {
        "request_id": template["request_id"],
        "source_id": plan["source_id"],
        "monitor_id": plan["draft_monitor_id"],
        "requested_url": template["requested_url"],
        "requested_at": requested_at,
        "onboarding_manifest_sha256": onboarding_sha,
        "collector_version": "0.3.0.dev0",
        "configuration_hash": collector_configuration_hash(),
        "boundary": (
            "Exact pre-registry CT.gov PRIMARY-route first capture bound to one onboarding manifest. "
            "Retrieval creates quarantine evidence only and confers no quarantine approval, monitor-registry, "
            "Source publication, clinical truth, assessment effect, or canonical authority."
        ),
    }
    validate_or_raise(request, REQUEST_SCHEMA)
    return request


def _build_collector(
    quarantine_root: Path,
    *,
    transport: Any | None = None,
    dns_guard: DnsGuard | None = None,
) -> HttpCollector:
    profile = COLLECTOR_PROFILE
    config = CollectorConfig(
        collector_version="0.3.0.dev0",
        configuration_hash=collector_configuration_hash(),
        user_agent=str(profile["user_agent"]),
        max_response_bytes=int(profile["max_response_bytes"]),
        max_redirects=int(profile["max_redirects"]),
        max_decompression_ratio=int(profile["max_decompression_ratio"]),
        connect_timeout_seconds=float(profile["connect_timeout_seconds"]),
        read_timeout_seconds=float(profile["read_timeout_seconds"]),
        total_timeout_seconds=float(profile["total_timeout_seconds"]),
        max_attempts=int(profile["max_attempts"]),
        requests_per_host_per_minute=int(profile["requests_per_host_per_minute"]),
        allowed_content_types=frozenset({"application/json"}),
    )
    actual_transport = transport or PinnedSocketHttpTransport(max_wire_bytes=config.max_response_bytes)
    collector = HttpCollector(config=config, transport=actual_transport, quarantine_root=quarantine_root)
    if dns_guard is not None:
        collector.http_client.dns_guard = dns_guard
    return collector


def _safe_capture_bytes(quarantine_root: Path, relative: str) -> bytes:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Unsafe quarantine path")
    root = quarantine_root.resolve()
    path = (root / relative).resolve()
    if root not in path.parents:
        raise ValueError("Quarantine path escapes operations root")
    return path.read_bytes()


def verify_result_quarantine_binding(result: Mapping[str, Any], quarantine: Mapping[str, Any]) -> None:
    for key in ("result_id", "source_id", "monitor_id", "sha256", "size_bytes", "quarantine_path"):
        if result.get(key) != quarantine.get(key):
            raise ValueError(f"Collection result/quarantine mismatch: {key}")
    if quarantine.get("approval_state") != "PENDING_HUMAN_APPROVAL":
        raise ValueError("First capture quarantine must remain PENDING_HUMAN_APPROVAL")
    if quarantine.get("approved_at") is not None or quarantine.get("approved_by") is not None:
        raise ValueError("First capture must not approve quarantine")


def _receipt_path(operations_root: Path, monitor_id: str, authorization_sha: str) -> Path:
    return operations_root / "ctgov-first-capture" / "receipts" / f"{monitor_id}-{authorization_sha[:16]}.json"


def _existing_success_for_monitor(operations_root: Path, onboarding_sha: str, monitor_id: str) -> bool:
    root = operations_root / "ctgov-first-capture" / "receipts"
    if not root.is_dir():
        return False
    for path in root.glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError(f"Malformed existing first-capture receipt: {path}")
        if (
            isinstance(value, dict)
            and value.get("status") == "SUCCESS_IDENTITY_VERIFIED"
            and value.get("onboarding_manifest_sha256") == onboarding_sha
            and value.get("draft_monitor_id") == monitor_id
        ):
            return True
    return False


def _write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    payload = json.dumps(dict(receipt), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ValueError(f"FIRST_CAPTURE_RECEIPT_COLLISION_REFUSED: {path}")
        return
    path.write_text(payload, encoding="utf-8")


def execute_first_captures(
    onboarding_dir: Path,
    authorization_path: Path,
    operations_root: Path,
    *,
    allow_network: bool,
    transport: Any | None = None,
    dns_guard: DnsGuard | None = None,
    requested_at: str | None = None,
) -> dict[str, Any]:
    operations_root = _require_operations_boundary(operations_root, authorization_path)
    onboarding = verify_onboarding(onboarding_dir)
    authorization = load_first_capture_authorization(authorization_path, onboarding)
    if not allow_network:
        raise PermissionError("--allow-network is required for first-capture execution")
    if os.environ.get("NEUROAI_LIVE_COLLECTION", "").strip() != "1":
        raise PermissionError("NEUROAI_LIVE_COLLECTION=1 is required in addition to --allow-network and authorization")

    capture_time = requested_at or _utc_now()
    quarantine_root = operations_root / "quarantine"
    collector = _build_collector(quarantine_root, transport=transport, dns_guard=dns_guard)
    service = EvidenceCollectionService(collector)
    adapter = ClinicalTrialsGovAdapter(collector)
    receipts: list[dict[str, Any]] = []

    for monitor_id in sorted(onboarding["plans"]):
        plan = onboarding["plans"][monitor_id]
        decision = authorization["decisions"][monitor_id]
        if decision["decision"] == "DEFER":
            receipts.append(
                {
                    "schema_version": "0.1.0",
                    "artifact": "ctgov_first_capture_receipt",
                    "status": "DEFERRED_NO_NETWORK",
                    "onboarding_manifest_sha256": onboarding["manifest_sha256"],
                    "first_capture_authorization_sha256": authorization["sha256"],
                    "draft_monitor_id": monitor_id,
                    "source_id": plan["source_id"],
                    "nct_id": plan["nct_id"],
                    "network_execution_performed": False,
                    "quarantine_approval_performed": False,
                    "monitor_registry_successor_created": False,
                    "source_namespace_publication_performed": False,
                    "trial_entity_creation_performed": False,
                    "trial_site_relationship_creation_performed": False,
                    "assessment_mutation_performed": False,
                    "canonical_successor_ready": False,
                    "boundary": "Explicit first-capture DEFER disposition; no network execution or downstream authority.",
                }
            )
            continue

        if _existing_success_for_monitor(operations_root, onboarding["manifest_sha256"], monitor_id):
            raise ValueError(f"REPEAT_SUCCESSFUL_FIRST_CAPTURE_REFUSED: {monitor_id}")

        request = build_collection_request(plan, onboarding["manifest_sha256"], requested_at=capture_time)
        wb_auth = build_authorization_packet(
            authorization_id=f"CTGOV-FIRST-{authorization['sha256'][:20]}-{monitor_id[-8:]}",
            authorized_by=authorization["record"]["authorized_by"],
            purpose=(
                f"Bounded CT.gov first capture for {monitor_id}; onboarding="
                f"{onboarding['manifest_sha256']}; authorization={authorization['sha256']}"
            ),
            network_mode="AUTHORIZED_NETWORK",
            network_permitted=True,
            authorized_at=authorization["record"]["authorized_at"],
        )
        outcome = service.collect(wb_auth, request, attempt_count=1)

        base = {
            "schema_version": "0.1.0",
            "artifact": "ctgov_first_capture_receipt",
            "onboarding_manifest_sha256": onboarding["manifest_sha256"],
            "first_capture_authorization_sha256": authorization["sha256"],
            "workbench_commit": WORKBENCH_COMMIT,
            "collector_profile_id": PROFILE_ID,
            "collector_configuration_sha256": collector_configuration_hash(),
            "draft_monitor_id": monitor_id,
            "source_id": plan["source_id"],
            "nct_id": plan["nct_id"],
            "request_id": request["request_id"],
            "primary_route_id": plan["initial_capture_route_id"],
            "requested_url": request["requested_url"],
            "network_execution_performed": True,
            "quarantine_approval_performed": False,
            "monitor_registry_successor_created": False,
            "source_namespace_publication_performed": False,
            "trial_entity_creation_performed": False,
            "trial_site_relationship_creation_performed": False,
            "assessment_mutation_performed": False,
            "canonical_successor_ready": False,
            "boundary": (
                "Sanitized first-capture receipt. It records controlled retrieval/identity mechanics only; "
                "raw response bytes remain in quarantine and no downstream authority is created."
            ),
        }
        if outcome.kind != "result":
            receipt = {
                **base,
                "status": "BLOCKED_COLLECTION_FAILURE",
                "collection_outcome_kind": outcome.kind,
                "failure_id": outcome.record.get("failure_id"),
                "failure_class": outcome.record.get("failure_class"),
                "failure_message": outcome.record.get("failure_message"),
                "result_id": None,
                "quarantine_id": None,
                "content_sha256": None,
                "identity_verified": False,
            }
            _write_receipt(_receipt_path(operations_root, monitor_id, authorization["sha256"]), receipt)
            receipts.append(receipt)
            continue

        result = outcome.record
        quarantine = outcome.quarantine_record
        if not isinstance(quarantine, dict):
            raise ValueError("Successful first capture missing persisted quarantine record")
        verify_result_quarantine_binding(result, quarantine)
        if result.get("http_status") != 200:
            raise ValueError("First capture requires HTTP 200")
        if result.get("media_type") != "application/json":
            raise ValueError("First capture requires application/json")
        if result.get("evidence_state") != "RETRIEVED_BYTES_NOT_SUBSTANTIVELY_ADJUDICATED":
            raise ValueError("First capture evidence state mismatch")
        if result.get("requested_url") != request["requested_url"] or result.get("final_url") != request["requested_url"]:
            raise ValueError("First capture PRIMARY route/final URL drift")
        if result.get("redirect_chain") != []:
            raise ValueError("First capture must not follow redirects")

        raw = _safe_capture_bytes(quarantine_root, str(result["quarantine_path"]))
        if _sha_bytes(raw) != result.get("sha256") or len(raw) != result.get("size_bytes"):
            raise ValueError("First capture quarantined bytes disagree with result digest/size")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            receipt = {
                **base,
                "status": "BLOCKED_INVALID_JSON",
                "collection_outcome_kind": "result",
                "result_id": result.get("result_id"),
                "quarantine_id": quarantine.get("quarantine_id"),
                "content_sha256": result.get("sha256"),
                "quarantine_path": result.get("quarantine_path"),
                "identity_verified": False,
            }
            _write_receipt(_receipt_path(operations_root, monitor_id, authorization["sha256"]), receipt)
            receipts.append(receipt)
            continue
        if not isinstance(payload, dict):
            raise ValueError("CT.gov first capture JSON must be an object")

        try:
            normalized = adapter.normalize_study(payload)
        except ValueError:
            normalized = None
        observed_nct = normalized.get("nct_id") if isinstance(normalized, dict) else None
        if observed_nct != plan["nct_id"]:
            receipt = {
                **base,
                "status": "BLOCKED_NCT_IDENTITY_MISMATCH",
                "collection_outcome_kind": "result",
                "result_id": result.get("result_id"),
                "quarantine_id": quarantine.get("quarantine_id"),
                "content_sha256": result.get("sha256"),
                "quarantine_path": result.get("quarantine_path"),
                "observed_nct_id": observed_nct,
                "identity_verified": False,
            }
            _write_receipt(_receipt_path(operations_root, monitor_id, authorization["sha256"]), receipt)
            receipts.append(receipt)
            continue

        receipt = {
            **base,
            "status": "SUCCESS_IDENTITY_VERIFIED",
            "collection_outcome_kind": "result",
            "result_id": result["result_id"],
            "quarantine_id": quarantine["quarantine_id"],
            "content_sha256": result["sha256"],
            "size_bytes": result["size_bytes"],
            "quarantine_path": result["quarantine_path"],
            "quarantine_approval_state": quarantine["approval_state"],
            "normalized_study_aggregate_digest": normalized["aggregate_digest"],
            "observed_nct_id": observed_nct,
            "identity_verified": True,
        }
        _write_receipt(_receipt_path(operations_root, monitor_id, authorization["sha256"]), receipt)
        receipts.append(receipt)

    summary = {
        "schema_version": "0.1.0",
        "artifact": "ctgov_first_capture_execution_summary",
        "onboarding_manifest_sha256": onboarding["manifest_sha256"],
        "first_capture_authorization_sha256": authorization["sha256"],
        "workbench_commit": WORKBENCH_COMMIT,
        "collector_profile_id": PROFILE_ID,
        "collector_configuration_sha256": collector_configuration_hash(),
        "authorized_plan_count": sum(
            1 for row in authorization["decisions"].values() if row["decision"] == "AUTHORIZE_PRIMARY_CAPTURE"
        ),
        "deferred_plan_count": sum(1 for row in authorization["decisions"].values() if row["decision"] == "DEFER"),
        "success_count": sum(1 for row in receipts if row["status"] == "SUCCESS_IDENTITY_VERIFIED"),
        "blocked_count": sum(1 for row in receipts if row["status"].startswith("BLOCKED_")),
        "receipts": receipts,
        "raw_response_bytes_embedded": False,
        "quarantine_approval_performed": False,
        "monitor_registry_successor_created": False,
        "source_namespace_publication_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "boundary": (
            "Execution summary for bounded pre-registry CT.gov first captures. Success is retrieval + exact NCT identity "
            "verification only; quarantine remains pending human approval and no monitor/canonical/assessment authority follows."
        ),
    }
    summary_path = operations_root / "ctgov-first-capture" / f"summary-{authorization['sha256'][:16]}.json"
    _write_receipt(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onboarding-dir", type=Path, required=True)
    parser.add_argument("--authorization-packet", type=Path, required=True)
    parser.add_argument("--operations-root", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    result = execute_first_captures(
        args.onboarding_dir,
        args.authorization_packet,
        args.operations_root,
        allow_network=args.allow_network,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["blocked_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
