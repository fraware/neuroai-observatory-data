from __future__ import annotations

import copy
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

import adjudicate_su_trials_source_namespace as adjudication
import materialize_discovery_sources_monitoring as materializer
import project_v14_sources_to_v2

try:
    import jsonschema
except ImportError:  # pragma: no cover - workflow installs jsonschema explicitly
    jsonschema = None


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _successor_record(*, nct_id: str = "NCT03333954", source_id: str | None = None) -> dict:
    current = adjudication._current_source_namespace()
    source_id = source_id or f"SRC-CTGOV-{nct_id}"
    accepted_proposal_id = "DSP-00000000000000000000000000000001"
    return {
        "schema_version": "0.1.0",
        "artifact": "source_namespace_successor_proposal",
        "status": "DRAFT_NONCANONICAL_SOURCE_NAMESPACE_SUCCESSOR",
        "proposal_id": "SNSP-00000000000000000000000000000001",
        "programme_id": "SU-TRIALS-CTGOV-v0.1",
        "created_at": "2026-08-31T12:00:00Z",
        "created_by": "test-reviewer",
        "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
        "base_source_namespace": {
            "materialized_source_count": current["materialized_source_count"],
            "source_ids_sha256": current["source_ids_sha256"],
            "known_ctgov_nct_count": current["known_ctgov_nct_count"],
            "known_nct_index_sha256": current["known_nct_index_sha256"],
        },
        "decision_provenance": {
            "projection_manifest_sha256": _hex("projection"),
            "review_index_sha256": _hex("review"),
            "decision_packet_sha256": _hex("decision"),
            "workbench_query_id": "DISCOVERY-CTGOV-SU-TRIALS-UNION-ABCDEF123456",
            "workbench_run_id": "DRUN-00000000000000000000000000000001",
        },
        "accepted_proposal_ids": [accepted_proposal_id],
        "accepted_sources": [
            {
                "source_id": source_id,
                "nct_id": nct_id,
                "title": "Early Feasibility Study of the PRIMA Retinal Prosthesis",
                "publisher": "ClinicalTrials.gov",
                "canonical_locator": f"https://clinicaltrials.gov/study/{nct_id}",
                "source_class": "OFFICIAL_TRIAL_REGISTRY",
                "source_origin": "DISCOVERY_CTGOV_RECORDED_REPLAY_HUMAN_ACCEPTED",
                "namespace_admission_state": "PROPOSED_NOT_CANONICAL",
                "from_proposal_id": accepted_proposal_id,
                "workbench_adjudication_id": "DADJ-00000000000000000000000000000001",
                "query_ids": ["DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001"],
                "normalized_aggregate_digest": _hex("normalized"),
                "candidate_input_sha256": _hex("candidate"),
                "claim_boundary": "Accepted public source identity only; no substantive or monitoring authority.",
            }
        ],
        "overwrite_refused": True,
        "source_namespace_publication_performed": False,
        "monitor_creation_performed": False,
        "trial_entity_creation_performed": False,
        "trial_site_relationship_creation_performed": False,
        "assessment_mutation_performed": False,
        "canonical_successor_ready": False,
        "authority_boundary": "Draft Source-namespace succession only.",
    }


def _write_successor(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@unittest.skipIf(jsonschema is None, "jsonschema not installed")
class DiscoverySourceSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads((ROOT / "schemas/observatory-v2-source.schema.json").read_text(encoding="utf-8"))

    def test_existing_v14_projected_source_remains_valid(self) -> None:
        legacy = project_v14_sources_to_v2.project()["sources"][0]
        jsonschema.Draft202012Validator(self.schema).validate(legacy)

    def test_discovery_origin_source_validates_without_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            successor_path = Path(td) / "successor.json"
            _write_successor(successor_path, _successor_record())
            result = materializer.materialize(successor_path)
            source = result["sources"][0]
            self.assertNotIn("predecessor", source)
            self.assertEqual(source["source_origin"], "DISCOVERY_HUMAN_ACCEPTED_SOURCE_NAMESPACE_PROPOSAL")
            self.assertEqual(source["record_state"], "NONCANONICAL_DISCOVERY_ADMITTED_CANDIDATE")
            jsonschema.Draft202012Validator(self.schema).validate(source)

    def test_predecessor_and_discovery_provenance_are_mutually_exclusive(self) -> None:
        legacy = project_v14_sources_to_v2.project()["sources"][0]
        legacy["source_origin"] = "LEGACY_PUBLIC_RELEASE_MIGRATION"
        legacy["discovery_provenance"] = {
            "source_namespace_successor_proposal_id": "SNSP-00000000000000000000000000000001",
            "programme_id": "SU-TRIALS-CTGOV-v0.1",
            "projection_manifest_sha256": _hex("p"),
            "review_index_sha256": _hex("r"),
            "decision_packet_sha256": _hex("d"),
            "workbench_query_id": "DISCOVERY-TEST",
            "workbench_run_id": "DRUN-00000000000000000000000000000001",
            "workbench_proposal_id": "DSP-00000000000000000000000000000001",
            "workbench_adjudication_id": "DADJ-00000000000000000000000000000001",
            "nct_id": "NCT03333954",
            "query_ids": ["DISCOVERY-TEST"],
            "normalized_aggregate_digest": _hex("n"),
            "candidate_input_sha256": _hex("c"),
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(legacy)


class DiscoverySourceMaterializationTests(unittest.TestCase):
    def test_materializes_exact_discovery_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            successor_path = Path(td) / "successor.json"
            successor = _successor_record()
            _write_successor(successor_path, successor)
            result = materializer.materialize(successor_path)
            source = result["sources"][0]
            accepted = successor["accepted_sources"][0]
            provenance = source["discovery_provenance"]

            self.assertEqual(source["source_id"], accepted["source_id"])
            self.assertEqual(source["canonical_locator"], accepted["canonical_locator"])
            self.assertEqual(provenance["nct_id"], accepted["nct_id"])
            self.assertEqual(provenance["query_ids"], accepted["query_ids"])
            self.assertEqual(provenance["normalized_aggregate_digest"], accepted["normalized_aggregate_digest"])
            self.assertEqual(provenance["candidate_input_sha256"], accepted["candidate_input_sha256"])
            self.assertEqual(provenance["workbench_proposal_id"], accepted["from_proposal_id"])
            self.assertEqual(provenance["workbench_adjudication_id"], accepted["workbench_adjudication_id"])
            self.assertFalse(result["reconciliation"]["source_namespace_publication_performed"])
            self.assertFalse(result["reconciliation"]["monitor_creation_performed"])
            self.assertFalse(result["reconciliation"]["canonical_successor_ready"])

    def test_trial_registry_monitoring_reuses_existing_monthly_high_rule(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            successor_path = Path(td) / "successor.json"
            _write_successor(successor_path, _successor_record())
            result = materializer.materialize(successor_path)
            proposal = result["monitoring"]["proposals"][0]

            self.assertEqual(proposal["source_class"], "OFFICIAL_TRIAL_REGISTRY")
            self.assertEqual(proposal["recommended_mode"], "RECURRING")
            self.assertEqual(proposal["recommended_cadence"], "MONTHLY")
            self.assertEqual(proposal["priority"], "HIGH")
            self.assertEqual(proposal["review_state"], "PENDING_MONITOR_REVIEW")
            self.assertFalse(proposal["monitor_present"])
            self.assertFalse(proposal["monitor_creation_performed"])
            self.assertFalse(result["monitoring"]["automatic_registry_mutation"])
            self.assertFalse(result["monitoring"]["canonical_successor_ready"])

    def test_base_source_namespace_drift_requires_rebase(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            successor_path = Path(td) / "successor.json"
            successor = _successor_record()
            successor["base_source_namespace"]["known_nct_index_sha256"] = _hex("stale-base")
            _write_successor(successor_path, successor)
            with self.assertRaisesRegex(ValueError, "SOURCE_NAMESPACE_BASE_DRIFT_REBASE_REQUIRED"):
                materializer.materialize(successor_path)

    def test_existing_source_id_collision_fails_closed(self) -> None:
        current = adjudication._current_source_namespace()
        existing_source_id = sorted(current["source_ids"])[0]
        with tempfile.TemporaryDirectory() as td:
            successor_path = Path(td) / "successor.json"
            _write_successor(successor_path, _successor_record(source_id=existing_source_id))
            with self.assertRaisesRegex(ValueError, "SOURCE_NAMESPACE_BASE_COLLISION"):
                materializer.materialize(successor_path)

    def test_existing_nct_collision_fails_closed(self) -> None:
        current = adjudication._current_source_namespace()
        existing_nct = sorted(current["nct_to_source"])[0]
        with tempfile.TemporaryDirectory() as td:
            successor_path = Path(td) / "successor.json"
            _write_successor(successor_path, _successor_record(nct_id=existing_nct))
            with self.assertRaisesRegex(ValueError, "SOURCE_NAMESPACE_NCT_COLLISION"):
                materializer.materialize(successor_path)

    def test_deterministic_output_is_idempotent_and_collision_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            successor_path = root / "successor.json"
            output = root / "projection"
            _write_successor(successor_path, _successor_record())
            result = materializer.materialize(successor_path)

            first = materializer.write_projection(result, output)
            first_bytes = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
            second = materializer.write_projection(result, output)
            second_bytes = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
            self.assertEqual(first, second)
            self.assertEqual(first_bytes, second_bytes)
            self.assertFalse(first["monitor_creation_performed"])
            self.assertFalse(first["canonical_successor_ready"])

            reconciliation_path = output / "reconciliation.json"
            reconciliation_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "OUTPUT_COLLISION_REFUSED"):
                materializer.write_projection(result, output)

    def test_duplicate_accepted_identity_fails_before_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            successor_path = Path(td) / "successor.json"
            successor = _successor_record()
            duplicate = copy.deepcopy(successor["accepted_sources"][0])
            duplicate["from_proposal_id"] = "DSP-00000000000000000000000000000002"
            duplicate["workbench_adjudication_id"] = "DADJ-00000000000000000000000000000002"
            successor["accepted_sources"].append(duplicate)
            successor["accepted_proposal_ids"].append(duplicate["from_proposal_id"])
            with self.assertRaisesRegex(ValueError, "duplicate source/NCT/proposal identity"):
                _write_successor(successor_path, successor)
                materializer.materialize(successor_path)


if __name__ == "__main__":
    unittest.main()
