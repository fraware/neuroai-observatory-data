from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import acquire_science_candidates as base
import acquire_science_candidates_strict as strict
import science_http_transport
import verify_science_acquisition
import verify_science_candidate_provenance
import verify_science_retry_custody

REQUIRED_REDIRECT_POLICY = "FAIL_CLOSED_NO_AUTO_FOLLOW"
VERIFIED_EXECUTION_PRODUCTS = (
    "run-manifest.json",
    "dedup-report.json",
    "retry-custody-verification.json",
    "candidate-provenance-verification.json",
    "candidate-manifest.json",
    "coverage-index.json",
    "verification-envelope.json",
)


def _load_plan(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("query plan root must be an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    base._atomic_write(
        path,
        (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _snapshot_verified_execution(output_root: Path, execution_id: str) -> None:
    archive_dir = output_root / "executions" / execution_id
    for name in VERIFIED_EXECUTION_PRODUCTS:
        source = output_root / name
        if not source.exists():
            raise ValueError(f"verified execution product is missing: {name}")
        source_bytes = source.read_bytes()
        target = archive_dir / name
        if target.exists():
            if target.read_bytes() != source_bytes:
                raise ValueError(f"verified execution archive identity collision: {execution_id}:{name}")
        else:
            base._atomic_write(target, source_bytes)


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

    provenance_report = verify_science_candidate_provenance.verify_candidate_provenance(
        output_root
    )
    if (
        provenance_report["provenance_verification_id"]
        != candidate_manifest["provenance_verification_id"]
        or provenance_report["provenance_verification_sha256"]
        != candidate_manifest["provenance_verification_sha256"]
        or provenance_report["status"]
        != candidate_manifest["provenance_verification_status"]
    ):
        raise ValueError(
            "persisted candidate provenance verification does not match candidate manifest"
        )
    _write_json(
        output_root / "candidate-provenance-verification.json",
        provenance_report,
    )

    verification_basis = {
        "result_state_id": manifest["result_state_id"],
        "execution_id": manifest["execution_id"],
        "execution_identity_sha256": manifest["execution_identity_sha256"],
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "acquisition_status": manifest["status"],
        "selected_query_units": manifest["selected_query_units"],
        "complete_query_units": manifest["complete_query_units"],
        "partial_query_units": manifest["partial_query_units"],
        "failed_query_units": manifest["failed_query_units"],
        "selected_is_full_plan": manifest["selected_is_full_plan"],
        "full_plan_complete": manifest["full_plan_complete"],
        "acquired_query_units_this_execution": manifest["acquired_query_units_this_execution"],
        "reused_complete_query_units_this_execution": manifest["reused_complete_query_units_this_execution"],
        "candidate_manifest_id": candidate_manifest["candidate_manifest_id"],
        "candidate_manifest_sha256": candidate_manifest["candidate_manifest_sha256"],
        "coverage_index_id": coverage_index["coverage_index_id"],
        "coverage_index_sha256": coverage_index["coverage_index_sha256"],
        "provenance_verification_id": provenance_report[
            "provenance_verification_id"
        ],
        "provenance_verification_sha256": provenance_report[
            "provenance_verification_sha256"
        ],
        "retry_custody_verification_id": retry_report["retry_custody_verification_id"],
        "retry_custody_verification_sha256": retry_report["retry_custody_verification_sha256"],
    }
    verification_sha = base._sha256_json(verification_basis)
    envelope = {
        "verification_envelope_id": f"SCIENCE-ACQUISITION-VERIFICATION-{verification_sha[:20].upper()}",
        "schema_version": "0.2.0",
        **verification_basis,
        "verification_envelope_sha256": verification_sha,
        "state": "ACQUISITION_EVIDENCE_VERIFIED_NOT_RELEASE_AUTHORIZED",
        "release_eligibility": base.RELEASE_INELIGIBLE,
        "canonical_effect": "NONE_CANDIDATE_DISCOVERY_ONLY",
        "authority_boundary": (
            "This envelope binds the execution identity, result-state identity, independent acquisition/provenance verification, "
            "and retry-response custody verification for the selected frozen query units. Verification of an incomplete or scoped "
            "run does not convert it into a complete run, and reuse of a complete result does not assert that provider retrieval "
            "occurred again. The envelope establishes no scientific relevance, validity, canonical identity, release authority, "
            "or open-world literature completeness."
        ),
    }
    _write_json(output_root / "verification-envelope.json", envelope)
    _snapshot_verified_execution(output_root, manifest["execution_id"])
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
        f"execution={envelope['execution_id']}; result_state={envelope['result_state_id']}; "
        f"acquisition_status={envelope['acquisition_status']}; "
        f"complete={envelope['complete_query_units']}/{envelope['selected_query_units']}; "
        f"full_plan_complete={envelope['full_plan_complete']}"
    )


if __name__ == "__main__":
    main()
