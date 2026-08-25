from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import acquire_science_candidates as base

STRICT_CUSTODY_SCHEMA_VERSION = "0.2.0"
STRICT_CUSTODY_STATE = "ALL_RECEIVED_HTTP_RESPONSES_CONTENT_ADDRESSED_AND_BOUND"
EXECUTION_IDENTITY_STATE = "EXECUTION_IDENTITY_BOUND_TO_TIMING_DISPOSITION_AND_RETRY_CUSTODY"
ACQUIRED_THIS_EXECUTION = "ACQUIRED_THIS_EXECUTION"
REUSED_COMPLETE_RESULT = "REUSED_COMPLETE_RESULT"
ARCHIVABLE_PRODUCTS = (
    "dedup-report.json",
    "candidate-manifest.json",
    "coverage-index.json",
    "candidate-provenance-verification.json",
    "retry-custody-verification.json",
    "verification-envelope.json",
)

_ORIGINAL_ACQUIRE_QUERY_UNIT = base.acquire_query_unit
_ACTIVE_CONTEXT: dict[str, Any] | None = None


class StrictFetchError(RuntimeError):
    """Raised after all HTTP responses from a failed logical request are captured."""


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("custody timestamps must be timezone-aware")
    return parsed


def _cursor_from_url(url: str, cursor_parameter: str) -> str | None:
    values = urllib.parse.parse_qs(
        urllib.parse.urlsplit(url).query,
        keep_blank_values=True,
    ).get(cursor_parameter)
    return values[0] if values else None


def _attempt_record(
    *,
    logical_request_index: int,
    attempt_index: int,
    requested_at: str,
    observed_at: str,
    url: str,
    cursor_in: str | None,
    outcome: str,
    retryable: bool,
    result: base.HttpResult | None = None,
    raw_sha: str | None = None,
    raw_pointer: str | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "logical_request_index": logical_request_index,
        "attempt_index": attempt_index,
        "requested_at": requested_at,
        "observed_at": observed_at,
        "request_url_sha256": base._sha256_bytes(url.encode("utf-8")),
        "cursor_in": cursor_in,
        "outcome": outcome,
        "retryable": retryable,
        "http_status": None,
        "response_headers": {},
        "content_sha256": None,
        "byte_count": None,
        "raw_custody_pointer": None,
        "error_type": error_type,
    }
    if result is not None:
        record.update(
            {
                "http_status": result.status,
                "response_headers": base._selected_headers(result.headers),
                "content_sha256": raw_sha,
                "byte_count": len(result.body),
                "raw_custody_pointer": raw_pointer,
            }
        )
    return record


def _strict_fetch_with_retries(
    transport: Any,
    url: str,
    *,
    max_attempts: int = 5,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> base.HttpResult:
    global _ACTIVE_CONTEXT
    context = _ACTIVE_CONTEXT
    if context is None:
        raise RuntimeError("strict fetch called without active acquisition context")
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    context["logical_request_index"] += 1
    logical_request_index = context["logical_request_index"]
    cursor_in = _cursor_from_url(url, context["cursor_parameter"])
    last_status: int | None = None

    for attempt_index in range(1, max_attempts + 1):
        requested_at = context["clock_fn"]()
        try:
            result = transport.fetch(url)
        except (OSError, urllib.error.URLError) as exc:
            observed_at = context["clock_fn"]()
            retryable = attempt_index < max_attempts
            context["attempts"].append(
                _attempt_record(
                    logical_request_index=logical_request_index,
                    attempt_index=attempt_index,
                    requested_at=requested_at,
                    observed_at=observed_at,
                    url=url,
                    cursor_in=cursor_in,
                    outcome="TRANSPORT_ERROR",
                    retryable=retryable,
                    error_type=type(exc).__name__,
                )
            )
            if not retryable:
                raise StrictFetchError(
                    f"transport failure after {attempt_index} attempts: {type(exc).__name__}"
                ) from exc
            sleep_fn(base._retry_delay({}, attempt_index))
            continue

        observed_at = context["clock_fn"]()
        raw_sha, raw_pointer = base._store_raw(context["output_root"] / "raw", result.body)
        last_status = result.status
        retryable = result.status in base.TRANSIENT_HTTP_STATUSES and attempt_index < max_attempts
        context["attempts"].append(
            _attempt_record(
                logical_request_index=logical_request_index,
                attempt_index=attempt_index,
                requested_at=requested_at,
                observed_at=observed_at,
                url=url,
                cursor_in=cursor_in,
                outcome="HTTP_RESPONSE",
                retryable=retryable,
                result=result,
                raw_sha=raw_sha,
                raw_pointer=raw_pointer,
            )
        )
        if result.status == 200:
            return result
        if not retryable:
            break
        sleep_fn(base._retry_delay(result.headers, attempt_index))

    if last_status is None:
        raise StrictFetchError("retry policy exhausted without an HTTP response")
    raise StrictFetchError(f"HTTP {last_status} after retry policy exhausted")


def _group_attempts(attempts: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    groups: dict[int, list[dict[str, Any]]] = {}
    for attempt in attempts:
        logical_index = attempt.get("logical_request_index")
        if not isinstance(logical_index, int) or logical_index < 1:
            raise ValueError("invalid logical_request_index in attempt custody")
        groups.setdefault(logical_index, []).append(attempt)
    return groups


def _validate_attempt_binding(result: dict[str, Any], attempts: list[dict[str, Any]]) -> None:
    groups = _group_attempts(attempts)
    if groups and sorted(groups) != list(range(1, len(groups) + 1)):
        raise ValueError("logical request indices are not contiguous")
    responses = result.get("response_manifest")
    if not isinstance(responses, list):
        raise ValueError("response_manifest must be an array")
    if len(groups) < len(responses) or len(groups) > len(responses) + 1:
        raise ValueError("attempt/request cardinality cannot reconcile to response manifest")

    for logical_index, group in sorted(groups.items()):
        if [row.get("attempt_index") for row in group] != list(range(1, len(group) + 1)):
            raise ValueError("attempt indices are not contiguous within logical request")
        for previous, current in zip(group, group[1:]):
            if _parse_time(current["requested_at"]) < _parse_time(previous["observed_at"]):
                raise ValueError("attempt timestamps are not monotone")
        successes = [row for row in group if row.get("http_status") == 200]
        if len(successes) > 1 or (successes and successes[0] is not group[-1]):
            raise ValueError("HTTP 200 must be the unique final attempt of a successful logical request")

        if logical_index <= len(responses):
            response = responses[logical_index - 1]
            if not successes:
                raise ValueError("recorded page response lacks a successful transport attempt")
            successful = successes[0]
            for key in (
                "request_url_sha256",
                "cursor_in",
                "http_status",
                "response_headers",
                "content_sha256",
                "byte_count",
                "raw_custody_pointer",
            ):
                if response.get(key) != successful.get(key):
                    raise ValueError(f"successful attempt does not bind response_manifest field {key}")
            if _parse_time(response["requested_at"]) > _parse_time(group[0]["requested_at"]):
                raise ValueError("page requested_at does not bracket retry attempts")
            if _parse_time(response["observed_at"]) < _parse_time(group[-1]["observed_at"]):
                raise ValueError("page observed_at does not bracket retry attempts")
        else:
            if logical_index != len(groups):
                raise ValueError("unbound logical request may occur only at the end")
            if successes:
                raise ValueError("successful logical request cannot be absent from response_manifest")
            if result.get("status") == "COMPLETE":
                raise ValueError("complete result cannot end with an unbound failed logical request")

    if result.get("status") == "COMPLETE" and len(groups) != len(responses):
        raise ValueError("complete result must bind every logical request to a successful response")


def _strict_acquire_query_unit(
    unit: dict[str, Any],
    *,
    output_root: Path,
    transport: Any,
    max_attempts: int = 5,
    max_pages: int = 10_000,
    sleep_fn: Callable[[float], None] = time.sleep,
    clock_fn: Callable[[], str] = base._utc_now,
) -> dict[str, Any]:
    global _ACTIVE_CONTEXT
    if _ACTIVE_CONTEXT is not None:
        raise RuntimeError("strict acquisition is serial and does not permit nested unit execution")
    context = {
        "query_unit_id": unit["query_unit_id"],
        "output_root": output_root,
        "clock_fn": clock_fn,
        "cursor_parameter": "cursor" if unit["provider"] == "CROSSREF" else "cursorMark",
        "logical_request_index": 0,
        "attempts": [],
    }
    previous_fetch = base.fetch_with_retries
    _ACTIVE_CONTEXT = context
    base.fetch_with_retries = _strict_fetch_with_retries
    try:
        result = _ORIGINAL_ACQUIRE_QUERY_UNIT(
            unit,
            output_root=output_root,
            transport=transport,
            max_attempts=max_attempts,
            max_pages=max_pages,
            sleep_fn=sleep_fn,
            clock_fn=clock_fn,
        )
    finally:
        base.fetch_with_retries = previous_fetch
        _ACTIVE_CONTEXT = None

    attempts = context["attempts"]
    _validate_attempt_binding(result, attempts)
    result.update(
        {
            "retry_custody_schema_version": STRICT_CUSTODY_SCHEMA_VERSION,
            "retry_custody_state": STRICT_CUSTODY_STATE,
            "attempt_response_manifest": attempts,
            "attempt_response_manifest_sha256": base._sha256_json(attempts),
            "received_http_response_count": sum(row["outcome"] == "HTTP_RESPONSE" for row in attempts),
            "transport_error_attempt_count": sum(row["outcome"] == "TRANSPORT_ERROR" for row in attempts),
        }
    )
    base._write_json(output_root / "units" / unit["query_unit_id"] / "result.json", result)
    return result


def _selected_units(
    plan: dict[str, Any],
    *,
    providers: set[str] | None,
    query_unit_ids: set[str] | None,
    max_units: int | None,
) -> list[dict[str, Any]]:
    unit_by_id = base.validate_plan_integrity(plan)
    if providers is not None:
        unknown = providers - base.SUPPORTED_PROVIDERS
        if unknown:
            raise ValueError(f"unsupported provider selection: {sorted(unknown)}")
    if query_unit_ids is not None:
        unknown = query_unit_ids - set(unit_by_id)
        if unknown:
            raise ValueError(f"query-unit selection contains unknown ids: {sorted(unknown)}")
    units = list(plan["query_units"])
    if providers is not None:
        units = [unit for unit in units if unit["provider"] in providers]
    if query_unit_ids is not None:
        units = [unit for unit in units if unit["query_unit_id"] in query_unit_ids]
    if max_units is not None:
        if max_units < 1:
            raise ValueError("max_units must be >= 1")
        units = units[:max_units]
    if not units:
        raise ValueError("selection contains no query units")
    return units


def _load_result(unit: dict[str, Any], output_root: Path) -> dict[str, Any] | None:
    path = output_root / "units" / unit["query_unit_id"] / "result.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{unit['query_unit_id']}: existing result root must be object")
    return value


def _validate_existing_strict_complete(unit: dict[str, Any], output_root: Path) -> bool:
    value = _load_result(unit, output_root)
    if value is None or value.get("status") != "COMPLETE":
        return False
    attempts = value.get("attempt_response_manifest")
    if value.get("retry_custody_state") != STRICT_CUSTODY_STATE or not isinstance(attempts, list):
        raise ValueError(
            f"{unit['query_unit_id']}: existing COMPLETE result predates strict retry custody; quarantine or reacquire it"
        )
    if value.get("retry_custody_schema_version") not in {"0.1.0", STRICT_CUSTODY_SCHEMA_VERSION}:
        raise ValueError(f"{unit['query_unit_id']}: unsupported existing retry custody schema version")
    if value.get("attempt_response_manifest_sha256") != base._sha256_json(attempts):
        raise ValueError(f"{unit['query_unit_id']}: existing strict attempt manifest digest mismatch")
    _validate_attempt_binding(value, attempts)
    return True


def _archive_identity(manifest: dict[str, Any], manifest_bytes: bytes) -> str:
    execution_id = manifest.get("execution_id")
    if isinstance(execution_id, str) and execution_id.startswith("SCIENCE-EXECUTION-"):
        return execution_id
    digest = base._sha256_bytes(manifest_bytes)
    return f"SCIENCE-EXECUTION-LEGACY-{digest[:20].upper()}"


def _archive_prior_execution(output_root: Path) -> None:
    manifest_path = output_root / "run-manifest.json"
    if not manifest_path.exists():
        return
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing run manifest is invalid; quarantine output root before continuing") from exc
    if not isinstance(manifest, dict):
        raise ValueError("existing run manifest root must be object")
    archive_id = _archive_identity(manifest, manifest_bytes)
    archive_dir = output_root / "executions" / archive_id
    archived_manifest = archive_dir / "run-manifest.json"
    if archived_manifest.exists():
        if archived_manifest.read_bytes() != manifest_bytes:
            raise ValueError(f"execution archive identity collision: {archive_id}")
    else:
        base._atomic_write(archived_manifest, manifest_bytes)

    dedup_path = output_root / "dedup-report.json"
    if dedup_path.exists():
        expected = manifest.get("dedup_report_sha256")
        dedup = json.loads(dedup_path.read_text(encoding="utf-8"))
        if expected != base._sha256_json(dedup):
            raise ValueError("existing dedup report digest does not match run manifest")

    for name in ARCHIVABLE_PRODUCTS:
        source = output_root / name
        if not source.exists():
            continue
        target = archive_dir / name
        source_bytes = source.read_bytes()
        if target.exists():
            if target.read_bytes() != source_bytes:
                raise ValueError(f"execution product archive identity collision: {archive_id}:{name}")
        else:
            base._atomic_write(target, source_bytes)
        source.unlink()
    manifest_path.unlink()


def _execution_basis(
    manifest: dict[str, Any],
    unit_execution_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "result_state_id": manifest["run_id"],
        "plan_sha256": manifest["plan_sha256"],
        "started_at": manifest["started_at"],
        "completed_at": manifest["completed_at"],
        "unit_execution_evidence": unit_execution_evidence,
    }


def _snapshot_execution_manifest(output_root: Path, manifest: dict[str, Any]) -> None:
    execution_id = manifest["execution_id"]
    rendered = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    path = output_root / "executions" / execution_id / "run-manifest.json"
    if path.exists():
        if path.read_bytes() != rendered:
            raise ValueError(f"execution snapshot identity collision: {execution_id}")
    else:
        base._atomic_write(path, rendered)


def acquire_plan(
    plan: dict[str, Any],
    *,
    output_root: Path,
    transport: Any,
    max_attempts: int = 5,
    max_pages: int = 10_000,
    providers: set[str] | None = None,
    query_unit_ids: set[str] | None = None,
    max_units: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    clock_fn: Callable[[], str] = base._utc_now,
) -> dict[str, Any]:
    base.validate_output_root(output_root)
    units = _selected_units(plan, providers=providers, query_unit_ids=query_unit_ids, max_units=max_units)
    preexisting_complete_ids = {
        unit["query_unit_id"]
        for unit in units
        if _validate_existing_strict_complete(unit, output_root)
    }

    _archive_prior_execution(output_root)

    previous_acquire = base.acquire_query_unit
    base.acquire_query_unit = _strict_acquire_query_unit
    try:
        manifest = base.acquire_plan(
            plan,
            output_root=output_root,
            transport=transport,
            max_attempts=max_attempts,
            max_pages=max_pages,
            providers=providers,
            query_unit_ids=query_unit_ids,
            max_units=max_units,
            sleep_fn=sleep_fn,
            clock_fn=clock_fn,
        )
    finally:
        base.acquire_query_unit = previous_acquire

    summaries: list[dict[str, Any]] = []
    execution_evidence: list[dict[str, Any]] = []
    for relative in manifest["query_unit_result_paths"]:
        result_path = base._resolve_inside(output_root, relative)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        attempts = result.get("attempt_response_manifest")
        if result.get("retry_custody_state") != STRICT_CUSTODY_STATE or not isinstance(attempts, list):
            raise ValueError(f"{result.get('query_unit_id')}: strict retry custody is absent")
        if result.get("attempt_response_manifest_sha256") != base._sha256_json(attempts):
            raise ValueError(f"{result.get('query_unit_id')}: attempt response manifest digest mismatch")
        _validate_attempt_binding(result, attempts)
        summary = {
            "query_unit_id": result["query_unit_id"],
            "attempt_response_manifest_sha256": result["attempt_response_manifest_sha256"],
            "received_http_response_count": result["received_http_response_count"],
            "transport_error_attempt_count": result["transport_error_attempt_count"],
        }
        summaries.append(summary)
        disposition = (
            REUSED_COMPLETE_RESULT
            if result["query_unit_id"] in preexisting_complete_ids
            else ACQUIRED_THIS_EXECUTION
        )
        execution_evidence.append(
            {
                "query_unit_id": result["query_unit_id"],
                "disposition": disposition,
                "result_status": result["status"],
                "attempt_response_manifest_sha256": result["attempt_response_manifest_sha256"],
            }
        )

    custody_basis = {"run_id": manifest["run_id"], "query_units": summaries}
    execution_basis = _execution_basis(manifest, execution_evidence)
    execution_sha = base._sha256_json(execution_basis)
    acquired = sum(row["disposition"] == ACQUIRED_THIS_EXECUTION for row in execution_evidence)
    reused = sum(row["disposition"] == REUSED_COMPLETE_RESULT for row in execution_evidence)
    manifest.update(
        {
            "retry_custody_schema_version": STRICT_CUSTODY_SCHEMA_VERSION,
            "retry_custody_state": STRICT_CUSTODY_STATE,
            "retry_custody_query_units": len(summaries),
            "retry_custody_sha256": base._sha256_json(custody_basis),
            "result_state_id": manifest["run_id"],
            "execution_identity_state": EXECUTION_IDENTITY_STATE,
            "execution_id": f"SCIENCE-EXECUTION-{execution_sha[:20].upper()}",
            "execution_identity_sha256": execution_sha,
            "unit_execution_evidence": execution_evidence,
            "acquired_query_units_this_execution": acquired,
            "reused_complete_query_units_this_execution": reused,
            "execution_authority_boundary": (
                "execution_id identifies this invocation's timing, reuse/acquisition dispositions, and bound retry-custody evidence. "
                "result_state_id identifies the resulting provider/candidate state. Reuse of a complete result does not assert that provider retrieval occurred again."
            ),
        }
    )
    base._write_json(output_root / "run-manifest.json", manifest)
    _snapshot_execution_manifest(output_root, manifest)
    return manifest


def _load_plan(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("query plan root must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the frozen Phase 4 science query plan with attempt-level HTTP response custody.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--provider", action="append", choices=["CROSSREF", "EUROPE_PMC"])
    parser.add_argument("--query-unit-id", action="append")
    parser.add_argument("--max-units", type=int)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=10_000)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    manifest = acquire_plan(
        _load_plan(args.plan),
        output_root=args.output_dir,
        transport=base.UrllibTransport(timeout_seconds=args.timeout_seconds),
        max_attempts=args.max_attempts,
        max_pages=args.max_pages,
        providers=set(args.provider) if args.provider else None,
        query_unit_ids=set(args.query_unit_id) if args.query_unit_id else None,
        max_units=args.max_units,
    )
    print(
        f"{manifest['status']}: complete={manifest['complete_query_units']}/{manifest['selected_query_units']}; "
        f"result_state_id={manifest['result_state_id']}; execution_id={manifest['execution_id']}; "
        f"acquired={manifest['acquired_query_units_this_execution']}; reused={manifest['reused_complete_query_units_this_execution']}"
    )


if __name__ == "__main__":
    main()
