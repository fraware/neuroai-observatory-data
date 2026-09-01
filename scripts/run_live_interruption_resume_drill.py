#!/usr/bin/env python3
"""Terminate a controlled live collection process after a durable target, then prove exact resume."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import time
from pathlib import Path
from typing import Any

from build_analytical_projection import DEFAULT_RECORDS_DIR, DEFAULT_SUPPLEMENTAL_DIR, build_tables, load_inputs
from build_development_monitor_registry import build_development_registry, verify_development_registry, write_registry
from neuroai_workbench.collector import (
    CollectionScheduler,
    CollectorConfig,
    PinnedSocketHttpTransport,
    SchedulerConfig,
)
from neuroai_workbench.collector.http_client import HttpRequest, TransportResult
from neuroai_workbench.monitoring import initialize_monitoring, plan_monitoring_run, validate_source_registry
from run_operational_due_cycle import CountingTransport, _configuration_hash

TERMINAL = {"SUCCESS", "FAILURE", "SKIPPED"}
BOUNDARY = (
    "This drill proves crash/interruption recovery mechanics over the declared development monitor view. "
    "It does not adjudicate source truth, assessment validity, governance, or release authority."
)


def _collector_config() -> CollectorConfig:
    return CollectorConfig(
        collector_version="0.3.0-dev-operational-pinned-dns",
        configuration_hash=_configuration_hash(),
        connect_timeout_seconds=8.0,
        read_timeout_seconds=20.0,
        total_timeout_seconds=45.0,
        max_attempts=3,
        retry_initial_delay_seconds=0.5,
        retry_max_delay_seconds=4.0,
        requests_per_host_per_minute=30,
        allowed_content_types=frozenset(
            {
                "text/html",
                "text/plain",
                "text/csv",
                "application/json",
                "application/ld+json",
                "application/xml",
                "text/xml",
                "application/rss+xml",
                "application/atom+xml",
                "application/pdf",
                "application/octet-stream",
            }
        ),
    )


def _scheduler_config() -> SchedulerConfig:
    # One worker makes the interruption point observable and deterministic enough for an OS-level drill.
    return SchedulerConfig(
        max_workers=1,
        max_workers_per_host=1,
        resume_enabled=True,
        collection_enabled=True,
        handoff_enabled=False,
    )


class SlowTransport:
    def __init__(self, delay_seconds: float = 0.8) -> None:
        self.inner = PinnedSocketHttpTransport()
        self.delay_seconds = delay_seconds

    def send(
        self,
        request: HttpRequest,
        *,
        connect_timeout: float,
        read_timeout: float,
    ) -> TransportResult:
        time.sleep(self.delay_seconds)
        return self.inner.send(request, connect_timeout=connect_timeout, read_timeout=read_timeout)


def _child_run(
    workspace: str,
    plan: dict[str, Any],
    registry_sha256: str,
    source_index: dict[str, dict[str, Any]],
) -> None:
    scheduler = CollectionScheduler(
        collector_config=_collector_config(),
        transport=SlowTransport(),
        quarantine_root=Path(workspace) / "quarantine",
        scheduler_config=_scheduler_config(),
    )
    scheduler.run_plan(plan, registry_sha256=registry_sha256, source_index=source_index)


def _terminal_checkpoints(workspace: Path) -> dict[Path, bytes]:
    result: dict[Path, bytes] = {}
    root = workspace / "quarantine" / "run-ledgers"
    for path in sorted(root.glob("*/targets/*.json")):
        raw = path.read_bytes()
        value = json.loads(raw)
        if value.get("state") in TERMINAL:
            result[path] = raw
    return result


def execute(
    *,
    records_dir: Path,
    supplemental_dir: Path,
    workspace: Path,
    as_of: str,
    checkpoint_timeout_seconds: float,
) -> dict[str, Any]:
    inputs = load_inputs(records_dir.resolve(), supplemental_dir=supplemental_dir.resolve())
    registry = build_development_registry(inputs)
    verify_development_registry(registry)
    if not validate_source_registry(registry).get("valid"):
        raise ValueError("Development registry failed workbench validation")

    workspace.mkdir(parents=True, exist_ok=True)
    registry_path = write_registry(registry, workspace / "development-monitor-registry.json")
    monitoring = initialize_monitoring(workspace, registry_path, actor="operational-interruption-drill")
    plan = plan_monitoring_run(workspace, as_of=as_of)
    if not plan.get("due"):
        raise ValueError("Interruption drill requires at least one due automatic source")
    source_index = {str(record["source_id"]): record for record in registry["sources"]}

    process = mp.Process(
        target=_child_run,
        args=(str(workspace), plan, str(monitoring["registry_sha256"]), source_index),
        name="neuroai-live-interruption-child",
    )
    process.start()
    deadline = time.monotonic() + checkpoint_timeout_seconds
    committed_before_kill: dict[Path, bytes] = {}
    while time.monotonic() < deadline:
        committed_before_kill = _terminal_checkpoints(workspace)
        if committed_before_kill:
            break
        if not process.is_alive():
            raise ValueError(f"Child exited before a durable terminal checkpoint; exitcode={process.exitcode}")
        time.sleep(0.05)
    if not committed_before_kill:
        process.terminate()
        process.join(timeout=5)
        raise TimeoutError("No durable terminal target became visible before interruption timeout")

    process.terminate()
    process.join(timeout=5)
    if process.is_alive():
        process.kill()
        process.join(timeout=5)
    interrupted_exitcode = process.exitcode
    if interrupted_exitcode in {0, None}:
        raise ValueError(f"Interruption drill did not terminate the child as intended: exitcode={interrupted_exitcode}")

    before_hashes = {
        str(path.relative_to(workspace)): hashlib.sha256(raw).hexdigest()
        for path, raw in committed_before_kill.items()
    }

    transport = CountingTransport()
    scheduler = CollectionScheduler(
        collector_config=_collector_config(),
        transport=transport,
        quarantine_root=workspace / "quarantine",
        scheduler_config=_scheduler_config(),
    )
    resumed = scheduler.run_plan(
        plan,
        registry_sha256=str(monitoring["registry_sha256"]),
        source_index=source_index,
    )
    if resumed.get("execution_status") not in {"COMPLETE", "COMPLETE_WITH_SOURCE_FAILURES"}:
        raise ValueError(f"Resumed drill remained internally incomplete: {resumed.get('execution_status')}")
    if resumed.get("slo", {}).get("source_accountability_coverage") != 1.0:
        raise ValueError("Resumed drill source-accountability SLO is below 1.0")
    if resumed.get("slo", {}).get("target_execution_coverage") != 1.0:
        raise ValueError("Resumed drill target-execution SLO is below 1.0")
    if int(resumed.get("counts", {}).get("resumed_targets", 0)) < len(committed_before_kill):
        raise ValueError("Resumed-target count is smaller than the number durably committed before interruption")

    unchanged: dict[str, bool] = {}
    for path, raw_before in committed_before_kill.items():
        unchanged[str(path.relative_to(workspace))] = path.read_bytes() == raw_before
    if not all(unchanged.values()):
        raise ValueError("At least one pre-interruption terminal checkpoint changed during resume")

    return {
        "schema_version": "2",
        "boundary": BOUNDARY,
        "transport_security": "DNS_PINNED_VALIDATED_ADDRESS_SET",
        "plan_id": plan.get("plan_id"),
        "due_source_count": len(plan.get("due", [])),
        "interrupted_exitcode": interrupted_exitcode,
        "terminal_targets_before_kill": len(committed_before_kill),
        "terminal_checkpoint_sha256_before_kill": before_hashes,
        "terminal_checkpoints_bit_identical_after_resume": unchanged,
        "resume_transport_sends": transport.sends,
        "resume_execution_status": resumed.get("execution_status"),
        "resume_counts": resumed.get("counts"),
        "resume_slo": resumed.get("slo"),
        "resume_semantic_summary_sha256": resumed.get("semantic_summary_sha256"),
        "development_registry_sha256": registry["metadata"]["registry_view_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", type=Path, default=DEFAULT_RECORDS_DIR)
    parser.add_argument("--supplemental-dir", type=Path, default=DEFAULT_SUPPLEMENTAL_DIR)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--checkpoint-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = execute(
        records_dir=args.records_dir,
        supplemental_dir=args.supplemental_dir,
        workspace=args.workspace.resolve(),
        as_of=args.as_of,
        checkpoint_timeout_seconds=args.checkpoint_timeout_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "SANITIZED_INTERRUPTION_RESUME_DRILL="
        + json.dumps(
            {
                "transport_security": report["transport_security"],
                "due_source_count": report["due_source_count"],
                "interrupted_exitcode": report["interrupted_exitcode"],
                "terminal_targets_before_kill": report["terminal_targets_before_kill"],
                "resume_transport_sends": report["resume_transport_sends"],
                "resume_execution_status": report["resume_execution_status"],
                "resumed_targets": report["resume_counts"].get("resumed_targets"),
                "source_accountability_coverage": report["resume_slo"].get("source_accountability_coverage"),
                "target_execution_coverage": report["resume_slo"].get("target_execution_coverage"),
                "all_committed_checkpoints_unchanged": all(
                    report["terminal_checkpoints_bit_identical_after_resume"].values()
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
