from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_pre_g2_d4_pilot_readiness_aggregate_v0_2 import (
    build_pilot_readiness_aggregate,
)
from scripts.evaluate_pre_g2_d4_pilot_readiness_v0_3 import (
    evaluate_pilot_readiness,
)
from scripts.execute_pre_g2_d4_final_selection_v0_3 import (
    EXECUTION_TYPE,
    PUBLIC_CONTROLLED_FAILURE,
    run_composed_selection,
)
from tests.test_pre_g2_d4_calibration_selection_composition_v0_2 import (
    _disposition,
    _envelope,
)
from tests.test_pre_g2_d4_pilot_execution import (
    PILOT_KEY,
    POOL_KEY,
    _attestation,
    _candidate_pool,
    _write_pilot,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _prepare(root: Path) -> dict[str, object]:
    manifest, _ = _write_pilot(root)
    packet_root = root / "packets"
    aggregate = build_pilot_readiness_aggregate(
        manifest,
        packet_root,
        PILOT_KEY,
    )
    readiness = evaluate_pilot_readiness(aggregate)
    disposition = _disposition(manifest, aggregate, readiness)
    pool = _candidate_pool()
    attestation = _attestation(manifest, pool)
    envelope = _envelope(manifest, disposition, pool, attestation)

    paths = {
        "manifest": root / "manifest.json",
        "disposition": root / "disposition.json",
        "envelope": root / "envelope.json",
        "pool": root / "pool.json",
        "attestation": root / "attestation.json",
        "pilot_key": root / "pilot.key",
        "pool_key": root / "pool.key",
        "controlled": root / "controlled" / "selection.json",
        "error": root / "controlled" / "error.json",
    }
    _write_json(paths["manifest"], manifest)
    _write_json(paths["disposition"], disposition)
    _write_json(paths["envelope"], envelope)
    _write_json(paths["pool"], pool)
    _write_json(paths["attestation"], attestation)
    paths["pilot_key"].write_bytes(PILOT_KEY)
    paths["pool_key"].write_bytes(POOL_KEY)
    return {
        "packet_root": packet_root,
        "aggregate": aggregate,
        "readiness": readiness,
        "paths": paths,
    }


def _run(fixture: dict[str, object]) -> tuple[int, dict[str, object] | None, str]:
    paths = fixture["paths"]
    return run_composed_selection(
        pilot_manifest_path=paths["manifest"],
        packet_root=fixture["packet_root"],
        pilot_key_path=paths["pilot_key"],
        calibration_disposition_path=paths["disposition"],
        authorization_envelope_path=paths["envelope"],
        candidate_pool_path=paths["pool"],
        candidate_pool_key_path=paths["pool_key"],
        identity_namespace_attestation_path=paths["attestation"],
        controlled_output=paths["controlled"],
        controlled_error_output=paths["error"],
    )


class D4CalibrationSelectionCompositionV03Tests(unittest.TestCase):
    def test_valid_composed_execution_binds_matrix_successor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare(Path(tmp))
            status, public, message = _run(fixture)
            self.assertEqual(status, 0)
            self.assertEqual(message, "")
            self.assertIsNotNone(public)
            assert public is not None
            self.assertEqual(public["execution_type"], EXECUTION_TYPE)
            self.assertEqual(
                public["pilot_readiness_aggregate_sha256"],
                fixture["paths"]["disposition"]
                and json.loads(
                    fixture["paths"]["disposition"].read_text(encoding="utf-8")
                )["pilot_readiness_aggregate_sha256"],
            )
            self.assertIn(
                "primary_secondary_confusion_matrix",
                fixture["aggregate"],
            )
            self.assertTrue(
                fixture["readiness"][
                    "full_confusion_matrix_required_for_human_calibration"
                ]
            )
            self.assertFalse(public["g2_passed"])

    def test_short_pilot_key_fails_at_successor_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare(Path(tmp))
            fixture["paths"]["pilot_key"].write_bytes(b"k" * 31)
            status, public, message = _run(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)

    def test_short_candidate_pool_key_fails_at_successor_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _prepare(Path(tmp))
            fixture["paths"]["pool_key"].write_bytes(b"k" * 31)
            status, public, message = _run(fixture)
            self.assertEqual(status, 1)
            self.assertIsNone(public)
            self.assertEqual(message, PUBLIC_CONTROLLED_FAILURE)


if __name__ == "__main__":
    unittest.main()
