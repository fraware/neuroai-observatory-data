from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_successor_discovery import (
    DEFAULT_WATCH_CONFIG,
    discover_from_html,
    verify_watch_config,
)
from source_lifecycle_overlay import DEFAULT_LIFECYCLE_OVERLAY, load_json


class SuccessorDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.overlay = load_json(DEFAULT_LIFECYCLE_OVERLAY)
        cls.config = load_json(DEFAULT_WATCH_CONFIG)
        cls.watches = verify_watch_config(cls.config, cls.overlay)
        cls.watch = cls.watches["DISC-SCIENCE-CAREERS-001"]

    def test_watch_is_exactly_bound_to_lifecycle_transition(self) -> None:
        self.assertEqual(set(self.watches), {"DISC-SCIENCE-CAREERS-001"})
        self.assertEqual(self.watch["trigger_source_id"], "SRC-PR-015")
        self.assertEqual(self.watch["trigger_lifecycle_state"], "NO_LONGER_LISTED")
        self.assertEqual(
            self.watch["trigger_transition_sha256"],
            self.overlay["transitions"][0]["transition_sha256"],
        )
        self.assertEqual(self.watch["official_host"], "science.xyz")

    def test_relevant_official_link_creates_candidate_only(self) -> None:
        body = b"""<html><body>
        <a href="/careers/prima-vision-rehabilitation-research-specialist-99">
          PRIMA Vision Rehabilitation Research Specialist
        </a>
        </body></html>"""
        candidates = discover_from_html(self.watch, body)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertTrue(candidate["url"].startswith("https://science.xyz/"))
        self.assertIn("vision", candidate["matched_domain_terms"])
        self.assertTrue(candidate["matched_context_terms"])
        self.assertFalse(candidate["canonical_source_created"])
        self.assertFalse(candidate["assessment_mutation_authorized"])
        self.assertFalse(candidate["registration_authorized"])

    def test_domain_only_or_context_only_links_are_not_candidates(self) -> None:
        body = b"""<html><body>
        <a href="/careers/vision-prima-retina-1">Vision PRIMA Retina</a>
        <a href="/careers/research-engineer-2">Research Engineer</a>
        </body></html>"""
        self.assertEqual(discover_from_html(self.watch, body), [])

    def test_external_links_are_ignored(self) -> None:
        body = b"""<html><body>
        <a href="https://example.org/vision-rehabilitation-research-specialist">
          Vision Rehabilitation Research Specialist
        </a>
        </body></html>"""
        self.assertEqual(discover_from_html(self.watch, body), [])

    def test_candidate_identity_is_deterministic_and_deduplicated(self) -> None:
        body = b"""<html><body>
        <a href="/careers/vision-rehabilitation-research-specialist-99">Vision Rehabilitation Research Specialist</a>
        <a href="/careers/vision-rehabilitation-research-specialist-99">Vision Rehabilitation Research Specialist</a>
        </body></html>"""
        first = discover_from_html(self.watch, body)
        second = discover_from_html(self.watch, body)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertTrue(first[0]["candidate_id"].startswith("DISC-CAND-"))

    def test_overlay_binding_drift_fails_closed(self) -> None:
        config = copy.deepcopy(self.config)
        config["metadata"]["lifecycle_overlay_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "overlay binding mismatch"):
            verify_watch_config(config, self.overlay)

    def test_auto_registration_or_assessment_mutation_fails_closed(self) -> None:
        for field in ("automatic_source_registration", "automatic_assessment_mutation"):
            config = copy.deepcopy(self.config)
            config["metadata"][field] = True
            with self.assertRaisesRegex(ValueError, "must forbid"):
                verify_watch_config(config, self.overlay)

    def test_trigger_transition_drift_fails_closed(self) -> None:
        config = copy.deepcopy(self.config)
        config["watches"][0]["trigger_transition_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "transition hash mismatch"):
            verify_watch_config(config, self.overlay)

    def test_watch_must_remain_on_declared_official_https_host(self) -> None:
        config = copy.deepcopy(self.config)
        config["watches"][0]["url"] = "https://example.org/careers"
        with self.assertRaisesRegex(ValueError, "official HTTPS host"):
            verify_watch_config(config, self.overlay)


if __name__ == "__main__":
    unittest.main()
