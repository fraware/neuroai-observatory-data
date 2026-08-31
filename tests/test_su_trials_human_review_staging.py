from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_su_trials_recorded_replay as replay
import stage_su_trials_human_review as staging


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _candidate(nct_id: str = "NCT03333954") -> dict:
    return {
        "record_key": nct_id,
        "title": "PRIMA feasibility study",
        "url": f"https://clinicaltrials.gov/study/{nct_id}",
        "publisher": "ClinicalTrials.gov",
        "source_class": "OFFICIAL_TRIAL_REGISTRY",
        "suggested_source_id": f"SRC-CTGOV-{nct_id}",
        "classification_hint": "NEW",
        "duplicate_of_source_id": None,
        "query_ids": ["DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001"],
        "normalized_aggregate_digest": _digest(f"normalized:{nct_id}"),
    }


def _projection_result(candidates=None) -> dict:
    rows = list(candidates if candidates is not None else [_candidate()])
    return {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_SU_TRIALS_RECORDED_REPLAY_PROJECTION",
        "programme_id": "SU-TRIALS-CTGOV-v0.1",
        "input_provenance": {
            "bundle_sha256": _digest("bundle"),
            "captured_at": "2026-08-31T10:00:00Z",
            "capture_scope": "FULL_PROGRAMME",
            "api_data_timestamp": "2026-08-31",
            "raw_pages_retained_in_output": False,
            "known_nct_index_sha256": _digest("known-index"),
        },
        "known_source_index_summary": {
            "materialized_source_count": 248,
            "known_ctgov_nct_count": 1,
            "global_completeness_claim": False,
        },
        "query_reports": [],
        "normalized_studies": [],
        "known_duplicates": [],
        "new_candidate_inputs": rows,
        "reconciliation": {
            "scope": "FULL_PROGRAMME",
            "configured_active_query_count": 4,
            "executed_query_count": 4,
            "all_active_queries_executed": True,
            "query_mechanical_blocker_count": 0,
            "union_unique_nct_count": len(rows),
            "known_controlled_duplicate_count": 0,
            "new_candidate_input_count": len(rows),
            "cross_query_repeat_membership_count": 0,
            "materialized_source_namespace_count": 248,
            "known_ctgov_nct_count_before_run": 1,
            "raw_input_page_count": 4,
            "raw_api_page_payloads_emitted": False,
            "participant_level_data_emitted": False,
            "automatic_source_admission": False,
            "automatic_trial_entity_creation": False,
            "automatic_trial_site_relationship_creation": False,
            "automatic_monitor_creation": False,
            "automatic_assessment_mutation": False,
            "human_adjudication_performed": False,
            "mechanically_complete": True,
            "global_neuroai_trial_recall_claim": False,
            "registry_completeness_claim": False,
            "canonical_successor_ready": False,
            "authority_boundary": "TEST_MECHANICAL_BOUNDARY",
        },
    }


def _write_projection(root: Path, candidates=None):
    result = _projection_result(candidates)
    replay.write_projection(result, root)
    return result


class FakeWorkbench:
    def __init__(self, *, proposal_state="PENDING_HUMAN_ACCEPTANCE", wrong_identity=False, auto_mutation=False):
        self.proposal_state = proposal_state
        self.wrong_identity = wrong_identity
        self.auto_mutation = auto_mutation
        self.queries = []
        self.calls = []
        self.run_counter = 0

    def store_query(self, workspace, query):
        self.queries.append(json.loads(json.dumps(query)))
        return query

    def execute_discovery_query(self, workspace, query_id, **kwargs):
        self.run_counter += 1
        records = kwargs["result_records"]
        self.calls.append({"workspace": str(workspace), "query_id": query_id, **kwargs})
        proposals = []
        for index, record in enumerate(records, start=1):
            nct_id = "NCT99999999" if self.wrong_identity and index == 1 else record["record_key"]
            proposals.append(
                {
                    "proposal_id": f"DSP-{'%032x' % index}",
                    "run_id": f"DRUN-{'%032x' % self.run_counter}",
                    "query_id": query_id,
                    "classification": "NEW",
                    "proposed_source": {
                        "record_key": nct_id,
                        "title": record["title"],
                        "url": record["url"],
                        "publisher": record["publisher"],
                        "source_class": record["source_class"],
                        "suggested_source_id": record["suggested_source_id"],
                        "notes": None,
                    },
                    "duplicate_of_source_id": None,
                    "exclusion_reason": None,
                    "status": self.proposal_state,
                    "adjudication_id": None,
                    "automatic_mutation_performed": self.auto_mutation,
                    "boundary": "TEST",
                }
            )
        return {
            "run": {
                "run_id": f"DRUN-{'%032x' % self.run_counter}",
                "query_id": query_id,
                "execution_mode": "OFFLINE_REPLAY",
                "result_counts": {"total": len(records), "new": len(records), "duplicate": 0, "excluded": 0},
                "automatic_registry_mutation_performed": self.auto_mutation,
            },
            "proposals": proposals,
            "query": self.queries[-1],
        }

    @property
    def api(self):
        return staging.WorkbenchAPI(self.store_query, self.execute_discovery_query)


class SUTrialsHumanReviewStagingTests(unittest.TestCase):
    def test_stages_new_candidate_as_pending_and_writes_provenance_index(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            workspace = Path(workspace_td)
            _write_projection(projection)
            fake = FakeWorkbench()
            result = staging.stage_projection(
                projection,
                workspace,
                actor="review-operator",
                staged_at="2026-08-31T11:00:00Z",
                workbench_api=fake.api,
            )

            self.assertEqual(result["status"], "STAGED_FOR_HUMAN_ACCEPTANCE")
            self.assertEqual(result["candidate_count"], 1)
            self.assertFalse(result["automatic_mutation_performed"])
            self.assertFalse(result["human_adjudication_performed"])
            self.assertFalse(result["canonical_successor_ready"])
            self.assertEqual(fake.calls[0]["execution_mode"], "OFFLINE_REPLAY")
            self.assertEqual(fake.calls[0]["actor"], "review-operator")

            review_path = Path(result["review_index_path"])
            self.assertTrue(review_path.is_file())
            review = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(review["proposal_count"], 1)
            self.assertEqual(review["proposals"][0]["nct_id"], "NCT03333954")
            self.assertEqual(
                review["proposals"][0]["query_ids"],
                ["DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001"],
            )
            self.assertEqual(review["workbench_run_id"], result["discovery_run_id"])
            self.assertFalse(review["automatic_mutation_performed"])
            self.assertFalse(review["human_adjudication_performed"])

    def test_union_query_id_is_manifest_bound_and_stable(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_a_td, tempfile.TemporaryDirectory() as workspace_b_td:
            projection = Path(projection_td)
            _write_projection(projection)
            manifest_sha = hashlib.sha256((projection / "manifest.json").read_bytes()).hexdigest()
            fake_a = FakeWorkbench()
            fake_b = FakeWorkbench()
            first = staging.stage_projection(projection, Path(workspace_a_td), workbench_api=fake_a.api)
            second = staging.stage_projection(projection, Path(workspace_b_td), workbench_api=fake_b.api)
            expected_query_id = f"DISCOVERY-CTGOV-SU-TRIALS-UNION-{manifest_sha[:12].upper()}"
            self.assertEqual(first["discovery_query_id"], expected_query_id)
            self.assertEqual(second["discovery_query_id"], expected_query_id)
            self.assertEqual(fake_a.queries[0], fake_b.queries[0])
            self.assertEqual(fake_a.queries[0]["filters"]["projection_manifest_sha256"], manifest_sha)

    def test_manifest_tampering_stops_before_workbench(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            _write_projection(projection)
            path = projection / "new-candidate-inputs.jsonl"
            path.write_text(path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
            fake = FakeWorkbench()
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                staging.stage_projection(projection, Path(workspace_td), workbench_api=fake.api)
            self.assertEqual(fake.calls, [])
            self.assertEqual(fake.queries, [])

    def test_stale_new_identity_requires_reprojection(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            _write_projection(projection, [_candidate("NCT04676854")])
            fake = FakeWorkbench()
            with self.assertRaisesRegex(ValueError, "STALE_PROJECTION_RECLASSIFICATION_REQUIRED"):
                staging.stage_projection(projection, Path(workspace_td), workbench_api=fake.api)
            self.assertEqual(fake.calls, [])

    def test_non_pending_proposal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            _write_projection(projection)
            fake = FakeWorkbench(proposal_state="ACCEPTED")
            with self.assertRaisesRegex(ValueError, "not NEW/PENDING_HUMAN_ACCEPTANCE"):
                staging.stage_projection(projection, Path(workspace_td), workbench_api=fake.api)

    def test_proposal_identity_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            _write_projection(projection)
            fake = FakeWorkbench(wrong_identity=True)
            with self.assertRaisesRegex(ValueError, "proposal identity mismatch"):
                staging.stage_projection(projection, Path(workspace_td), workbench_api=fake.api)

    def test_automatic_mutation_signal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            _write_projection(projection)
            fake = FakeWorkbench(auto_mutation=True)
            with self.assertRaisesRegex(ValueError, "automatic registry mutation"):
                staging.stage_projection(projection, Path(workspace_td), workbench_api=fake.api)

    def test_zero_new_candidates_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            _write_projection(projection, [])
            fake = FakeWorkbench()
            result = staging.stage_projection(projection, Path(workspace_td), workbench_api=fake.api)
            self.assertEqual(result["status"], "NO_NEW_CANDIDATES_TO_STAGE")
            self.assertEqual(result["candidate_count"], 0)
            self.assertEqual(fake.calls, [])
            self.assertEqual(fake.queries, [])


if __name__ == "__main__":
    unittest.main()
