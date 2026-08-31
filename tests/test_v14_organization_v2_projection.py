from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "project_v14_organizations_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v14_organizations_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
BASELINE = (
    ROOT
    / "releases"
    / "data-v0.1.0-public-governing"
    / "records"
    / "canonical_observatory_release_v1.4.json"
)


class V14OrganizationV2ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cls.result = module.project(BASELINE)
        cls.predecessors = {
            row["organization_id"]: row for row in cls.baseline["organizations"]
        }
        cls.entities = {row["entity_id"]: row for row in cls.result["entities"]}
        cls.assertions_by_subject: dict[str, list[dict[str, object]]] = {}
        for assertion in cls.result["assertions"]:
            cls.assertions_by_subject.setdefault(str(assertion["subject_id"]), []).append(assertion)

    def test_exact_predecessor_population_is_preserved(self) -> None:
        reconciliation = self.result["reconciliation"]
        self.assertEqual(len(self.baseline["organizations"]), 223)
        self.assertEqual(reconciliation["input_entry_count"], 223)
        self.assertEqual(reconciliation["projected_entity_count"], 223)
        self.assertEqual(reconciliation["organization_entity_count"], 217)
        self.assertEqual(reconciliation["provenance_node_count"], 6)
        self.assertEqual(reconciliation["projected_assertion_count"], 2925)
        self.assertEqual(reconciliation["source_linked_entry_count"], 154)
        self.assertEqual(
            reconciliation["predecessor_source_linkage_unresolved_entry_count"], 69
        )
        self.assertEqual(reconciliation["legacy_only_entry_count"], 63)
        self.assertFalse(reconciliation["canonical_successor_ready"])

    def test_every_predecessor_payload_and_identity_round_trips(self) -> None:
        self.assertEqual(set(self.predecessors), set(self.entities))
        for entity_id, predecessor in self.predecessors.items():
            entity = self.entities[entity_id]
            self.assertEqual(entity["entity_id"], predecessor["organization_id"])
            self.assertEqual(entity["canonical_name"], predecessor["canonical_name"])
            self.assertEqual(entity["aliases"], predecessor["aliases"])
            self.assertEqual(entity["predecessor"]["payload"], predecessor)
            self.assertEqual(
                entity["predecessor"]["record_sha256"], module._digest(predecessor)
            )

    def test_reclassified_entries_remain_provenance_nodes(self) -> None:
        reclassified = [
            row
            for row in self.baseline["organizations"]
            if row["verification_state"] == "NON_ORGANIZATION_PROVENANCE_NODE"
        ]
        self.assertEqual(len(reclassified), 6)
        for predecessor in reclassified:
            entity = self.entities[predecessor["organization_id"]]
            self.assertEqual(entity["entity_kind"], "PROVENANCE_NODE")
            self.assertEqual(predecessor["current_status"], "RECLASSIFIED")

    def test_source_linked_entries_preserve_exact_sources_and_date_precision(self) -> None:
        linked = [row for row in self.baseline["organizations"] if row["source_ids"]]
        self.assertEqual(len(linked), 154)
        governing_source_ids = {row["source_id"] for row in self.baseline["sources"]}
        for predecessor in linked:
            self.assertEqual(predecessor["last_verified"], "2026-07-29")
            self.assertTrue(set(predecessor["source_ids"]).issubset(governing_source_ids))
            for assertion in self.assertions_by_subject[predecessor["organization_id"]]:
                self.assertEqual(assertion["source_ids"], predecessor["source_ids"])
                self.assertEqual(assertion["source_linkage_state"], "SOURCE_LINKED")
                self.assertEqual(assertion["knowledge_time_state"], "EXACT_PREDECESSOR_TIME")
                self.assertEqual(
                    assertion["observed_at"],
                    {"value": "2026-07-29", "precision": "DATE"},
                )
                self.assertEqual(assertion["claim_boundary"], predecessor["claim_boundary"])

    def test_source_less_legacy_and_provenance_records_do_not_invent_evidence(self) -> None:
        source_less = [row for row in self.baseline["organizations"] if not row["source_ids"]]
        self.assertEqual(len(source_less), 69)
        self.assertEqual(
            sum(row["verification_state"] == "LEGACY_ONLY" for row in source_less), 63
        )
        self.assertEqual(
            sum(
                row["verification_state"] == "NON_ORGANIZATION_PROVENANCE_NODE"
                for row in source_less
            ),
            6,
        )
        for predecessor in source_less:
            self.assertIsNone(predecessor["last_verified"])
            for assertion in self.assertions_by_subject[predecessor["organization_id"]]:
                self.assertEqual(assertion["source_ids"], [])
                self.assertEqual(
                    assertion["source_linkage_state"],
                    "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED",
                )
                self.assertEqual(
                    assertion["evidence_state"],
                    "PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED",
                )
                self.assertEqual(
                    assertion["knowledge_time_state"], "PREDECESSOR_TIME_UNRESOLVED"
                )
                self.assertIsNone(assertion["observed_at"])
                self.assertEqual(assertion["review_state"], "MIGRATED_PREDECESSOR_STATE")
                self.assertEqual(assertion["record_state"], "NONCANONICAL_CANDIDATE")

    def test_reconciliation_has_no_claimed_loss_or_fabrication_in_this_slice(self) -> None:
        reconciliation = self.result["reconciliation"]
        for key in (
            "identity_mismatch_count",
            "entity_kind_mismatch_count",
            "predecessor_payload_roundtrip_failure_count",
            "predecessor_field_loss_count",
            "claim_boundary_loss_count",
            "source_reference_loss_count",
            "dangling_source_reference_count",
            "source_linkage_fabrication_count",
            "temporal_precision_fabrication_count",
            "invented_predecessor_field_value_count",
        ):
            self.assertEqual(reconciliation[key], 0, key)


if __name__ == "__main__":
    unittest.main()
