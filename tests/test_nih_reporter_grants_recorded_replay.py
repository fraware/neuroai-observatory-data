from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import run_su_grants_nih_reporter_recorded_replay as replay


def _query_payload(stream: dict, *, partition: bool = False) -> dict:
    criteria = {"advanced_text_search": stream["advanced_text_search"]}
    if partition:
        criteria["fiscal_years"] = [2026]
    return {"criteria": criteria, "offset": 0, "limit": 500}


def _capture(stream: dict, *, leaf: str | None = None, partition: bool = False) -> dict:
    return {
        "query_id": stream["query_id"],
        "leaf_query_id": leaf or f"{stream['query_id']}-root",
        "query_payload": _query_payload(stream, partition=partition),
        "partition_path": [{"dimension": "FISCAL_YEAR", "value": 2026}] if partition else [],
        "pages": [{"meta": {"total": 1, "offset": 0, "limit": 500}, "results": [{"appl_id": 1}]}],
    }


def _bundle(captures: list[dict], *, scope: str = "PARTIAL_VALIDATION") -> dict:
    programme = replay._programme()
    return {
        "schema_version": "0.1.0",
        "programme_id": programme["programme_id"],
        "provider": programme["provider_contract"]["provider"],
        "capture_scope": scope,
        "captured_at": "2026-09-01T00:00:00Z",
        "leaf_query_captures": captures,
    }


def _projection(appl_id: int = 1, *, digest: str | None = None, duplicate: str | None = None) -> dict:
    digest = digest or hashlib.sha256(f"grant-{appl_id}".encode()).hexdigest()
    normalized = {
        "record_kind": "NORMALIZED_NIH_REPORTER_GRANT_APPLICATION",
        "appl_id": appl_id,
        "project_num": f"R01-{appl_id}",
        "core_project_num": f"R01-CORE-{appl_id}",
        "subproject_id": None,
        "fiscal_year": 2026,
        "project_title": f"Synthetic grant {appl_id}",
        "abstract_text": "Synthetic controlled fixture",
        "project_start_date": None,
        "project_end_date": None,
        "award_notice_date": None,
        "award_amount": 1,
        "funding_mechanism": None,
        "agency_ic_admin": None,
        "organization": None,
        "principal_investigators": None,
        "query_memberships": ["fixture"],
        "normalized_record_sha256": digest,
    }
    record = {
        "record_key": f"REPORTER:APPL:{appl_id}",
        "title": normalized["project_title"],
        "url": f"https://reporter.nih.gov/project-details/{appl_id}",
        "publisher": "NIH RePORTER",
        "source_class": "OFFICIAL_GRANT_DATABASE",
        "suggested_source_id": f"SRC-REPORTER-APPL-{appl_id}",
        "classification_hint": "DUPLICATE" if duplicate else "NEW",
    }
    if duplicate:
        record["duplicate_of_source_id"] = duplicate
    coverage = {
        "supplied_page_count": 1,
        "returned_record_count": 1,
        "unique_appl_id_count": 1,
        "reported_total_count": 1,
        "reported_total_count_state": "CONSISTENT",
        "offset_sequence_valid": True,
        "offset_coverage_state": "MATCH",
        "over_15000_limit": False,
        "partition_required": False,
        "candidate_emission_refused_due_to_over_limit": False,
        "known_controlled_duplicate_count": 1 if duplicate else 0,
        "new_candidate_count": 0 if duplicate else 1,
        "duplicate_representation_count": 0,
        "unresolved_appl_id_count": 0,
    }
    return {"result_records": [record], "normalized_records": [normalized], "coverage": coverage}


def _known(mapping: dict[int, str] | None = None) -> dict:
    mapping = mapping or {}
    return {
        "materialized_source_count": 248,
        "grant_typed_source_count": len(mapping),
        "known_reporter_appl_id_count": len(mapping),
        "appl_to_source": {str(k): v for k, v in mapping.items()},
        "appl_lineage": {},
        "global_grant_completeness_claim": False,
    }


class NihReporterRecordedReplayTests(unittest.TestCase):
    def test_real_source_namespace_materializes_248(self) -> None:
        index = replay.build_known_appl_source_index()
        self.assertEqual(index["materialized_source_count"], 248)
        self.assertFalse(index["global_grant_completeness_claim"])

    def test_partial_replay_is_noncanonical(self) -> None:
        stream = replay._programme()["query_streams"][0]
        result = replay.build_replay(_bundle([_capture(stream)]), projector=lambda **_: _projection(), known_index=_known())
        rec = result["reconciliation"]
        self.assertEqual(rec["new_candidate_input_count"], 1)
        self.assertFalse(rec["mechanically_complete"])
        self.assertFalse(rec["canonical_successor_ready"])
        self.assertFalse(rec["automatic_pi_or_organization_entity_creation"])
        self.assertFalse(rec["automatic_funding_success_claim_creation"])

    def test_known_exact_appl_id_is_preserved_as_duplicate(self) -> None:
        stream = replay._programme()["query_streams"][0]
        result = replay.build_replay(
            _bundle([_capture(stream)]),
            projector=lambda **_: _projection(1, duplicate="SRC-GRANT-001"),
            known_index=_known({1: "SRC-GRANT-001"}),
        )
        self.assertEqual(result["reconciliation"]["known_controlled_duplicate_count"], 1)
        self.assertEqual(result["reconciliation"]["new_candidate_input_count"], 0)
        self.assertEqual(result["known_duplicates"][0]["duplicate_of_source_id"], "SRC-GRANT-001")

    def test_cross_query_same_application_unions_memberships(self) -> None:
        streams = replay._programme()["query_streams"][:2]
        result = replay.build_replay(
            _bundle([_capture(streams[0], leaf="a"), _capture(streams[1], leaf="b")]),
            projector=lambda **_: _projection(1),
            known_index=_known(),
        )
        self.assertEqual(result["reconciliation"]["union_unique_appl_id_count"], 1)
        self.assertEqual(result["normalized_grants"][0]["query_memberships"], sorted([s["query_id"] for s in streams]))

    def test_cross_query_content_conflict_fails_closed(self) -> None:
        streams = replay._programme()["query_streams"][:2]
        calls = iter([_projection(1, digest="a" * 64), _projection(1, digest="b" * 64)])
        with self.assertRaisesRegex(ValueError, "content conflict"):
            replay.build_replay(
                _bundle([_capture(streams[0], leaf="a"), _capture(streams[1], leaf="b")]),
                projector=lambda **_: next(calls),
                known_index=_known(),
            )

    def test_partitioned_leaf_requires_separate_reconciliation(self) -> None:
        stream = replay._programme()["query_streams"][0]
        result = replay.build_replay(
            _bundle([_capture(stream, partition=True)]),
            projector=lambda **_: _projection(),
            known_index=_known(),
        )
        self.assertTrue(result["reconciliation"]["partition_reconciliation_required"])
        self.assertFalse(result["reconciliation"]["mechanically_complete"])

    def test_full_programme_can_be_mechanically_complete_without_partitions(self) -> None:
        streams = replay._programme()["query_streams"]
        by_query = {stream["query_id"]: index + 1 for index, stream in enumerate(streams)}
        captures = [_capture(stream, leaf=f"leaf-{index}") for index, stream in enumerate(streams)]

        def projector(*, query_id: str, **_: object) -> dict:
            return _projection(by_query[query_id])

        result = replay.build_replay(_bundle(captures, scope="FULL_PROGRAMME"), projector=projector, known_index=_known())
        self.assertEqual(result["reconciliation"]["leaf_mechanical_blocker_count"], 0)
        self.assertTrue(result["reconciliation"]["all_logical_queries_represented"])
        self.assertTrue(result["reconciliation"]["mechanically_complete"])
        self.assertFalse(result["reconciliation"]["global_neuroai_grant_recall_claim"])
        self.assertFalse(result["reconciliation"]["canonical_successor_ready"])

    def test_writer_is_deterministic_and_never_emits_raw_pages(self) -> None:
        stream = replay._programme()["query_streams"][0]
        result = replay.build_replay(_bundle([_capture(stream)]), projector=lambda **_: _projection(), known_index=_known())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            first = replay.write_projection(result, out)
            bytes_one = {path.name: path.read_bytes() for path in out.iterdir()}
            second = replay.write_projection(result, out)
            bytes_two = {path.name: path.read_bytes() for path in out.iterdir()}
            self.assertEqual(first, second)
            self.assertEqual(bytes_one, bytes_two)
            self.assertFalse(any("raw" in name.lower() or "page" in name.lower() for name in bytes_one))
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertFalse(manifest["raw_provider_pages_included"])
            self.assertFalse(manifest["canonical_successor_ready"])


if __name__ == "__main__":
    unittest.main()
