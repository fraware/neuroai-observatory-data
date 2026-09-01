from __future__ import annotations

import unittest

from scripts.run_su_publications_europepmc_recorded_replay import _bibliographic_source_class


class EuropePmcReplaySourceClassBoundaryTests(unittest.TestCase):
    def test_explicit_bibliographic_classes_are_eligible(self) -> None:
        self.assertTrue(_bibliographic_source_class("OFFICIAL_BIBLIOGRAPHIC_METADATA"))
        self.assertTrue(_bibliographic_source_class("OFFICIAL_BIBLIOGRAPHIC_RECORD"))
        self.assertTrue(_bibliographic_source_class("PUBLICATION_RECORD"))

    def test_substantive_publication_sources_are_not_collapsed_into_metadata_sources(self) -> None:
        self.assertFalse(_bibliographic_source_class("PRIMARY_RESEARCH_PREPRINT"))
        self.assertFalse(_bibliographic_source_class("PEER_REVIEWED_PRIMARY_CLINICAL_STUDY"))
        self.assertFalse(_bibliographic_source_class("OFFICIAL_SYSTEM_OR_PUBLICATION_PAGE"))


if __name__ == "__main__":
    unittest.main()
