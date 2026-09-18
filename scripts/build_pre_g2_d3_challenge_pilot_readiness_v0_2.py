from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts import build_pre_g2_d3_challenge_pilot_readiness as predecessor

D3ChallengePilotExecutionError = predecessor.D3ChallengePilotExecutionError
PUBLIC_CONTROLLED_FAILURE = predecessor.PUBLIC_CONTROLLED_FAILURE
PUBLIC_INTERNAL_FAILURE = predecessor.PUBLIC_INTERNAL_FAILURE
PROTOCOL_ID = predecessor.PROTOCOL_ID
MIN_COMMITMENT_KEY_BYTES = 32


def _require_strong_commitment_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) < MIN_COMMITMENT_KEY_BYTES:
        raise D3ChallengePilotExecutionError(
            "pilot membership commitment key must contain at least 32 bytes"
        )


def derive_readiness_aggregate(
    manifest: dict[str, Any],
    packet_root: Path,
    commitment_key: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the append-only key-strength guard, then reuse historical D3 semantics."""

    _require_strong_commitment_key(commitment_key)
    return predecessor.derive_readiness_aggregate(
        manifest,
        packet_root,
        commitment_key,
    )


def run_builder(
    manifest_path: Path,
    packet_root: Path,
    key_path: Path,
    *,
    controlled_aggregate_output: Path | None = None,
    controlled_error_output: Path | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    """Run the historical builder only after enforcing the successor key floor."""

    try:
        key = key_path.read_bytes()
        _require_strong_commitment_key(key)
    except (OSError, D3ChallengePilotExecutionError):
        return 1, None, PUBLIC_CONTROLLED_FAILURE

    return predecessor.run_builder(
        manifest_path,
        packet_root,
        key_path,
        controlled_aggregate_output=controlled_aggregate_output,
        controlled_error_output=controlled_error_output,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Derive PRE-G2 D3 challenge pilot readiness under the "
            "append-only >=32-byte HMAC-key successor"
        )
    )
    parser.add_argument("pilot_manifest", type=Path)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--pilot-commitment-key-file", type=Path, required=True)
    parser.add_argument("--controlled-aggregate-output", type=Path, default=None)
    parser.add_argument("--controlled-error-output", type=Path, default=None)
    args = parser.parse_args()

    status, result, public_message = run_builder(
        args.pilot_manifest,
        args.packet_root,
        args.pilot_commitment_key_file,
        controlled_aggregate_output=args.controlled_aggregate_output,
        controlled_error_output=args.controlled_error_output,
    )
    if result is None:
        print(public_message)
        return status
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
