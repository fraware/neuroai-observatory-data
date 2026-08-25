from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import acquire_science_candidates as acquisition


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: row must be an object")
            rows.append(value)
    return rows


def _inside(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes acquisition root: {relative}")
    return path


def _records_from_raw(provider: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if provider == "CROSSREF":
        _total, records, _cursor = acquisition._crossref_page(payload)
        return records
    if provider == "EUROPE_PMC":
        _total, records, _cursor = acquisition._europe_pmc_page(payload)
        return records
    raise ValueError(f"unsupported provider in first-acquisition provenance audit: {provider}")


def _raw_provider_identity(provider: str, record: dict[str, Any]) -> tuple[str | None, str]:
    if provider == "CROSSREF":
        doi = acquisition._normalize_doi(record.get("DOI"))
        if doi is None:
            raise ValueError("Crossref raw record lacks usable DOI provider identity")
        return None, doi
    if provider == "EUROPE_PMC":
        source = record.get("source")
        record_id = record.get("id")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Europe PMC raw record lacks source database code")
        if record_id is None or not str(record_id).strip():
            raise ValueError("Europe PMC raw record lacks id")
        return source.strip().upper(), str(record_id).strip()
    raise ValueError(f"unsupported provider identity audit: {provider}")


def _expected_candidate(
    provider: str,
    record: dict[str, Any],
    *,
    result: dict[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    freeze = result["freeze"]
    query_families = freeze.get("query_family_ids")
    if not isinstance(query_families, list) or len(query_families) != 1:
        raise ValueError(f"{result.get('query_unit_id')}: provenance reconstruction requires one query family")
    unit = {
        "query_unit_id": result["query_unit_id"],
        "source_universe_id": freeze["source_universe_id"],
        "query_family_id": query_families[0],
    }
    if provider == "CROSSREF":
        return acquisition._crossref_candidate(
            record,
            unit=unit,
            freeze_id=freeze["freeze_id"],
            observed_at=observed_at,
        )
    if provider == "EUROPE_PMC":
        return acquisition._europe_pmc_candidate(
            record,
            unit=unit,
            freeze_id=freeze["freeze_id"],
            observed_at=observed_at,
        )
    raise ValueError(f"unsupported provider candidate reconstruction: {provider}")


def verify_candidate_provenance(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    manifest = _load_json(run_dir / "run-manifest.json")
    result_paths = manifest.get("query_unit_result_paths")
    if not isinstance(result_paths, list) or not result_paths:
        raise ValueError("run manifest requires query-unit result paths")

    verified_candidates = 0
    verified_raw_records = 0
    europe_pmc_source_ids: set[tuple[str, str]] = set()

    for result_relative in result_paths:
        if not isinstance(result_relative, str):
            raise ValueError("query-unit result path must be string")
        result = _load_json(_inside(run_dir, result_relative))
        unit_id = result.get("query_unit_id")
        source_universe = result.get("freeze", {}).get("source_universe_id")
        if source_universe == "SU-SCI-CROSSREF":
            provider_name = "CROSSREF"
        elif source_universe == "SU-SCI-EUROPEPMC":
            provider_name = "EUROPE_PMC"
        else:
            raise ValueError(f"{unit_id}: unsupported source universe in provenance audit")

        provenance: dict[str, list[tuple[str, str | None, str, dict[str, Any]]]] = {}
        raw_record_count = 0
        pages = result.get("page_manifest")
        if not isinstance(pages, list):
            raise ValueError(f"{unit_id}: page_manifest must be an array")
        for page in pages:
            pointer = page.get("raw_custody_pointer")
            digest = page.get("content_sha256")
            observed_at = page.get("observed_at")
            if not all(isinstance(value, str) and value for value in (pointer, digest, observed_at)):
                raise ValueError(f"{unit_id}: invalid page provenance metadata")
            raw_path = _inside(run_dir, pointer)
            if not raw_path.is_file():
                raise ValueError(f"{unit_id}: missing raw response {pointer}")
            raw_bytes = raw_path.read_bytes()
            if _sha256_bytes(raw_bytes) != digest:
                raise ValueError(f"{unit_id}: raw response digest mismatch")
            try:
                payload = json.loads(raw_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{unit_id}: raw response is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{unit_id}: raw response root must be object")
            records = _records_from_raw(provider_name, payload)
            raw_record_count += len(records)
            for record in records:
                record_sha = _sha256_json(record)
                provider_source, provider_id = _raw_provider_identity(provider_name, record)
                provenance.setdefault(record_sha, []).append(
                    (observed_at, provider_source, provider_id, record)
                )
                if provider_name == "EUROPE_PMC":
                    assert provider_source is not None
                    europe_pmc_source_ids.add((provider_source, provider_id))

        candidates_relative = result.get("candidates_path")
        if not isinstance(candidates_relative, str):
            raise ValueError(f"{unit_id}: result lacks candidates_path")
        candidates = _load_jsonl(_inside(run_dir, candidates_relative))
        for candidate in candidates:
            record_sha = candidate.get("source_record_sha256")
            observed_at = candidate.get("observed_at")
            provider_id = candidate.get("provider_record_id")
            provider_source = candidate.get("provider_record_source")
            if not isinstance(record_sha, str) or record_sha not in provenance:
                raise ValueError(f"{unit_id}: candidate source_record_sha256 is not present in captured raw responses")
            if not isinstance(observed_at, str) or not isinstance(provider_id, str):
                raise ValueError(f"{unit_id}: candidate provider identity or observed_at is invalid")
            if provider_name == "EUROPE_PMC":
                if not isinstance(provider_source, str) or not provider_source:
                    raise ValueError(f"{unit_id}: Europe PMC candidate lacks provider_record_source")
                provider_source = provider_source.upper()
            elif provider_source is not None:
                raise ValueError(f"{unit_id}: Crossref candidate unexpectedly carries provider_record_source")

            matches = [
                record
                for raw_observed_at, raw_source, raw_id, record in provenance[record_sha]
                if (raw_observed_at, raw_source, raw_id) == (observed_at, provider_source, provider_id)
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"{unit_id}: candidate provider identity/observation does not resolve uniquely to its captured raw record"
                )
            expected = _expected_candidate(
                provider_name,
                matches[0],
                result=result,
                observed_at=observed_at,
            )
            if candidate != expected:
                raise ValueError(
                    f"{unit_id}: candidate normalization does not reproduce exactly from its captured raw provider record"
                )
            verified_candidates += 1

        if result.get("status") == "COMPLETE" and raw_record_count != len(candidates):
            raise ValueError(f"{unit_id}: complete query raw-record count does not equal candidate count")
        verified_raw_records += raw_record_count

    report_basis = {
        "run_id": manifest.get("run_id"),
        "verified_candidates": verified_candidates,
        "verified_raw_records": verified_raw_records,
        "europe_pmc_distinct_source_ids": len(europe_pmc_source_ids),
    }
    report_sha = _sha256_json(report_basis)
    return {
        "provenance_verification_id": f"SCIENCE-PROVENANCE-{report_sha[:20].upper()}",
        "schema_version": "0.1.0",
        **report_basis,
        "provenance_verification_sha256": report_sha,
        "status": "RAW_RESPONSE_PROVENANCE_VERIFIED",
        "canonical_effect": "NONE",
        "authority_boundary": (
            "This verifies that each candidate is exactly reproducible from its provider identity, source-record hash, "
            "observation time, and captured raw provider record. It does not establish scientific validity, relevance, "
            "canonical identity, or release authority."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify candidate-to-raw-response provenance for a Phase 4 science acquisition run.")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    report = verify_candidate_provenance(args.run_dir)
    output = args.run_dir / "candidate-provenance-verification.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"PASS candidate provenance: candidates={report['verified_candidates']}; "
        f"raw_records={report['verified_raw_records']}"
    )


if __name__ == "__main__":
    main()
