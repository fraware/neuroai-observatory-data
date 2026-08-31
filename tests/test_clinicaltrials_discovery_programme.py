from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_clinicaltrials_discovery_programme as programme


class ClinicalTrialsDiscoveryProgrammeTests(unittest.TestCase):
    def test_programme_is_bounded_and_cross_reconciled(self) -> None:
        result = programme.validate()
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["programme_id"], "SU-TRIALS-CTGOV-v0.1")
        self.assertEqual(result["query_stream_count"], 4)
        self.assertEqual(
            set(result["query_stream_ids"]),
            {
                "DISCOVERY-CTGOV-BCI-001",
                "DISCOVERY-CTGOV-NEURAL-PROSTHESIS-001",
                "DISCOVERY-CTGOV-BRAIN-IMPLANT-001",
                "DISCOVERY-CTGOV-RETINAL-VISUAL-PROSTHESIS-001",
            },
        )
        self.assertEqual(result["known_anchor_count"], 1)
        self.assertTrue(result["count_total_first_page_required"])
        self.assertTrue(result["total_count_reconciliation_required"])
        self.assertEqual(result["workbench_integration_state"], "PENDING_S1_MERGE")
        self.assertFalse(result["automatic_mutation_enabled"])
        self.assertFalse(result["registry_completeness_claim"])
        self.assertFalse(result["global_neuroai_trial_recall_claim"])


if __name__ == "__main__":
    unittest.main()
