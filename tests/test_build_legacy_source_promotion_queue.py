from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "build_legacy_source_promotion_queue.py"
SPEC = importlib.util.spec_from_file_location("build_legacy_source_promotion_queue", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
queue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(queue)

MANIFEST_PATH = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"
SCHEMA_PATH = ROOT / "schemas" / "legacy-source-registration-proposals.schema.json"
POLICY_PATH = ROOT / "curation" / "source_namespace_eligibility_policy_v0.1.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _policy() -> dict[str, object]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _queue() -> dict[str, object]:
    return queue.build_queue(_manifest(), _policy())


def _row(payload: dict[str, object], proposal_id: str) -> dict[str, object]:
    return next(row for row in payload["rows"] if row["proposal_id"] == proposal_id)


class PromotionReadinessQueueTests(unittest.TestCase):
    def test_exact_queue_and_lane_counts(self) -> None:
        payload = _queue()
        checkpoint = payload["queue_checkpoint"]
        self.assertEqual(checkpoint["queue_row_count"], 35)
        self.assertEqual(checkpoint["linked_unresolved_evidence_row_count"], 37)
        self.assertEqual(
            checkpoint["lane_counts"],
            {
                "CURATION_REQUIRED": 2,
                "LIVE_SOURCE_REFRESH_REQUIRED": 11,
                "STATIC_IDENTITY_AND_METADATA_REVIEW": 22,
            },
        )
        self.assertEqual(
            checkpoint["eligible_monitoring_mode_counts"],
            {"ARCHIVAL_STATIC": 22, "ON_CHANGE": 7, "RECURRING": 4},
        )

    def test_authority_states_are_fail_closed_for_every_row(self) -> None:
        payload = _queue()
        self.assertEqual(payload["status"], "NONCANONICAL_REVIEW_QUEUE")
        self.assertEqual(payload["approval_status"], "NOT_APPROVED")
        self.assertEqual(payload["canonical_status"], "NOT_CANONICAL")
        self.assertEqual(payload["human_review_status"], "UNREVIEWED")
        for row in payload["rows"]:
            self.assertEqual(row["approval_status"], "NOT_APPROVED")
            self.assertEqual(row["canonical_status"], "NOT_CANONICAL")
            self.assertEqual(row["human_review_status"], "UNREVIEWED")
            self.assertIsNone(row["reviewer_identity"])
            self.assertIsNone(row["decision_record_id"])

    def test_curation_holds_are_exact_and_have_no_monitoring_action(self) -> None:
        payload = _queue()
        curation = [row for row in payload["rows"] if row["review_lane"] == "CURATION_REQUIRED"]
        self.assertEqual(len(curation), 2)
        scoped = {
            evidence_id
            for row in curation
            for evidence_id in row["assessment_scoped_evidence_ids"]
        }
        self.assertEqual(scoped, {"BrainGate2 T15:EV-T15-012", "FDA adaptive DBS:EV-15"})
        for row in curation:
            self.assertFalse(row["source_namespace_eligible"])
            self.assertIsNone(row["monitoring_mode"])
            self.assertEqual(row["refresh_status"], "NOT_APPLICABLE")
            self.assertIsNone(row["prospective_source_identity_key"])

    def test_all_mutable_sources_require_fresh_capture(self) -> None:
        payload = _queue()
        mutable = [
            row for row in payload["rows"] if row["monitoring_mode"] in {"ON_CHANGE", "RECURRING"}
        ]
        self.assertEqual(len(mutable), 11)
        self.assertEqual(sum(row["monitoring_mode"] == "RECURRING" for row in mutable), 4)
        self.assertEqual(sum(row["monitoring_mode"] == "ON_CHANGE" for row in mutable), 7)
        for row in mutable:
            self.assertEqual(row["review_lane"], "LIVE_SOURCE_REFRESH_REQUIRED")
            self.assertEqual(row["refresh_status"], "REQUIRED")
            self.assertIn("fresh retrieval/capture", row["required_next_action"])

    def test_archival_sources_enter_static_identity_review_without_freshness_gate(self) -> None:
        payload = _queue()
        static = [row for row in payload["rows"] if row["monitoring_mode"] == "ARCHIVAL_STATIC"]
        self.assertEqual(len(static), 22)
        for row in static:
            self.assertEqual(row["review_lane"], "STATIC_IDENTITY_AND_METADATA_REVIEW")
            self.assertEqual(row["refresh_status"], "NOT_REQUIRED")
            self.assertTrue(row["source_namespace_eligible"])

    def test_source_id_authority_is_preserved(self) -> None:
        payload = _queue()
        requested = [row for row in payload["rows"] if row["requested_source_id"]]
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0]["requested_source_id"], "SRC-PR-011")
        self.assertEqual(requested[0]["effective_source_action"], "REGISTER_MISSING_EXPLICIT_SOURCE")
        new_sources = [row for row in payload["rows"] if row["effective_source_action"] == "REGISTER_NEW_SOURCE"]
        self.assertEqual(len(new_sources), 32)
        self.assertTrue(all(row["requested_source_id"] is None for row in new_sources))
        self.assertTrue(all(row["existing_source_id"] is None for row in new_sources))

    def test_impacted_requirements_and_source_boundaries_are_preserved_verbatim(self) -> None:
        manifest = _manifest()
        payload = queue.build_queue(manifest, _policy())
        manifest_by_id = {row["proposal_id"]: row for row in manifest["proposals"]}
        for row in payload["rows"]:
            source = manifest_by_id[row["proposal_id"]]
            self.assertEqual(row["impacted_requirement_count"], source["impacted_requirement_count"])
            self.assertEqual(row["impacted_requirement_ids"], source["impacted_requirement_ids"])
            self.assertEqual(row["source_boundary_note"], source["source_boundary_note"])

    def test_assessment_local_evidence_identity_is_scoped_by_system(self) -> None:
        payload = _queue()
        scoped = [
            evidence_id
            for row in payload["rows"]
            for evidence_id in row["assessment_scoped_evidence_ids"]
        ]
        self.assertEqual(len(scoped), 37)
        self.assertEqual(len(scoped), len(set(scoped)))
        self.assertIn("Brain2Qwerty:EV-06", scoped)
        self.assertIn("FDA adaptive DBS:EV-06", scoped)

    def test_layer_disagreement_fails_closed(self) -> None:
        manifest = _manifest()
        policy = _policy()
        real_monitoring = queue.build_monitoring_projection(manifest, policy)
        broken = copy.deepcopy(real_monitoring)
        removed = broken["sources"].pop()
        broken["excluded_curation_holds"].append(
            {
                "proposal_id": removed["proposal_id"],
                "effective_action": removed["effective_source_action"],
                "linked_evidence_ids": removed["linked_evidence_ids"],
                "systems": removed["systems"],
                "eligibility_reason": "SYNTHETIC_DISAGREEMENT",
            }
        )
        with patch.object(queue, "build_monitoring_projection", return_value=broken):
            with self.assertRaisesRegex(queue.PromotionReadinessError, "Namespace/monitoring disagreement"):
                queue.build_queue(manifest, policy)

    def test_validator_rejects_approval_canonical_or_reviewer_mutation(self) -> None:
        mutations = (
            ("approval_status", "APPROVED", "approval/canonical"),
            ("canonical_status", "CANONICAL", "approval/canonical"),
            ("human_review_status", "REVIEWED", "human review"),
        )
        for field, value, message in mutations:
            payload = _queue()
            payload[field] = value
            with self.assertRaisesRegex(queue.PromotionReadinessError, message):
                queue.validate_queue(payload)

        payload = _queue()
        payload["rows"][0]["reviewer_identity"] = "invented-reviewer"
        with self.assertRaisesRegex(queue.PromotionReadinessError, "fabricates reviewer"):
            queue.validate_queue(payload)

    def test_validator_rejects_lane_or_refresh_drift(self) -> None:
        payload = _queue()
        static = next(row for row in payload["rows"] if row["review_lane"] == "STATIC_IDENTITY_AND_METADATA_REVIEW")
        static["refresh_status"] = "REQUIRED"
        with self.assertRaisesRegex(queue.PromotionReadinessError, "cannot require freshness"):
            queue.validate_queue(payload)

    def test_outputs_are_deterministic_and_machine_readable(self) -> None:
        payload = _queue()
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = queue.write_outputs(payload, Path(first_dir))
            second = queue.write_outputs(payload, Path(second_dir))
            for kind in ("json", "csv", "markdown"):
                self.assertEqual(Path(first[kind]).read_bytes(), Path(second[kind]).read_bytes())
            decoded = json.loads(Path(first["json"]).read_text(encoding="utf-8"))
            self.assertEqual(decoded["queue_checkpoint"]["queue_row_count"], 35)
            markdown = Path(first["markdown"]).read_text(encoding="utf-8")
            self.assertIn("NONCANONICAL REVIEW QUEUE", markdown)
            self.assertIn("STATIC_IDENTITY_AND_METADATA_REVIEW: 22", markdown)

    def test_cli_writes_three_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            code = queue.main(
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
            root = Path(output_dir)
            self.assertTrue((root / "legacy-source-promotion-readiness.json").is_file())
            self.assertTrue((root / "legacy-source-promotion-readiness.csv").is_file())
            self.assertTrue((root / "legacy-source-promotion-readiness.md").is_file())


if __name__ == "__main__":
    unittest.main()
