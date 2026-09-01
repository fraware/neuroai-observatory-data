from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path("scripts/run_su_patents_epo_ops_recorded_replay.py")
spec = importlib.util.spec_from_file_location("epo_replay_current", MODULE_PATH)
assert spec and spec.loader
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def _known(mapping: dict[str, str] | None = None) -> dict:
    mapping = mapping or {}
    return {
        "materialized_source_count": 248,
        "source_id_set_sha256": "a" * 64,
        "patent_typed_source_count": len(set(mapping.values())),
        "known_docdb_publication_count": len(mapping),
        "docdb_to_source": mapping,
        "docdb_lineage": {},
        "global_patent_completeness_claim": False,
    }


def _capture(query_id: str, cql: str, *, leaf: str = "leaf-1", applicant: str | None = None, partition: list | None = None) -> dict:
    return {
        "query_id": query_id,
        "leaf_query_id": leaf,
        "effective_cql": cql,
        "applicant_term": applicant,
        "partition_path": partition or [],
        "search_constituent": "biblio",
        "response_media_type": "application/exchange+xml",
        "range_transport": "X-OPS-Range",
        "pages": [{"xml": "<synthetic />"}],
    }


def _bundle(captures: list[dict], scope: str = "PARTIAL_VALIDATION") -> dict:
    return {
        "schema_version": "0.1.0",
        "programme_id": "SU-PATENTS-EPO-OPS-v0.1",
        "capture_scope": scope,
        "captured_at": "2026-09-02T00:00:00Z",
        "provider": "European Patent Office Open Patent Services",
        "leaf_query_captures": captures,
    }


def _projection(identity: str = "DOCDB:EP:1234567:A1", *, duplicate: str | None = None, digest: str = "a" * 64) -> dict:
    country, number, kind = identity.split(":")[1:]
    normalized = {
        "docdb_publication_reference": identity,
        "country": country,
        "document_number": number,
        "kind_code": kind,
        "title": "Synthetic patent",
        "publication_date": "20260801",
        "applicants": ["Example Applicant"],
        "inventors": [],
        "ipc_symbols": [],
        "cpc_symbols": [],
        "application_references": [],
        "priority_references": [],
        "query_memberships": ["synthetic"],
        "normalized_record_sha256": digest,
    }
    record = {
        "record_key": identity,
        "title": "Synthetic patent",
        "url": "https://worldwide.espacenet.com/patent/search?q=pn%3DEP1234567A1",
        "publisher": "European Patent Office Open Patent Services",
        "source_class": "OFFICIAL_PATENT_BIBLIOGRAPHIC_METADATA",
        "suggested_source_id": "SRC-OPS-SYNTHETIC",
        "classification_hint": "DUPLICATE" if duplicate else "NEW",
    }
    if duplicate:
        record["duplicate_of_source_id"] = duplicate
    coverage = {
        "requested_range_count": 1,
        "returned_publication_reference_count": 1,
        "unique_docdb_publication_count": 1,
        "reported_total_result_count": 1,
        "reported_total_result_count_state": "CONSISTENT",
        "range_sequence_valid": True,
        "range_coverage_state": "MATCH",
        "over_2000_limit": False,
        "partition_required": False,
        "known_controlled_duplicate_count": 1 if duplicate else 0,
        "new_candidate_count": 0 if duplicate else 1,
        "cross_query_duplicate_representation_count": 0,
        "unresolved_docdb_identity_count": 0,
        "candidate_emission_refused_due_to_over_limit": False,
    }
    return {"result_records": [record], "normalized_records": [normalized], "coverage": coverage}


class EpoOpsPatentRecordedReplayTests(unittest.TestCase):
    def test_real_namespace_is_exact_and_digest_bound(self) -> None:
        index = replay.build_known_docdb_source_index()
        self.assertEqual(index["materialized_source_count"], 248)
        self.assertEqual(len(index["source_id_set_sha256"]), 64)
        self.assertFalse(index["global_patent_completeness_claim"])

    def test_docdb_locator_extraction_requires_explicit_identity(self) -> None:
        self.assertEqual(replay._docdb_identities_from_locator("https://example.invalid/DOCDB:EP:1234567:A1"), {"DOCDB:EP:1234567:A1"})
        self.assertEqual(replay._docdb_identities_from_locator("https://example.invalid?id=EP1234567A1"), set())

    def test_partial_replay_is_noncanonical(self) -> None:
        q = next(row for row in replay._programme()["query_streams"] if row["query_id"] == "DISCOVERY-OPS-BCI-001")
        result = replay.build_replay(_bundle([_capture(q["query_id"], q["cql"])]), projector=lambda **_: _projection(), known_index=_known())
        self.assertEqual(result["reconciliation"]["new_candidate_input_count"], 1)
        self.assertEqual(result["reconciliation"]["controlled_source_id_set_sha256"], "a" * 64)
        self.assertFalse(result["reconciliation"]["mechanically_complete"])
        self.assertFalse(result["reconciliation"]["canonical_successor_ready"])

    def test_exact_known_docdb_is_duplicate(self) -> None:
        q = next(row for row in replay._programme()["query_streams"] if row["query_id"] == "DISCOVERY-OPS-BCI-001")
        identity = "DOCDB:EP:1234567:A1"
        result = replay.build_replay(_bundle([_capture(q["query_id"], q["cql"])]), projector=lambda **_: _projection(identity, duplicate="SRC-PAT-001"), known_index=_known({identity: "SRC-PAT-001"}))
        self.assertEqual(result["known_duplicates"][0]["duplicate_of_source_id"], "SRC-PAT-001")
        self.assertEqual(result["reconciliation"]["new_candidate_input_count"], 0)

    def test_partitioned_leaf_requires_separate_proof(self) -> None:
        q = next(row for row in replay._programme()["query_streams"] if row["query_id"] == "DISCOVERY-OPS-BCI-001")
        cql = f'({q["cql"]}) and pd within "20260101 20261231"'
        capture = _capture(q["query_id"], cql, partition=[{"dimension": "PUBLICATION_DATE_YEAR", "lower_bound": "2026", "upper_bound": "2026"}])
        result = replay.build_replay(_bundle([capture]), projector=lambda **_: _projection(), known_index=_known())
        self.assertTrue(result["reconciliation"]["partition_reconciliation_required"])
        self.assertFalse(result["reconciliation"]["mechanically_complete"])

    def test_partition_cql_must_be_exact_root_plus_date_interval(self) -> None:
        q = next(row for row in replay._programme()["query_streams"] if row["query_id"] == "DISCOVERY-OPS-BCI-001")
        bad = _capture(q["query_id"], f'({q["cql"]}) and foo=bar and pd within "20260101 20261231"', partition=[{"dimension": "PUBLICATION_DATE_YEAR", "lower_bound": "2026", "upper_bound": "2026"}])
        with self.assertRaisesRegex(ValueError, "exact root plus pd within"):
            replay.build_replay(_bundle([bad]), projector=lambda **_: _projection(), known_index=_known())

    def test_applicant_watch_requires_declared_term(self) -> None:
        q = next(row for row in replay._programme()["query_streams"] if row["query_id"] == "DISCOVERY-OPS-KNOWN-APPLICANTS-001")
        term = q["applicant_terms"][0]
        root = q["cql_template"].format(applicant_term=term)
        result = replay.build_replay(_bundle([_capture(q["query_id"], root, applicant=term)]), projector=lambda **_: _projection(), known_index=_known())
        self.assertNotIn(term, result["reconciliation"]["missing_applicant_terms"])
        bad = _capture(q["query_id"], root, applicant="Not in watch set")
        with self.assertRaisesRegex(ValueError, "invalid applicant_term"):
            replay.build_replay(_bundle([bad]), projector=lambda **_: _projection(), known_index=_known())

    def test_cross_leaf_content_conflict_fails_closed(self) -> None:
        programme = replay._programme()
        q1 = next(row for row in programme["query_streams"] if row["query_id"] == "DISCOVERY-OPS-BCI-001")
        q2 = next(row for row in programme["query_streams"] if row["query_id"] == "DISCOVERY-OPS-NEURAL-DECODING-AI-001")
        calls = iter([_projection(digest="a" * 64), _projection(digest="b" * 64)])
        with self.assertRaisesRegex(ValueError, "Cross-leaf conflict"):
            replay.build_replay(_bundle([_capture(q1["query_id"], q1["cql"], leaf="leaf-1"), _capture(q2["query_id"], q2["cql"], leaf="leaf-2")]), projector=lambda **_: next(calls), known_index=_known())

    def test_writer_is_deterministic_and_never_emits_raw_xml(self) -> None:
        q = next(row for row in replay._programme()["query_streams"] if row["query_id"] == "DISCOVERY-OPS-BCI-001")
        result = replay.build_replay(_bundle([_capture(q["query_id"], q["cql"])]), projector=lambda **_: _projection(), known_index=_known())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            first = replay.write_projection(result, out)
            second = replay.write_projection(result, out)
            self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
            self.assertFalse(first["raw_ops_xml_emitted"])
            self.assertFalse(first["canonical_successor_ready"])
            self.assertFalse(any(path.suffix.lower() == ".xml" for path in out.iterdir()))

    def test_no_authority_escalation(self) -> None:
        q = next(row for row in replay._programme()["query_streams"] if row["query_id"] == "DISCOVERY-OPS-BCI-001")
        reconciliation = replay.build_replay(_bundle([_capture(q["query_id"], q["cql"])]), projector=lambda **_: _projection(), known_index=_known())["reconciliation"]
        for key in ("automatic_source_admission", "automatic_patent_family_creation", "automatic_applicant_or_inventor_entity_creation", "automatic_product_or_system_relationship_creation", "automatic_capability_claim_creation", "automatic_assessment_mutation", "global_neuroai_patent_recall_claim", "epo_database_completeness_claim", "patent_family_completeness_claim", "canonical_successor_ready"):
            self.assertFalse(reconciliation[key], key)


if __name__ == "__main__":
    unittest.main()
