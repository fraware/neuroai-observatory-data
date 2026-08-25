from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import acquire_science_candidates as base

STRICT_CUSTODY_SCHEMA_VERSION = "0.1.0"
STRICT_CUSTODY_STATE = "ALL_RECEIVED_HTTP_RESPONSES_CONTENT_ADDRESSED_AND_BOUND"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _resolve_inside(root: Path, relative: str) -> Path:
    root_resolved = root.resolve()
    path = (root_resolved / relative).resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ValueError(f"path escapes acquisition root: {relative}")
    return path


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date-time string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid ISO date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _groups(attempts: list[dict[str, Any]], unit_id: str) -> dict[int, list[dict[str, Any]]]:
    groups: dict[int, list[dict[str, Any]]] = {}
    for row in attempts:
        if not isinstance(row, dict):
            raise ValueError(f"{unit_id}: attempt row must be object")
        logical_index = row.get("logical_request_index")
        if not isinstance(logical_index, int) or logical_index < 1:
            raise ValueError(f"{unit_id}: invalid logical_request_index")
        groups.setdefault(logical_index, []).append(row)
    if groups and sorted(groups) != list(range(1, len(groups) + 1)):
        raise ValueError(f"{unit_id}: logical request indices are not contiguous")
    return groups


def _verify_http_body(run_dir: Path, row: dict[str, Any], unit_id: str) -> None:
    pointer = row.get("raw_custody_pointer")
    digest = row.get("content_sha256")
    byte_count = row.get("byte_count")
    if not isinstance(pointer, str) or not isinstance(digest, str) or not isinstance(byte_count, int):
        raise ValueError(f"{unit_id}: HTTP response lacks raw custody metadata")
    raw_path = _resolve_inside(run_dir, pointer)
    if not raw_path.is_file():
        raise ValueError(f"{unit_id}: missing retry-custody raw response")
    raw_bytes = raw_path.read_bytes()
    if _sha256_bytes(raw_bytes) != digest:
        raise ValueError(f"{unit_id}: retry-custody raw response digest mismatch")
    if raw_path.name != f"{digest}.json":
        raise ValueError(f"{unit_id}: retry-custody raw response is not content-addressed")
    if len(raw_bytes) != byte_count:
        raise ValueError(f"{unit_id}: retry-custody byte_count mismatch")


def _expected_url_sha(unit: dict[str, Any], cursor_in: str | None) -> str:
    parameters = dict(unit["parameters"])
    cursor_parameter = "cursor" if unit["provider"] == "CROSSREF" else "cursorMark"
    parameters[cursor_parameter] = cursor_in
    url = base._build_url(unit["endpoint"], parameters)
    return _sha256_bytes(url.encode("utf-8"))


def _verify_unit(
    run_dir: Path,
    result: dict[str, Any],
    unit: dict[str, Any],
) -> dict[str, Any]:
    unit_id = unit["query_unit_id"]
    if result.get("query_unit_id") != unit_id:
        raise ValueError(f"{unit_id}: result query-unit mismatch")
    if result.get("retry_custody_schema_version") != STRICT_CUSTODY_SCHEMA_VERSION:
        raise ValueError(f"{unit_id}: retry custody schema version mismatch")
    if result.get("retry_custody_state") != STRICT_CUSTODY_STATE:
        raise ValueError(f"{unit_id}: retry custody state missing or invalid")

    attempts = result.get("attempt_response_manifest")
    if not isinstance(attempts, list):
        raise ValueError(f"{unit_id}: attempt_response_manifest must be an array")
    if result.get("attempt_response_manifest_sha256") != _sha256_json(attempts):
        raise ValueError(f"{unit_id}: attempt response manifest digest mismatch")

    groups = _groups(attempts, unit_id)
    responses = result.get("response_manifest")
    pages = result.get("page_manifest")
    if not isinstance(responses, list) or not isinstance(pages, list):
        raise ValueError(f"{unit_id}: response/page manifests must be arrays")
    if len(groups) < len(responses) or len(groups) > len(responses) + 1:
        raise ValueError(f"{unit_id}: attempt/request cardinality mismatch")

    initial_cursor = unit["parameters"]["cursor" if unit["provider"] == "CROSSREF" else "cursorMark"]
    expected_cursor = initial_cursor
    received_http = 0
    transport_errors = 0

    for logical_index, group in sorted(groups.items()):
        if [row.get("attempt_index") for row in group] != list(range(1, len(group) + 1)):
            raise ValueError(f"{unit_id}: attempt indices are not contiguous")

        expected_url_sha = _expected_url_sha(unit, expected_cursor)
        prior_observed: datetime | None = None
        successful: dict[str, Any] | None = None
        for attempt in group:
            if attempt.get("cursor_in") != expected_cursor:
                raise ValueError(f"{unit_id}: attempt cursor does not match logical request")
            if attempt.get("request_url_sha256") != expected_url_sha:
                raise ValueError(f"{unit_id}: attempt request URL digest mismatch")
            requested_at = _parse_time(attempt.get("requested_at"), f"{unit_id}:attempt requested_at")
            observed_at = _parse_time(attempt.get("observed_at"), f"{unit_id}:attempt observed_at")
            if observed_at < requested_at:
                raise ValueError(f"{unit_id}: attempt observed_at precedes requested_at")
            if prior_observed is not None and requested_at < prior_observed:
                raise ValueError(f"{unit_id}: attempt timestamps are not monotone")
            prior_observed = observed_at

            outcome = attempt.get("outcome")
            if outcome == "HTTP_RESPONSE":
                received_http += 1
                status = attempt.get("http_status")
                if not isinstance(status, int):
                    raise ValueError(f"{unit_id}: HTTP attempt lacks status")
                if not isinstance(attempt.get("response_headers"), dict):
                    raise ValueError(f"{unit_id}: HTTP attempt headers must be object")
                _verify_http_body(run_dir, attempt, unit_id)
                if attempt.get("error_type") is not None:
                    raise ValueError(f"{unit_id}: HTTP attempt carries transport error type")
                if status == 200:
                    if successful is not None:
                        raise ValueError(f"{unit_id}: multiple HTTP 200 attempts in one logical request")
                    successful = attempt
                expected_retryable = (
                    status in base.TRANSIENT_HTTP_STATUSES
                    and attempt["attempt_index"] < len(group)
                )
                if attempt.get("retryable") is not expected_retryable:
                    raise ValueError(f"{unit_id}: HTTP attempt retryable flag is inconsistent")
            elif outcome == "TRANSPORT_ERROR":
                transport_errors += 1
                if attempt.get("http_status") is not None:
                    raise ValueError(f"{unit_id}: transport error carries HTTP status")
                if any(
                    attempt.get(key) is not None
                    for key in ("content_sha256", "byte_count", "raw_custody_pointer")
                ):
                    raise ValueError(f"{unit_id}: transport error cannot claim response bytes")
                if not isinstance(attempt.get("error_type"), str) or not attempt["error_type"]:
                    raise ValueError(f"{unit_id}: transport error lacks error_type")
                expected_retryable = attempt["attempt_index"] < len(group)
                if attempt.get("retryable") is not expected_retryable:
                    raise ValueError(f"{unit_id}: transport-error retryable flag is inconsistent")
            else:
                raise ValueError(f"{unit_id}: unsupported attempt outcome")

        if successful is not None and successful is not group[-1]:
            raise ValueError(f"{unit_id}: successful attempt must terminate logical request")

        if logical_index <= len(responses):
            response = responses[logical_index - 1]
            if successful is None:
                raise ValueError(f"{unit_id}: response_manifest row lacks successful attempt")
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
                    raise ValueError(f"{unit_id}: successful attempt/response mismatch for {key}")
            if _parse_time(response.get("requested_at"), f"{unit_id}:page requested_at") > _parse_time(
                group[0].get("requested_at"), f"{unit_id}:first attempt requested_at"
            ):
                raise ValueError(f"{unit_id}: page requested_at does not bracket attempts")
            if _parse_time(response.get("observed_at"), f"{unit_id}:page observed_at") < _parse_time(
                group[-1].get("observed_at"), f"{unit_id}:last attempt observed_at"
            ):
                raise ValueError(f"{unit_id}: page observed_at does not bracket attempts")

            if logical_index <= len(pages):
                page = pages[logical_index - 1]
                if page.get("response_index") != logical_index:
                    raise ValueError(f"{unit_id}: parsed page response index mismatch")
                expected_cursor = page.get("cursor_out")
            else:
                if logical_index != len(responses):
                    raise ValueError(f"{unit_id}: unparsed successful response may occur only at end")
        else:
            if logical_index != len(groups):
                raise ValueError(f"{unit_id}: unbound failed request may occur only at end")
            if successful is not None:
                raise ValueError(f"{unit_id}: successful attempt cannot be absent from response_manifest")
            if result.get("status") == "COMPLETE":
                raise ValueError(f"{unit_id}: complete result cannot end in failed request")

    if result.get("status") == "COMPLETE":
        if len(groups) != len(responses) or len(responses) != len(pages):
            raise ValueError(f"{unit_id}: complete result lacks one-to-one request/page binding")
    if result.get("received_http_response_count") != received_http:
        raise ValueError(f"{unit_id}: received HTTP response count mismatch")
    if result.get("transport_error_attempt_count") != transport_errors:
        raise ValueError(f"{unit_id}: transport error attempt count mismatch")

    return {
        "query_unit_id": unit_id,
        "attempt_response_manifest_sha256": result["attempt_response_manifest_sha256"],
        "received_http_response_count": received_http,
        "transport_error_attempt_count": transport_errors,
    }


def verify_retry_custody(plan: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    units = base.validate_plan_integrity(plan)
    manifest = _load_json(run_dir / "run-manifest.json")
    if manifest.get("plan_id") != plan["plan_id"] or manifest.get("plan_sha256") != plan["plan_sha256"]:
        raise ValueError("run manifest is not bound to supplied frozen plan")
    if manifest.get("retry_custody_schema_version") != STRICT_CUSTODY_SCHEMA_VERSION:
        raise ValueError("run retry custody schema version mismatch")
    if manifest.get("retry_custody_state") != STRICT_CUSTODY_STATE:
        raise ValueError("run retry custody state missing or invalid")

    result_paths = manifest.get("query_unit_result_paths")
    if not isinstance(result_paths, list) or not result_paths:
        raise ValueError("run manifest requires query-unit result paths")
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative in result_paths:
        if not isinstance(relative, str):
            raise ValueError("query-unit result path must be string")
        result = _load_json(_resolve_inside(run_dir, relative))
        unit_id = result.get("query_unit_id")
        if unit_id not in units:
            raise ValueError(f"run contains query unit outside frozen plan: {unit_id}")
        if unit_id in seen:
            raise ValueError(f"duplicate query-unit result in retry custody: {unit_id}")
        seen.add(unit_id)
        summaries.append(_verify_unit(run_dir, result, units[unit_id]))

    if manifest.get("retry_custody_query_units") != len(summaries):
        raise ValueError("run retry custody query-unit count mismatch")
    custody_basis = {
        "run_id": manifest.get("run_id"),
        "query_units": summaries,
    }
    custody_sha = _sha256_json(custody_basis)
    if manifest.get("retry_custody_sha256") != custody_sha:
        raise ValueError("run retry custody digest mismatch")

    report_basis = {
        "run_id": manifest.get("run_id"),
        "retry_custody_sha256": custody_sha,
        "query_units": len(summaries),
        "received_http_responses": sum(row["received_http_response_count"] for row in summaries),
        "transport_error_attempts": sum(row["transport_error_attempt_count"] for row in summaries),
    }
    report_sha = _sha256_json(report_basis)
    return {
        "retry_custody_verification_id": f"SCIENCE-RETRY-CUSTODY-{report_sha[:20].upper()}",
        "schema_version": STRICT_CUSTODY_SCHEMA_VERSION,
        **report_basis,
        "retry_custody_verification_sha256": report_sha,
        "status": "RECEIVED_HTTP_RESPONSE_CUSTODY_VERIFIED",
        "canonical_effect": "NONE",
        "authority_boundary": (
            "This verifies custody and logical-request binding for every HTTP response recorded by the strict "
            "acquisition path, plus transport-error attempt metadata. It establishes no scientific relevance, "
            "validity, canonical identity, release authority, or open-world completeness."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independently verify attempt-level HTTP response custody for a Phase 4 science acquisition."
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    plan = _load_json(args.plan)
    report = verify_retry_custody(plan, args.run_dir)
    output = args.run_dir / "retry-custody-verification.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"PASS retry custody: units={report['query_units']}; "
        f"http_responses={report['received_http_responses']}; "
        f"transport_errors={report['transport_error_attempts']}"
    )


if __name__ == "__main__":
    main()
