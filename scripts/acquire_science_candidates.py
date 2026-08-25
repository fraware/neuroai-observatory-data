from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple

ROOT = Path(__file__).parents[1]
DEFAULT_USER_AGENT = "neuroai-observatory-data/0.1 (+https://github.com/fraware/neuroai-observatory-data)"
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
RELEASE_INELIGIBLE = "NOT_RELEASE_ELIGIBLE_UNTIL_DURABLE_CUSTODY_AND_RIGHTS_REVIEW"
SUPPORTED_PROVIDERS = {"CROSSREF", "EUROPE_PMC"}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{random.randrange(1_000_000)}")
    temp.write_bytes(data)
    os.replace(temp, path)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(
        path,
        (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    body = b"".join(_canonical_bytes(row) + b"\n" for row in rows)
    _atomic_write(path, body)


def _is_within(child: Path, parent: Path) -> bool:
    child_r = child.resolve()
    parent_r = parent.resolve()
    return child_r == parent_r or parent_r in child_r.parents


def validate_output_root(output_root: Path) -> None:
    if _is_within(output_root, ROOT):
        raise ValueError("acquisition output must remain outside the Git repository")


def _resolve_inside(root: Path, relative: str) -> Path:
    root_r = root.resolve()
    path = (root_r / relative).resolve()
    if path != root_r and root_r not in path.parents:
        raise ValueError(f"path escapes acquisition root: {relative}")
    return path


class HttpResult(NamedTuple):
    status: int
    headers: dict[str, str]
    body: bytes


class UrllibTransport:
    def __init__(self, *, user_agent: str = DEFAULT_USER_AGENT, timeout_seconds: float = 60.0):
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> HttpResult:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return HttpResult(
                    status=int(response.status),
                    headers={k.lower(): v for k, v in response.headers.items()},
                    body=response.read(),
                )
        except urllib.error.HTTPError as exc:
            return HttpResult(
                status=int(exc.code),
                headers={k.lower(): v for k, v in exc.headers.items()},
                body=exc.read(),
            )


def _retry_delay(headers: dict[str, str], attempt: int) -> float:
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), 120.0))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
                return max(0.0, min(seconds, 120.0))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(2 ** (attempt - 1), 30.0)


def fetch_with_retries(
    transport: Any,
    url: str,
    *,
    max_attempts: int = 5,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> HttpResult:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last: HttpResult | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = transport.fetch(url)
        except (OSError, urllib.error.URLError) as exc:
            if attempt == max_attempts:
                raise RuntimeError(f"transport failure after {attempt} attempts: {exc}") from exc
            sleep_fn(_retry_delay({}, attempt))
            continue
        last = result
        if result.status == 200:
            return result
        if result.status not in TRANSIENT_HTTP_STATUSES or attempt == max_attempts:
            break
        sleep_fn(_retry_delay(result.headers, attempt))
    assert last is not None
    raise RuntimeError(f"HTTP {last.status} after retry policy exhausted")


def _build_url(endpoint: str, parameters: dict[str, Any]) -> str:
    return endpoint + "?" + urllib.parse.urlencode(parameters)


def _selected_headers(headers: dict[str, str]) -> dict[str, str]:
    allow = (
        "date",
        "etag",
        "last-modified",
        "content-type",
        "retry-after",
        "x-api-pool",
    )
    return {key: headers[key] for key in allow if key in headers}


def _store_raw(raw_root: Path, body: bytes) -> tuple[str, str]:
    digest = _sha256_bytes(body)
    relative = Path("raw") / "sha256" / digest[:2] / f"{digest}.json"
    path = raw_root / "sha256" / digest[:2] / f"{digest}.json"
    if path.exists():
        if _sha256_bytes(path.read_bytes()) != digest:
            raise RuntimeError(f"content-addressed raw collision: {digest}")
    else:
        _atomic_write(path, body)
    return digest, relative.as_posix()


def _json_body(body: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label}: provider returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label}: provider JSON root must be an object")
    return payload


def _crossref_page(payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]], str | None]:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("CROSSREF: missing message object")
    total = message.get("total-results")
    items = message.get("items")
    if not isinstance(total, int) or total < 0:
        raise RuntimeError("CROSSREF: invalid total-results")
    if not isinstance(items, list) or not all(isinstance(row, dict) for row in items):
        raise RuntimeError("CROSSREF: invalid items")
    cursor = message.get("next-cursor")
    if cursor is not None and not isinstance(cursor, str):
        raise RuntimeError("CROSSREF: invalid next-cursor")
    return total, items, cursor


def _europe_pmc_page(payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]], str | None]:
    total = payload.get("hitCount")
    result_list = payload.get("resultList")
    if not isinstance(total, int) or total < 0:
        raise RuntimeError("EUROPE_PMC: invalid hitCount")
    if not isinstance(result_list, dict):
        raise RuntimeError("EUROPE_PMC: missing resultList")
    items = result_list.get("result", [])
    if not isinstance(items, list) or not all(isinstance(row, dict) for row in items):
        raise RuntimeError("EUROPE_PMC: invalid resultList.result")
    cursor = payload.get("nextCursorMark")
    if cursor is not None and not isinstance(cursor, str):
        raise RuntimeError("EUROPE_PMC: invalid nextCursorMark")
    return total, items, cursor


def _parse_crossref_date(record: dict[str, Any]) -> str | None:
    published = record.get("published")
    if not isinstance(published, dict):
        return None
    parts = published.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list) or not parts[0]:
        return None
    first = parts[0]
    try:
        values = [int(value) for value in first[:3]]
    except (TypeError, ValueError):
        return None
    if not (1 <= len(values) <= 3):
        return None
    year = values[0]
    if year < 1:
        return None
    if len(values) == 1:
        return f"{year:04d}"
    month = values[1]
    if not 1 <= month <= 12:
        return None
    if len(values) == 2:
        return f"{year:04d}-{month:02d}"
    day = values[2]
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def _normalize_doi(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    result = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if result[: len(prefix)].casefold() == prefix.casefold():
            result = result[len(prefix):]
            break
    return result.lower()


def _normalize_pmid(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    for prefix in ("PMID:", "pmid:"):
        if result.startswith(prefix):
            result = result[len(prefix):]
            break
    return result if result.isdigit() else None


def _normalize_pmcid(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip().upper()
    if result.startswith("PMCID:"):
        result = result[6:]
    return result if result.startswith("PMC") and result[3:].isdigit() else None


def _normalize_openalex_work(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    result = value.strip()
    for prefix in (
        "https://openalex.org/works/",
        "http://openalex.org/works/",
        "https://openalex.org/",
        "http://openalex.org/",
    ):
        if result[: len(prefix)].casefold() == prefix.casefold():
            result = result[len(prefix):]
            break
    result = result.upper()
    return result if result.startswith("W") and result[1:].isdigit() else None


def _provider_slug(provider: str) -> str:
    return provider.replace("_", "-")


def _candidate_id(
    provider: str,
    provider_record_id: str,
    query_unit_id: str,
    provider_record_source: str | None = None,
) -> str:
    digest = _sha256_json(
        {
            "provider": provider,
            "provider_record_source": provider_record_source,
            "provider_record_id": provider_record_id,
            "query_unit_id": query_unit_id,
        }
    )
    return f"SCI-CAND-{_provider_slug(provider)}-{digest[:20].upper()}"


def _crossref_candidate(
    record: dict[str, Any],
    *,
    unit: dict[str, Any],
    freeze_id: str,
    observed_at: str,
) -> dict[str, Any]:
    doi = _normalize_doi(record.get("DOI"))
    if doi is None:
        raise RuntimeError("CROSSREF: work lacks a usable DOI provider identifier")
    title_value = record.get("title")
    if not isinstance(title_value, list):
        raise RuntimeError(f"CROSSREF:{doi}: title is not a list")
    title = next((value.strip() for value in title_value if isinstance(value, str) and value.strip()), None)
    if title is None:
        raise RuntimeError(f"CROSSREF:{doi}: missing required title")
    return {
        "record_kind": "SCIENCE_DISCOVERY_CANDIDATE",
        "candidate_id": _candidate_id("CROSSREF", doi, unit["query_unit_id"]),
        "provider": "CROSSREF",
        "provider_record_id": doi,
        "source_universe_id": unit["source_universe_id"],
        "acquisition_freeze_id": freeze_id,
        "title": title,
        "publication_date": _parse_crossref_date(record),
        "identifiers": {"doi": doi, "pmid": None, "pmcid": None, "openalex": None},
        "discovery_query_family_ids": [unit["query_family_id"]],
        "selection_state": "DISCOVERED_CANDIDATE",
        "canonical_effect": "NONE_REQUIRES_RELEVANCE_ADJUDICATION",
        "source_record_sha256": _sha256_json(record),
        "observed_at": observed_at,
    }


def _europe_pmc_candidate(
    record: dict[str, Any],
    *,
    unit: dict[str, Any],
    freeze_id: str,
    observed_at: str,
) -> dict[str, Any]:
    source = record.get("source")
    if not isinstance(source, str) or not source.strip():
        raise RuntimeError("EUROPE_PMC: record lacks provider source database code")
    provider_source = source.strip().upper()
    provider_id = record.get("id")
    if provider_id is None or not str(provider_id).strip():
        raise RuntimeError("EUROPE_PMC: record lacks provider id")
    provider_id = str(provider_id).strip()
    title = record.get("title")
    if not isinstance(title, str) or not title.strip():
        raise RuntimeError(f"EUROPE_PMC:{provider_source}:{provider_id}: missing required title")
    pub_year = record.get("pubYear")
    publication_date = str(pub_year).strip() if pub_year is not None else None
    if publication_date is not None and (len(publication_date) != 4 or not publication_date.isdigit()):
        publication_date = None
    return {
        "record_kind": "SCIENCE_DISCOVERY_CANDIDATE",
        "candidate_id": _candidate_id(
            "EUROPE_PMC",
            provider_id,
            unit["query_unit_id"],
            provider_source,
        ),
        "provider": "EUROPE_PMC",
        "provider_record_source": provider_source,
        "provider_record_id": provider_id,
        "source_universe_id": unit["source_universe_id"],
        "acquisition_freeze_id": freeze_id,
        "title": title.strip(),
        "publication_date": publication_date,
        "identifiers": {
            "doi": _normalize_doi(record.get("doi")),
            "pmid": _normalize_pmid(record.get("pmid")),
            "pmcid": _normalize_pmcid(record.get("pmcid")),
            "openalex": None,
        },
        "discovery_query_family_ids": [unit["query_family_id"]],
        "selection_state": "DISCOVERED_CANDIDATE",
        "canonical_effect": "NONE_REQUIRES_RELEVANCE_ADJUDICATION",
        "source_record_sha256": _sha256_json(record),
        "observed_at": observed_at,
    }


def _coverage_report(unit: dict[str, Any], *, frozen_at: str, eligible: int, discovered: int) -> dict[str, Any]:
    rates: dict[str, float | None]
    if eligible == 0:
        rates = {
            "discovery": None,
            "resolution": None,
            "sourcing": None,
            "temporal_verification": None,
            "linkage": None,
        }
    else:
        rates = {
            "discovery": discovered / eligible,
            "resolution": 0.0,
            "sourcing": discovered / eligible,
            "temporal_verification": 0.0,
            "linkage": 0.0,
        }
    digest = _sha256_json({"query_unit_id": unit["query_unit_id"], "frozen_at": frozen_at})
    return {
        "coverage_id": f"COV-{_provider_slug(unit['provider'])}-{digest[:20].upper()}",
        "schema_version": "0.1.0",
        "universe_id": unit["source_universe_id"],
        "frozen_at": frozen_at,
        "denominator": {"eligible": eligible, "method": "API_TOTAL"},
        "states": {
            "discovered": discovered,
            "resolved": 0,
            "sourced": discovered,
            "temporally_verified": 0,
            "linked": 0,
            "stale": 0,
            "conflicted": 0,
            "inaccessible": 0,
            "excluded": 0,
        },
        "rates": rates,
        "exclusions": [],
        "authority_boundary": (
            "Coverage applies only to this frozen provider query unit. It does not establish "
            "global literature completeness, NeuroAI relevance, scientific validity, or canonical identity."
        ),
    }


def _freeze_id(unit: dict[str, Any]) -> str:
    return f"AF-SCI-{_provider_slug(unit['provider'])}-{unit['request_identity_sha256'][:20].upper()}"


def _request_basis(unit: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": unit["provider"],
        "endpoint": unit["endpoint"],
        "parameters": unit["parameters"],
        "query_family_id": unit["query_family_id"],
        "term_index": unit["term_index"],
        "term": unit["term"],
        "window": unit["window"],
        "adapter_id": unit["adapter_id"],
        "source_universe_id": unit["source_universe_id"],
    }


def _plan_basis(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_id": plan["protocol_id"],
        "compilation_id": plan["compilation_id"],
        "evidence_cutoff": plan["evidence_cutoff"],
        "priority_window": plan["priority_window"],
        "query_units": plan["query_units"],
    }


def validate_plan_integrity(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if plan.get("status") != "FROZEN_QUERY_PLAN_NO_ACQUISITION_EXECUTED":
        raise ValueError("input plan is not a frozen pre-acquisition query plan")
    units = plan.get("query_units")
    if not isinstance(units, list) or not units:
        raise ValueError("query plan requires query units")
    if plan.get("unit_count") != len(units):
        raise ValueError("query plan unit_count mismatch")

    expected_plan_sha = _sha256_json(_plan_basis(plan))
    if plan.get("plan_sha256") != expected_plan_sha:
        raise ValueError("query plan SHA-256 mismatch")
    expected_plan_id = f"SCIENCE-QUERY-PLAN-{expected_plan_sha[:20].upper()}"
    if plan.get("plan_id") != expected_plan_id:
        raise ValueError("query plan id mismatch")

    by_id: dict[str, dict[str, Any]] = {}
    provider_counts = {provider: 0 for provider in SUPPORTED_PROVIDERS}
    for unit in units:
        provider = unit.get("provider")
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported first-acquisition provider: {provider}")
        request_sha = _sha256_json(_request_basis(unit))
        if unit.get("request_identity_sha256") != request_sha:
            raise ValueError(f"{unit.get('query_unit_id')}: request identity SHA-256 mismatch")
        expected_unit_id = f"QUNIT-{provider}-{request_sha[:20].upper()}"
        if unit.get("query_unit_id") != expected_unit_id:
            raise ValueError(f"{unit.get('query_unit_id')}: query-unit id mismatch")
        if unit.get("coverage_denominator_method") != "API_TOTAL":
            raise ValueError(f"{expected_unit_id}: denominator method drift")
        if unit.get("canonical_effect") != "NONE_DISCOVERY_QUERY_ONLY":
            raise ValueError(f"{expected_unit_id}: query unit crossed canonical authority boundary")
        if expected_unit_id in by_id:
            raise ValueError(f"duplicate query_unit_id: {expected_unit_id}")
        by_id[expected_unit_id] = unit
        provider_counts[provider] += 1

    expected_counts = plan.get("provider_counts")
    if not isinstance(expected_counts, dict) or expected_counts != provider_counts:
        raise ValueError("query plan provider_counts mismatch")
    return by_id


def acquire_query_unit(
    unit: dict[str, Any],
    *,
    output_root: Path,
    transport: Any,
    max_attempts: int = 5,
    max_pages: int = 10_000,
    sleep_fn: Callable[[float], None] = time.sleep,
    clock_fn: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    validate_output_root(output_root)
    if max_pages < 1:
        raise ValueError("max_pages must be >= 1")

    unit_dir = output_root / "units" / unit["query_unit_id"]
    raw_root = output_root / "raw"
    freeze_id = _freeze_id(unit)
    unit_started_at = clock_fn()
    parameters = dict(unit["parameters"])
    provider = unit["provider"]
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported acquisition provider: {provider}")
    cursor_parameter = "cursor" if provider == "CROSSREF" else "cursorMark"

    pages: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    seen_provider_keys: set[tuple[str | None, str]] = set()
    expected_total: int | None = None
    failure_reason: str | None = None
    continuation_state: str | None = None

    try:
        for page_index in range(1, max_pages + 1):
            url = _build_url(unit["endpoint"], parameters)
            requested_at = clock_fn()
            result = fetch_with_retries(
                transport,
                url,
                max_attempts=max_attempts,
                sleep_fn=sleep_fn,
            )
            observed_at = clock_fn()
            raw_sha, raw_pointer = _store_raw(raw_root, result.body)
            payload = _json_body(result.body, f"{provider}:{unit['query_unit_id']}:page-{page_index}")
            if provider == "CROSSREF":
                total, records, next_cursor = _crossref_page(payload)
            else:
                total, records, next_cursor = _europe_pmc_page(payload)

            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                failure_reason = "PROVIDER_TOTAL_CHANGED_DURING_TRAVERSAL"
                continuation_state = parameters.get(cursor_parameter)
                break

            page_manifest = {
                "page_index": page_index,
                "requested_at": requested_at,
                "observed_at": observed_at,
                "request_url_sha256": _sha256_bytes(url.encode("utf-8")),
                "cursor_in": parameters.get(cursor_parameter),
                "http_status": result.status,
                "response_headers": _selected_headers(result.headers),
                "content_sha256": raw_sha,
                "byte_count": len(result.body),
                "raw_custody_pointer": raw_pointer,
                "provider_total": total,
                "record_count": len(records),
                "cursor_out": next_cursor,
            }
            pages.append(page_manifest)

            for record in records:
                if provider == "CROSSREF":
                    candidate = _crossref_candidate(
                        record,
                        unit=unit,
                        freeze_id=freeze_id,
                        observed_at=observed_at,
                    )
                else:
                    candidate = _europe_pmc_candidate(
                        record,
                        unit=unit,
                        freeze_id=freeze_id,
                        observed_at=observed_at,
                    )
                provider_key = (
                    candidate.get("provider_record_source"),
                    candidate["provider_record_id"],
                )
                if provider_key in seen_provider_keys:
                    source_label = f"{provider_key[0]}:" if provider_key[0] else ""
                    raise RuntimeError(
                        f"{provider}:{source_label}{provider_key[1]}: duplicate provider record inside query unit"
                    )
                seen_provider_keys.add(provider_key)
                candidates.append(candidate)

            if len(candidates) >= total:
                if len(candidates) != total:
                    failure_reason = "RECORD_COUNT_EXCEEDED_PROVIDER_TOTAL"
                continuation_state = None
                break
            if not records:
                failure_reason = "EMPTY_PAGE_BEFORE_PROVIDER_TOTAL"
                continuation_state = parameters.get(cursor_parameter)
                break
            if not next_cursor or next_cursor == parameters.get(cursor_parameter):
                failure_reason = "CURSOR_DID_NOT_ADVANCE_BEFORE_PROVIDER_TOTAL"
                continuation_state = next_cursor
                break
            parameters[cursor_parameter] = next_cursor
        else:
            failure_reason = "MAX_PAGES_REACHED"
            continuation_state = parameters.get(cursor_parameter)
    except Exception as exc:
        failure_reason = f"ACQUISITION_ERROR:{type(exc).__name__}:{exc}"
        continuation_state = parameters.get(cursor_parameter)

    if expected_total is None:
        expected_total = 0

    complete = failure_reason is None and len(candidates) == expected_total
    exhaustion_state = "COMPLETE" if complete else ("FAILED" if not pages else "PARTIAL")
    page_manifest_sha = _sha256_json(pages)
    freeze = {
        "freeze_id": freeze_id,
        "schema_version": "0.1.0",
        "source_universe_id": unit["source_universe_id"],
        "adapter_id": unit["adapter_id"],
        "adapter_version": "0.1.0",
        "protocol_id": "SCIENCE-DISCOVERY-PROTOCOL-V0.1",
        "query_family_ids": [unit["query_family_id"]],
        "retrieval_cutoff": unit["evidence_cutoff"],
        "source_state_identity": f"OBSERVED-{page_manifest_sha[:32].upper()}",
        "request_identity_sha256": unit["request_identity_sha256"],
        "raw_response_manifest_sha256": page_manifest_sha,
        "raw_bytes_location_class": "OUTSIDE_GIT_CONTENT_ADDRESSED",
        "records_observed": len(candidates),
        "exhaustion_state": exhaustion_state,
        "continuation_state": continuation_state,
        "failure_reason": failure_reason,
        "canonical_effect": "NONE_CANDIDATE_DISCOVERY_ONLY",
        "created_at": unit_started_at,
        "authority_boundary": (
            "Provider-attributed acquisition state only. Even COMPLETE means only that this "
            "declared query unit reconciled to its provider-reported total; it establishes no "
            "NeuroAI relevance, scientific validity, canonical identity, or global completeness."
        ),
    }
    coverage = (
        _coverage_report(
            unit,
            frozen_at=clock_fn(),
            eligible=expected_total,
            discovered=len(candidates),
        )
        if complete
        else None
    )

    _write_jsonl(unit_dir / "candidates.jsonl", candidates)
    candidates_sha = _sha256_bytes((unit_dir / "candidates.jsonl").read_bytes())
    result_record = {
        "query_unit_id": unit["query_unit_id"],
        "request_identity_sha256": unit["request_identity_sha256"],
        "status": exhaustion_state,
        "freeze": freeze,
        "coverage": coverage,
        "coverage_state": "ISSUED_COMPLETE_QUERY_UNIT" if complete else "NOT_ISSUED_INCOMPLETE_QUERY_UNIT",
        "page_manifest": pages,
        "candidates_path": f"units/{unit['query_unit_id']}/candidates.jsonl",
        "candidates_sha256": candidates_sha,
        "candidate_count": len(candidates),
        "provider_total": expected_total,
        "raw_custody_root": "raw/sha256",
        "release_eligibility": RELEASE_INELIGIBLE,
    }
    _write_json(unit_dir / "result.json", result_record)
    return result_record


def _load_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path}:{line_number}: invalid JSONL") from exc
            if not isinstance(row, dict):
                raise RuntimeError(f"{path}:{line_number}: JSONL row must be object")
            yield row


def _validate_existing_result_integrity(
    existing: dict[str, Any],
    *,
    unit: dict[str, Any],
    output_root: Path,
) -> None:
    unit_id = unit["query_unit_id"]
    if existing.get("query_unit_id") != unit_id:
        raise ValueError(f"{unit_id}: existing result query-unit mismatch")
    if existing.get("request_identity_sha256") != unit["request_identity_sha256"]:
        raise ValueError(f"{unit_id}: existing result request identity mismatch")
    if existing.get("release_eligibility") != RELEASE_INELIGIBLE:
        raise ValueError(f"{unit_id}: existing result crossed release-eligibility boundary")

    freeze = existing.get("freeze")
    if not isinstance(freeze, dict):
        raise ValueError(f"{unit_id}: existing result lacks freeze")
    if freeze.get("request_identity_sha256") != unit["request_identity_sha256"]:
        raise ValueError(f"{unit_id}: existing freeze request identity mismatch")
    if freeze.get("raw_response_manifest_sha256") != _sha256_json(existing.get("page_manifest")):
        raise ValueError(f"{unit_id}: existing page manifest digest mismatch")

    candidate_relative = existing.get("candidates_path")
    candidate_sha = existing.get("candidates_sha256")
    if not isinstance(candidate_relative, str) or not isinstance(candidate_sha, str):
        raise ValueError(f"{unit_id}: existing candidate file metadata missing")
    candidate_path = _resolve_inside(output_root, candidate_relative)
    if not candidate_path.is_file():
        raise ValueError(f"{unit_id}: existing candidate file missing")
    actual_candidate_sha = _sha256_bytes(candidate_path.read_bytes())
    if actual_candidate_sha != candidate_sha:
        raise ValueError(f"{unit_id}: existing candidate file digest mismatch")
    candidate_count = sum(1 for _ in _load_jsonl(candidate_path))
    if existing.get("candidate_count") != candidate_count:
        raise ValueError(f"{unit_id}: existing candidate_count mismatch")
    if freeze.get("records_observed") != candidate_count:
        raise ValueError(f"{unit_id}: existing freeze records_observed mismatch")

    pages = existing.get("page_manifest")
    if not isinstance(pages, list):
        raise ValueError(f"{unit_id}: existing page_manifest must be an array")
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError(f"{unit_id}: existing page manifest row must be object")
        pointer = page.get("raw_custody_pointer")
        digest = page.get("content_sha256")
        if not isinstance(pointer, str) or not isinstance(digest, str):
            raise ValueError(f"{unit_id}: existing raw custody entry invalid")
        raw_path = _resolve_inside(output_root, pointer)
        if not raw_path.is_file() or _sha256_bytes(raw_path.read_bytes()) != digest:
            raise ValueError(f"{unit_id}: existing raw custody digest mismatch")
        if raw_path.name != f"{digest}.json":
            raise ValueError(f"{unit_id}: existing raw custody path is not content-addressed")

    status = existing.get("status")
    if status == "COMPLETE":
        if freeze.get("exhaustion_state") != "COMPLETE":
            raise ValueError(f"{unit_id}: existing COMPLETE result has non-complete freeze")
        if existing.get("provider_total") != candidate_count:
            raise ValueError(f"{unit_id}: existing COMPLETE result does not reconcile to provider total")
        if existing.get("coverage_state") != "ISSUED_COMPLETE_QUERY_UNIT" or not isinstance(existing.get("coverage"), dict):
            raise ValueError(f"{unit_id}: existing COMPLETE result lacks coverage")
    elif status in {"PARTIAL", "FAILED"}:
        if freeze.get("exhaustion_state") != status:
            raise ValueError(f"{unit_id}: existing incomplete result/freeze state mismatch")
        if existing.get("coverage_state") != "NOT_ISSUED_INCOMPLETE_QUERY_UNIT" or existing.get("coverage") is not None:
            raise ValueError(f"{unit_id}: existing incomplete result must not issue coverage")
    else:
        raise ValueError(f"{unit_id}: unsupported existing result status {status!r}")


def _archive_incomplete_attempt(
    existing: dict[str, Any],
    *,
    unit: dict[str, Any],
    output_root: Path,
) -> None:
    unit_id = unit["query_unit_id"]
    candidate_path = _resolve_inside(output_root, existing["candidates_path"])
    result_basis = {
        "query_unit_id": unit_id,
        "request_identity_sha256": unit["request_identity_sha256"],
        "status": existing["status"],
        "freeze": existing["freeze"],
        "page_manifest": existing["page_manifest"],
        "candidates_sha256": existing["candidates_sha256"],
    }
    archive_sha = _sha256_json(result_basis)
    archive_id = f"ATTEMPT-{archive_sha[:20].upper()}"
    archive_dir = output_root / "units" / unit_id / "attempts" / archive_id
    snapshot_relative = (
        Path("units") / unit_id / "attempts" / archive_id / "candidates.jsonl"
    ).as_posix()
    snapshot_path = output_root / snapshot_relative
    archive_record = {
        "archive_id": archive_id,
        "query_unit_id": unit_id,
        "archived_status": existing["status"],
        "request_identity_sha256": unit["request_identity_sha256"],
        "original_result": existing,
        "candidate_snapshot_path": snapshot_relative,
        "candidate_snapshot_sha256": existing["candidates_sha256"],
        "authority_boundary": (
            "Immutable operational archive of an incomplete acquisition attempt. It is retained for "
            "auditability and is not a completeness, release, relevance, or canonical-identity claim."
        ),
    }
    archive_bytes = (
        json.dumps(archive_record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    archive_path = archive_dir / "attempt.json"
    if archive_path.exists():
        if archive_path.read_bytes() != archive_bytes:
            raise RuntimeError(f"{unit_id}: attempt archive identity collision")
    else:
        _atomic_write(snapshot_path, candidate_path.read_bytes())
        _atomic_write(archive_path, archive_bytes)


def _archive_previous_run(output_root: Path) -> None:
    manifest_path = output_root / "run-manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("existing run-manifest.json is invalid; quarantine output root before continuing") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("run_id"), str):
        raise RuntimeError("existing run manifest lacks a valid run_id")
    run_id = manifest["run_id"]
    archive_dir = output_root / "runs" / run_id
    archive_manifest = archive_dir / "run-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    if archive_manifest.exists():
        if archive_manifest.read_bytes() != manifest_bytes:
            raise RuntimeError(f"run archive identity collision: {run_id}")
    else:
        _atomic_write(archive_manifest, manifest_bytes)

    dedup_path = output_root / "dedup-report.json"
    if dedup_path.exists():
        expected = manifest.get("dedup_report_sha256")
        actual = _sha256_json(json.loads(dedup_path.read_text(encoding="utf-8")))
        if expected != actual:
            raise RuntimeError("existing dedup report digest does not match run manifest")
        archived_dedup = archive_dir / "dedup-report.json"
        if archived_dedup.exists():
            if archived_dedup.read_bytes() != dedup_path.read_bytes():
                raise RuntimeError(f"run dedup archive identity collision: {run_id}")
        else:
            _atomic_write(archived_dedup, dedup_path.read_bytes())


def build_dedup_report(output_root: Path, unit_results: list[dict[str, Any]]) -> dict[str, Any]:
    indexes: dict[str, dict[str, list[str]]] = {
        "DOI": {},
        "PMID": {},
        "PMCID": {},
        "OPENALEX_WORK": {},
    }
    candidate_count = 0
    for result in unit_results:
        path = _resolve_inside(output_root, result["candidates_path"])
        for candidate in _load_jsonl(path):
            candidate_count += 1
            identifiers = candidate["identifiers"]
            values = {
                "DOI": identifiers.get("doi"),
                "PMID": identifiers.get("pmid"),
                "PMCID": identifiers.get("pmcid"),
                "OPENALEX_WORK": _normalize_openalex_work(identifiers.get("openalex")),
            }
            for namespace, value in values.items():
                if value:
                    indexes[namespace].setdefault(value, []).append(candidate["candidate_id"])

    groups: dict[str, list[dict[str, Any]]] = {}
    for namespace, mapping in indexes.items():
        groups[namespace] = [
            {
                "normalized_identifier": identifier,
                "candidate_ids": sorted(candidate_ids),
                "candidate_count": len(candidate_ids),
            }
            for identifier, candidate_ids in sorted(mapping.items())
            if len(candidate_ids) > 1
        ]
    return {
        "report_id": f"SCIENCE-DEDUP-{_sha256_json(groups)[:20].upper()}",
        "schema_version": "0.1.0",
        "state": "EXACT_IDENTIFIER_MATCH_CANDIDATES_ONLY",
        "identifier_precedence": ["DOI", "PMID", "PMCID", "OPENALEX_WORK"],
        "candidate_records_scanned": candidate_count,
        "duplicate_identifier_groups": groups,
        "canonical_merge_performed": False,
        "fuzzy_matching_performed": False,
        "authority_boundary": (
            "Shared explicit identifiers create reviewable deduplication candidates only. "
            "This report performs no canonical entity merge and preserves provider disagreement for adjudication."
        ),
    }


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
    clock_fn: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    validate_output_root(output_root)
    unit_by_id = validate_plan_integrity(plan)

    if providers is not None:
        unknown_providers = providers - SUPPORTED_PROVIDERS
        if unknown_providers:
            raise ValueError(f"unsupported provider selection: {sorted(unknown_providers)}")
    if query_unit_ids is not None:
        unknown_ids = query_unit_ids - set(unit_by_id)
        if unknown_ids:
            raise ValueError(f"query-unit selection contains unknown ids: {sorted(unknown_ids)}")

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

    output_root.mkdir(parents=True, exist_ok=True)
    _archive_previous_run(output_root)
    started_at = clock_fn()
    results: list[dict[str, Any]] = []
    for unit in units:
        existing_path = output_root / "units" / unit["query_unit_id"] / "result.json"
        if existing_path.exists():
            try:
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"{unit['query_unit_id']}: existing result is invalid; quarantine output root before continuing"
                ) from exc
            if not isinstance(existing, dict):
                raise RuntimeError(f"{unit['query_unit_id']}: existing result root must be object")
            _validate_existing_result_integrity(existing, unit=unit, output_root=output_root)
            if existing["status"] == "COMPLETE":
                results.append(existing)
                continue
            _archive_incomplete_attempt(existing, unit=unit, output_root=output_root)

        unit_for_acquisition = {**unit, "evidence_cutoff": plan["evidence_cutoff"]}
        results.append(
            acquire_query_unit(
                unit_for_acquisition,
                output_root=output_root,
                transport=transport,
                max_attempts=max_attempts,
                max_pages=max_pages,
                sleep_fn=sleep_fn,
                clock_fn=clock_fn,
            )
        )

    complete_units = sum(result["status"] == "COMPLETE" for result in results)
    selected_ids = {u["query_unit_id"] for u in units}
    full_plan_ids = set(unit_by_id)
    selected_is_full_plan = selected_ids == full_plan_ids and len(units) == len(unit_by_id)
    full_plan_complete = selected_is_full_plan and complete_units == len(results)
    dedup = build_dedup_report(output_root, results)
    _write_json(output_root / "dedup-report.json", dedup)

    run_basis = {
        "plan_sha256": plan["plan_sha256"],
        "selected_query_unit_ids": [unit["query_unit_id"] for unit in units],
        "result_digests": [
            _sha256_json(
                {
                    "query_unit_id": result["query_unit_id"],
                    "status": result["status"],
                    "freeze": result["freeze"],
                    "coverage": result["coverage"],
                    "candidates_sha256": result["candidates_sha256"],
                }
            )
            for result in results
        ],
    }
    run_sha = _sha256_json(run_basis)
    manifest = {
        "run_id": f"SCIENCE-ACQ-{run_sha[:20].upper()}",
        "schema_version": "0.1.0",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "started_at": started_at,
        "completed_at": clock_fn(),
        "selected_query_units": len(units),
        "complete_query_units": complete_units,
        "partial_query_units": sum(result["status"] == "PARTIAL" for result in results),
        "failed_query_units": sum(result["status"] == "FAILED" for result in results),
        "selected_is_full_plan": selected_is_full_plan,
        "full_plan_complete": full_plan_complete,
        "status": "COMPLETE_QUERY_PLAN" if full_plan_complete else "PARTIAL_OR_SCOPED_ACQUISITION",
        "query_unit_result_paths": [
            f"units/{result['query_unit_id']}/result.json" for result in results
        ],
        "dedup_report_path": "dedup-report.json",
        "dedup_report_sha256": _sha256_json(dedup),
        "raw_custody_root": "raw/sha256",
        "release_eligibility": RELEASE_INELIGIBLE,
        "canonical_effect": "NONE_CANDIDATE_DISCOVERY_ONLY",
        "authority_boundary": (
            "This run records provider acquisition mechanics only. full_plan_complete, when true, "
            "means every frozen query unit reconciled to its provider-reported denominator. It is "
            "not a claim of open-world NeuroAI literature completeness, relevance, validity, or canonical identity."
        ),
    }
    _write_json(output_root / "run-manifest.json", manifest)
    return manifest


def _load_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("query plan root must be an object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the frozen Phase 4 Crossref/Europe PMC science query plan.")
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
        transport=UrllibTransport(timeout_seconds=args.timeout_seconds),
        max_attempts=args.max_attempts,
        max_pages=args.max_pages,
        providers=set(args.provider) if args.provider else None,
        query_unit_ids=set(args.query_unit_id) if args.query_unit_id else None,
        max_units=args.max_units,
    )
    print(
        f"{manifest['status']}: complete={manifest['complete_query_units']}/"
        f"{manifest['selected_query_units']}; run_id={manifest['run_id']}"
    )


if __name__ == "__main__":
    main()
