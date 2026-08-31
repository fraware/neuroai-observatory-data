from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
for path in (SCRIPTS, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import adjudicate_su_trials_source_namespace as adjudication
import stage_su_trials_human_review as staging
import test_su_trials_human_review_staging as base


STATUS = {
    "ACCEPT": "ACCEPTED",
    "REJECT": "REJECTED",
    "DEFER": "DEFERRED",
    "EXCLUDE": "EXCLUDED",
}


def _candidate(nct_id: str, title: str) -> dict:
    row = base._candidate(nct_id)
    row["title"] = title
    return row


class FakeAdjudicationWorkbench:
    def __init__(self, proposals: dict[str, dict], *, fail_on: str | None = None, leak_successor: bool = False):
        self.proposals = json.loads(json.dumps(proposals))
        self.adjudications: dict[str, dict] = {}
        self.fail_on = fail_on
        self.leak_successor = leak_successor
        self.calls: list[str] = []
        self.counter = 0

    def load_proposal(self, workspace, proposal_id):
        return json.loads(json.dumps(self.proposals[proposal_id]))

    def load_adjudication(self, workspace, adjudication_id):
        return json.loads(json.dumps(self.adjudications[adjudication_id]))

    def adjudicate_candidate_source(
        self,
        workspace,
        proposal_id,
        decision,
        *,
        rationale,
        actor,
        create_successor,
        adjudicated_at,
        **kwargs,
    ):
        self.calls.append(proposal_id)
        if create_successor is not False:
            raise AssertionError("test fake requires create_successor=False")
        if proposal_id == self.fail_on:
            raise RuntimeError("injected adjudication failure")
        proposal = self.proposals[proposal_id]
        if proposal["status"] != "PENDING_HUMAN_ACCEPTANCE":
            raise RuntimeError("proposal already adjudicated")
        self.counter += 1
        adjudication_id = f"DADJ-{self.counter:032x}"
        record = {
            "adjudication_id": adjudication_id,
            "proposal_id": proposal_id,
            "run_id": proposal["run_id"],
            "decision": decision,
            "rationale": rationale,
            "adjudicated_at": adjudicated_at,
            "adjudicated_by": actor,
            "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
            "registry_successor_id": None,
            "automatic_mutation_performed": False,
            "boundary": "TEST",
        }
        updated = {**proposal, "status": STATUS[decision], "adjudication_id": adjudication_id}
        self.adjudications[adjudication_id] = record
        self.proposals[proposal_id] = updated
        return {
            "adjudication": json.loads(json.dumps(record)),
            "proposal": json.loads(json.dumps(updated)),
            "successor": {"unexpected": True} if self.leak_successor else None,
        }

    @property
    def api(self):
        return adjudication.WorkbenchAPI(
            self.load_proposal,
            self.load_adjudication,
            self.adjudicate_candidate_source,
        )


def _prepare(projection: Path, workspace: Path, candidates: list[dict]) -> tuple[dict, dict[str, dict]]:
    base._write_projection(projection, candidates)
    staging_fake = base.FakeWorkbench()
    staged = staging.stage_projection(
        projection,
        workspace,
        actor="review-stager",
        staged_at="2026-08-31T11:00:00Z",
        workbench_api=staging_fake.api,
    )
    review = json.loads(Path(staged["review_index_path"]).read_text(encoding="utf-8"))
    records = staging_fake.calls[0]["result_records"]
    proposals: dict[str, dict] = {}
    for index, (proposal_id, record) in enumerate(zip(staged["proposal_ids"], records), start=1):
        proposals[proposal_id] = {
            "proposal_id": proposal_id,
            "run_id": staged["discovery_run_id"],
            "query_id": staged["discovery_query_id"],
            "created_at": "2026-08-31T11:00:00Z",
            "created_by": "review-stager",
            "classification": "NEW",
            "proposed_source": {
                "record_key": record["record_key"],
                "title": record["title"],
                "url": record["url"],
                "publisher": record["publisher"],
                "source_class": record["source_class"],
                "suggested_source_id": record["suggested_source_id"],
                "notes": None,
            },
            "duplicate_of_source_id": None,
            "exclusion_reason": None,
            "status": "PENDING_HUMAN_ACCEPTANCE",
            "adjudication_id": None,
            "automatic_mutation_performed": False,
            "boundary": "TEST",
        }
    return staged, proposals


def _write_packet(
    path: Path,
    staged: dict,
    review_path: Path,
    decisions: list[dict],
    *,
    actor: str = "human-reviewer",
    when: str = "2026-08-31T12:00:00Z",
) -> dict:
    review_sha = hashlib.sha256(review_path.read_bytes()).hexdigest()
    packet = {
        "schema_version": "0.1.0",
        "artifact": "su_trials_human_decision_packet",
        "status": "EXPLICIT_LOCAL_HUMAN_DECISION_PACKET",
        "programme_id": "SU-TRIALS-CTGOV-v0.1",
        "projection_manifest_sha256": staged["projection_manifest_sha256"],
        "review_index_sha256": review_sha,
        "workbench_query_id": staged["discovery_query_id"],
        "workbench_run_id": staged["discovery_run_id"],
        "adjudicated_by": actor,
        "adjudicated_at": when,
        "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
        "decisions": decisions,
        "source_namespace_admission_only": True,
        "monitor_creation_authorized": False,
        "trial_entity_creation_authorized": False,
        "trial_site_relationship_creation_authorized": False,
        "assessment_mutation_authorized": False,
        "canonical_publication_authorized": False,
        "authority_boundary": "Local source-identity disposition only; no monitoring, graph, assessment or publication authority.",
    }
    path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet


class SUTrialsSourceNamespaceSuccessorTests(unittest.TestCase):
    def test_accept_creates_source_namespace_successor_without_monitor_successor(self) -> None:
        with tempfile.TemporaryDirectory() as ptd, tempfile.TemporaryDirectory() as wtd:
            projection, workspace = Path(ptd), Path(wtd)
            staged, proposals = _prepare(projection, workspace, [_candidate("NCT03333954", "Retinal prosthesis study")])
            review_path = Path(staged["review_index_path"])
            pid = staged["proposal_ids"][0]
            packet_path = workspace / "decision.json"
            _write_packet(packet_path, staged, review_path, [{
                "proposal_id": pid,
                "nct_id": "NCT03333954",
                "decision": "ACCEPT",
                "rationale": "Exact official registry identity is relevant to the bounded SU-TRIALS source universe.",
            }])
            fake = FakeAdjudicationWorkbench(proposals)

            result = adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)
            self.assertEqual(result["status"], "COMPLETED_WITH_DRAFT_SOURCE_NAMESPACE_SUCCESSOR")
            self.assertEqual(result["accept_count"], 1)
            self.assertFalse(result["workbench_monitor_registry_successor_created"])
            self.assertFalse(result["monitor_creation_performed"])
            successor = json.loads(Path(result["source_namespace_successor_path"]).read_text(encoding="utf-8"))
            self.assertEqual(successor["status"], "DRAFT_NONCANONICAL_SOURCE_NAMESPACE_SUCCESSOR")
            self.assertEqual(successor["accepted_proposal_ids"], [pid])
            self.assertEqual(successor["accepted_sources"][0]["source_id"], "SRC-CTGOV-NCT03333954")
            self.assertEqual(successor["accepted_sources"][0]["nct_id"], "NCT03333954")
            self.assertEqual(successor["base_source_namespace"]["materialized_source_count"], 248)
            self.assertFalse(successor["source_namespace_publication_performed"])
            self.assertFalse(successor["monitor_creation_performed"])
            self.assertFalse(successor["canonical_successor_ready"])

    def test_non_accept_decisions_create_no_source_namespace_successor(self) -> None:
        with tempfile.TemporaryDirectory() as ptd, tempfile.TemporaryDirectory() as wtd:
            projection, workspace = Path(ptd), Path(wtd)
            staged, proposals = _prepare(projection, workspace, [_candidate("NCT03333954", "Retinal prosthesis study")])
            review_path = Path(staged["review_index_path"])
            pid = staged["proposal_ids"][0]
            packet_path = workspace / "decision.json"
            _write_packet(packet_path, staged, review_path, [{
                "proposal_id": pid,
                "nct_id": "NCT03333954",
                "decision": "DEFER",
                "rationale": "Relevant identity but additional source-namespace curation is required.",
            }])
            fake = FakeAdjudicationWorkbench(proposals)
            result = adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)
            self.assertEqual(result["status"], "COMPLETED_NO_SOURCE_NAMESPACE_ACCEPTANCES")
            self.assertEqual(result["accept_count"], 0)
            self.assertIsNone(result["source_namespace_successor_path"])

    def test_incomplete_decision_packet_fails_before_workbench_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as ptd, tempfile.TemporaryDirectory() as wtd:
            projection, workspace = Path(ptd), Path(wtd)
            candidates = [_candidate("NCT03333954", "A"), _candidate("NCT12345678", "B")]
            staged, proposals = _prepare(projection, workspace, candidates)
            review_path = Path(staged["review_index_path"])
            packet_path = workspace / "decision.json"
            _write_packet(packet_path, staged, review_path, [{
                "proposal_id": staged["proposal_ids"][0],
                "nct_id": candidates[0]["record_key"],
                "decision": "ACCEPT",
                "rationale": "Accept first only.",
            }])
            fake = FakeAdjudicationWorkbench(proposals)
            with self.assertRaisesRegex(ValueError, "dispose every staged proposal"):
                adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)
            self.assertEqual(fake.calls, [])

    def test_stale_accept_nct_fails_before_adjudication(self) -> None:
        with tempfile.TemporaryDirectory() as ptd, tempfile.TemporaryDirectory() as wtd:
            projection, workspace = Path(ptd), Path(wtd)
            staged, proposals = _prepare(projection, workspace, [_candidate("NCT03333954", "A")])
            review_path = Path(staged["review_index_path"])
            pid = staged["proposal_ids"][0]
            packet_path = workspace / "decision.json"
            _write_packet(packet_path, staged, review_path, [{
                "proposal_id": pid,
                "nct_id": "NCT03333954",
                "decision": "ACCEPT",
                "rationale": "Would accept absent concurrent source admission.",
            }])
            fake = FakeAdjudicationWorkbench(proposals)
            current = adjudication._current_source_namespace()
            current = {**current, "nct_to_source": {**current["nct_to_source"], "NCT03333954": "SRC-OTHER"}}
            with mock.patch.object(adjudication, "_current_source_namespace", return_value=current):
                with self.assertRaisesRegex(ValueError, "STALE_ACCEPT_RECLASSIFICATION_REQUIRED"):
                    adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)
            self.assertEqual(fake.calls, [])

    def test_workbench_monitor_successor_leakage_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as ptd, tempfile.TemporaryDirectory() as wtd:
            projection, workspace = Path(ptd), Path(wtd)
            staged, proposals = _prepare(projection, workspace, [_candidate("NCT03333954", "A")])
            review_path = Path(staged["review_index_path"])
            pid = staged["proposal_ids"][0]
            packet_path = workspace / "decision.json"
            _write_packet(packet_path, staged, review_path, [{
                "proposal_id": pid,
                "nct_id": "NCT03333954",
                "decision": "ACCEPT",
                "rationale": "Accept source identity only.",
            }])
            fake = FakeAdjudicationWorkbench(proposals, leak_successor=True)
            with self.assertRaisesRegex(RuntimeError, "PARTIAL_WORKBENCH_ADJUDICATION_FAILURE"):
                adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)
            summary_files = list((workspace / "programme-adjudication").rglob("adjudication-summary.json"))
            self.assertEqual(len(summary_files), 1)
            summary = json.loads(summary_files[0].read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "PARTIAL_WORKBENCH_ADJUDICATION_FAILURE")
            self.assertFalse(summary["source_namespace_successor_emitted"])

    def test_partial_failure_resumes_without_duplicate_adjudication(self) -> None:
        with tempfile.TemporaryDirectory() as ptd, tempfile.TemporaryDirectory() as wtd:
            projection, workspace = Path(ptd), Path(wtd)
            candidates = [_candidate("NCT03333954", "A"), _candidate("NCT12345678", "B")]
            staged, proposals = _prepare(projection, workspace, candidates)
            review_path = Path(staged["review_index_path"])
            pid1, pid2 = staged["proposal_ids"]
            packet_path = workspace / "decision.json"
            _write_packet(packet_path, staged, review_path, [
                {"proposal_id": pid1, "nct_id": "NCT03333954", "decision": "ACCEPT", "rationale": "Accept A."},
                {"proposal_id": pid2, "nct_id": "NCT12345678", "decision": "REJECT", "rationale": "Reject B as outside the bounded source scope."},
            ])
            fake = FakeAdjudicationWorkbench(proposals, fail_on=pid2)
            with self.assertRaisesRegex(RuntimeError, "PARTIAL_WORKBENCH_ADJUDICATION_FAILURE"):
                adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)
            self.assertEqual(fake.calls, [pid1, pid2])
            self.assertEqual(fake.proposals[pid1]["status"], "ACCEPTED")
            self.assertEqual(fake.proposals[pid2]["status"], "PENDING_HUMAN_ACCEPTANCE")

            fake.fail_on = None
            result = adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)
            self.assertEqual(fake.calls, [pid1, pid2, pid2])
            self.assertEqual(result["accept_count"], 1)
            successor = json.loads(Path(result["source_namespace_successor_path"]).read_text(encoding="utf-8"))
            self.assertEqual(successor["accepted_proposal_ids"], [pid1])

            successor_id = result["source_namespace_successor_proposal_id"]
            again = adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)
            self.assertEqual(fake.calls, [pid1, pid2, pid2])
            self.assertEqual(again["source_namespace_successor_proposal_id"], successor_id)

    def test_existing_adjudication_must_match_exact_decision_packet(self) -> None:
        with tempfile.TemporaryDirectory() as ptd, tempfile.TemporaryDirectory() as wtd:
            projection, workspace = Path(ptd), Path(wtd)
            staged, proposals = _prepare(projection, workspace, [_candidate("NCT03333954", "A")])
            review_path = Path(staged["review_index_path"])
            pid = staged["proposal_ids"][0]
            packet_path = workspace / "decision.json"
            _write_packet(packet_path, staged, review_path, [{
                "proposal_id": pid,
                "nct_id": "NCT03333954",
                "decision": "ACCEPT",
                "rationale": "Exact rationale.",
            }])
            fake = FakeAdjudicationWorkbench(proposals)
            adjudication.adjudicate(projection, workspace, review_path, packet_path, workbench_api=fake.api)

            changed_packet_path = workspace / "decision-changed.json"
            _write_packet(changed_packet_path, staged, review_path, [{
                "proposal_id": pid,
                "nct_id": "NCT03333954",
                "decision": "ACCEPT",
                "rationale": "Different rationale.",
            }])
            with self.assertRaisesRegex(ValueError, "existing adjudication does not match decision packet"):
                adjudication.adjudicate(projection, workspace, review_path, changed_packet_path, workbench_api=fake.api)


if __name__ == "__main__":
    unittest.main()
