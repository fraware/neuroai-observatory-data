#!/usr/bin/env python3
"""Execute explicitly authorized CT.gov primary first captures into Workbench quarantine.

This is an operational/S3 gate. It consumes a verified noncanonical monitor-onboarding package
and an explicit local first-capture authorization packet. It may retrieve only the plan's primary
ClinicalTrials.gov API route. Successful bytes remain in Workbench quarantine with pending human
approval. This gate never approves quarantine, prepares monitoring handoff, creates a monitor or
monitor-registry successor, publishes a Source, mutates graph/assessment state, or authorizes a
canonical release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

WORKBENCH_COMMIT = "a25b09bdf0533e73cbaf65d909acf4a4fa0fc065"
COLLECTOR_PROFILE_ID = "CTGOV_FIRST_CAPTURE_V0_1"
EXPECTED_ONBOARDING_FILES = {"monitor-review-summary.json", "ctgov-monitor-onboarding.json"}
REQUIRED_TEMPLATE_FIELDS = [
    "requested_at",
    "onboarding_manifest_sha256",
    "collector_version",
    "configuration_hash",
    "boundary",
]
FIRST_CAPTURE_BOUNDARY = (
    "Explicit pre-registry CT.gov primary-route first capture into Workbench quarantine only. "
    "Retrieval and exact NCT identity matching do not establish clinical truth, approve evidence, "
    "create a monitor, authorize monitoring handoff, or publish canonical state."
)
SUMMARY_BOUNDARY = (
    "Sanitized operational first-capture accounting only. Raw capture bytes remain in the caller-supplied "
    "Workbench quarantine. Every captured object remains ineligible for monitoring handoff until a later "
    "explicit quarantine-review gate approves it."
)
COLLECTOR_PROFILE: dict[str, Any] = {
    "profile_id": COLLECTOR_PROFILE_ID,
    "workbench_commit": WORKBENCH_COMMIT,
    "collector_version": "0.3.0.dev0-collector",
    "user_agent": "NeuroAI-Observatory-CTGov-FirstCapture/0.1 (+https://github.com/fraware/neuroai-observatory-data)",
    "max_response_bytes": 2 * 1024 * 1024,
    "max_redirects": 0,
    "max_decompression_ratio": 50,
    "connect_timeout_seconds": 10.0,
    "read_timeout_seconds": 30.0,
    "total_timeout_seconds": 45.0,
    "max_attempts": 1,
    "retry_initial_delay_seconds": 1.0,
    "retry_max_delay_seconds": 1.0,
    "requests_per_host_per_minute": 6,
    "allowed_content_types": ["application/json"],
}

ROOT = Path(__file__).parents[1].resolve()


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def collector_configuration_hash() -> str:
    return _digest(COLLECTOR_PROFILE)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _normalize_timestamp(value: str | None = None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("requested_at must include an explicit timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def _reserve_request(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(dict(value), indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"FIRST_CAPTURE_REQUEST_ALREADY_RESERVED: {path.name}") from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def verify_onboarding(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Onboarding manifest.json missing")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("Onboarding manifest must be an object")
    if manifest.get("schema_version") != "0.1.0" or manifest.get("status") != "NONCANONICAL_CT_GOV_MONITOR_ONBOARDING":
        raise ValueError("Onboarding manifest status/contract mismatch")
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
            raise ValueError(f"Onboarding authority boundary weakened: {key}")

    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("file_count") != len(entries):
        raise ValueError("Onboarding manifest file list/count invalid")
    paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    if len(paths) != len(entries) or set(paths) != EXPECTED_ONBOARDING_FILES or len(paths) != len(set(paths)):
        raise ValueError("Onboarding manifest file set mismatch")
    for entry in entries:
        relative = entry.get("path")
        if not isinstance(relative, str) or Path(relative).name != relative:
            raise ValueError(f"Unsafe onboarding manifest path {relative!r}")
        path = root / relative
        if not path.is_file():
            raise ValueError(f"Onboarding file missing: {relative}")
        payload = path.read_bytes()
        if entry.get("sha256") != _sha256_bytes(payload) or entry.get("bytes") != len(payload):
            raise ValueError(f"Onboarding manifest mismatch: {relative}")

    package = json.loads((root / "ctgov-monitor-onboarding.json").read_text(encoding="utf-8"))
    if not isinstance(package, dict):
        raise ValueError("CT.gov onboarding package must be an object")
    if package.get("schema_version") != "0.1.0" or package.get("status") != "DRAFT_NONCANONICAL_MONITOR_ONBOARDING":
        raise ValueError("CT.gov onboarding package status/contract mismatch")
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

    plans_raw = package.get("plans")
    if not isinstance(plans_raw, list) or not plans_raw or package.get("approved_plan_count") != len(plans_raw):
        raise ValueError("CT.gov onboarding plans missing/count mismatch")
    plans: dict[str, dict[str, Any]] = {}
    request_ids: set[str] = set()
    for plan in plans_raw:
        if not isinstance(plan, dict):
            raise ValueError("CT.gov onboarding plan must be an object")
        monitor_id = plan.get("draft_monitor_id")
        source_id = plan.get("source_id")
        nct_id = plan.get("nct_id")
        template = plan.get("first_capture_request_template")
        routes = plan.get("routes")
        if not isinstance(monitor_id, str) or monitor_id in plans:
            raise ValueError("Draft monitor identities must be unique")
        if not isinstance(source_id, str) or not source_id or not isinstance(nct_id, str):
            raise ValueError(f"{monitor_id}: Source/NCT identity invalid")
        expected_url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
        if not isinstance(routes, list) or len(routes) != 3 or not all(isinstance(route, dict) for route in routes):
            raise ValueError(f"{monitor_id}: route set invalid")
        primary = routes[0]
        if (
            primary.get("priority") != 0
            or primary.get("role") != "PRIMARY"
            or primary.get("route_class") != "PRIMARY"
            or primary.get("url") != expected_url
            or primary.get("accept") != "application/json"
            or plan.get("initial_capture_route_id") != primary.get("route_id")
        ):
            raise ValueError(f"{monitor_id}: primary first-capture route contract mismatch")
        if not isinstance(template, dict):
            raise ValueError(f"{monitor_id}: first-capture request template missing")
        request_id = template.get("request_id")
        if not isinstance(request_id, str) or request_id in request_ids:
            raise ValueError(f"{monitor_id}: first-capture request identity invalid/duplicate")
        request_ids.add(request_id)
        if (
            template.get("source_id") != source_id
            or template.get("monitor_id") != monitor_id
            or template.get("requested_url") != expected_url
            or template.get("execution_state") != "TEMPLATE_NOT_EXECUTED"
            or template.get("required_execution_fields") != REQUIRED_TEMPLATE_FIELDS
        ):
            raise ValueError(f"{monitor_id}: first-capture template binding mismatch")
        if "registry_sha256" in template.get("required_execution_fields", []):
            raise ValueError(f"{monitor_id}: pre-registry template must not request registry_sha256")
        plans[monitor_id] = plan
    return {
        "root": root,
        "manifest": manifest,
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "package": package,
        "plans": plans,
    }


def load_authorization(path: Path, onboarding: Mapping[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("First-capture authorization packet missing")
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("First-capture authorization must be an object")
    if (
        value.get("schema_version") != "0.1.0"
        or value.get("artifact") != "ctgov_first_capture_authorization"
        or value.get("status") != "EXPLICIT_LOCAL_FIRST_CAPTURE_AUTHORIZATION"
    ):
        raise ValueError("First-capture authorization status/contract mismatch")
    if value.get("onboarding_manifest_sha256") != onboarding["manifest_sha256"]:
        raise ValueError("First-capture authorization onboarding-manifest binding mismatch")
    if value.get("workbench_commit") != WORKBENCH_COMMIT:
        raise ValueError("First-capture authorization Workbench commit mismatch")
    if value.get("collector_profile_id") != COLLECTOR_PROFILE_ID:
        raise ValueError("First-capture authorization collector profile mismatch")
    if value.get("identity_boundary") != "LOCAL_UNAUTHENTICATED_ATTRIBUTION":
        raise ValueError("First-capture authorization identity boundary mismatch")
    for key in ("authorized_by", "authorized_at", "authority_boundary"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"First-capture authorization field {key} must be non-empty")
    expected_authority = {
        "network_execution_authorized": True,
        "primary_route_only": True,
        "fallback_route_authorized": False,
        "quarantine_approval_authorized": False,
        "monitoring_handoff_authorized": False,
        "monitor_registry_successor_authorized": False,
        "source_namespace_publication_authorized": False,
        "trial_entity_creation_authorized": False,
        "trial_site_relationship_creation_authorized": False,
        "assessment_mutation_authorized": False,
        "canonical_publication_authorized": False,
    }
    for key, expected in expected_authority.items():
        if value.get(key) is not expected:
            raise ValueError(f"First-capture authorization authority boundary weakened: {key}")

    captures = value.get("captures")
    if not isinstance(captures, list) or not captures or not all(isinstance(row, dict) for row in captures):
        raise ValueError("First-capture authorization captures must be a non-empty object array")
    decisions: dict[str, dict[str, Any]] = {}
    for row in captures:
        monitor_id = row.get("draft_monitor_id")
        if monitor_id not in onboarding["plans"]:
            raise ValueError(f"First-capture authorization contains unknown draft monitor {monitor_id!r}")
        if monitor_id in decisions:
            raise ValueError(f"Duplicate first-capture authorization for {monitor_id}")
        plan = onboarding["plans"][monitor_id]
        template = plan["first_capture_request_template"]
        if (
            row.get("request_id") != template["request_id"]
            or row.get("source_id") != plan["source_id"]
            or row.get("nct_id") != plan["nct_id"]
        ):
            raise ValueError(f"{monitor_id}: authorization identity binding mismatch")
        if row.get("decision") not in {"AUTHORIZE_PRIMARY_CAPTURE", "DEFER"}:
            raise ValueError(f"{monitor_id}: unsupported first-capture authorization decision")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            raise ValueError(f"{monitor_id}: authorization rationale must be non-empty")
        decisions[monitor_id] = row
    if set(decisions) != set(onboarding["plans"]):
        missing = sorted(set(onboarding["plans"]) - set(decisions))
        raise ValueError(f"First-capture authorization must dispose every onboarding plan; missing={missing}")
    return {"record": value, "sha256": _sha256_bytes(payload), "decisions": decisions}


def _build_config() -> Any:
    from neuroai_workbench.collector import CollectorConfig

    return CollectorConfig(
        collector_version=COLLECTOR_PROFILE["collector_version"],
        configuration_hash=collector_configuration_hash(),
        user_agent=COLLECTOR_PROFILE["user_agent"],
        max_response_bytes=COLLECTOR_PROFILE["max_response_bytes"],
        max_redirects=COLLECTOR_PROFILE["max_redirects"],
        max_decompression_ratio=COLLECTOR_PROFILE["max_decompression_ratio"],
        connect_timeout_seconds=COLLECTOR_PROFILE["connect_timeout_seconds"],
        read_timeout_seconds=COLLECTOR_PROFILE["read_timeout_seconds"],
        total_timeout_seconds=COLLECTOR_PROFILE["total_timeout_seconds"],
        max_attempts=COLLECTOR_PROFILE["max_attempts"],
        retry_initial_delay_seconds=COLLECTOR_PROFILE["retry_initial_delay_seconds"],
        retry_max_delay_seconds=COLLECTOR_PROFILE["retry_max_delay_seconds"],
        requests_per_host_per_minute=COLLECTOR_PROFILE["requests_per_host_per_minute"],
        allowed_content_types=frozenset(COLLECTOR_PROFILE["allowed_content_types"]),
    )


def _materialize_request(plan: Mapping[str, Any], *, requested_at: str, onboarding_manifest_sha256: str) -> dict[str, Any]:
    template = plan["first_capture_request_template"]
    return {
        "request_id": template["request_id"],
        "source_id": plan["source_id"],
        "monitor_id": plan["draft_monitor_id"],
        "requested_url": template["requested_url"],
        "requested_at": requested_at,
        "onboarding_manifest_sha256": onboarding_manifest_sha256,
        "collector_version": COLLECTOR_PROFILE["collector_version"],
        "configuration_hash": collector_configuration_hash(),
        "boundary": FIRST_CAPTURE_BOUNDARY,
    }


def execute_first_capture(
    onboarding_dir: Path,
    authorization_packet: Path,
    operations_root: Path,
    *,
    execution_mode: str,
    requested_at: str | None = None,
    transport: Any | None = None,
    dns_guard: Any | None = None,
) -> dict[str, Any]:
    if execution_mode not in {"INJECTED_TEST_TRANSPORT", "OPT_IN_NETWORK"}:
        raise ValueError("Unsupported first-capture execution mode")
    onboarding = verify_onboarding(onboarding_dir)
    authorization = load_authorization(authorization_packet, onboarding)

    resolved_ops = operations_root.resolve()
    if resolved_ops == ROOT or _is_within(resolved_ops, ROOT):
        raise ValueError("OPERATIONS_ROOT_INSIDE_S2_REPOSITORY_REFUSED")
    resolved_ops.mkdir(parents=True, exist_ok=True)
    quarantine_root = resolved_ops / "quarantine"
    execution_root = resolved_ops / "first-capture" / "executions"
    normalized_requested_at = _normalize_timestamp(requested_at)

    from neuroai_workbench.collector import ClinicalTrialsGovAdapter, HttpCollector, PinnedSocketHttpTransport

    if execution_mode == "OPT_IN_NETWORK":
        if transport is not None:
            raise ValueError("OPT_IN_NETWORK must use the pinned production transport, not a caller-supplied transport")
        transport = PinnedSocketHttpTransport(max_wire_bytes=COLLECTOR_PROFILE["max_response_bytes"])
    elif transport is None:
        raise ValueError("INJECTED_TEST_TRANSPORT requires an explicit injected transport")

    config = _build_config()
    collector = HttpCollector(config=config, transport=transport, quarantine_root=quarantine_root)
    if dns_guard is not None:
        collector.http_client.dns_guard = dns_guard
    adapter = ClinicalTrialsGovAdapter(collector)

    rows: list[dict[str, Any]] = []
    authorized_count = 0
    deferred_count = 0
    for monitor_id in sorted(onboarding["plans"]):
        plan = onboarding["plans"][monitor_id]
        decision = authorization["decisions"][monitor_id]
        if decision["decision"] == "DEFER":
            deferred_count += 1
            continue
        authorized_count += 1
        request = _materialize_request(
            plan,
            requested_at=normalized_requested_at,
            onboarding_manifest_sha256=onboarding["manifest_sha256"],
        )
        request_digest = _digest(request)
        reservation_path = execution_root / f"{request['request_id']}.json"
        reservation = {
            "schema_version": "0.1.0",
            "artifact": "ctgov_first_capture_execution_reservation",
            "status": "STARTED",
            "request_id": request["request_id"],
            "draft_monitor_id": monitor_id,
            "source_id": plan["source_id"],
            "nct_id": plan["nct_id"],
            "requested_at": normalized_requested_at,
            "onboarding_manifest_sha256": onboarding["manifest_sha256"],
            "authorization_packet_sha256": authorization["sha256"],
            "workbench_commit": WORKBENCH_COMMIT,
            "collector_profile_id": COLLECTOR_PROFILE_ID,
            "collector_configuration_hash": collector_configuration_hash(),
            "collection_request_sha256": request_digest,
            "authority_boundary": "Reservation created before first-capture execution; automatic replay is refused.",
        }
        _reserve_request(reservation_path, reservation)

        outcome = collector.collect(request)
        row: dict[str, Any] = {
            "draft_monitor_id": monitor_id,
            "request_id": request["request_id"],
            "source_id": plan["source_id"],
            "expected_nct_id": plan["nct_id"],
            "requested_url": request["requested_url"],
            "requested_at": normalized_requested_at,
            "execution_state": "COLLECTOR_FAILURE",
            "result_id": None,
            "failure_id": None,
            "http_status": None,
            "content_sha256": None,
            "size_bytes": None,
            "quarantine_id": None,
            "quarantine_approval_state": None,
            "evidence_state": None,
            "observed_nct_id": None,
            "normalized_aggregate_digest": None,
            "identity_match": None,
            "handoff_eligible": False,
            "raw_bytes_in_summary": False,
            "boundary": FIRST_CAPTURE_BOUNDARY,
        }

        if outcome.kind == "failure":
            row["failure_id"] = outcome.record.get("failure_id")
            reservation = {
                **reservation,
                "status": "COMPLETED_COLLECTOR_FAILURE",
                "failure_id": row["failure_id"],
            }
            _atomic_json(reservation_path, reservation)
            rows.append(row)
            continue

        result = outcome.record
        quarantine = outcome.quarantine_record
        if quarantine is None:
            raise RuntimeError("Successful first capture did not expose a persisted quarantine record")
        if result.get("evidence_state") != "RETRIEVED_BYTES_NOT_SUBSTANTIVELY_ADJUDICATED":
            raise RuntimeError("Successful first capture evidence state is outside the quarantine-only boundary")
        if quarantine.get("approval_state") != "PENDING_HUMAN_APPROVAL":
            raise RuntimeError("First-capture quarantine record was not left pending human approval")
        if (
            quarantine.get("source_id") != plan["source_id"]
            or quarantine.get("monitor_id") != monitor_id
            or quarantine.get("result_id") != result.get("result_id")
            or quarantine.get("sha256") != result.get("sha256")
        ):
            raise RuntimeError("First-capture result/quarantine identity binding mismatch")

        row.update(
            {
                "result_id": result.get("result_id"),
                "http_status": result.get("http_status"),
                "content_sha256": result.get("sha256"),
                "size_bytes": result.get("size_bytes"),
                "quarantine_id": quarantine.get("quarantine_id"),
                "quarantine_approval_state": quarantine.get("approval_state"),
                "evidence_state": result.get("evidence_state"),
            }
        )

        bytes_path = (quarantine_root / str(quarantine["quarantine_path"])).resolve()
        if not _is_within(bytes_path, quarantine_root.resolve()) or not bytes_path.is_file():
            raise RuntimeError("First-capture quarantine bytes missing or escaped quarantine root")
        if _sha256_bytes(bytes_path.read_bytes()) != result.get("sha256"):
            raise RuntimeError("First-capture quarantine bytes do not match result digest")

        try:
            payload = json.loads(bytes_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("CT.gov first-capture JSON root must be an object")
            normalized = adapter.normalize_study(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            row["execution_state"] = "CAPTURED_JSON_INVALID_BLOCKED"
            reservation = {
                **reservation,
                "status": "COMPLETED_CAPTURED_JSON_INVALID_BLOCKED",
                "result_id": result.get("result_id"),
                "quarantine_id": quarantine.get("quarantine_id"),
            }
            _atomic_json(reservation_path, reservation)
            rows.append(row)
            continue

        observed_nct = normalized["nct_id"]
        identity_match = observed_nct == plan["nct_id"]
        row["observed_nct_id"] = observed_nct
        row["normalized_aggregate_digest"] = normalized["aggregate_digest"]
        row["identity_match"] = identity_match
        row["execution_state"] = (
            "CAPTURED_IDENTITY_VERIFIED_PENDING_QUARANTINE_REVIEW"
            if identity_match
            else "CAPTURED_IDENTITY_MISMATCH_BLOCKED"
        )
        reservation = {
            **reservation,
            "status": "COMPLETED_IDENTITY_VERIFIED_PENDING_QUARANTINE_REVIEW"
            if identity_match
            else "COMPLETED_IDENTITY_MISMATCH_BLOCKED",
            "result_id": result.get("result_id"),
            "quarantine_id": quarantine.get("quarantine_id"),
            "observed_nct_id": observed_nct,
            "identity_match": identity_match,
        }
        _atomic_json(reservation_path, reservation)
        rows.append(row)

    summary = {
        "schema_version": "0.1.0",
        "artifact": "ctgov_first_capture_summary",
        "status": "NONCANONICAL_OPERATIONAL_FIRST_CAPTURE",
        "onboarding_manifest_sha256": onboarding["manifest_sha256"],
        "authorization_packet_sha256": authorization["sha256"],
        "workbench_commit": WORKBENCH_COMMIT,
        "collector_profile_id": COLLECTOR_PROFILE_ID,
        "collector_configuration_hash": collector_configuration_hash(),
        "execution_mode": execution_mode,
        "capture_execution_performed": authorized_count > 0,
        "network_execution_performed": execution_mode == "OPT_IN_NETWORK" and authorized_count > 0,
        "authorized_capture_count": authorized_count,
        "deferred_capture_count": deferred_count,
        "capture_rows": rows,
        "quarantine_approval_performed": False,
        "monitoring_handoff_performed": False,
        "monitor_registry_successor_created": False,
        "monitor_creation_performed": False,
        "source_namespace_publication_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": SUMMARY_BOUNDARY,
    }
    return {
        "summary": summary,
        "onboarding": onboarding,
        "authorization": authorization,
        "operations_root": resolved_ops,
    }


def write_sanitized_outputs(result: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if output_dir == ROOT or _is_within(output_dir, ROOT):
        raise ValueError("FIRST_CAPTURE_SANITIZED_OUTPUT_INSIDE_S2_REPOSITORY_REFUSED")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_payload = (json.dumps(result["summary"], indent=2, sort_keys=True) + "\n").encode("utf-8")
    summary_path = output_dir / "first-capture-summary.json"
    if summary_path.exists() and summary_path.read_bytes() != summary_payload:
        raise ValueError(f"OUTPUT_COLLISION_REFUSED: {summary_path}")
    summary_path.write_bytes(summary_payload)
    manifest = {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_OPERATIONAL_FIRST_CAPTURE_MANIFEST",
        "file_count": 1,
        "files": [{"path": "first-capture-summary.json", "sha256": _sha256_bytes(summary_payload), "bytes": len(summary_payload)}],
        "raw_capture_bytes_packaged": False,
        "quarantine_approval_performed": False,
        "monitoring_handoff_performed": False,
        "monitor_registry_successor_created": False,
        "monitor_creation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": "Manifest for sanitized operational summary only; raw capture bytes remain in Workbench quarantine.",
    }
    manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists() and manifest_path.read_bytes() != manifest_payload:
        raise ValueError(f"OUTPUT_COLLISION_REFUSED: {manifest_path}")
    manifest_path.write_bytes(manifest_payload)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onboarding-dir", type=Path, required=True)
    parser.add_argument("--authorization-packet", type=Path, required=True)
    parser.add_argument("--operations-root", type=Path, required=True)
    parser.add_argument("--sanitized-output-dir", type=Path, required=True)
    parser.add_argument("--requested-at")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicitly authorize this invocation to instantiate the DNS-pinned production network transport.",
    )
    args = parser.parse_args()
    if not args.allow_network:
        raise SystemExit("Refusing network execution: --allow-network is required")
    result = execute_first_capture(
        args.onboarding_dir,
        args.authorization_packet,
        args.operations_root,
        execution_mode="OPT_IN_NETWORK",
        requested_at=args.requested_at,
    )
    manifest = write_sanitized_outputs(result, args.sanitized_output_dir)
    print(
        json.dumps(
            {
                "authorized_capture_count": result["summary"]["authorized_capture_count"],
                "deferred_capture_count": result["summary"]["deferred_capture_count"],
                "manifest": manifest,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
