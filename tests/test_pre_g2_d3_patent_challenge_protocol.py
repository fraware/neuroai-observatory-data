from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

PROTOCOL_PATH = Path("curation/PRE_G2_D3_PATENT_CHALLENGE_PROTOCOL_2026-09-11_v0.1.json")
SCHEMA_PATH = Path("schemas/pre-g2-d3-patent-review-packet-v0.1.schema.json")


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


class D3PatentChallengeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_protocol_identity_and_governing_bindings_are_exact(self) -> None:
        self.assertEqual(self.protocol["schema_version"], "0.1.0")
        self.assertEqual(
            self.protocol["control_id"],
            "PRE_G2_D3_PATENT_CHALLENGE_PROTOCOL_2026-09-11_v0.1",
        )
        self.assertEqual(self.protocol["governing_issue"], 234)
        self.assertEqual(self.protocol["umbrella_d3_issue"], 222)
        self.assertEqual(self.protocol["baseline_a_audit_issue"], 220)
        self.assertEqual(self.protocol["patstat_rights_issue"], 210)
        self.assertEqual(
            self.protocol["parent_main_binding"]["main_commit_sha"],
            "955b9e86886f11bba588bb97a5850b6ac59d7e65",
        )
        semantics = self.protocol["governing_semantics"]
        self.assertEqual(
            semantics["d1_canonical_json_sha256"],
            "7d270002094dcdecb703d5b70ef2268e4869005c284ffd98db3eb936641a78cb",
        )
        self.assertEqual(
            semantics["d2_canonical_json_sha256"],
            "bd9451a5084485ef7a36251b0bc39d486fe0c2174636171a29ec03d7010cbf1d",
        )
        self.assertEqual(
            semantics["g1_disposition_sha256"],
            "ed6489fe1085b5aec1b594970dd1c574b57bd6bbd25a659643e9bd1b7b72d8ef",
        )

    def test_workbench_contract_binding_is_exact(self) -> None:
        binding = self.protocol["workbench_contract_binding"]
        self.assertEqual(binding["commit_sha"], "854cc9d1c8e24a9e8ae8b21d871329bc3c24c118")
        self.assertEqual(
            binding["patent_public_contract_git_blob_sha"],
            "d60bac3f7fec00575fd4f2e68e6833d83a8c390e",
        )
        self.assertEqual(
            binding["evaluation_evidence_roles_git_blob_sha"],
            "a79c92dd3c3419ef97b38c62fea8b850b6f02c23",
        )
        self.assertEqual(binding["benchmark_id"], "PRE_G2_PATENT_V0_1")
        self.assertEqual(binding["public_contract_schema_version"], "0.2")
        self.assertEqual(binding["evaluation_plan_schema_version"], "0.1")
        self.assertEqual(binding["evidence_binding_schema_version"], "0.3")

    def test_local_artifacts_are_exactly_blob_bound(self) -> None:
        for name, binding in self.protocol["local_artifact_bindings"].items():
            with self.subTest(name=name):
                path = Path(binding["path"])
                self.assertTrue(path.is_file(), path)
                self.assertEqual(_git_blob_sha(path), binding["git_blob_sha"], path)

    def test_challenge_role_cannot_create_population_inference(self) -> None:
        role = self.protocol["statistical_evidence_role"]
        self.assertEqual(role["role"], "CHALLENGE_CONSTRUCT_COVERAGE")
        self.assertEqual(role["sampling_design_type"], "NONPROBABILITY_CHALLENGE")
        self.assertFalse(role["population_generalizable"])
        self.assertEqual(role["component_pooling_policy"], "NO_CROSS_ROLE_POOLING")
        self.assertIsNone(role["population_frame_id"])
        self.assertIsNone(role["inclusion_probability_manifest_sha256"])
        self.assertIsNone(role["estimator_id"])
        self.assertIsNone(role["uncertainty_method_id"])
        self.assertFalse(role["prevalence_reporting_allowed"])
        self.assertFalse(role["patent_population_total_reporting_allowed"])
        self.assertFalse(role["population_recall_reporting_allowed"])
        self.assertFalse(role["global_completeness_reporting_allowed"])

    def test_probability_audit_remains_explicitly_unimplemented(self) -> None:
        boundary = self.protocol["separate_probability_audit_boundary"]
        self.assertEqual(boundary["status"], "NOT_IMPLEMENTED_BY_THIS_PROTOCOL")
        self.assertFalse(boundary["roman_baseline_a_second_stage_estimator_certified"])
        self.assertFalse(boundary["roman_reported_population_estimates_validated"])
        self.assertFalse(boundary["roman_reported_query_recall_validated"])
        self.assertFalse(boundary["may_inherit_generalizability_from_challenge_component"])

    def test_baseline_a_model_labels_never_become_reference_truth(self) -> None:
        boundary = self.protocol["baseline_a_use_boundary"]
        self.assertEqual(boundary["role"], "SAMPLING_AND_CANDIDATE_DISCOVERY_ASSET_ONLY")
        self.assertFalse(boundary["historical_model_labels_may_be_human_reference_standard"])
        self.assertFalse(boundary["historical_model_labels_visible_to_reviewers"])
        self.assertFalse(boundary["gold_labels_csv_is_human_gold"])
        self.assertTrue(boundary["historical_borderline_is_not_d1_exclude"])

    def test_required_strata_match_workbench_patent_contract(self) -> None:
        self.assertEqual(
            set(self.protocol["required_construct_strata"]),
            {
                "GRAY_CAPABILITY",
                "MISSING_OR_SHORT_ABSTRACT",
                "MULTI_JURISDICTION",
                "MULTI_YEAR",
                "MULTILINGUAL",
                "SEMANTICALLY_DECEPTIVE_NEGATIVE",
            },
        )
        schema_strata = set(
            self.schema["$defs"]["stratum"]["enum"]
        )
        self.assertEqual(schema_strata, set(self.protocol["required_construct_strata"]))

    def test_schema_is_s3_and_non_authorizing(self) -> None:
        self.assertFalse(self.schema.get("examples"))
        props = self.schema["properties"]
        self.assertEqual(props["benchmark_id"]["const"], "PRE_G2_PATENT_V0_1")
        self.assertEqual(props["evidence_role"]["const"], "CHALLENGE_CONSTRUCT_COVERAGE")
        rights = self.schema["$defs"]["rights_containment"]["properties"]
        self.assertEqual(rights["packet_custody"]["const"], "S3_CONTROLLED")
        self.assertFalse(rights["patstat_rights_clearance"]["const"])
        self.assertFalse(rights["redistribution_authority_claimed"]["const"])
        authority = self.schema["$defs"]["authority"]["properties"]
        for key in (
            "g2_passed",
            "benchmark_adequacy_established",
            "population_generalization_authority",
            "canonical_s2_authority",
            "publication_authority",
        ):
            self.assertFalse(authority[key]["const"], key)
        self.assertEqual(authority["assessment_effect"]["const"], "NONE")

    def test_sample_size_is_deliberately_unset(self) -> None:
        boundary = self.protocol["sample_size_boundary"]
        self.assertIsNone(boundary["real_challenge_final_n"])
        self.assertIsNone(boundary["minimum_per_stratum_counts"])
        self.assertFalse(boundary["sample_size_claim_created"])

    def test_authority_remains_fail_closed(self) -> None:
        authority = self.protocol["authority"]
        self.assertTrue(authority["g1_approved"])
        for key in (
            "g0_passed",
            "g2_passed",
            "g5_passed",
            "rights_clearance",
            "benchmark_adequacy_established",
            "population_generalization_authority",
            "canonical_s2_authority",
            "publication_authority",
            "phase4_online_first_default_authorized",
        ):
            self.assertFalse(authority[key], key)
        self.assertEqual(authority["assessment_effect"], "NONE")

        evidence = self.protocol["current_evidence_state"]
        self.assertFalse(evidence["real_challenge_membership_selected"])
        self.assertFalse(evidence["real_human_labels_created"])
        self.assertFalse(evidence["real_d3_frozen"])
        self.assertFalse(evidence["probability_audit_implemented"])
        self.assertFalse(evidence["benchmark_adequacy_established"])


if __name__ == "__main__":
    unittest.main()
