from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "curation" / "PATSTAT_BASELINE_A_ROMAN_RESPONSE_EVIDENCE_2026-09-17_v0.1.json"
STATUS = ROOT / "curation" / "PATSTAT_BASELINE_A_PROVENANCE_INTAKE_STATUS_2026-09-17_ROMAN_RESPONSE_v0.1.json"
CONTROL = ROOT / "curation" / "PATSTAT_BASELINE_A_PROVENANCE_INTAKE_CONTROL_2026-09-17_ROMAN_RESPONSE_v0.1.json"
EVIDENCE_SHA256 = "a180f37ec27d0dc4fa74c9e6f72fcb6609bc9103ed2b15d43b17bc3cb79b6c51"


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


class PatstatBaselineARomanResponseIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))
        cls.control = json.loads(CONTROL.read_text(encoding="utf-8"))

    def test_response_manifest_is_exactly_sha256_bound(self) -> None:
        self.assertEqual(hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(), EVIDENCE_SHA256)
        self.assertEqual(self.status["response_binding"]["controlled_response_sha256"], EVIDENCE_SHA256)
        self.assertEqual(self.status["response_binding"]["state"], "RESPONSE_RECEIVED")
        self.assertIn("bb6df60f31e76936fa9957bbac545994b96b2e34", self.status["response_binding"]["source_ref"])

    def test_response_source_files_are_exact_git_blob_bindings(self) -> None:
        for binding in self.evidence["source_files"]:
            path = ROOT / binding["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(_git_blob_sha(path), binding["git_blob_sha"], path)

    def test_partial_evidence_map_matches_status_true_flags(self) -> None:
        for component_id, component in self.status["components"].items():
            supported = set(self.evidence["supported_requirements"][component_id])
            actual = {key for key, present in component["required_evidence"].items() if present}
            self.assertEqual(actual, supported, component_id)
            self.assertEqual(component["state"], "MISSING", component_id)
            self.assertEqual(component["evidence_manifest_sha256"], EVIDENCE_SHA256, component_id)
            self.assertIsNone(component["independent_verification_sha256"], component_id)

    def test_response_does_not_promote_audit_readiness_or_scientific_authority(self) -> None:
        self.assertEqual(self.status["declared_readiness"], "WAITING_FOR_PROVENANCE")
        self.assertTrue(self.control["current_evidence_state"]["roman_response_received_and_bound"])
        self.assertFalse(self.control["current_evidence_state"]["ready_for_scientific_audit"])
        self.assertFalse(self.control["current_evidence_state"]["scientific_validity_established"])
        for key in (
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "rights_clearance",
            "canonical_scientific_finding",
            "benchmark_adequacy_established",
            "population_generalization_authority",
            "canonical_s2_authority",
            "publication_authority",
            "phase4_online_first_default_authorized",
        ):
            self.assertFalse(self.control["authority"][key], key)
        self.assertEqual(self.control["authority"]["assessment_effect"], "NONE")

    def test_control_artifact_bindings_are_exact(self) -> None:
        for name, binding in self.control["artifact_bindings"].items():
            with self.subTest(name=name):
                path = ROOT / binding["path"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(_git_blob_sha(path), binding["git_blob_sha"], path)

    def test_reported_interval_conflict_remains_explicit(self) -> None:
        findings = "\n".join(self.evidence["unresolved_findings"])
        self.assertIn("[41,512, 58,192]", findings)
        self.assertIn("[40,256, 57,854]", findings)
        self.assertFalse(self.status["fixed_scientific_boundaries"]["reported_interval_validated"])
        self.assertFalse(self.status["fixed_scientific_boundaries"]["roman_49671_validated"])
        self.assertFalse(self.status["fixed_scientific_boundaries"]["roman_67_percent_retrieval_recall_validated"])


if __name__ == "__main__":
    unittest.main()
