from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


acquisition = _load_module(
    "acquire_science_candidates",
    SCRIPTS / "acquire_science_candidates.py",
)
sys.modules["acquire_science_candidates"] = acquisition
preflight = _load_module(
    "preflight_science_custody",
    SCRIPTS / "preflight_science_custody.py",
)


class Clock:
    def __init__(self):
        self.second = 0

    def __call__(self) -> str:
        value = f"2026-08-25T09:20:{self.second:02d}Z"
        self.second += 1
        return value


class ScienceCustodyPreflightTests(unittest.TestCase):
    def test_prepare_and_fresh_process_verification_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custody"
            clock = Clock()
            manifest = preflight.prepare_preflight(
                root,
                payload_size=1024,
                clock_fn=clock,
            )

            report = preflight.verify_persistence(
                root,
                manifest["preflight_id"],
                clock_fn=clock,
            )

            self.assertEqual(
                report["status"],
                "PERSISTENCE_AND_EXACT_BYTES_VERIFIED_IN_CURRENT_PROCESS",
            )
            self.assertEqual(len(report["verified_files"]), 3)
            self.assertTrue(
                (
                    root
                    / preflight.PREFLIGHT_DIRNAME
                    / manifest["preflight_id"]
                    / preflight.PERSISTENCE_REPORT_NAME
                ).is_file()
            )

    def test_compare_restore_requires_byte_identical_manifest_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            primary = base / "primary"
            restored = base / "restored"
            clock = Clock()
            manifest = preflight.prepare_preflight(primary, clock_fn=clock)
            shutil.copytree(primary, restored)

            report = preflight.compare_restore(
                primary,
                restored,
                manifest["preflight_id"],
                clock_fn=clock,
            )

            self.assertEqual(
                report["status"],
                "RESTORE_PATHS_AND_EXACT_BYTES_MATCH_PRIMARY",
            )

    def test_tampered_restored_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            primary = base / "primary"
            restored = base / "restored"
            manifest = preflight.prepare_preflight(primary, clock_fn=Clock())
            shutil.copytree(primary, restored)
            payload = (
                restored
                / preflight.PREFLIGHT_DIRNAME
                / manifest["preflight_id"]
                / "payload.bin"
            )
            payload.write_bytes(payload.read_bytes() + b"tamper")

            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                preflight.compare_restore(
                    primary,
                    restored,
                    manifest["preflight_id"],
                    clock_fn=Clock(),
                )

    def test_repository_path_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "acquisition output must remain outside the Git repository",
        ):
            preflight.prepare_preflight(
                ROOT / "should-never-be-created",
                clock_fn=Clock(),
            )


if __name__ == "__main__":
    unittest.main()
