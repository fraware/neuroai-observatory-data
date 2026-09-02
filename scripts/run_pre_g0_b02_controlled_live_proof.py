"""Execute the bounded PRE-G0 B02 governed controlled-live acquisition proof.

The proof uses exactly one reviewed public source from the immutable v1.5 monitor
registry and the Workbench live-shadow facade. Response bytes remain in an ephemeral
quarantine root; only sanitized proof metadata is emitted. No capture handoff,
assessment mutation, or canonical publication is authorized.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from build_analytical_projection import (
    DEFAULT_RECORDS_DIR,
    DEFAULT_SUPPLEMENTAL_DIR,
    build_tables,
    load_inputs,
)
from build_development_monitor_registry import (
    build_development_registry,
    verify_development_registry,
    write_registry,
)
from neuroai_workbench.collector.authorization import (
    LIVE_AUTHORIZATION_ENV,
    LIVE_COLLECTION_ENV,
    build_authorization_packet,
)
from neuroai_workbench.monitoring import initialize_monitoring, plan_monitoring_run
from neuroai_workbench.shadow_refresh.live import run_live_cohort_collection
from neuroai_workbench.shadow_refresh.schemas import SHADOW_EVALUATION_STATUS
from source_lifecycle_overlay import (
    DEFAULT_LIFECYCLE_OVERLAY,
    DEFAULT_ROUTE_POLICY,
    load_verified_lifecycle_overlay,
)

EXPECTED_WORKBENCH_COMMIT = "33414065e53c45221d29209ef4703b6d900781f7"
PROOF_SOURCE_ID = "SRC-0002"
PROOF_SOURCE_EXPECTED = {
    "source_id": PROOF_SOURCE_ID,
    "url": "https://neurosity.co/",
    "publisher": "Neurosity",
    "source_class": "OFFICIAL_COMPANY_PAGE",
    "cadence": "QUARTERLY",
    "last_successful_retrieval": "2026-07-29",
    "network_access_required": True,
}
EXPECTED_SCANNER_ID = "workbench.fail_closed_default"
EXPECTED_SCAN_STATE = "NOT_EXECUTED_FAIL_CLOSED"
STATUS = "PRE_G0_B02_CONTROLLED_LIVE_PROOF_NOT_CANONICAL"
BOUNDARY = (
    "This PRE-G0 proof demonstrates one bounded public retrieval through the Workbench "
    "live-shadow authorization, pinned-network, quarantine, and content-safety custody path. "
    "It does not establish scientific truth, source authenticity beyond retrieval identity, "
    "clinical effectiveness, safety, regulatory status, conformance, completeness, "
    "assessment authority, operational health of other workflows, or canonical publication."
)


def _restore_env(name: str, prior: str | None) -> None:
    if prior is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = prior


def _build_registry(
    *,
    records_dir: Path,
    supplemental_dir: Path,
    route_policy_path: Path,
    lifecycle_overlay_path: Path,
) -> dict[str, Any]:
    inputs = load_inputs(
        records_dir.resolve(),
        supplemental_dir=supplemental_dir.resolve(),
    )
    tables = build_tables(inputs)
    source_ids = {
        str(row["record_id"])
        for row in tables["sources"]
        if row.get("record_id")
    }
    monitor_source_ids = {
        str(row["record_id"])
        for row in tables["source_monitors"]
        if row.get("record_id")
    }
    _, _, transitions = load_verified_lifecycle_overlay(
        route_policy_path=route_policy_path,
        overlay_path=lifecycle_overlay_path,
        effective_source_ids=source_ids,
        governing_monitor_source_ids=monitor_source_ids,
    )
    registry = build_development_registry(inputs, transitions)
    verify_development_registry(registry)
    return registry


def _resolve_fixed_source(registry: dict[str, Any]) -> dict[str, Any]:
    matches = [
        record
        for record in registry.get("sources", [])
        if isinstance(record, dict) and record.get("source_id") == PROOF_SOURCE_ID
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one {PROOF_SOURCE_ID} monitor record; found {len(matches)}"
        )
    source = dict(matches[0])
    mismatches = {
        field: {"expected": expected, "observed": source.get(field)}
        for field, expected in PROOF_SOURCE_EXPECTED.items()
        if source.get(field) != expected
    }
    if mismatches:
        raise ValueError(
            "PRE-G0 B02 fixed proof source identity changed: "
            + json.dumps(mismatches, sort_keys=True)
        )
    return source


def _plan_single_source(
    *,
    registry: dict[str, Any],
    workspace: Path,
    as_of: str,
    actor: str,
) -> tuple[dict[str, Any], str]:
    registry_path = workspace / "input" / "development-monitor-registry.json"
    write_registry(registry, registry_path)
    monitoring_workspace = workspace / "monitoring"
    monitoring = initialize_monitoring(
        monitoring_workspace,
        registry_path,
        actor=actor,
    )
    plan = plan_monitoring_run(
        monitoring_workspace,
        as_of=as_of,
        source_ids=[PROOF_SOURCE_ID],
    )
    items = [
        item
        for bucket in ("due", "not_due", "manual")
        for item in plan.get(bucket, [])
        if isinstance(item, dict)
    ]
    if len(items) != 1 or items[0].get("source_id") != PROOF_SOURCE_ID:
        raise ValueError(
            "PRE-G0 B02 planner did not return exactly the fixed proof source"
        )
    if items[0].get("network_access_required") is not True:
        raise ValueError("PRE-G0 B02 proof source is not network-enabled")
    if any(
        item.get("source_id") == PROOF_SOURCE_ID
        for item in plan.get("manual", [])
        if isinstance(item, dict)
    ):
        raise ValueError("PRE-G0 B02 proof source unexpectedly entered manual queue")
    return plan, str(monitoring["registry_sha256"])


def _execute_live(
    *,
    plan: dict[str, Any],
    registry: dict[str, Any],
    registry_sha256: str,
    quarantine_root: Path,
    authorization_id: str,
    actor: str,
) -> dict[str, Any]:
    authorization = build_authorization_packet(
        authorization_id=authorization_id,
        authorized_by=actor,
        purpose=(
            "Explicit PRE-G0 B02 one-source controlled-live acquisition proof into "
            "ephemeral quarantine-only evaluation state."
        ),
        network_mode="AUTHORIZED_NETWORK",
        network_permitted=True,
    )
    prior_live = os.environ.get(LIVE_COLLECTION_ENV)
    prior_authorization = os.environ.get(LIVE_AUTHORIZATION_ENV)
    try:
        os.environ[LIVE_COLLECTION_ENV] = "1"
        os.environ[LIVE_AUTHORIZATION_ENV] = json.dumps(
            authorization,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return run_live_cohort_collection(
            plan=plan,
            registry=registry,
            registry_sha256=registry_sha256,
            quarantine_root=quarantine_root,
        )
    finally:
        _restore_env(LIVE_COLLECTION_ENV, prior_live)
        _restore_env(LIVE_AUTHORIZATION_ENV, prior_authorization)


def build_sanitized_proof(
    package: dict[str, Any],
    *,
    authorization_id: str,
    as_of: str,
    workbench_commit: str,
) -> dict[str, Any]:
    if workbench_commit != EXPECTED_WORKBENCH_COMMIT:
        raise ValueError(
            f"Expected Workbench {EXPECTED_WORKBENCH_COMMIT}, got {workbench_commit}"
        )
    if package.get("status") != SHADOW_EVALUATION_STATUS:
        raise ValueError(f"Unexpected live package status: {package.get('status')!r}")

    collector = package.get("collector")
    if not isinstance(collector, dict):
        raise ValueError("Live package collector metadata is missing")
    expected_collector = {
        "handoff_enabled": False,
        "default_transport": "PinnedSocketHttpTransport",
        "dns_guard": "DnsGuard",
    }
    for field, expected in expected_collector.items():
        if collector.get(field) != expected:
            raise ValueError(
                f"Controlled-live collector invariant {field} changed: "
                f"{collector.get(field)!r}"
            )

    run = package.get("collection_run")
    if not isinstance(run, dict):
        raise ValueError("Live package collection_run is missing")
    counts = run.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("Live package collection counts are missing")
    expected_counts = {"total": 1, "succeeded": 1, "failed": 0, "skipped": 0}
    for field, expected in expected_counts.items():
        if int(counts.get(field, -1)) != expected:
            raise ValueError(
                f"PRE-G0 B02 requires one successful retrieval; "
                f"{field}={counts.get(field)!r}"
            )

    outcomes = [
        item for item in run.get("outcomes", []) if isinstance(item, dict)
    ]
    if len(outcomes) != 1 or outcomes[0].get("source_id") != PROOF_SOURCE_ID:
        raise ValueError("Live package outcome identity does not match fixed proof source")
    if outcomes[0].get("status") != "SUCCESS":
        raise ValueError(
            f"Fixed proof source did not succeed: {outcomes[0].get('status')!r}"
        )

    digests = [
        item for item in package.get("capture_digests", []) if isinstance(item, dict)
    ]
    if len(digests) != 1 or digests[0].get("source_id") != PROOF_SOURCE_ID:
        raise ValueError(
            "PRE-G0 B02 requires exactly one durable capture digest for the fixed source"
        )
    capture = digests[0]
    if not isinstance(capture.get("sha256"), str) or len(str(capture["sha256"])) != 64:
        raise ValueError("Durable capture digest is missing or malformed")
    if int(capture.get("size_bytes") or 0) <= 0:
        raise ValueError("Durable capture size must be positive")

    content_safety = package.get("content_safety")
    if not isinstance(content_safety, dict):
        raise ValueError("Live package content-safety summary is missing")
    expected_scan_fields = {
        "scope": "ALL_DURABLE_RESULTS_IN_QUARANTINE_ROOT",
        "durable_result_records_checked": 1,
        "scans_created": 1,
        "existing_scans_verified": 0,
        "detail_exposed": False,
    }
    for field, expected in expected_scan_fields.items():
        if content_safety.get(field) != expected:
            raise ValueError(
                f"Content-safety custody invariant {field} changed: "
                f"{content_safety.get(field)!r}"
            )
    if content_safety.get("state_counts") != {EXPECTED_SCAN_STATE: 1}:
        raise ValueError(
            "Default PRE-G0 proof must remain fail-closed; no substantive CLEAN "
            "verdict is configured"
        )
    if content_safety.get("scanner_ids") != [EXPECTED_SCANNER_ID]:
        raise ValueError(
            "Unexpected PRE-G0 content-safety scanner IDs: "
            f"{content_safety.get('scanner_ids')!r}"
        )

    metadata = package.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Live package metadata is missing")
    authorization = metadata.get("authorization")
    if not isinstance(authorization, dict):
        raise ValueError("Live package authorization provenance is missing")
    if authorization.get("authorization_id") != authorization_id:
        raise ValueError("Authorization provenance does not match requested run ID")
    if authorization.get("identity_boundary") != "LOCAL_UNAUTHENTICATED_ATTRIBUTION":
        raise ValueError("Authorization identity boundary changed")
    authorization_sha256 = authorization.get("authorization_sha256")
    if not isinstance(authorization_sha256, str) or len(authorization_sha256) != 64:
        raise ValueError("Authorization digest is missing or malformed")

    return {
        "schema_version": "1",
        "status": STATUS,
        "as_of": as_of,
        "workbench_commit": workbench_commit,
        "source": {
            **PROOF_SOURCE_EXPECTED,
            "claim_boundary": (
                "The official company page establishes only the reviewed public retrieval "
                "target and current official representation/web presence. It does not "
                "independently establish clinical effectiveness, safety, scientific validity, "
                "commercial availability, or conformance."
            ),
        },
        "authorization": {
            "authorization_id": authorization_id,
            "authorization_sha256": authorization_sha256,
            "authorized_by": authorization.get("authorized_by"),
            "authorized_at": authorization.get("authorized_at"),
            "purpose": authorization.get("purpose"),
            "identity_boundary": authorization.get("identity_boundary"),
        },
        "collection": {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "counts": expected_counts,
            "capture": {
                "result_id": capture.get("result_id"),
                "sha256": capture.get("sha256"),
                "http_status": capture.get("http_status"),
                "size_bytes": capture.get("size_bytes"),
                "media_type": capture.get("media_type"),
                "evidence_state": capture.get("evidence_state"),
            },
        },
        "content_safety": {
            "scope": content_safety.get("scope"),
            "durable_result_records_checked": 1,
            "scans_created": 1,
            "existing_scans_verified": 0,
            "state_counts": {EXPECTED_SCAN_STATE: 1},
            "scanner_ids": [EXPECTED_SCANNER_ID],
            "detail_exposed": False,
            "substantive_clean_claim": False,
        },
        "controls": {
            "live_facade": "run_live_cohort_collection",
            "default_transport": "PinnedSocketHttpTransport",
            "dns_guard": "DnsGuard",
            "handoff_enabled": False,
            "monitoring_handoff_performed": False,
            "assessment_mutation_performed": False,
            "canonical_publication_performed": False,
            "raw_response_body_exposed": False,
            "quarantine_retention": "EPHEMERAL_RUNNER_TEMP_DELETE_AFTER_PROOF",
        },
        "boundary": BOUNDARY,
    }


def execute(
    *,
    workspace: Path,
    output: Path,
    authorization_id: str,
    actor: str,
    as_of: str,
    workbench_commit: str,
    records_dir: Path = DEFAULT_RECORDS_DIR,
    supplemental_dir: Path = DEFAULT_SUPPLEMENTAL_DIR,
    route_policy_path: Path = DEFAULT_ROUTE_POLICY,
    lifecycle_overlay_path: Path = DEFAULT_LIFECYCLE_OVERLAY,
) -> dict[str, Any]:
    if not authorization_id.strip():
        raise ValueError("authorization_id must be non-empty")
    if not actor.strip():
        raise ValueError("actor must be non-empty")
    if workbench_commit != EXPECTED_WORKBENCH_COMMIT:
        raise ValueError(
            f"Workbench commit mismatch: expected {EXPECTED_WORKBENCH_COMMIT}, "
            f"got {workbench_commit}"
        )

    registry = _build_registry(
        records_dir=records_dir,
        supplemental_dir=supplemental_dir,
        route_policy_path=route_policy_path,
        lifecycle_overlay_path=lifecycle_overlay_path,
    )
    _resolve_fixed_source(registry)
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    plan, registry_sha256 = _plan_single_source(
        registry=registry,
        workspace=workspace,
        as_of=as_of,
        actor=actor,
    )
    package = _execute_live(
        plan=plan,
        registry=registry,
        registry_sha256=registry_sha256,
        quarantine_root=workspace / "quarantine",
        authorization_id=authorization_id,
        actor=actor,
    )
    proof = build_sanitized_proof(
        package,
        authorization_id=authorization_id,
        as_of=as_of,
        workbench_commit=workbench_commit,
    )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(proof, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return proof


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--workbench-commit", required=True)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument(
        "--supplemental-dir",
        type=Path,
        default=DEFAULT_SUPPLEMENTAL_DIR,
    )
    parser.add_argument("--route-policy", type=Path, default=DEFAULT_ROUTE_POLICY)
    parser.add_argument(
        "--lifecycle-overlay",
        type=Path,
        default=DEFAULT_LIFECYCLE_OVERLAY,
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    proof = execute(
        workspace=args.workspace,
        output=args.output,
        authorization_id=args.authorization_id,
        actor=args.actor,
        as_of=args.as_of,
        workbench_commit=args.workbench_commit,
        records_dir=args.records_dir,
        supplemental_dir=args.supplemental_dir,
        route_policy_path=args.route_policy,
        lifecycle_overlay_path=args.lifecycle_overlay,
    )
    print(
        json.dumps(
            {
                "status": proof["status"],
                "source_id": proof["source"]["source_id"],
                "authorization_id": proof["authorization"]["authorization_id"],
                "capture_sha256": proof["collection"]["capture"]["sha256"],
                "scan_state_counts": proof["content_safety"]["state_counts"],
                "handoff_enabled": proof["controls"]["handoff_enabled"],
                "canonical_publication_performed": proof["controls"][
                    "canonical_publication_performed"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
