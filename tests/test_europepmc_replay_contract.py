from __future__ import annotations

import hashlib
import json
import unittest

import scripts.run_su_publications_europepmc_recorded_replay as replay


def _hash(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fake_projector(*, query_id, query_text, pages, known_publication_sources=None, known_anchor_identities=None):
    row = pages[0]["record"]
    identity = row["identity"]
    content = {
        "record_kind": "NORMALIZED_EUROPEPMC_PUBLICATION",
        "resolved_identity": identity,
        "identity_type": identity.split(":", 1)[0],
        "source": "MED",
        "ext_id": row.get("ext_id", "1"),
        "source_plus_ext_id": "MED:" + row.get("ext_id", "1"),
        "pmid": row.get("pmid"),
        "pmcid": None,
        "doi": row.get("doi"),
        "title": row.get("title", identity),
        "author_string": "Example",
        "journal_or_source": "Example Journal",
        "publication_year": "2026",
        "publication_type": "Journal Article",
        "is_preprint": False,
        "boundary": "test",
    }
    normalized = {
        **content,
        "query_memberships": [query_id],
        "normalized_record_sha256": _hash(content),
    }
    duplicate_of = (known_publication_sources or {}).get(identity)
    result = {
        "record_key": identity,
        "title": content["title"],
        "url": "https://europepmc.org/article/MED/" + content["ext_id"],
        "publisher": "Europe PMC",
        "source_class": "OFFICIAL_BIBLIOGRAPHIC_METADATA",
        "suggested_source_id": "SRC-EPMC-TEST",
        "classification_hint": "DUPLICATE" if duplicate_of else "NEW",
    }
    if duplicate_of:
        result["duplicate_of_source_id"] = duplicate_of
    coverage = {
        "supplied_page_count": 1,
        "raw_returned_record_count": 1,
        "unique_resolved_identity_count": 1,
        "reported_hit_count_state": "CONSISTENT",
        "reported_hit_count": 1,
        "cursor_sequence_valid": True,
        "terminal_cursor_state": "TERMINAL",
        "reported_total_reconciliation_state": "MATCH",
        "known_anchor_count": int(identity in set(known_anchor_identities or [])),
        "known_controlled_source_duplicate_count": int(bool(duplicate_of)),
        "new_candidate_count": int(not duplicate_of),
        "cross_query_duplicate_representation_count": 0,
        "unresolved_identity_count": 0,
        "preprint_count": 0,
        "non_preprint_record_count": 1,
        "publication_type_missing_count": 0,
        "source_distribution": {"MED": 1},
    }
    return {"result_records": [result], "normalized_records": [normalized], "coverage": coverage}


def known_index(mapping=None):
    mapping = mapping or {}
    return {
        "materialized_source_count": 248,
        "eligible_bibliographic_source_count": len(set(mapping.values())),
        "known_publication_identity_count": len(mapping),
        "identity_to_source": mapping,
    }


def capture(programme, stream, identity, title="Same"):
    provider = programme["provider_contract"]
    return {
        "query_id": stream["query_id"],
        "query_term": stream["query_term"],
        "request": {
            "endpoint": provider["api_endpoint"],
            "format": provider["format"],
            "result_type": provider["result_type"],
            "page_size": provider["page_size"],
            "synonym_expansion": provider["synonym_expansion"],
            "first_cursor_mark": provider["first_cursor_mark"],
        },
        "pages": [{"record": {"identity": identity, "doi": identity.removeprefix("DOI:"), "title": title}}],
    }


def bundle(programme, captures, scope):
    return {
        "schema_version": "0.1.0",
        "programme_id": programme["programme_id"],
        "provider": "Europe PMC",
        "capture_scope": scope,
        "captured_at": "2026-09-01T12:00:00Z",
        "raw_input_contains_full_text": False,
        "participant_level_data_expected": False,
        "query_captures": captures,
    }


class EuropePmcReplayContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programme = replay._programme()
        cls.streams = cls.programme["query_streams"]

    def test_partial_replay_remains_noncanonical(self):
        identity = "DOI:10.9999/new"
        value = bundle(self.programme, [capture(self.programme, self.streams[0], identity)], "PARTIAL_VALIDATION")
        result = replay.build_replay(value, projector=fake_projector, known_index=known_index())
        self.assertFalse(result["reconciliation"]["mechanically_complete"])
        self.assertEqual(result["reconciliation"]["new_candidate_input_count"], 1)
        self.assertFalse(result["reconciliation"]["automatic_source_admission"])
        self.assertFalse(result["reconciliation"]["canonical_successor_ready"])

    def test_full_programme_deduplicates_same_publication_across_queries(self):
        identity = "DOI:10.9999/shared"
        captures = [capture(self.programme, stream, identity) for stream in self.streams]
        result = replay.build_replay(
            bundle(self.programme, captures, "FULL_PROGRAMME"),
            projector=fake_projector,
            known_index=known_index(),
        )
        self.assertTrue(result["reconciliation"]["mechanically_complete"])
        self.assertEqual(result["reconciliation"]["union_unique_publication_identity_count"], 1)
        self.assertEqual(result["reconciliation"]["cross_query_repeat_membership_count"], 7)

    def test_known_bibliographic_identity_is_duplicate(self):
        identity = "DOI:10.9999/known"
        value = bundle(self.programme, [capture(self.programme, self.streams[0], identity)], "PARTIAL_VALIDATION")
        result = replay.build_replay(
            value,
            projector=fake_projector,
            known_index=known_index({identity: "SRC-BIB-001"}),
        )
        self.assertEqual(result["reconciliation"]["known_bibliographic_duplicate_count"], 1)
        self.assertEqual(result["known_bibliographic_duplicates"][0]["duplicate_of_source_id"], "SRC-BIB-001")

    def test_cross_query_content_conflict_fails_closed(self):
        identity = "DOI:10.9999/conflict"
        captures = [
            capture(self.programme, self.streams[0], identity, title="A"),
            capture(self.programme, self.streams[1], identity, title="B"),
        ]
        with self.assertRaisesRegex(ValueError, "Cross-query normalized-content conflict"):
            replay.build_replay(
                bundle(self.programme, captures, "PARTIAL_VALIDATION"),
                projector=fake_projector,
                known_index=known_index(),
            )


if __name__ == "__main__":
    unittest.main()
