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


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


class LegacySourceRegistrationImpactTests(unittest.TestCase):
    def test_projection_derives_safe_joinability_ceiling(self) -> None:
        projection = impact.build_projection(_manifest(), manifest_sha256="a" * 64)
        current = projection["current_state"]
        scenario = projection["full_identity_safe_acceptance_scenario"]

        self.assertEqual(current["effective_source_count"], 248)
        self.assertEqual(current["assessment_evidence_count"], 52)
        self.assertEqual(current["deterministically_matched_evidence_count"], 15)
        self.assertEqual(current["unresolved_evidence_count"], 37)
        self.assertEqual(scenario["newly_joinable_evidence_count"], 36)
        self.assertEqual(scenario["projected_deterministically_matched_evidence_count"], 51)
        self.assertEqual(scenario["projected_unresolved_evidence_count"], 1)
        self.assertEqual(scenario["projected_joinability"], {"numerator": 51, "denominator": 52})
        self.assertEqual(scenario["projected_added_source_identity_count"], 34)
        self.assertEqual(scenario["projected_effective_source_count"], 282)
        self.assertEqual(scenario["canonical_status"], "SCENARIO_ONLY_NOT_CURRENT_CANONICAL_DATA")

    def test_projection_preserves_review_and_monitoring_boundaries(self) -> None:
        projection = impact.build_projection(_manifest())
        self.assertEqual(projection["status"], "NONCANONICAL_PROJECTION")
        self.assertTrue(projection["scenario_only"])
        packet = projection["review_packet"]
        self.assertEqual(len(packet), 35)
        self.assertEqual(
            {row["review_disposition"] for row in packet},
            {"READY_FOR_IDENTITY_REVIEW", "CURATION_REQUIRED"},
        )
        self.assertTrue(
            all(row["monitoring_disposition"] == impact.MONITORING_DISPOSITION for row in packet)
        )
        self.assertNotIn("APPROVED", {row["review_disposition"] for row in packet})
        self.assertNotIn("ACCEPTED", {row["review_disposition"] for row in packet})

    def test_only_prima_carries_a_requested_source_id(self) -> None:
        projection = impact.build_projection(_manifest())
        requested = [row for row in projection["review_packet"] if row["requested_source_id"]]
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0]["requested_source_id"], "SRC-PR-011")
        self.assertEqual(requested[0]["action"], "REGISTER_MISSING_EXPLICIT_SOURCE")
        self.assertEqual(requested[0]["linked_evidence_ids"], ["EV-PR-011"])
        new_sources = [row for row in projection["review_packet"] if row["action"] == "REGISTER_NEW_SOURCE"]
        self.assertTrue(all(row["requested_source_id"] is None for row in new_sources))
        self.assertTrue(all(row["existing_source_id"] is None for row in new_sources))

    def test_fda_ev15_is_the_only_remaining_unresolved_evidence(self) -> None:
        projection = impact.build_projection(_manifest())
        remaining = projection["remaining_unresolved_evidence"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["system"], "FDA adaptive DBS")
        self.assertEqual(remaining[0]["evidence_id"], "EV-15")
        self.assertEqual(
            remaining[0]["reason"],
            "CURATION_REQUIRED_NO_SAFE_DETERMINISTIC_SOURCE_IDENTITY",
        )

    def test_braingate_group_unlocks_three_evidence_rows_with_one_source_delta(self) -> None:
        projection = impact.build_projection(_manifest())
        row = next(
            row
            for row in projection["review_packet"]
            if set(row["linked_evidence_ids"]) == {"EV-T15-001", "EV-T15-009", "EV-T15-010"}
        )
        self.assertEqual(row["projected_newly_joinable_evidence_count"], 3)
        self.assertEqual(row["projected_source_universe_delta"], 1)
        self.assertEqual(row["review_disposition"], "READY_FOR_IDENTITY_REVIEW")

    def test_projection_rejects_duplicate_evidence_across_proposals(self) -> None:
        manifest = _manifest()
        duplicate = dict(manifest["proposals"][0]["linked_evidence"][0])
        manifest["proposals"][1]["linked_evidence"].append(duplicate)
        with self.assertRaisesRegex(impact.ProjectionError, "appears in more than one proposal"):
            impact.build_projection(manifest)

    def test_projection_validator_rejects_approval_like_disposition(self) -> None:
        projection = impact.build_projection(_manifest())
        projection["review_packet"][0]["review_disposition"] = "APPROVED"
        with self.assertRaisesRegex(impact.ProjectionError, "Unsupported review disposition"):
            impact.validate_projection(projection)

    def test_projection_validator_rejects_monitoring_classification(self) -> None:
        projection = impact.build_projection(_manifest())
        projection["review_packet"][0]["monitoring_disposition"] = "RECURRING"
        with self.assertRaisesRegex(impact.ProjectionError, "Monitoring cadence must remain unclassified"):
            impact.validate_projection(projection)

    def test_output_is_deterministic_and_marked_noncanonical(self) -> None:
        manifest = _manifest()
        projection = impact.build_projection(manifest, manifest_sha256="b" * 64)
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

    def test_cli_validates_manifest_and_writes_review_packet(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            code = impact.main(
                [
                    "--manifest",
                    str(MANIFEST_PATH),
                    "--schema",
                    str(SCHEMA_PATH),
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
                51,
            )
            self.assertEqual(len(payload["review_packet"]), 35)


if __name__ == "__main__":
    unittest.main()
