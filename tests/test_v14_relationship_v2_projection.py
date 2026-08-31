from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "project_v14_relationships_to_v2.py"
SPEC = importlib.util.spec_from_file_location("project_v14_relationships_to_v2", SCRIPT)
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


class V14RelationshipV2ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cls.result = module.project(BASELINE)
        cls.relationships = {row["relationship_id"]: row for row in cls.result["relationships"]}

    def test_exact_relationship_population_is_preserved(self) -> None:
        reconciliation = self.result["reconciliation"]
        self.assertEqual(reconciliation["input_relationship_count"], 22)
        self.assertEqual(reconciliation["projected_relationship_count"], 22)
        self.assertEqual(
            reconciliation["family_counts"],
            {
                "PARTICIPANT_AUTHORITY": 6,
                "SUPPLIER_DEPENDENCY": 9,
                "TRIAL_SITE": 7,
            },
        )
        self.assertEqual(reconciliation["explicit_predecessor_evidence_state_count"], 13)
        self.assertEqual(reconciliation["unspecified_predecessor_evidence_state_count"], 9)
        self.assertEqual(reconciliation["unresolved_endpoint_count"], 44)
        self.assertEqual(reconciliation["unresolved_knowledge_time_count"], 22)
        self.assertFalse(reconciliation["canonical_successor_ready"])

    def test_every_endpoint_remains_exact_unresolved_predecessor_literal(self) -> None:
        for section, config in module.FAMILIES.items():
            for predecessor in self.baseline[section]:
                rid = predecessor[config["id_field"]]
                relationship = self.relationships[rid]
                self.assertEqual(
                    relationship["subject_reference"],
                    {
                        "value": predecessor[config["subject_field"]],
                        "resolution_state": "PREDECESSOR_LITERAL_UNRESOLVED",
                        "entity_id": None,
                    },
                )
                self.assertEqual(
                    relationship["object_reference"],
                    {
                        "value": predecessor[config["object_field"]],
                        "resolution_state": "PREDECESSOR_LITERAL_UNRESOLVED",
                        "entity_id": None,
                    },
                )

    def test_family_specific_semantics_are_preserved_exactly(self) -> None:
        for section, config in module.FAMILIES.items():
            for predecessor in self.baseline[section]:
                relationship = self.relationships[predecessor[config["id_field"]]]
                self.assertEqual(relationship["relationship_family"], config["family"])
                self.assertEqual(
                    relationship["relationship_type"], predecessor[config["type_field"]]
                )
                self.assertEqual(
                    relationship["qualifiers"],
                    {field: predecessor[field] for field in config["qualifier_fields"]},
                )
                self.assertEqual(relationship["claim_boundary"], predecessor["boundary"])

    def test_source_and_evidence_states_are_not_strengthened(self) -> None:
        governing_source_ids = {row["source_id"] for row in self.baseline["sources"]}
        for section, config in module.FAMILIES.items():
            for predecessor in self.baseline[section]:
                relationship = self.relationships[predecessor[config["id_field"]]]
                self.assertEqual(relationship["source_ids"], predecessor["source_ids"])
                self.assertTrue(set(relationship["source_ids"]).issubset(governing_source_ids))
                self.assertEqual(relationship["source_linkage_state"], "SOURCE_LINKED")
                if predecessor.get("evidence_state"):
                    self.assertEqual(relationship["evidence_state"], predecessor["evidence_state"])
                else:
                    self.assertEqual(
                        relationship["evidence_state"],
                        "PREDECESSOR_SOURCE_LINKED_EVIDENCE_STATE_UNSPECIFIED",
                    )

    def test_supplier_capability_is_not_promoted_to_named_system_dependency(self) -> None:
        capability = [
            row
            for row in self.baseline["supplier_dependency_relationships"]
            if row["relationship_type"] == "SUPPLIER_CAPABILITY"
        ]
        self.assertEqual(len(capability), 2)
        for predecessor in capability:
            relationship = self.relationships[predecessor["dependency_id"]]
            self.assertEqual(relationship["relationship_type"], "SUPPLIER_CAPABILITY")
            self.assertIn("does not", relationship["claim_boundary"].lower())
            self.assertIsNone(relationship["object_reference"]["entity_id"])

    def test_no_relationship_time_is_inferred_from_release_cutoff(self) -> None:
        for relationship in self.relationships.values():
            self.assertIsNone(relationship["observed_at"])
            self.assertEqual(
                relationship["knowledge_time_state"], "PREDECESSOR_TIME_UNRESOLVED"
            )
            self.assertEqual(relationship["observation_ids"], [])

    def test_reconciliation_has_no_loss_or_fabrication_in_this_slice(self) -> None:
        reconciliation = self.result["reconciliation"]
        for key in (
            "relationship_id_loss_count",
            "predecessor_payload_roundtrip_failure_count",
            "predecessor_field_loss_count",
            "relationship_type_loss_count",
            "endpoint_literal_loss_count",
            "qualifier_loss_count",
            "claim_boundary_loss_count",
            "source_reference_loss_count",
            "dangling_source_reference_count",
            "endpoint_resolution_fabrication_count",
            "temporal_precision_fabrication_count",
            "invented_predecessor_field_value_count",
        ):
            self.assertEqual(reconciliation[key], 0, key)


if __name__ == "__main__":
    unittest.main()
