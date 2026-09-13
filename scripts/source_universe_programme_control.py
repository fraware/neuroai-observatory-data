#!/usr/bin/env python3
"""Shared validation for the current noncanonical Source-universe programme control.

This module validates only programme-planning invariants and declared stream identity.
It does not infer Source truth, domain completeness, canonical admission, publication
authority, or assessment effects.
"""

from __future__ import annotations

from typing import Any

REQUIRED_PROGRAMME_INVARIANTS = {
    "DISCOVERY_RESULT_IS_NOT_CANONICAL_SOURCE",
    "SOURCE_IDENTITY_ACCEPTANCE_REQUIRES_HUMAN_DISPOSITION",
    "MECHANICAL_COMPLETION_IS_NOT_DOMAIN_COMPLETENESS",
    "NO_SILENT_CANONICAL_MUTATION",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_source_universe_stream(
    control: dict[str, Any],
    stream_id: str,
) -> dict[str, Any]:
    """Return one exact declared stream after validating current planning boundaries."""
    _require(
        control.get("control_id") == "NEUROAI-SOURCE-UNIVERSE-EXPANSION-v0.1",
        "Unexpected Source-universe planning control",
    )
    _require(
        control.get("status") == "NONCANONICAL_PLANNING_CONTROL",
        "Source-universe expansion control must remain noncanonical",
    )
    invariants = set(control.get("programme_invariants") or [])
    missing = sorted(REQUIRED_PROGRAMME_INVARIANTS - invariants)
    _require(not missing, f"Missing source-universe programme invariants: {missing}")
    streams = control.get("streams")
    _require(isinstance(streams, list), "Source-universe planning control must contain streams")
    matches = [
        row
        for row in streams
        if isinstance(row, dict) and row.get("stream_id") == stream_id
    ]
    _require(len(matches) == 1, f"Expected exactly one {stream_id} stream")
    state = matches[0].get("state")
    _require(isinstance(state, str) and bool(state.strip()), f"{stream_id}: state is required")
    return matches[0]
