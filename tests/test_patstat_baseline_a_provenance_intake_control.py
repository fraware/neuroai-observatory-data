from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

CONTROL_PATH = Path(
    "curation/PATSTAT_BASELINE_A_PROVENANCE_INTAKE_CONTROL_2026-09-12_v0.1.json"
)


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


class PatstatBaselineAProvenanceIntakeControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.control = json.loads(
            CONTROL_PATH.read_text(encoding="utf-8")
        )

    def test_identity_and_issue_bindings(self) -> None:
        self.assertEqual(
            self.control["control_id"],
            "PATSTAT_BASELINE_A_PROVENANCE_INTAKE_CONTROL_2026-09-12_v0.1",
        )
        self.assertEqual(self.control["status"], "WAITING_FOR_PROVENANCE")
        self.assertEqual(self.control["governing_issue"], 243)
        self.assertEqual(self.control["baseline_audit_issue"], 220)
        self.assertEqual(self.control["d3_umbrella_issue"], 222)
        self.assertEqual(self.control["rights_issue"], 210)
        self.assertEqual(
            self.control["created_against_main_sha"],
            "8d780ae2276f23ab9091bca94fb7f33a7d666e3d",
        )

    def test_all_artifacts_are_exactly_blob_bound(self) -> None:
        for name, binding in self.control["artifact_bindings"].items():
            with self.subTest(name=name):
                path = Path(binding["path"])
                self.assertTrue(path.is_file(), path)
                self.assertEqual(
                    _git_blob_sha(path),
                    binding["git_blob_sha"],
                    path,
                )

    def test_current_evidence_state_is_explicitly_waiting(self) -> None:
        for key, value in self.control[
            "current_evidence_state"
        ].items():
            with self.subTest(key=key):
                self.assertFalse(value)

    def test_intake_readiness_is_not_scientific_validation(self) -> None:
        boundary = self.control["intake_boundary"]
        self.assertEqual(
            boundary["ready_for_scientific_audit_means"],
            "ALL_MANDATORY_PROVENANCE_COMPONENTS_SUPPLIED_AND_DIGEST_BOUND_ONLY",
        )
        self.assertTrue(
            boundary[
                "verified_reconstructible_requires_independent_verification_digest"
            ]
        )
        for key in (
            "provided_by_original_author_implies_verified_reconstructible",
            "intake_completeness_implies_design_unbiasedness",
            "intake_completeness_implies_interval_validity",
            "intake_completeness_implies_human_truth",
            "intake_completeness_implies_global_completeness",
            "intake_completeness_implies_rights_clearance",
        ):
            self.assertFalse(boundary[key], key)

    def test_authority_remains_fail_closed(self) -> None:
        authority = self.control["authority"]
        self.assertTrue(authority["g1_approved"])
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
            self.assertFalse(authority[key], key)
        self.assertEqual(authority["assessment_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
