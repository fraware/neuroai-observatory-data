from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.build_pre_g2_d4_pilot_readiness_aggregate import (
    D4PilotExecutionError,
    build_pilot_readiness_aggregate as build_predecessor_aggregate,
    load_validated_pilot_packets,
)
from scripts.evaluate_pre_g2_d4_pilot_readiness_v0_3 import (
    DISPOSITIONS,
    D4PilotReadinessV03Error,
    evaluate_pilot_readiness,
)


def _derive_primary_secondary_confusion_matrix(
    packets: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    matrix = {
        primary: {secondary: 0 for secondary in DISPOSITIONS}
        for primary in DISPOSITIONS
    }
    for packet in packets:
        by_role = {
            record["adjudicator_role"]: record
            for record in packet["reviewer_records"]
        }
        primary = by_role["PRIMARY_REVIEWER"]["decision"]
        secondary = by_role["SECONDARY_REVIEWER"]["decision"]
        matrix[primary][secondary] += 1
    return matrix


def build_pilot_readiness_aggregate(
    manifest: dict[str, Any],
    packet_root: Path,
    commitment_key: bytes,
) -> dict[str, Any]:
    """Build the D4 v0.3-ready aggregate without mutating historical v0.1 evidence.

    Historical aggregation remains intact. The successor revalidates the exact
    controlled packets, derives the governance-mandated full PRIMARY x SECONDARY
    four-way matrix from those same packets, and validates the extended aggregate
    under the v0.3 readiness contract.
    """

    if not isinstance(commitment_key, bytes) or len(commitment_key) < 32:
        raise D4PilotExecutionError(
            "pilot membership commitment key must contain at least 32 bytes"
        )

    aggregate = build_predecessor_aggregate(manifest, packet_root, commitment_key)
    packets, _ = load_validated_pilot_packets(
        manifest,
        packet_root,
        commitment_key,
    )
    successor = {
        **aggregate,
        "primary_secondary_confusion_matrix": (
            _derive_primary_secondary_confusion_matrix(packets)
        ),
    }
    evaluate_pilot_readiness(successor)
    return successor


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Derive the PRE-G2 D4 pilot aggregate with the full 4x4 "
            "PRIMARY x SECONDARY confusion matrix"
        )
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--commitment-key-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise D4PilotExecutionError("manifest root must be an object")
        commitment_key = args.commitment_key_file.read_bytes()
        aggregate = build_pilot_readiness_aggregate(
            manifest,
            args.packet_root,
            commitment_key,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        D4PilotExecutionError,
        D4PilotReadinessV03Error,
        ValueError,
    ) as exc:
        print(f"INVALID: {exc}")
        return 1
    print(json.dumps(aggregate, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
