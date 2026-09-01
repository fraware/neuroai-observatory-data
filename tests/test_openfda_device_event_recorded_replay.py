from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import run_su_regulation_openfda_device_events_recorded_replay as replay

SOURCE_DIGEST = "a" * 64


def _capture(stream: dict, *, leaf: str | None = None, partition: tuple[str, str] | None = None) -> dict:
    search = stream["search"]
    path: list[dict] = []
    if partition is not None:
        lower, upper = partition
        path = [{"dimension": "DATE_RECEIVED", "lower_bound": lower, "upper_bound": upper}]
        search = f"({search})+AND+date_received:[{lower}+TO+{upper}]"
    return {
        "query_id": stream["query_id"],
        "leaf_query_id": leaf or f"{stream['query_id']}-root",
        "effective_search": search,
        "partition_path": path,
        "pages": [{"meta": {"results": {"total": 1, "skip": 0, "limit": 1000}}, "results": [{"mdr_report_key": "1"}]}],
    }


def _bundle(captures: list[dict], *, scope: str = "PARTIAL_VALIDATION") -> dict:
    programme = replay._programme()
    return {
        "schema_version": "0.1.0",
        "programme_id": programme["programme_id"],
        "provider": programme["provider_contract"]["provider"],
        "capture_scope": scope,
        "captured_at": "2026-09-02T00:00:00Z",
        "leaf_query_captures": captures,
    }


def _projection(key: str = "1", *, digest: str | None = None, duplicate: str | None = None) -> dict:
    digest = digest or hashlib.sha256(f"mdr-{key}".encode()).hexdigest()
    normalized = {
        "record_kind": "NORMALIZED_OPENFDA_MAUDE_DEVICE_EVENT_REPORT",
        "mdr_report_key": key,
        "report_number": f"R-{key}",
        "date_received": "20260801",
        "report_date": "20260731",
        "event_type": "Malfunction",
        "product_problems": [],
        "source_type": [],
        "remedial_action": [],
        "removal_correction_number": None,
        "devices": [],
        "query_memberships": ["fixture"],
        "patient_level_fields_included": False,
        "mdr_text_narrative_included": False,
        "normalized_record_sha256": digest,
    }
    record = {
        "record_key": f"MAUDE:MDR:{key}",
        "title": f"MAUDE device adverse-event report {key}",
        "url": f'https://api.fda.gov/device/event.json?search=mdr_report_key:"{key}"&limit=1',
        "publisher": "U.S. FDA / openFDA",
        "source_class": "OFFICIAL_REGULATORY_POSTMARKET_REPORT",
        "suggested_source_id": f"SRC-MAUDE-MDR-{key}",
        "classification_hint": "DUPLICATE" if duplicate else "NEW",
    }
    if duplicate:
        record["duplicate_of_source_id"] = duplicate
    coverage = {
        "supplied_page_count": 1,
        "returned_record_count": 1,
        "unique_mdr_report_key_count": 1,
        "reported_total_count": 1,
        "reported_total_count_state": "CONSISTENT",
        "skip_sequence_valid": True,
        "skip_coverage_state": "MATCH",
        "over_26000_limit": False,
        "search_after_or_partition_required": False,
        "candidate_emission_refused_due_to_over_limit": False,
        "known_controlled_duplicate_count": 1 if duplicate else 0,
        "new_candidate_count": 0 if duplicate else 1,
        "duplicate_representation_count": 0,
        "unresolved_mdr_report_key_count": 0,
        "patient_level_fields_projected": False,
        "mdr_text_narrative_projected": False,
    }
    return {"result_records": [record], "normalized_records": [normalized], "coverage": coverage}


def _known(mapping: dict[str, str] | None = None) -> dict:
    mapping = mapping or {}
    return {
        "materialized_source_count": 248,
        "source_id_set_sha256": SOURCE_DIGEST,
        "postmarket_typed_source_count": len(mapping),
        "known_mdr_report_key_count": len(mapping),
        "mdr_to_source": mapping,
        "mdr_lineage": {},
        "global_postmarket_completeness_claim": False,
    }


class OpenFdaDeviceEventRecordedReplayTests(unittest.TestCase):
    def test_real_source_namespace_binds_248_and_digest(self) -> None:
        index = replay.build_known_mdr_source_index()
        self.assertEqual(index["materialized_source_count"], 248)
        self.assertRegex(index["source_id_set_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(index["global_postmarket_completeness_claim"])

    def test_partial_replay_is_noncanonical_and_minimized(self) -> None:
        stream = replay._programme()["query_streams"][0]
        result = replay.build_replay(_bundle([_capture(stream)]), projector=lambda **_: _projection(), known_index=_known())
        rec = result["reconciliation"]
        self.assertEqual(rec["new_candidate_input_count"], 1)
        self.assertEqual(rec["controlled_source_id_set_sha256"], SOURCE_DIGEST)
        self.assertFalse(rec["mechanically_complete"])
        self.assertFalse(rec["patient_level_fields_emitted"])
        self.assertFalse(rec["mdr_text_narratives_emitted"])
        self.assertFalse(rec["causality_claim"])
        self.assertFalse(rec["incidence_or_rate_claim"])
        self.assertFalse(rec["comparative_safety_claim"])
        self.assertFalse(rec["canonical_successor_ready"])

    def test_known_exact_mdr_is_preserved_as_duplicate(self) -> None:
        stream = replay._programme()["query_streams"][0]
        result = replay.build_replay(
            _bundle([_capture(stream)]),
            projector=lambda **_: _projection("777", duplicate="SRC-MAUDE-777"),
            known_index=_known({"777": "SRC-MAUDE-777"}),
        )
        self.assertEqual(result["reconciliation"]["known_controlled_duplicate_count"], 1)
        self.assertEqual(result["reconciliation"]["new_candidate_input_count"], 0)
        self.assertEqual(result["known_duplicates"][0]["duplicate_of_source_id"], "SRC-MAUDE-777")

    def test_cross_query_same_report_unions_memberships(self) -> None:
        streams = replay._programme()["query_streams"][:2]
        result = replay.build_replay(
            _bundle([_capture(streams[0], leaf="a"), _capture(streams[1], leaf="b")]),
            projector=lambda **_: _projection("1"),
            known_index=_known(),
        )
        self.assertEqual(result["reconciliation"]["union_unique_mdr_report_key_count"], 1)
        self.assertEqual(result["normalized_mdr_reports"][0]["query_memberships"], sorted([s["query_id"] for s in streams]))

    def test_cross_query_content_or_classification_conflict_fails_closed(self) -> None:
        streams = replay._programme()["query_streams"][:2]
        calls = iter([_projection("1", digest="a" * 64), _projection("1", digest="b" * 64)])
        with self.assertRaisesRegex(ValueError, "Cross-leaf conflict"):
            replay.build_replay(
                _bundle([_capture(streams[0], leaf="a"), _capture(streams[1], leaf="b")]),
                projector=lambda **_: next(calls),
                known_index=_known(),
            )

    def test_partitioned_leaf_is_exactly_bound_and_never_completes_programme(self) -> None:
        stream = replay._programme()["query_streams"][0]
        result = replay.build_replay(
            _bundle([_capture(stream, partition=("20260101", "20260902"))]),
            projector=lambda **_: _projection(),
            known_index=_known(),
        )
        self.assertTrue(result["reconciliation"]["partition_reconciliation_required"])
        self.assertFalse(result["reconciliation"]["mechanically_complete"])

        bad = _capture(stream, partition=("20260101", "20260902"))
        bad["effective_search"] = stream["search"]
        with self.assertRaisesRegex(ValueError, "partitioned effective_search"):
            replay.build_replay(_bundle([bad]), projector=lambda **_: _projection(), known_index=_known())

    def test_invalid_calendar_partition_date_fails_closed(self) -> None:
        stream = replay._programme()["query_streams"][0]
        capture = _capture(stream, partition=("20260230", "20260902"))
        with self.assertRaisesRegex(ValueError, "valid YYYYMMDD"):
            replay.build_replay(_bundle([capture]), projector=lambda **_: _projection(), known_index=_known())

    def test_full_unpartitioned_programme_can_be_mechanically_complete_only_with_clean_leaves(self) -> None:
        streams = replay._programme()["query_streams"]
        mapping = {stream["query_id"]: str(index + 1) for index, stream in enumerate(streams)}
        captures = [_capture(stream, leaf=f"leaf-{index}") for index, stream in enumerate(streams)]
        result = replay.build_replay(
            _bundle(captures, scope="FULL_PROGRAMME"),
            projector=lambda *, query_id, **_: _projection(mapping[query_id]),
            known_index=_known(),
        )
        rec = result["reconciliation"]
        self.assertEqual(rec["leaf_mechanical_blocker_count"], 0)
        self.assertTrue(rec["all_logical_queries_represented"])
        self.assertTrue(rec["mechanically_complete"])
        self.assertFalse(rec["global_neuroai_postmarket_recall_claim"])
        self.assertFalse(rec["canonical_successor_ready"])

    def test_minimization_violation_fails_closed_even_if_coverage_flags_are_clean(self) -> None:
        stream = replay._programme()["query_streams"][0]
        bad = _projection()
        bad["normalized_records"][0]["patient_level_fields_included"] = True
        with self.assertRaisesRegex(ValueError, "minimized metadata boundary violated"):
            replay.build_replay(_bundle([_capture(stream)]), projector=lambda **_: bad, known_index=_known())

    def test_writer_is_deterministic_and_never_emits_raw_or_patient_payloads(self) -> None:
        stream = replay._programme()["query_streams"][0]
        result = replay.build_replay(_bundle([_capture(stream)]), projector=lambda **_: _projection(), known_index=_known())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            first = replay.write_projection(result, out)
            first_bytes = {p.name: p.read_bytes() for p in out.iterdir()}
            second = replay.write_projection(result, out)
            second_bytes = {p.name: p.read_bytes() for p in out.iterdir()}
            self.assertEqual(first, second)
            self.assertEqual(first_bytes, second_bytes)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertFalse(manifest["raw_reporter_pages_emitted"])
            self.assertFalse(manifest["patient_level_fields_emitted"])
            self.assertFalse(manifest["mdr_text_narratives_emitted"])
            self.assertFalse(manifest["canonical_successor_ready"])
            self.assertFalse(any("raw" in p.name.lower() for p in out.iterdir()))


if __name__ == "__main__":
    unittest.main()
