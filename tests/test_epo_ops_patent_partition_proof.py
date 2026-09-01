from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path("scripts/reconcile_su_patents_epo_ops_partitions.py")
spec = importlib.util.spec_from_file_location("partition_proof", MODULE_PATH)
assert spec and spec.loader
proofmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proofmod)

ROOT_CQL = '(ta all "brain computer interface") or (ta all "brain machine interface") or (ta all "brain neural interface")'
CAPTURED_AT = "2026-09-01T12:00:00Z"
MANIFEST_SHA = "1" * 64


def _leaf(leaf_id: str, lower: str, upper: str, total: int) -> dict:
    return {
        "query_id": "DISCOVERY-OPS-BCI-001",
        "leaf_query_id": leaf_id,
        "applicant_term": None,
        "partition_path": [{"dimension": "PUBLICATION_DATE_YEAR", "lower_bound": lower[:4], "upper_bound": upper[:4]}],
        "effective_cql": f'({ROOT_CQL}) and pd within "{lower} {upper}"',
        "capture_sha256": "a" * 64,
        "coverage": {
            "reported_total_result_count": total,
            "reported_total_result_count_state": "CONSISTENT",
            "range_sequence_valid": True,
            "range_coverage_state": "MATCH",
            "over_2000_limit": False,
            "partition_required": False,
        },
        "mechanical_blockers": [],
    }


def _replay(*, first_total: int = 1200, second_total: int = 900, duplicate: bool = False) -> dict:
    normalized = [
        {
            "docdb_publication_reference": "DOCDB:EP:111:A1",
            "leaf_query_ids": ["leaf-old"],
        },
        {
            "docdb_publication_reference": "DOCDB:EP:222:A1",
            "leaf_query_ids": ["leaf-recent"],
        },
    ]
    if duplicate:
        normalized.append({
            "docdb_publication_reference": "DOCDB:EP:333:A1",
            "leaf_query_ids": ["leaf-old", "leaf-recent"],
        })
    return {
        "manifest_sha256": MANIFEST_SHA,
        "input_provenance": {"captured_at": CAPTURED_AT},
        "query_reports": [
            _leaf("leaf-old", "18000101", "20251231", first_total),
            _leaf("leaf-recent", "20260101", "20260901", second_total),
        ],
        "normalized_patents": normalized,
        "reconciliation": {
            "scope": "FULL_PROGRAMME",
            "all_logical_queries_represented": True,
            "leaf_mechanical_blocker_count": 0,
            "partition_reconciliation_required": True,
        },
    }


def _proof() -> dict:
    return {
        "schema_version": "0.1.0",
        "programme_id": "SU-PATENTS-EPO-OPS-v0.1",
        "proof_id": "OPS-PARTITION-PROOF-TEST-001",
        "replay_manifest_sha256": MANIFEST_SHA,
        "captured_at": CAPTURED_AT,
        "dated_universe_lower_bound": "18000101",
        "partition_roots": [{
            "query_id": "DISCOVERY-OPS-BCI-001",
            "applicant_term": None,
            "bounded_parent_cql": f'({ROOT_CQL}) and pd within "18000101 20260901"',
            "parent_probe_pages": [{"xml": "<synthetic-parent />"}],
            "leaf_intervals": [
                {"leaf_query_id": "leaf-old", "lower_date": "18000101", "upper_date": "20251231"},
                {"leaf_query_id": "leaf-recent", "lower_date": "20260101", "upper_date": "20260901"},
            ],
        }],
    }


def _parent_projection(total: int = 2100) -> dict:
    return {
        "result_records": [],
        "normalized_records": [],
        "coverage": {
            "reported_total_result_count": total,
            "reported_total_result_count_state": "CONSISTENT",
            "over_2000_limit": True,
            "partition_required": True,
        },
    }


class EpoOpsPatentPartitionProofTests(unittest.TestCase):
    def test_exact_dated_partition_reconciliation_can_complete(self) -> None:
        result = proofmod.build_partition_proof(
            _replay(),
            _proof(),
            projector=lambda **_: _parent_projection(),
        )
        self.assertTrue(result["dated_partition_reconciliation_complete"])
        self.assertEqual(result["root_blocker_count"], 0)
        self.assertEqual(result["root_reports"][0]["parent_reported_total_result_count"], 2100)
        self.assertEqual(result["root_reports"][0]["child_reported_total_sum"], 2100)
        self.assertFalse(result["unbounded_query_completeness_claim"])
        self.assertFalse(result["global_neuroai_patent_recall_claim"])
        self.assertFalse(result["canonical_successor_ready"])

    def test_gap_in_child_intervals_blocks_reconciliation(self) -> None:
        proof = _proof()
        proof["partition_roots"][0]["leaf_intervals"][1]["lower_date"] = "20260102"
        result = proofmod.build_partition_proof(
            _replay(), proof, projector=lambda **_: _parent_projection()
        )
        self.assertFalse(result["dated_partition_reconciliation_complete"])
        self.assertIn("PARTITION_INTERVAL_GAP", result["root_reports"][0]["blockers"])

    def test_child_denominator_sum_must_equal_parent(self) -> None:
        result = proofmod.build_partition_proof(
            _replay(first_total=1200, second_total=899),
            _proof(),
            projector=lambda **_: _parent_projection(2100),
        )
        self.assertFalse(result["dated_partition_reconciliation_complete"])
        self.assertIn("CHILD_DENOMINATOR_SUM_MISMATCH", result["root_reports"][0]["blockers"])

    def test_cross_partition_docdb_duplicate_blocks_reconciliation(self) -> None:
        result = proofmod.build_partition_proof(
            _replay(duplicate=True),
            _proof(),
            projector=lambda **_: _parent_projection(),
        )
        self.assertFalse(result["dated_partition_reconciliation_complete"])
        self.assertIn("CROSS_PARTITION_DOCDB_DUPLICATE", result["root_reports"][0]["blockers"])
        self.assertEqual(result["root_reports"][0]["cross_partition_duplicate_count"], 1)

    def test_parent_must_be_over_ops_retrieval_limit(self) -> None:
        result = proofmod.build_partition_proof(
            _replay(first_total=1000, second_total=900),
            _proof(),
            projector=lambda **_: _parent_projection(1900),
        )
        self.assertFalse(result["dated_partition_reconciliation_complete"])
        self.assertIn("PARENT_NOT_OVER_RETRIEVAL_LIMIT", result["root_reports"][0]["blockers"])

    def test_manifest_binding_is_exact(self) -> None:
        proof = copy.deepcopy(_proof())
        proof["replay_manifest_sha256"] = "2" * 64
        with self.assertRaisesRegex(ValueError, "manifest binding mismatch"):
            proofmod.build_partition_proof(_replay(), proof, projector=lambda **_: _parent_projection())

    def test_replay_must_be_full_and_logically_complete(self) -> None:
        replay = _replay()
        replay["reconciliation"]["scope"] = "PARTIAL_VALIDATION"
        result = proofmod.build_partition_proof(replay, _proof(), projector=lambda **_: _parent_projection())
        self.assertFalse(result["dated_partition_reconciliation_complete"])
        self.assertIn("REPLAY_SCOPE_NOT_FULL_PROGRAMME", result["replay_level_blockers"])

    def test_unbounded_or_global_completeness_is_never_inferred(self) -> None:
        result = proofmod.build_partition_proof(_replay(), _proof(), projector=lambda **_: _parent_projection())
        self.assertFalse(result["unbounded_query_completeness_claim"])
        self.assertFalse(result["global_neuroai_patent_recall_claim"])
        self.assertFalse(result["patent_family_completeness_claim"])
        self.assertFalse(result["automatic_source_admission"])
        self.assertFalse(result["automatic_patent_family_creation"])
        self.assertFalse(result["automatic_entity_creation"])
        self.assertFalse(result["automatic_assessment_mutation"])


if __name__ == "__main__":
    unittest.main()
