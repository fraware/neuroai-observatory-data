from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "project_legacy_source_registration_impact.py"
SPEC = importlib.util.spec_from_file_location("project_legacy_source_registration_impact", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
impact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(impact)

MANIFEST_PATH = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"
SCHEMA_PATH = ROOT / "schemas" / "legacy-source-registration-proposals.schema.json"
POLICY_PATH = ROOT / "curation" / "source_namespace_eligibility_policy_v0.1.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _policy() -> dict[str, object]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


class LegacySourceRegistrationImpactTests(unittest.TestCase):
    def test_projection_derives_namespace_safe_joinability_ceiling(self) -> None:
        projection = impact.build_projection(
            _manifest(),
            policy=_policy(),
            manifest_sha256="a" * 64,
            policy_sha256="b" * 64,
        )
        current = projection["current_state"]
        candidates = projection["candidate_state"]
        scenario = projection["full_identity_safe_acceptance_scenario"]

        self.assertEqual(current["effective_source_count"], 248)
        self.assertEqual(current["assessment_evidence_count"], 52)
        self.assertEqual(current["deterministically_matched_evidence_count"], 15)
        self.assertEqual(current["unresolved_evidence_count"], 37)
        self.assertEqual(candidates["exact_key_candidate_evidence_count"], 35)
        self.assertEqual(candidates["source_namespace_eligible_exact_key_evidence_count"], 34)
        self.assertEqual(scenario["newly_joinable_evidence_count"], 35)
        self.assertEqual(scenario["projected_deterministically_matched_evidence_count"], 50)
        self.assertEqual(scenario["projected_unresolved_evidence_count"], 2)
        self.assertEqual(scenario["projected_joinability"], {"numerator": 50, "denominator": 52})
        self.assertEqual(scenario["projected_added_source_identity_count"], 33)
        self.assertEqual(scenario["projected_effective_source_count"], 281)
        self.assertEqual(scenario["canonical_status"], "SCENARIO_ONLY_NOT_CURRENT_CANONICAL_DATA")

    def test_projection_preserves_review_monitoring_and_policy_boundaries(self) -> None:
        projection = impact.build_projection(_manifest(), policy=_policy())
        self.assertEqual(projection["status"], "NONCANONICAL_PROJECTION")
        self.assertTrue(projection["scenario_only"])
        self.assertEqual(
            projection["source_manifest"]["interpretation"],
            "MECHANICAL_EXACT_IDENTITY_CANDIDATE_LAYER",
        )
        self.assertEqual(projection["source_namespace_policy"]["status"], "NONCANONICAL_POLICY")
        packet = projection["review_packet"]
        self.assertEqual(len(packet), 35)
        self.assertEqual(
            {row["review_disposition"] for row in packet},
            {"READY_FOR_IDENTITY_REVIEW", "CURATION_REQUIRED"},
        )
        self.assertTrue(all(row["monitoring_disposition"] == impact.MONITORING_DISPOSITION for row in packet))
        self.assertNotIn("APPROVED", {row["review_disposition"] for row in packet})
        self.assertNotIn("ACCEPTED", {row["review_disposition"] for row in packet})

    def test_only_prima_carries_a_requested_source_id(self) -> None:
        projection = impact.build_projection(_manifest(), policy=_policy())
        requested = [row for row in projection["review_packet"] if row["requested_source_id"]]
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0]["requested_source_id"], "SRC-PR-011")
        self.assertEqual(requested[0]["effective_action"], "REGISTER_MISSING_EXPLICIT_SOURCE")
        self.assertEqual(requested[0]["linked_evidence_ids"], ["EV-PR-011"])
        new_sources = [
            row for row in projection["review_packet"] if row["effective_action"] == "REGISTER_NEW_SOURCE"
        ]
        self.assertEqual(len(new_sources), 32)
        self.assertTrue(all(row["requested_source_id"] is None for row in new_sources))
        self.assertTrue(all(row["existing_source_id"] is None for row in new_sources))

    def test_two_assessment_local_records_remain_unresolved(self) -> None:
        projection = impact.build_projection(_manifest(), policy=_policy())
        remaining = projection["remaining_unresolved_evidence"]
        self.assertEqual(len(remaining), 2)
        observed = {(row["system"], row["evidence_id"], row["reason"]) for row in remaining}
        self.assertEqual(
            observed,
            {
                (
                    "BrainGate2 T15",
                    "EV-T15-012",
                    "ASSESSMENT_LOCAL_CONTROLLED_ADJUDICATION",
                ),
                (
                    "FDA adaptive DBS",
                    "EV-15",
                    "MECHANICAL_CURATION_REQUIRED",
                ),
            },
        )

    def test_controlled_adjudication_checksum_does_not_unlock_source_identity(self) -> None:
        projection = impact.build_projection(_manifest(), policy=_policy())
        row = next(row for row in projection["review_packet"] if row["linked_evidence_ids"] == ["EV-T15-012"])
        self.assertEqual(row["raw_action"], "REGISTER_NEW_SOURCE")
        self.assertEqual(row["effective_action"], "CURATION_REQUIRED")
        self.assertFalse(row["source_namespace_eligible"])
        self.assertEqual(row["review_disposition"], "CURATION_REQUIRED")
        self.assertEqual(row["projected_newly_joinable_evidence_count"], 0)
        self.assertEqual(row["projected_source_universe_delta"], 0)
        self.assertEqual(row["eligibility_reason"], "ASSESSMENT_LOCAL_CONTROLLED_ADJUDICATION")
        self.assertEqual(row["matched_ineligible_markers"], ["CONTROLLED ADJUDICATION"])
        self.assertTrue(row["checksum_is_provenance_only"])

    def test_braingate_nature_group_still_unlocks_three_evidence_rows_with_one_source_delta(self) -> None:
        projection = impact.build_projection(_manifest(), policy=_policy())
        row = next(
            row
            for row in projection["review_packet"]
            if set(row["linked_evidence_ids"]) == {"EV-T15-001", "EV-T15-009", "EV-T15-010"}
        )
        self.assertEqual(row["projected_newly_joinable_evidence_count"], 3)
        self.assertEqual(row["projected_source_universe_delta"], 1)
        self.assertEqual(row["review_disposition"], "READY_FOR_IDENTITY_REVIEW")
        self.assertTrue(row["source_namespace_eligible"])

    def test_effective_action_counts_are_policy_corrected(self) -> None:
        projection = impact.build_projection(_manifest(), policy=_policy())
        counts = projection["proposal_state"]["effective_action_counts"]
        self.assertEqual(
            counts,
            {
                "CURATION_REQUIRED": 2,
                "REGISTER_MISSING_EXPLICIT_SOURCE": 1,
                "REGISTER_NEW_SOURCE": 32,
            },
        )
        self.assertEqual(projection["proposal_state"]["identity_safe_proposal_count"], 33)
        self.assertEqual(projection["proposal_state"]["curation_required_proposal_count"], 2)

    def test_projection_rejects_duplicate_evidence_across_proposals(self) -> None:
        manifest = _manifest()
        duplicate = dict(manifest["proposals"][0]["linked_evidence"][0])
        manifest["proposals"][1]["linked_evidence"].append(duplicate)
        with self.assertRaisesRegex(impact.ProjectionError, "appears in more than one proposal"):
            impact.build_projection(manifest, policy=_policy())

    def test_projection_validator_rejects_approval_like_disposition(self) -> None:
        projection = impact.build_projection(_manifest(), policy=_policy())
        projection["review_packet"][0]["review_disposition"] = "APPROVED"
        with self.assertRaisesRegex(impact.ProjectionError, "Unsupported review disposition"):
            impact.validate_projection(projection)

    def test_projection_validator_rejects_monitoring_classification(self) -> None:
        projection = impact.build_projection(_manifest(), policy=_policy())
        projection["review_packet"][0]["monitoring_disposition"] = "RECURRING"
        with self.assertRaisesRegex(impact.ProjectionError, "Monitoring cadence must remain unclassified"):
            impact.validate_projection(projection)

    def test_output_is_deterministic_and_marked_noncanonical(self) -> None:
        projection = impact.build_projection(
            _manifest(),
            policy=_policy(),
            manifest_sha256="b" * 64,
            policy_sha256="c" * 64,
        )
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = impact.write_outputs(projection, Path(first_dir))
            second = impact.write_outputs(projection, Path(second_dir))
            first_json = Path(first["json"]).read_bytes()
            second_json = Path(second["json"]).read_bytes()
            first_md = Path(first["markdown"]).read_bytes()
            second_md = Path(second["markdown"]).read_bytes()
            self.assertEqual(first_json, second_json)
            self.assertEqual(first_md, second_md)
            self.assertIn(b"NONCANONICAL PROJECTION", first_md)
            self.assertIn(b"scenario only", first_md)
            self.assertIn(b"Source-namespace-eligible exact-key evidence: 34", first_md)

    def test_cli_validates_manifest_policy_and_writes_review_packet(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            code = impact.main(
                [
                    "--manifest",
                    str(MANIFEST_PATH),
                    "--schema",
                    str(SCHEMA_PATH),
                    "--namespace-policy",
                    str(POLICY_PATH),
                    "--output-dir",
                    output_dir,
                ]
            )
            self.assertEqual(code, 0)
            payload = json.loads(
                (Path(output_dir) / "legacy-source-registration-impact.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                payload["full_identity_safe_acceptance_scenario"]["projected_deterministically_matched_evidence_count"],
                50,
            )
            self.assertEqual(len(payload["remaining_unresolved_evidence"]), 2)
            self.assertEqual(len(payload["review_packet"]), 35)


if __name__ == "__main__":
    unittest.main()
