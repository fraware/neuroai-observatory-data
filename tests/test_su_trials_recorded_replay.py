from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_su_trials_recorded_replay as replay


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _fake_projector(
    adapter,
    *,
    query_id: str,
    query_text: str,
    pages,
    required_study_types,
    known_nct_sources,
):
    del adapter
    rows = []
    for page in pages:
        rows.extend(page.get("records", []))

    unique = {}
    duplicate_representations = 0
    for row in rows:
        nct_id = row["nct_id"]
        normalized = {
            "record_kind": "NORMALIZED_CTGOV_STUDY",
            "nct_id": nct_id,
            "brief_title": row["title"],
            "overall_status": row.get("overall_status", "RECRUITING"),
            "study_type": row.get("study_type", "INTERVENTIONAL"),
            "last_update_post_date": "2026-08-31",
            "primary_completion_date": None,
            "enrollment_count": None,
            "phase": None,
            "field_digests": {},
            "aggregate_digest": row.get("aggregate_digest", _digest(f"{nct_id}|{row['title']}")),
            "boundary": "TEST_NORMALIZED_RECORD_ONLY",
        }
        prior = unique.get(nct_id)
        if prior is None:
            unique[nct_id] = normalized
        elif prior == normalized:
            duplicate_representations += 1
        else:
            raise ValueError(f"Conflicting normalized ClinicalTrials.gov representations for {nct_id}")

    required = {value.upper() for value in required_study_types}
    normalized_records = []
    result_records = []
    excluded = []
    known_duplicates = []
    for nct_id in sorted(unique):
        normalized = unique[nct_id]
        study_type = normalized["study_type"].upper()
        if required and study_type not in required:
            excluded.append({"nct_id": nct_id, "study_type": study_type, "reason": "STUDY_TYPE_NOT_IN_PROGRAMME_SCOPE"})
            continue
        duplicate_of = known_nct_sources.get(nct_id)
        candidate = {
            "record_key": nct_id,
            "title": normalized["brief_title"],
            "url": f"https://clinicaltrials.gov/study/{nct_id}",
            "publisher": "ClinicalTrials.gov",
            "source_class": "OFFICIAL_TRIAL_REGISTRY",
            "suggested_source_id": f"SRC-CTGOV-{nct_id}",
            "classification_hint": "DUPLICATE" if duplicate_of else "NEW",
        }
        if duplicate_of:
            candidate["duplicate_of_source_id"] = duplicate_of
            known_duplicates.append({"nct_id": nct_id, "source_id": duplicate_of})
        result_records.append(candidate)
        normalized_records.append(normalized)

    total = len(unique)
    coverage = {
        "source_system": "CLINICALTRIALS_GOV",
        "adapter_id": "clinicaltrials_gov",
        "query_id": query_id,
        "query_text": query_text,
        "required_study_types": list(required_study_types),
        "supplied_page_count": len(pages),
        "raw_returned_record_count": len(rows),
        "unique_nct_record_count_before_programme_filter": total,
        "included_candidate_count": len(result_records),
        "known_nct_duplicate_count": len(known_duplicates),
        "known_nct_duplicates": known_duplicates,
        "new_candidate_count": len(result_records) - len(known_duplicates),
        "excluded_by_study_type_count": len(excluded),
        "excluded_by_study_type": excluded,
        "duplicate_nct_representation_count": duplicate_representations,
        "reported_total_count_state": "CONSISTENT",
        "reported_total_count": total,
        "reported_total_count_values": [total],
        "pagination_sequence_valid": True,
        "fully_paginated": True,
        "final_next_page_token_present": False,
        "reported_total_reconciliation_state": "MATCH",
        "page_reports": [],
        "registry_completeness_claim": False,
        "neuroai_discovery_recall_claim": False,
        "automatic_registry_mutation_performed": False,
        "boundary": "TEST_PROJECTION_BOUNDARY_ONLY",
    }
    return {
        "result_records": result_records,
        "normalized_records": normalized_records,
        "coverage": coverage,
    }


def _full_bundle(*, conflict: bool = False):
    programme = replay._programme()
    captures = []
    for stream in programme["query_streams"]:
        query_id = stream["query_id"]
        if query_id == "DISCOVERY-CTGOV-BCI-001":
            records = [
                {"nct_id": "NCT04676854", "title": "PRIMAvera"},
                {"nct_id": "NCT00001001", "title": "Cross-query BCI study", "aggregate_digest": _digest("shared")},
            ]
        elif query_id == "DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001":
            records = [
                {"nct_id": "NCT03333954", "title": "PRIMA feasibility study"},
                {
                    "nct_id": "NCT00001001",
                    "title": "Cross-query BCI study" if not conflict else "Conflicting title",
                    "aggregate_digest": _digest("shared" if not conflict else "conflict"),
                },
            ]
        elif query_id == "DISCOVERY-CTGOV-NEURAL-PROSTHESIS-001":
            records = [{"nct_id": "NCT00001002", "title": "Neural prosthesis study"}]
        else:
            records = [{"nct_id": "NCT00001003", "title": "Brain implant study"}]
        captures.append(
            {
                "query_id": query_id,
                "query_term": stream["query_term"],
                "count_total_first_page_requested": True,
                "count_total_later_pages_requested": False,
                "pages": [
                    {
                        "records": records,
                        "raw_contact_sentinel": "PRIVATE_CONTACT_SHOULD_NOT_EMIT",
                        "raw_location_sentinel": "RAW_SITE_LOCATION_SHOULD_NOT_EMIT",
                    }
                ],
            }
        )
    return {
        "schema_version": "0.1.0",
        "programme_id": "SU-TRIALS-CTGOV-v0.1",
        "capture_scope": "FULL_PROGRAMME",
        "captured_at": "2026-08-31T10:00:00Z",
        "api_data_timestamp": "2026-08-31",
        "query_captures": captures,
    }


class SUTrialsRecordedReplayTests(unittest.TestCase):
    def test_real_namespace_resolves_prima_anchor(self) -> None:
        known = replay.build_known_nct_source_index()
        self.assertEqual(known["materialized_source_count"], 248)
        self.assertEqual(known["nct_to_source"].get("NCT04676854"), "SRC-PR-002")
        self.assertGreaterEqual(known["known_ctgov_nct_count"], 1)
        self.assertFalse(known["global_completeness_claim"])

    def test_full_replay_separates_known_duplicate_and_new_candidate(self) -> None:
        result = replay.build_replay(_full_bundle(), adapter=object(), projector=_fake_projector)
        rec = result["reconciliation"]
        self.assertTrue(rec["mechanically_complete"], rec)
        self.assertEqual(rec["query_mechanical_blocker_count"], 0)
        self.assertEqual(rec["configured_active_query_count"], 4)
        self.assertEqual(rec["executed_query_count"], 4)
        self.assertEqual(rec["known_controlled_duplicate_count"], 1)
        self.assertEqual(rec["new_candidate_input_count"], 4)
        self.assertEqual(rec["cross_query_repeat_membership_count"], 1)
        self.assertFalse(rec["raw_api_page_payloads_emitted"])
        self.assertFalse(rec["participant_level_data_emitted"])
        self.assertFalse(rec["canonical_successor_ready"])

        known = {row["record_key"]: row for row in result["known_duplicates"]}
        self.assertEqual(known["NCT04676854"]["duplicate_of_source_id"], "SRC-PR-002")
        new_ids = {row["record_key"] for row in result["new_candidate_inputs"]}
        self.assertIn("NCT03333954", new_ids)
        self.assertEqual(
            next(row for row in result["normalized_studies"] if row["nct_id"] == "NCT00001001")["query_ids"],
            ["DISCOVERY-CTGOV-BCI-001", "DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001"],
        )

    def test_raw_page_fields_do_not_leak_and_output_is_deterministic(self) -> None:
        bundle = _full_bundle()
        first = replay.build_replay(bundle, adapter=object(), projector=_fake_projector)
        second = replay.build_replay(bundle, adapter=object(), projector=_fake_projector)
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            json.dumps(second, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )
        serialized = json.dumps(first, sort_keys=True)
        self.assertNotIn("PRIVATE_CONTACT_SHOULD_NOT_EMIT", serialized)
        self.assertNotIn("RAW_SITE_LOCATION_SHOULD_NOT_EMIT", serialized)

        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ma = replay.write_projection(first, Path(a))
            mb = replay.write_projection(second, Path(b))
            self.assertEqual(ma["manifest_sha256"], mb["manifest_sha256"])
            for root in (Path(a), Path(b)):
                output_text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.iterdir()))
                self.assertNotIn("PRIVATE_CONTACT_SHOULD_NOT_EMIT", output_text)
                self.assertNotIn("RAW_SITE_LOCATION_SHOULD_NOT_EMIT", output_text)
                self.assertFalse((root / "raw-pages.json").exists())

    def test_cross_query_conflicting_same_nct_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Cross-query conflict for NCT00001001"):
            replay.build_replay(_full_bundle(conflict=True), adapter=object(), projector=_fake_projector)

    def test_partial_validation_never_becomes_mechanically_complete(self) -> None:
        bundle = _full_bundle()
        bundle["capture_scope"] = "PARTIAL_VALIDATION"
        bundle["query_captures"] = bundle["query_captures"][:1]
        result = replay.build_replay(bundle, adapter=object(), projector=_fake_projector)
        self.assertFalse(result["reconciliation"]["all_active_queries_executed"])
        self.assertFalse(result["reconciliation"]["mechanically_complete"])

    def test_request_policy_mismatch_is_a_mechanical_blocker(self) -> None:
        bundle = _full_bundle()
        bundle["query_captures"][0]["count_total_first_page_requested"] = False
        result = replay.build_replay(bundle, adapter=object(), projector=_fake_projector)
        self.assertGreater(result["reconciliation"]["query_mechanical_blocker_count"], 0)
        self.assertFalse(result["reconciliation"]["mechanically_complete"])

    def test_missing_s1_capability_fails_explicitly(self) -> None:
        with patch.object(
            replay,
            "_load_workbench_capability",
            side_effect=RuntimeError("Required Workbench capability unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Required Workbench capability unavailable"):
                replay.build_replay(_full_bundle())


if __name__ == "__main__":
    unittest.main()
