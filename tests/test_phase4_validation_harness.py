from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_phase4_validation as validation


class RuntimeContractTests(unittest.TestCase):
    def test_accepts_exact_runtime_contract(self) -> None:
        validation._validate_runtime((3, 12), "4.26.0")

    def test_rejects_wrong_python_minor(self) -> None:
        with self.assertRaises(validation.ValidationError):
            validation._validate_runtime((3, 13), "4.26.0")

    def test_rejects_wrong_jsonschema_version(self) -> None:
        with self.assertRaises(validation.ValidationError):
            validation._validate_runtime((3, 12), "4.25.1")


class CommitIdentityTests(unittest.TestCase):
    def test_normalizes_full_commit_sha(self) -> None:
        value = "A" * 40
        self.assertEqual(validation._validate_expected_commit(value), "a" * 40)

    def test_rejects_abbreviated_commit_sha(self) -> None:
        with self.assertRaises(validation.ValidationError):
            validation._validate_expected_commit("abc123")

    def test_rejects_non_hex_commit_sha(self) -> None:
        with self.assertRaises(validation.ValidationError):
            validation._validate_expected_commit("z" * 40)


class EvidenceDirectoryTests(unittest.TestCase):
    def test_rejects_evidence_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            with self.assertRaises(validation.ValidationError):
                validation._require_external_empty_evidence_dir(repo, repo / "evidence")

    def test_rejects_non_empty_external_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            evidence = root / "evidence"
            repo.mkdir()
            evidence.mkdir()
            (evidence / "existing.txt").write_text("occupied\n", encoding="utf-8")
            with self.assertRaises(validation.ValidationError):
                validation._require_external_empty_evidence_dir(repo, evidence)

    def test_accepts_empty_external_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            evidence = root / "evidence"
            repo.mkdir()
            resolved = validation._require_external_empty_evidence_dir(repo, evidence)
            self.assertEqual(resolved, evidence.resolve())
            self.assertTrue(evidence.is_dir())


class FrozenPlanTests(unittest.TestCase):
    @staticmethod
    def valid_plan() -> dict[str, object]:
        return {
            "plan_id": validation.EXPECTED_PLAN_ID,
            "plan_sha256": validation.EXPECTED_PLAN_SHA256,
            "unit_count": validation.EXPECTED_UNIT_COUNT,
            "provider_counts": dict(validation.EXPECTED_PROVIDER_COUNTS),
        }

    def test_accepts_exact_frozen_plan_identity(self) -> None:
        self.assertEqual(validation._validate_frozen_plan(self.valid_plan()), self.valid_plan())

    def test_rejects_plan_sha_drift(self) -> None:
        plan = self.valid_plan()
        plan["plan_sha256"] = "0" * 64
        with self.assertRaises(validation.ValidationError):
            validation._validate_frozen_plan(plan)

    def test_rejects_provider_count_drift(self) -> None:
        plan = self.valid_plan()
        plan["provider_counts"] = {"CROSSREF": 383, "EUROPE_PMC": 384}
        with self.assertRaises(validation.ValidationError):
            validation._validate_frozen_plan(plan)

    def test_load_frozen_plan_rejects_non_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps([]), encoding="utf-8")
            with self.assertRaises(validation.ValidationError):
                validation._load_frozen_plan(path)


class EvidenceHashTests(unittest.TestCase):
    def test_report_digest_is_deterministic(self) -> None:
        basis = {
            "schema_version": validation.SCHEMA_VERSION,
            "status": "PASS",
            "steps": [],
        }
        first = validation._finalize_report(dict(basis))
        second = validation._finalize_report(dict(basis))
        self.assertEqual(first["validation_sha256"], second["validation_sha256"])
        self.assertEqual(first["validation_id"], second["validation_id"])

    def test_unittest_count_extraction(self) -> None:
        stderr = b"................................\nRan 97 tests in 1.234s\n\nOK\n"
        self.assertEqual(validation._extract_unittest_count(stderr), 97)

    def test_unittest_count_absent_returns_none(self) -> None:
        self.assertIsNone(validation._extract_unittest_count(b"no test summary here\n"))


if __name__ == "__main__":
    unittest.main()
