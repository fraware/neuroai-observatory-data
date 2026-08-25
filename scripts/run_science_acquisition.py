from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import acquire_science_candidates as base
import acquire_science_candidates_strict as strict
import science_http_transport
import verify_science_acquisition
import verify_science_retry_custody

REQUIRED_REDIRECT_POLICY = "FAIL_CLOSED_NO_AUTO_FOLLOW"
DERIVED_VERIFICATION_PRODUCTS = (
    "candidate-manifest.json",
    "coverage-index.json",
    "candidate-provenance-verification.json",
    "retry-custody-verification.json",
    "verification-envelope.json",
)


def _load_plan(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("query plan root must be an object")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    base._atomic_write(
        path,
        (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _archive_prior_derived_products(output_root: Path) -> None:
    manifest_path = output_root / "run-manifest.json"
    if not manifest_path.exists():
        return
    manifest = _load_json(manifest_path)
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("existing run manifest lacks run_id; quarantine output root before continuing")

    archive_dir = output_root / "runs" / run_id
    for name in DERIVED_VERIFICATION_PRODUCTS:
        source = output_root / name
        if not source.exists():
            continue
        payload = _load_json(source)
        if payload.get("run_id") != run_id:
            raise ValueError(
                f"existing {name} does not belong to current run manifest; quarantine output root before continuing"
            )
        source_bytes = source.read_bytes()
        target = archive_dir / name
        if target.exists():
            if target.read_bytes() != source_bytes:
                raise ValueError(f"derived-product archive identity collision: {run_id}:{name}")
        else:
            base._atomic_write(target, source_bytes)
        source.unlink()


def run_acquisition(
    plan: dict[str, Any],
    *,
    output_root: Path,
    transport: Any,
    max_attempts: int = 5,
    max_pages: int = 10_000,
    providers: set[str] | None = None,
    query_unit_ids: set[str] | None = None,
    max_units: int | None = None,
    sleep_fn: Callable[[float], None],
    clock_fn: Callable[[], str],
) -> dict[str, Any]:
    if getattr(transport, "redirect_policy", None) != REQUIRED_REDIRECT_POLICY:
        raise ValueError(
            "production acquisition requires a transport that disables automatic redirects"
        )

    base.validate_output_root(output_root)
    _archive_prior_derived_products(output_root)

    manifest = strict.acquire_plan(
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

    retry_report = verify_science_retry_custody.verify_retry_custody(plan, output_root)
    _write_json(output_root / "retry-custody-verification.json", retry_report)

    candidate_manifest, coverage_index = verify_science_acquisition.verify_acquisition(
        plan,
        output_root,
    )
    verify_science_acquisition.write_verified_products(
        output_root,
        candidate_manifest,
        coverage_index,
    )

    verification_basis = {
        "run_id": manifest["run_id"],
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "acquisition_status": manifest["status"],
        "selected_query_units": manifest["selected_query_units"],
        "complete_query_units": manifest["complete_query_units"],
        "partial_query_units": manifest["partial_query_units"],
        "failed_query_units": manifest["failed_query_units"],
        "selected_is_full_plan": manifest["selected_is_full_plan"],
        "full_plan_complete": manifest["full_plan_complete"],
        "candidate_manifest_id": candidate_manifest["candidate_manifest_id"],
        "candidate_manifest_sha256": candidate_manifest["candidate_manifest_sha256"],
        "coverage_index_id": coverage_index["coverage_index_id"],
        "coverage_index_sha256": coverage_index["coverage_index_sha256"],
        "retry_custody_verification_id": retry_report["retry_custody_verification_id"],
        "retry_custody_verification_sha256": retry_report["retry_custody_verification_sha256"],
    }
    verification_sha = base._sha256_json(verification_basis)
    envelope = {
        "verification_envelope_id": f"SCIENCE-ACQUISITION-VERIFICATION-{verification_sha[:20].upper()}",
        "schema_version": "0.1.0",
        **verification_basis,
        "verification_envelope_sha256": verification_sha,
        "state": "ACQUISITION_EVIDENCE_VERIFIED_NOT_RELEASE_AUTHORIZED",
        "release_eligibility": base.RELEASE_INELIGIBLE,
        "canonical_effect": "NONE_CANDIDATE_DISCOVERY_ONLY",
        "authority_boundary": (
            "This envelope binds independent acquisition, raw-response provenance, and retry-response custody "
            "verification products for the selected frozen query units. Verification of an incomplete or scoped "
            "run does not convert it into a complete run. The envelope establishes no scientific relevance, "
            "validity, canonical identity, release authority, or open-world literature completeness."
        ),
    }
    _write_json(output_root / "verification-envelope.json", envelope)
    return envelope


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute and independently verify a Phase 4 science acquisition with fail-closed HTTP semantics."
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--provider", action="append", choices=["CROSSREF", "EUROPE_PMC"])
    parser.add_argument("--query-unit-id", action="append")
    parser.add_argument("--max-units", type=int)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=10_000)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()

    envelope = run_acquisition(
        _load_plan(args.plan),
        output_root=args.output_dir,
        transport=science_http_transport.NoRedirectUrllibTransport(
            timeout_seconds=args.timeout_seconds
        ),
        max_attempts=args.max_attempts,
        max_pages=args.max_pages,
        providers=set(args.provider) if args.provider else None,
        query_unit_ids=set(args.query_unit_id) if args.query_unit_id else None,
        max_units=args.max_units,
        sleep_fn=base.time.sleep,
        clock_fn=base._utc_now,
    )
    print(
        f"VERIFICATION_PASS: envelope={envelope['verification_envelope_id']}; "
        f"acquisition_status={envelope['acquisition_status']}; "
        f"complete={envelope['complete_query_units']}/{envelope['selected_query_units']}; "
        f"full_plan_complete={envelope['full_plan_complete']}"
    )


if __name__ == "__main__":
    main()
