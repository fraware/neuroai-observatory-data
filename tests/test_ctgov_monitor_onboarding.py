from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import review_ctgov_monitoring_onboarding as onboarding


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_materialization(root: Path, *, cadence: str = "MONTHLY") -> tuple[dict, dict]:
    successor_id = "SNSP-" + "a" * 32
    source = {
        "schema_version": "2.0.0-draft",
        "source_id": "SRC-CTGOV-NCT03333954",
        "title": "PRIMA Feasibility Study",
        "publisher": "ClinicalTrials.gov",
        "canonical_locator": "https://clinicaltrials.gov/study/NCT03333954",
        "source_class": "OFFICIAL_TRIAL_REGISTRY",
        "legacy_source_ids": [],
        "source_claim_boundary": "Registry identity and metadata only; no clinical effectiveness or safety conclusion.",
        "source_origin": "DISCOVERY_HUMAN_ACCEPTED_SOURCE_NAMESPACE_PROPOSAL",
        "discovery_provenance": {
            "source_namespace_successor_proposal_id": successor_id,
            "programme_id": "SU-TRIALS-CTGOV-v0.1",
            "projection_manifest_sha256": "1" * 64,
            "review_index_sha256": "2" * 64,
            "decision_packet_sha256": "3" * 64,
            "workbench_query_id": "DISCOVERY-CTGOV-SU-TRIALS-UNION-ABCDEF012345",
            "workbench_run_id": "DRUN-" + "4" * 32,
            "workbench_proposal_id": "DSP-" + "5" * 32,
            "workbench_adjudication_id": "DADJ-" + "6" * 32,
            "nct_id": "NCT03333954",
            "query_ids": ["DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001"],
            "normalized_aggregate_digest": "7" * 64,
            "candidate_input_sha256": "8" * 64,
        },
        "record_state": "NONCANONICAL_DISCOVERY_ADMITTED_CANDIDATE",
        "authority_boundary": "TEST NONCANONICAL SOURCE",
    }
    proposal = {
        "proposal_id": "SMEP-" + "9" * 32,
        "source_namespace_successor_proposal_id": successor_id,
        "source_id": source["source_id"],
        "nct_id": "NCT03333954",
        "source_class": "OFFICIAL_TRIAL_REGISTRY",
        "recommended_mode": "RECURRING",
        "recommended_cadence": cadence,
        "priority": "HIGH",
        "reason": "Living trial-registry metadata can change.",
        "review_state": "PENDING_MONITOR_REVIEW",
        "monitor_present": False,
        "monitor_creation_performed": False,
        "automatic_registry_mutation": False,
        "authority_boundary": "TEST MONITOR REVIEW ONLY",
    }
    monitoring = {
        "schema_version": "0.1.0",
        "artifact": "monitoring_eligibility_proposals",
        "status": "NONCANONICAL_PENDING_MONITOR_REVIEW",
        "source_namespace_successor_proposal_id": successor_id,
        "source_candidate_count": 1,
        "proposal_count": 1,
        "proposals": [proposal],
        "automatic_registry_mutation": False,
        "monitor_creation_performed": False,
        "source_namespace_publication_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": "TEST NONCANONICAL MONITORING PROPOSALS",
    }
    reconciliation = {
        "source_namespace_successor_proposal_id": successor_id,
        "source_candidate_count": 1,
        "monitoring_proposal_count": 1,
        "source_namespace_publication_performed": False,
        "monitor_creation_performed": False,
        "canonical_successor_ready": False,
    }
    payloads = {
        "discovery-sources.jsonl": (json.dumps(source, sort_keys=True) + "\n").encode(),
        "monitoring-eligibility-proposals.json": (json.dumps(monitoring, indent=2, sort_keys=True) + "\n").encode(),
        "reconciliation.json": (json.dumps(reconciliation, indent=2, sort_keys=True) + "\n").encode(),
    }
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (root / name).write_bytes(payload)
    manifest = {
        "schema_version": "0.1.0",
        "status": "NONCANONICAL_DISCOVERY_SOURCE_MATERIALIZATION",
        "source_namespace_successor_proposal_id": successor_id,
        "source_namespace_publication_performed": False,
        "monitor_creation_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "file_count": len(payloads),
        "files": [
            {"path": name, "sha256": _sha256_bytes(payload), "bytes": len(payload)}
            for name, payload in sorted(payloads.items())
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return source, proposal


def _write_decisions(root: Path, materialization: Path, *, decision: str = "APPROVE_RECOMMENDATION") -> Path:
    manifest_sha = _sha256_bytes((materialization / "manifest.json").read_bytes())
    packet = {
        "schema_version": "0.1.0",
        "artifact": "monitor_review_decision_packet",
        "status": "EXPLICIT_LOCAL_MONITOR_REVIEW",
        "source_materialization_manifest_sha256": manifest_sha,
        "source_namespace_successor_proposal_id": "SNSP-" + "a" * 32,
        "reviewed_by": "local-reviewer",
        "reviewed_at": "2026-08-31T12:30:00Z",
        "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
        "decisions": [{
            "monitoring_proposal_id": "SMEP-" + "9" * 32,
            "source_id": "SRC-CTGOV-NCT03333954",
            "decision": decision,
            "rationale": "Explicit test disposition.",
        }],
        "onboarding_plan_authorized_only": True,
        "network_execution_authorized": False,
        "quarantine_approval_authorized": False,
        "monitor_registry_successor_authorized": False,
        "source_namespace_publication_authorized": False,
        "trial_entity_creation_authorized": False,
        "trial_site_relationship_creation_authorized": False,
        "assessment_mutation_authorized": False,
        "canonical_publication_authorized": False,
        "authority_boundary": "TEST ONBOARDING ONLY",
    }
    path = root / "monitor-review.json"
    path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    return path


class CTGovMonitorOnboardingTests(unittest.TestCase):
    def test_approved_plan_is_deterministic_bounded_and_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            _write_materialization(materialization)
            decisions = _write_decisions(root, materialization)
            first = onboarding.build_onboarding(materialization, decisions)
            second = onboarding.build_onboarding(materialization, decisions)
            self.assertEqual(first, second)
            plan = first["onboarding"]["plans"][0]
            self.assertRegex(plan["draft_monitor_id"], r"^DMON-[0-9a-f]{32}$")
            self.assertEqual(plan["approved_mode"], "RECURRING")
            self.assertEqual(plan["approved_cadence"], "MONTHLY")
            self.assertEqual(plan["priority"], "HIGH")
            self.assertEqual(plan["routes"][0]["url"], "https://clinicaltrials.gov/api/v2/studies/NCT03333954")
            self.assertEqual(
                plan["routes"][1]["url"],
                "https://clinicaltrials.gov/api/v2/studies?query.id=NCT03333954&pageSize=1&format=json",
            )
            self.assertEqual(plan["routes"][2]["url"], "https://clinicaltrials.gov/study/NCT03333954")
            self.assertEqual(plan["initial_capture_route_id"], plan["routes"][0]["route_id"])
            self.assertEqual(plan["routes"][0]["route_class"], "PRIMARY")
            self.assertEqual(plan["routes"][2]["route_class"], "LIVENESS_CORROBORATION")
            self.assertNotEqual(plan["first_capture_request_template"]["requested_url"], plan["routes"][2]["url"])
            self.assertEqual(plan["first_capture_request_template"]["execution_state"], "TEMPLATE_NOT_EXECUTED")
            self.assertFalse(first["onboarding"]["network_execution_performed"])
            self.assertFalse(first["onboarding"]["monitor_registry_successor_created"])
            schema = json.loads((ROOT / "schemas" / "ctgov-monitor-onboarding-package.schema.json").read_text())
            errors = list(Draft202012Validator(schema).iter_errors(first["onboarding"]))
            self.assertEqual(errors, [], [error.message for error in errors])

    def test_defer_produces_summary_without_onboarding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            _write_materialization(materialization)
            decisions = _write_decisions(root, materialization, decision="DEFER")
            result = onboarding.build_onboarding(materialization, decisions)
            self.assertEqual(result["summary"]["approved_count"], 0)
            self.assertIsNone(result["onboarding"])
            self.assertFalse(result["summary"]["network_execution_performed"])

    def test_manifest_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            _write_materialization(materialization)
            decisions = _write_decisions(root, materialization)
            path = materialization / "monitoring-eligibility-proposals.json"
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "manifest mismatch"):
                onboarding.build_onboarding(materialization, decisions)

    def test_decision_packet_must_cover_every_proposal_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            _write_materialization(materialization)
            decisions = _write_decisions(root, materialization)
            packet = json.loads(decisions.read_text())
            packet["decisions"] = []
            decisions.write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError, "non-empty object array"):
                onboarding.build_onboarding(materialization, decisions)

    def test_duplicate_decision_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            _write_materialization(materialization)
            decisions = _write_decisions(root, materialization)
            packet = json.loads(decisions.read_text())
            packet["decisions"].append(copy.deepcopy(packet["decisions"][0]))
            decisions.write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError, "Duplicate monitor-review decision"):
                onboarding.build_onboarding(materialization, decisions)

    def test_recommendation_drift_requires_new_review(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            _write_materialization(materialization, cadence="WEEKLY")
            decisions = _write_decisions(root, materialization)
            with self.assertRaisesRegex(ValueError, "RECOMMENDATION_DRIFT_REVIEW_REQUIRED"):
                onboarding.build_onboarding(materialization, decisions)

    def test_decision_schema_rejects_network_authority(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            _write_materialization(materialization)
            decisions = _write_decisions(root, materialization)
            packet = json.loads(decisions.read_text())
            packet["network_execution_authorized"] = True
            schema = json.loads((ROOT / "schemas" / "monitor-review-decision-packet.schema.json").read_text())
            errors = list(Draft202012Validator(schema).iter_errors(packet))
            self.assertTrue(errors)
            with self.assertRaisesRegex(ValueError, "authority boundary weakened"):
                onboarding.build_onboarding(materialization, decisions)

    def test_output_is_idempotent_and_collision_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            materialization = root / "materialization"
            output = root / "output"
            _write_materialization(materialization)
            decisions = _write_decisions(root, materialization)
            result = onboarding.build_onboarding(materialization, decisions)
            first = onboarding.write_outputs(result, output)
            second = onboarding.write_outputs(result, output)
            self.assertEqual(first, second)
            target = output / "monitor-review-summary.json"
            target.write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "OUTPUT_COLLISION_REFUSED"):
                onboarding.write_outputs(result, output)


if __name__ == "__main__":
    unittest.main()
