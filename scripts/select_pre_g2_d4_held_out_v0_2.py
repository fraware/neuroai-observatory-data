from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.select_pre_g2_d4_held_out import D4SelectionError, select_candidates

SUCCESS = 0
CONTROLLED_INPUT_FAILURE = 1
UNEXPECTED_INTERNAL_FAILURE = 70
PUBLIC_CONTROLLED_FAILURE = "INVALID: controlled candidate-pool selection failed under the D4 v0.2 diagnostic-containment boundary"
PUBLIC_INTERNAL_FAILURE = "INVALID: internal selector failure contained; inspect the configured S3 diagnostic record"


class D4SelectorV02Error(ValueError):
    """Public-boundary selector error with no controlled row identifiers."""


def _controlled_diagnostic(error: BaseException, *, failure_class: str) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "protocol_id": "PRE_G2_D4_SELECTOR_DIAGNOSTIC_CONTAINMENT_2026-09-10_v0.1",
        "failure_class": failure_class,
        "exception_type": type(error).__name__,
        "controlled_detail": str(error),
        "custody": "S3_CONTROLLED",
        "public_output_authority": false,
    }


def _write_controlled_diagnostic(path: Path | None, error: BaseException, *, failure_class: str) -> None:
    if path is None:
        return
    payload = _controlled_diagnostic(error, failure_class=failure_class)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_inputs(candidate_pool_path: Path, commitment_key_path: Path) -> tuple[dict[str, Any], bytes]:
    pool = json.loads(candidate_pool_path.read_text(encoding="utf-8"))
    if not isinstance(pool, dict):
        raise D4SelectionError("candidate-pool root must be an object")
    commitment_key = commitment_key_path.read_bytes()
    if not commitment_key:
        raise D4SelectionError("commitment key file must not be empty")
    return pool, commitment_key


def run_selector(
    candidate_pool_path: Path,
    commitment_key_path: Path,
    *,
    controlled_output: Path | None = None,
    controlled_error_output: Path | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    """Execute v0.1 selection semantics with a fail-closed diagnostic boundary.

    Detailed v0.1 exceptions may contain S3 candidate identifiers. They are never
    returned through the public message. If explicitly configured, the original
    detail is written only to the controlled diagnostic path.
    """

    try:
        pool, commitment_key = _load_inputs(candidate_pool_path, commitment_key_path)
        controlled, aggregate = select_candidates(pool, commitment_key)
        if controlled_output is not None:
            controlled_output.write_text(
                json.dumps(controlled, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return SUCCESS, aggregate, ""
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, D4SelectionError) as exc:
        try:
            _write_controlled_diagnostic(
                controlled_error_output,
                exc,
                failure_class="CONTROLLED_INPUT_OR_SELECTION_FAILURE",
            )
        except OSError:
            pass
        return CONTROLLED_INPUT_FAILURE, None, PUBLIC_CONTROLLED_FAILURE
    except Exception as exc:  # fail closed at the public diagnostic boundary
        try:
            _write_controlled_diagnostic(
                controlled_error_output,
                exc,
                failure_class="UNEXPECTED_INTERNAL_FAILURE",
            )
        except OSError:
            pass
        return UNEXPECTED_INTERNAL_FAILURE, None, PUBLIC_INTERNAL_FAILURE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PRE-G2 D4 deterministic selector v0.2 diagnostic-containment entrypoint"
    )
    parser.add_argument("candidate_pool", type=Path)
    parser.add_argument("--commitment-key-file", type=Path, required=True)
    parser.add_argument(
        "--controlled-output",
        type=Path,
        default=None,
        help="Explicit S3 path for the selected membership payload. Candidate IDs are never printed publicly.",
    )
    parser.add_argument(
        "--controlled-error-output",
        type=Path,
        default=None,
        help="Optional explicit S3 path for detailed failure diagnostics. Do not place this file on a public surface.",
    )
    args = parser.parse_args()

    status, aggregate, public_message = run_selector(
        args.candidate_pool,
        args.commitment_key_file,
        controlled_output=args.controlled_output,
        controlled_error_output=args.controlled_error_output,
    )
    if status != SUCCESS:
        print(public_message)
        return status
    assert aggregate is not None
    print(json.dumps(aggregate, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
