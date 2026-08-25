from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import validate_science_graph as science_contract
import validate_source_universes as coverage_contract

RELEASE_INELIGIBLE = "NOT_RELEASE_ELIGIBLE_UNTIL_DURABLE_CUSTODY_AND_RIGHTS_REVIEW"


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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot open JSONL: {path}") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be object")
            rows.append(row)
    return rows


def _resolve_inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    root_resolved = root.resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ValueError(f"path escapes acquisition root: {relative}")
    return path


def _verify_file_sha(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"missing {label}: {path}")
    actual = _sha256_bytes(path.read_bytes())
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")


def _plan_basis(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_id": plan["protocol_id"],
        "compilation_id": plan["compilation_id"],
        "evidence_cutoff": plan["evidence_cutoff"],
        "priority_window": plan["priority_window"],
        "query_units": plan["query_units"],
    }


def validate_plan(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if plan.get("status") != "FROZEN_QUERY_PLAN_NO_ACQUISITION_EXECUTED":
        raise ValueError("query plan must be a frozen pre-acquisition plan")
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
    for unit in units:
        unit_id = unit.get("query_unit_id")
        if not isinstance(unit_id, str) or not unit_id:
            raise ValueError("query unit lacks query_unit_id")
        if unit_id in by_id:
            raise ValueError(f"duplicate query_unit_id: {unit_id}")
        by_id[unit_id] = unit
    return by_id


def _validate_raw_custody(run_dir: Path, result: dict[str, Any]) -> None:
    pages = result.get("page_manifest")
    if not isinstance(pages, list):
        raise ValueError(f"{result.get('query_unit_id')}: page_manifest must be an array")
    for page in pages:
        pointer = page.get("raw_custody_pointer")
        digest = page.get("content_sha256")
        if not isinstance(pointer, str) or not isinstance(digest, str):
            raise ValueError(f"{result.get('query_unit_id')}: invalid raw custody entry")
        raw_path = _resolve_inside(run_dir, pointer)
        _verify_file_sha(raw_path, digest, "raw response")
        if raw_path.name != f"{digest}.json":
            raise ValueError(f"{result.get('query_unit_id')}: raw custody filename is not content-addressed")


def _validate_result(
    run_dir: Path,
    result: dict[str, Any],
    unit: dict[str, Any],
    evidence_cutoff: str,
) -> dict[str, Any]:
    unit_id = unit["query_unit_id"]
    if result.get("query_unit_id") != unit_id:
        raise ValueError(f"{unit_id}: result query_unit_id mismatch")
    if result.get("request_identity_sha256") != unit.get("request_identity_sha256"):
        raise ValueError(f"{unit_id}: result request identity mismatch")
    if result.get("release_eligibility") != RELEASE_INELIGIBLE:
        raise ValueError(f"{unit_id}: result release eligibility crossed authority boundary")

    freeze = result.get("freeze")
    if not isinstance(freeze, dict):
        raise ValueError(f"{unit_id}: result lacks freeze")
    science_contract._structural(science_contract.FREEZE_VALIDATOR, freeze, freeze.get("freeze_id", unit_id))
    if freeze["request_identity_sha256"] != unit["request_identity_sha256"]:
        raise ValueError(f"{unit_id}: freeze request identity mismatch")
    if freeze["source_universe_id"] != unit["source_universe_id"]:
        raise ValueError(f"{unit_id}: freeze source universe mismatch")
    if freeze["adapter_id"] != unit["adapter_id"]:
        raise ValueError(f"{unit_id}: freeze adapter mismatch")
    if freeze["retrieval_cutoff"] != evidence_cutoff:
        raise ValueError(f"{unit_id}: freeze evidence cutoff mismatch")
    if freeze["query_family_ids"] != [unit["query_family_id"]]:
        raise ValueError(f"{unit_id}: freeze query family mismatch")

    candidates_path = result.get("candidates_path")
    candidates_sha = result.get("candidates_sha256")
    if not isinstance(candidates_path, str) or not isinstance(candidates_sha, str):
        raise ValueError(f"{unit_id}: candidate file metadata missing")
    candidate_file = _resolve_inside(run_dir, candidates_path)
    _verify_file_sha(candidate_file, candidates_sha, "candidate JSONL")
    candidates = _load_jsonl(candidate_file)
    if result.get("candidate_count") != len(candidates):
        raise ValueError(f"{unit_id}: candidate_count mismatch")
    if freeze["records_observed"] != len(candidates):
        raise ValueError(f"{unit_id}: freeze records_observed mismatch")

    candidate_ids: set[str] = set()
    for candidate in candidates:
        science_contract._structural(
            science_contract.CANDIDATE_VALIDATOR,
            candidate,
            candidate.get("candidate_id", unit_id),
        )
        candidate_id = candidate["candidate_id"]
        if candidate_id in candidate_ids:
            raise ValueError(f"{unit_id}: duplicate candidate_id")
        candidate_ids.add(candidate_id)
        if candidate["acquisition_freeze_id"] != freeze["freeze_id"]:
            raise ValueError(f"{unit_id}: candidate freeze reference mismatch")
        if candidate["provider"] != unit["provider"]:
            raise ValueError(f"{unit_id}: candidate provider mismatch")
        if candidate["source_universe_id"] != unit["source_universe_id"]:
            raise ValueError(f"{unit_id}: candidate source universe mismatch")
        if candidate["discovery_query_family_ids"] != [unit["query_family_id"]]:
            raise ValueError(f"{unit_id}: candidate query family mismatch")

    status = result.get("status")
    coverage = result.get("coverage")
    if status == "COMPLETE":
        if freeze["exhaustion_state"] != "COMPLETE":
            raise ValueError(f"{unit_id}: complete result has non-complete freeze")
        if result.get("provider_total") != len(candidates):
            raise ValueError(f"{unit_id}: complete result does not reconcile to provider total")
        if result.get("coverage_state") != "ISSUED_COMPLETE_QUERY_UNIT" or not isinstance(coverage, dict):
            raise ValueError(f"{unit_id}: complete result lacks coverage")
        coverage_contract.validate_coverage(coverage)
        if coverage["universe_id"] != unit["source_universe_id"]:
            raise ValueError(f"{unit_id}: coverage source universe mismatch")
        if coverage["denominator"] != {"eligible": len(candidates), "method": "API_TOTAL"}:
            raise ValueError(f"{unit_id}: coverage denominator mismatch")
        if coverage["states"]["discovered"] != len(candidates):
            raise ValueError(f"{unit_id}: coverage discovered count mismatch")
    elif status in {"PARTIAL", "FAILED"}:
        if freeze["exhaustion_state"] != status:
            raise ValueError(f"{unit_id}: incomplete result/freeze state mismatch")
        if result.get("coverage_state") != "NOT_ISSUED_INCOMPLETE_QUERY_UNIT" or coverage is not None:
            raise ValueError(f"{unit_id}: incomplete result must not issue coverage")
    else:
        raise ValueError(f"{unit_id}: unsupported result status {status!r}")

    _validate_raw_custody(run_dir, result)
    return {
        "query_unit_id": unit_id,
        "provider": unit["provider"],
        "query_family_id": unit["query_family_id"],
        "window": unit["window"],
        "request_identity_sha256": unit["request_identity_sha256"],
        "status": status,
        "freeze_id": freeze["freeze_id"],
        "candidate_count": len(candidates),
        "candidates_path": candidates_path,
        "candidates_sha256": candidates_sha,
        "coverage_id": coverage["coverage_id"] if isinstance(coverage, dict) else None,
        "provider_total": result.get("provider_total"),
    }


def verify_acquisition(plan: dict[str, Any], run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    units = validate_plan(plan)
    manifest = _load_json(run_dir / "run-manifest.json")
    if manifest.get("plan_id") != plan["plan_id"] or manifest.get("plan_sha256") != plan["plan_sha256"]:
        raise ValueError("run manifest is not bound to the supplied query plan")
    if manifest.get("release_eligibility") != RELEASE_INELIGIBLE:
        raise ValueError("run manifest crossed release-eligibility boundary")
    if manifest.get("canonical_effect") != "NONE_CANDIDATE_DISCOVERY_ONLY":
        raise ValueError("run manifest crossed canonical authority boundary")

    result_paths = manifest.get("query_unit_result_paths")
    if not isinstance(result_paths, list) or not result_paths:
        raise ValueError("run manifest requires query-unit result paths")
    if len(result_paths) != manifest.get("selected_query_units"):
        raise ValueError("selected_query_units does not match result paths")

    verified_units: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative in result_paths:
        if not isinstance(relative, str):
            raise ValueError("query-unit result path must be string")
        result = _load_json(_resolve_inside(run_dir, relative))
        unit_id = result.get("query_unit_id")
        if unit_id not in units:
            raise ValueError(f"run contains query unit outside supplied plan: {unit_id}")
        if unit_id in seen:
            raise ValueError(f"duplicate query-unit result: {unit_id}")
        seen.add(unit_id)
        verified_units.append(_validate_result(run_dir, result, units[unit_id], plan["evidence_cutoff"]))

    complete = sum(row["status"] == "COMPLETE" for row in verified_units)
    partial = sum(row["status"] == "PARTIAL" for row in verified_units)
    failed = sum(row["status"] == "FAILED" for row in verified_units)
    if manifest.get("complete_query_units") != complete:
        raise ValueError("run manifest complete_query_units mismatch")
    if manifest.get("partial_query_units") != partial:
        raise ValueError("run manifest partial_query_units mismatch")
    if manifest.get("failed_query_units") != failed:
        raise ValueError("run manifest failed_query_units mismatch")

    selected_is_full_plan = len(seen) == len(units) and seen == set(units)
    full_plan_complete = selected_is_full_plan and complete == len(verified_units)
    if manifest.get("selected_is_full_plan") is not selected_is_full_plan:
        raise ValueError("run manifest selected_is_full_plan mismatch")
    if manifest.get("full_plan_complete") is not full_plan_complete:
        raise ValueError("run manifest full_plan_complete mismatch")
    expected_status = "COMPLETE_QUERY_PLAN" if full_plan_complete else "PARTIAL_OR_SCOPED_ACQUISITION"
    if manifest.get("status") != expected_status:
        raise ValueError("run manifest status mismatch")

    dedup_path = _resolve_inside(run_dir, manifest.get("dedup_report_path", ""))
    dedup = _load_json(dedup_path)
    if _sha256_json(dedup) != manifest.get("dedup_report_sha256"):
        raise ValueError("dedup report digest mismatch")
    if dedup.get("canonical_merge_performed") is not False or dedup.get("fuzzy_matching_performed") is not False:
        raise ValueError("dedup report crossed identity authority boundary")

    candidate_manifest_basis = {
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "run_id": manifest["run_id"],
        "query_units": verified_units,
        "dedup_report_sha256": manifest["dedup_report_sha256"],
    }
    candidate_manifest_sha = _sha256_json(candidate_manifest_basis)
    candidate_manifest = {
        "candidate_manifest_id": f"SCIENCE-CANDIDATE-MANIFEST-{candidate_manifest_sha[:20].upper()}",
        "schema_version": "0.1.0",
        "state": "PROVIDER_ATTRIBUTED_DISCOVERY_CANDIDATES_NOT_CANONICAL",
        **candidate_manifest_basis,
        "selected_query_units": len(verified_units),
        "complete_query_units": complete,
        "candidate_record_occurrences": sum(row["candidate_count"] for row in verified_units),
        "candidate_manifest_sha256": candidate_manifest_sha,
        "release_eligibility": RELEASE_INELIGIBLE,
        "authority_boundary": (
            "This manifest inventories provider-attributed discovery candidates. Counts include repeated "
            "occurrences across overlapping frozen query units and are not unique-publication or scientific-validity counts."
        ),
    }

    complete_coverages = [
        {
            "query_unit_id": row["query_unit_id"],
            "coverage_id": row["coverage_id"],
            "provider": row["provider"],
            "provider_total": row["provider_total"],
        }
        for row in verified_units
        if row["status"] == "COMPLETE"
    ]
    coverage_basis = {
        "plan_id": plan["plan_id"],
        "run_id": manifest["run_id"],
        "complete_query_unit_coverages": complete_coverages,
    }
    coverage_sha = _sha256_json(coverage_basis)
    coverage_index = {
        "coverage_index_id": f"SCIENCE-COVERAGE-INDEX-{coverage_sha[:20].upper()}",
        "schema_version": "0.1.0",
        **coverage_basis,
        "coverage_index_sha256": coverage_sha,
        "aggregate_denominator_claim": "NOT_CLAIMED_QUERY_UNITS_OVERLAP",
        "full_plan_complete": full_plan_complete,
        "release_eligibility": RELEASE_INELIGIBLE,
        "authority_boundary": (
            "Each entry is complete only within one frozen provider query unit. Provider totals are not additive "
            "across overlapping terms/windows and do not establish open-world NeuroAI literature completeness."
        ),
    }
    return candidate_manifest, coverage_index


def write_verified_products(run_dir: Path, candidate_manifest: dict[str, Any], coverage_index: dict[str, Any]) -> None:
    (run_dir / "candidate-manifest.json").write_text(
        json.dumps(candidate_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "coverage-index.json").write_text(
        json.dumps(coverage_index, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a Phase 4 science acquisition bundle and build deterministic candidate/coverage manifests.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()

    plan = _load_json(args.plan)
    candidate_manifest, coverage_index = verify_acquisition(plan, args.run_dir)
    write_verified_products(args.run_dir, candidate_manifest, coverage_index)
    print(
        f"PASS science acquisition verification: units={candidate_manifest['selected_query_units']}; "
        f"complete={candidate_manifest['complete_query_units']}; "
        f"candidate_occurrences={candidate_manifest['candidate_record_occurrences']}"
    )


if __name__ == "__main__":
    main()
