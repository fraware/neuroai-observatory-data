from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

PROTOCOL_PATH = Path("curation/PRE_G2_D4_SELECTOR_DIAGNOSTIC_CONTAINMENT_2026-09-10_v0.1.json")


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


class D4SelectorDiagnosticProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))

    def test_protocol_identity_and_parent_main_are_exact(self) -> None:
        self.assertEqual(self.protocol["schema_version"], "0.1.0")
        self.assertEqual(
            self.protocol["protocol_id"],
            "PRE_G2_D4_SELECTOR_DIAGNOSTIC_CONTAINMENT_2026-09-10_v0.1",
        )
        self.assertEqual(self.protocol["governing_issue"], 232)
        self.assertEqual(
            self.protocol["parent_main_binding"]["main_commit_sha"],
            "9105aae4b36e8e03f71ffa76e9c7656ea8dd3570",
        )

    def test_parent_and_successor_artifacts_are_exactly_blob_bound(self) -> None:
        for binding in self.protocol["parent_artifact_bindings"].values():
            path = Path(binding["path"])
            self.assertTrue(path.is_file(), path)
            self.assertEqual(_git_blob_sha(path), binding["git_blob_sha"], path)

        for binding in self.protocol["successor_artifact_binding"].values():
            path = Path(binding["path"])
            self.assertTrue(path.is_file(), path)
            self.assertEqual(_git_blob_sha(path), binding["git_blob_sha"], path)

    def test_successor_preserves_selection_semantics_and_changes_only_diagnostic_boundary(self) -> None:
        contract = self.protocol["semantic_contract"]
        self.assertEqual(contract["selection_semantics_source"], "V0_1_SELECT_CANDIDATES_UNCHANGED")
        self.assertFalse(contract["selection_arithmetic_changed"])
        self.assertFalse(contract["candidate_pool_commitment_semantics_changed"])
        self.assertFalse(contract["selected_membership_semantics_changed"])
        self.assertFalse(contract["aggregate_summary_semantics_changed"])
        self.assertEqual(contract["public_failure_detail_policy"], "FIXED_GENERIC_MESSAGES_ONLY")
        self.assertTrue(contract["path_validation_occurs_before_any_diagnostic_write"])
        self.assertTrue(contract["unexpected_exceptions_fail_closed"])

    def test_public_boundary_is_non_authorizing_and_runtime_custody_is_external(self) -> None:
        boundary = self.protocol["controlled_diagnostic_boundary"]
        for key in (
            "candidate_ids_publicly_permitted",
            "membership_ids_publicly_permitted",
            "evidence_refs_publicly_permitted",
            "reviewer_refs_publicly_permitted",
            "hmac_keys_publicly_permitted",
            "controlled_detail_publicly_permitted",
            "standalone_v0_1_real_s3_cli_approved",
            "v0_2_real_s3_cli_approved_by_this_protocol",
        ):
            self.assertFalse(boundary[key], key)
        self.assertFalse(self.protocol["semantic_contract"]["runtime_path_custody_established_by_software"])

        authority = self.protocol["authority"]
        for key in (
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "benchmark_adequacy_established",
            "rights_clearance",
            "population_generalization_authority",
            "canonical_s2_authority",
            "publication_authority",
            "phase4_online_first_default_authorized",
        ):
            self.assertFalse(authority[key], key)
        self.assertEqual(authority["assessment_effect"], "NONE")

    def test_current_evidence_state_contains_no_real_selection_claim(self) -> None:
        evidence = self.protocol["current_evidence_state"]
        self.assertFalse(evidence["real_candidate_pool_selected"])
        self.assertFalse(evidence["real_final_membership_selected"])
        self.assertFalse(evidence["real_human_labels_created"])
        self.assertFalse(evidence["d4_frozen"])
        self.assertFalse(evidence["benchmark_adequacy_established"])


if __name__ == "__main__":
    unittest.main()
