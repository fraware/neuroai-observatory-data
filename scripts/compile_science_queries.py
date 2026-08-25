from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
PROTOCOL_PATH = ROOT / "science" / "discovery-protocol-v0.1.json"
COMPILATION_PATH = ROOT / "science" / "query-compilation-v0.1.json"

PLAN_STATUS = "FROZEN_QUERY_PLAN_NO_ACQUISITION_EXECUTED"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _year_windows(start: str, through: str) -> list[tuple[str, str]]:
    first = _parse_date(start)
    last = _parse_date(through)
    if last < first:
        raise ValueError("partition through date precedes from date")

    windows: list[tuple[str, str]] = []
    year = first.year
    while year <= last.year:
        window_start = max(first, date(year, 1, 1))
        window_end = min(last, date(year, 12, 31))
        windows.append((window_start.isoformat(), window_end.isoformat()))
        year += 1
    return windows


def _escape_europe_pmc_phrase(term: str) -> str:
    return term.replace("\\", "\\\\").replace('"', '\\"')


def validate_inputs(protocol: dict[str, Any], compilation: dict[str, Any]) -> bool:
    if protocol.get("protocol_id") != compilation.get("protocol_id"):
        raise ValueError("query compilation protocol_id mismatch")
    if compilation.get("status") != "FROZEN_COMPILATION_NO_PRODUCTION_ACQUISITION_YET":
        raise ValueError("query compilation must remain explicitly pre-acquisition")
    if compilation.get("partitioning", {}).get("mode") != "CALENDAR_YEAR":
        raise ValueError("only CALENDAR_YEAR partitioning is supported in v0.1")
    if compilation.get("partitioning", {}).get("inclusive") is not True:
        raise ValueError("v0.1 partitioning must be inclusive")

    priority = protocol.get("baseline_strategy", {}).get("priority_window", {})
    partition = compilation.get("partitioning", {})
    if priority.get("from") != partition.get("from") or priority.get("through") != partition.get("through"):
        raise ValueError("query compilation partition does not match protocol priority window")

    provider_scope = compilation.get("provider_scope")
    if provider_scope != ["CROSSREF", "EUROPE_PMC"]:
        raise ValueError("v0.1 first-acquisition provider order must be CROSSREF then EUROPE_PMC")
    provider_specs = compilation.get("providers", {})
    if set(provider_specs) != set(provider_scope):
        raise ValueError("provider_scope does not match provider compilation records")

    families = protocol.get("query_families")
    if not isinstance(families, list) or not families:
        raise ValueError("protocol requires query families")
    if any(not row.get("discovery_terms") for row in families):
        raise ValueError("each query family requires discovery terms")
    return True


def _query_unit(
    *,
    provider: str,
    provider_spec: dict[str, Any],
    family_id: str,
    term_index: int,
    term: str,
    window_from: str,
    window_through: str,
) -> dict[str, Any]:
    if provider == "CROSSREF":
        date_filters = provider_spec["date_filter_parameters"]
        filter_value = (
            f"{date_filters['from']}:{window_from},"
            f"{date_filters['through']}:{window_through}"
        )
        parameters = {
            provider_spec["term_parameter"]: term,
            provider_spec["filter_parameter"]: filter_value,
            **provider_spec["fixed_parameters"],
            provider_spec["cursor_parameter"]: provider_spec["initial_cursor"],
        }
    elif provider == "EUROPE_PMC":
        escaped = _escape_europe_pmc_phrase(term)
        query = provider_spec["query_template"].format(
            term=escaped,
            **{"from": window_from, "through": window_through},
        )
        parameters = {
            provider_spec["query_parameter"]: query,
            **provider_spec["fixed_parameters"],
            provider_spec["cursor_parameter"]: provider_spec["initial_cursor"],
        }
    else:
        raise ValueError(f"unsupported provider: {provider}")

    request_basis = {
        "provider": provider,
        "endpoint": provider_spec["endpoint"],
        "parameters": parameters,
        "query_family_id": family_id,
        "term_index": term_index,
        "term": term,
        "window": {"from": window_from, "through": window_through},
        "adapter_id": provider_spec["adapter_id"],
        "source_universe_id": provider_spec["source_universe_id"],
    }
    request_sha = _sha256(request_basis)
    return {
        "query_unit_id": f"QUNIT-{provider}-{request_sha[:20].upper()}",
        **request_basis,
        "request_identity_sha256": request_sha,
        "coverage_denominator_method": "API_TOTAL",
        "canonical_effect": "NONE_DISCOVERY_QUERY_ONLY",
    }


def compile_plan(
    protocol: dict[str, Any],
    compilation: dict[str, Any],
) -> dict[str, Any]:
    validate_inputs(protocol, compilation)
    partition = compilation["partitioning"]
    windows = _year_windows(partition["from"], partition["through"])

    query_units: list[dict[str, Any]] = []
    for provider in compilation["provider_scope"]:
        provider_spec = compilation["providers"][provider]
        for family in protocol["query_families"]:
            family_id = family["query_family_id"]
            for term_index, term in enumerate(family["discovery_terms"], start=1):
                for window_from, window_through in windows:
                    query_units.append(
                        _query_unit(
                            provider=provider,
                            provider_spec=provider_spec,
                            family_id=family_id,
                            term_index=term_index,
                            term=term,
                            window_from=window_from,
                            window_through=window_through,
                        )
                    )

    ids = [unit["query_unit_id"] for unit in query_units]
    if len(ids) != len(set(ids)):
        raise ValueError("query-unit identity collision")

    provider_counts = {
        provider: sum(unit["provider"] == provider for unit in query_units)
        for provider in compilation["provider_scope"]
    }
    plan_basis = {
        "protocol_id": protocol["protocol_id"],
        "compilation_id": compilation["compilation_id"],
        "evidence_cutoff": protocol["evidence_cutoff"],
        "priority_window": protocol["baseline_strategy"]["priority_window"],
        "query_units": query_units,
    }
    plan_sha = _sha256(plan_basis)
    return {
        "plan_id": f"SCIENCE-QUERY-PLAN-{plan_sha[:20].upper()}",
        "schema_version": "0.1.0",
        "status": PLAN_STATUS,
        **plan_basis,
        "unit_count": len(query_units),
        "provider_counts": provider_counts,
        "plan_sha256": plan_sha,
        "coverage_semantics": compilation["coverage_semantics"],
        "authority_boundary": (
            "This file is a deterministic request plan only. It proves no provider request "
            "was sent, no cursor was exhausted, no record was retrieved, and no coverage or "
            "scientific claim was established."
        ),
    }


def write_plan(plan: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    output.write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile the frozen Phase 4 science discovery protocol into exact provider query units.")
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--compilation", type=Path, default=COMPILATION_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = compile_plan(_load(args.protocol), _load(args.compilation))
    write_plan(plan, args.output)
    print(
        f"PASS query compilation: {plan['unit_count']} units; "
        f"plan_sha256={plan['plan_sha256']}"
    )


if __name__ == "__main__":
    main()
