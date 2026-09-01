from __future__ import annotations

import unittest

import scripts.run_su_publications_europepmc_recorded_replay as replay


class EuropePmcReplayKnownIndexTests(unittest.TestCase):
    def test_real_index_uses_bibliographic_sources_only(self) -> None:
        known = replay.build_known_publication_source_index()
        self.assertEqual(known["materialized_source_count"], 248)
        self.assertEqual(known["identity_to_source"].get("PMID:41124203"), "SRC-PR-013")
        self.assertNotEqual(
            known["identity_to_source"].get("DOI:10.1056/nejmoa2501396"),
            "SRC-PR-001",
        )
        self.assertFalse(known["source_admission_completeness_claim"])
        self.assertFalse(known["publication_universe_completeness_claim"])


if __name__ == "__main__":
    unittest.main()
