from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "project_legacy_source_monitoring.py"
SPEC = importlib.util.spec_from_file_location("project_legacy_source_monitoring", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
monitoring = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitoring)

MANIFEST_PATH = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"
SCHEMA_PATH = ROOT / "schemas" / "legacy-source-registration-proposals.schema.json"
POLICY_PATH = ROOT / "curation" / "source_namespace_eligibility_policy_v0.1.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _policy() -> dict[str, object]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _projection() -> dict[str, object]:
    return monitoring.build_projection(_manifest(), _policy())


def _row_for_evidence(
    projection: dict[str, object],
    evidence_id: str,
    *,
    system: str,
) -> dict[str, object]:
    matches = [
        row
        for row in projection["sources"]
        if evidence_id in row["linked_evidence_ids"] and system in row["systems"]
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one row for {system} {evidence_id}; found {len(matches)}")
    return matches[0]


class ProspectiveLegacyMonitoringTests(unittest.TestCase):
    def test_population_is_exactly_namespace_safe_33(self) -> None:
        projection = _projection()
        population = projection["prospective_population"]
        self.assertEqual(population["source_identity_count"], 33)
        self.assertEqual(population["excluded_curation_hold_count"], 2)
        self.assertEqual(len(projection["sources"]), 33)
        self.assertEqual(len({row["proposal_id"] for row in projection["sources"]}), 33)
        self.assertTrue(all(row["source_namespace_eligible"] for row in projection["sources"]))

    def test_fixed_corpus_mode_and_rule_counts_are_explicit(self) -> None:
        population = _projection()["prospective_population"]
        self.assertEqual(
            population["mode_counts"],
            {
                "ARCHIVAL_STATIC": 22,
                "ON_CHANGE": 7,
                "RECURRING": 4,
            },
        )
        self.assertEqual(
            population["rule_counts"],
            {
                "DATED_PUBLICATION_OR_EVENT_ARTIFACT": 9,
                "IMMUTABLE_GIT_OBJECT": 6,
                "LIVE_PROJECT_OR_REPOSITORY_PAGE": 2,
                "LIVE_REGULATORY_DATABASE": 5,
                "LIVE_TRIAL_REGISTRY": 4,
                "STATIC_FILE_OR_VERSIONED_DOCUMENT": 7,
            },
        )
        self.assertNotIn("CONSERVATIVE_ON_CHANGE_FALLBACK", population["rule_counts"])

    def test_curation_holds_are_excluded(self) -> None:
        projection = _projection()
        included_evidence = {
            (system, evidence_id)
            for row in projection["sources"]
            for system in row["systems"]
            for evidence_id in row["linked_evidence_ids"]
        }
        self.assertNotIn(("FDA adaptive DBS", "EV-15"), included_evidence)
        self.assertNotIn(("BrainGate2 T15", "EV-T15-012"), included_evidence)
        excluded = {
            (system, evidence_id)
            for row in projection["excluded_curation_holds"]
            for system in row["systems"]
            for evidence_id in row["linked_evidence_ids"]
        }
        self.assertEqual(
            excluded,
            {
                ("FDA adaptive DBS", "EV-15"),
                ("BrainGate2 T15", "EV-T15-012"),
            },
        )

    def test_authority_boundary_and_source_identity_rules(self) -> None:
        projection = _projection()
        self.assertEqual(projection["status"], "NONCANONICAL_PROJECTION")
        self.assertTrue(projection["scenario_only"])
        self.assertEqual(projection["registration_status"], "NOT_REGISTERED")
        self.assertEqual(projection["monitor_status"], "PROSPECTIVE_ONLY")
        self.assertEqual(
            projection["current_canonical_monitoring_checkpoint"],
            {
                "effective_source_count": 248,
                "monitor_registry_source_count": 224,
                "unmonitored_effective_source_count": 24,
                "mutated_by_this_projection": False,
            },
        )
        new_sources = [
            row for row in projection["sources"] if row["effective_source_action"] == "REGISTER_NEW_SOURCE"
        ]
        self.assertEqual(len(new_sources), 32)
        self.assertTrue(all(row["requested_source_id"] is None for row in new_sources))
        self.assertTrue(all(row["existing_source_id"] is None for row in new_sources))
        requested = [row for row in projection["sources"] if row["requested_source_id"]]
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0]["requested_source_id"], "SRC-PR-011")
        self.assertEqual(requested[0]["effective_source_action"], "REGISTER_MISSING_EXPLICIT_SOURCE")

    def test_real_corpus_trial_registries_are_recurring(self) -> None:
        projection = _projection()
        cases = (
            ("FDA adaptive DBS", "EV-06"),
            ("BrainGate2 T15", "EV-T15-002"),
        )
        for system, evidence_id in cases:
            row = _row_for_evidence(projection, evidence_id, system=system)
            self.assertEqual(row["monitoring_mode"], "RECURRING", row)
            self.assertEqual(row["recommended_interval"], "MONTHLY", row)
            self.assertEqual(row["rule"], "LIVE_TRIAL_REGISTRY", row)

    def test_real_corpus_pinned_git_and_preprint_are_archival(self) -> None:
        projection = _projection()
        preprint = _row_for_evidence(projection, "EV-01", system="Brain2Qwerty")
        pinned = _row_for_evidence(projection, "EV-04", system="Brain2Qwerty")
        self.assertEqual(preprint["monitoring_mode"], "ARCHIVAL_STATIC", preprint)
        self.assertEqual(pinned["monitoring_mode"], "ARCHIVAL_STATIC", pinned)
        self.assertEqual(pinned["rule"], "IMMUTABLE_GIT_OBJECT")

    def test_real_corpus_project_page_is_on_change(self) -> None:
        row = _row_for_evidence(_projection(), "EV-02", system="Brain2Qwerty")
        self.assertEqual(row["monitoring_mode"], "ON_CHANGE", row)
        self.assertEqual(row["rule"], "LIVE_PROJECT_OR_REPOSITORY_PAGE", row)

    def test_prima_press_release_is_archival_static(self) -> None:
        row = _row_for_evidence(_projection(), "EV-PR-011", system="PRIMA")
        self.assertEqual(row["monitoring_mode"], "ARCHIVAL_STATIC", row)
        self.assertEqual(row["rule"], "DATED_PUBLICATION_OR_EVENT_ARTIFACT", row)

    def test_synthetic_static_fda_pdf_precedes_live_database_rule(self) -> None:
        result = monitoring.classify_proposal(
            {
                "proposal_id": "X",
                "normalized_public_url": "https://www.accessdata.fda.gov/cdrh_docs/pdf/P960009S478B.pdf",
                "linked_evidence": [
                    {
                        "evidence_id": "EV-X",
                        "system": "Synthetic",
                        "evidence_type": "REGULATORY RECORD",
                        "title": "Summary of Safety and Effectiveness Data",
                    }
                ],
            }
        )
        self.assertEqual(result["monitoring_mode"], "ARCHIVAL_STATIC")
        self.assertEqual(result["rule"], "STATIC_FILE_OR_VERSIONED_DOCUMENT")

    def test_synthetic_live_fda_recall_is_on_change(self) -> None:
        result = monitoring.classify_proposal(
            {
                "proposal_id": "X",
                "normalized_public_url": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfres/res.cfm?id=123",
                "linked_evidence": [
                    {
                        "evidence_id": "EV-X",
                        "system": "Synthetic",
                        "evidence_type": "REGULATORY RECORD",
                        "title": "Class II recall",
                    }
                ],
            }
        )
        self.assertEqual(result["monitoring_mode"], "ON_CHANGE")
        self.assertEqual(result["recommended_interval"], "QUARTERLY_REVIEW")
        self.assertEqual(result["rule"], "LIVE_REGULATORY_DATABASE")

    def test_synthetic_git_landing_vs_pinned_content(self) -> None:
        common = {
            "linked_evidence": [
                {
                    "evidence_id": "EV-X",
                    "system": "Synthetic",
                    "evidence_type": "CODE REPOSITORY",
                    "title": "Repository",
                }
            ]
        }
        live = monitoring.classify_proposal(
            {**common, "proposal_id": "LIVE", "normalized_public_url": "https://github.com/example/repo"}
        )
        pinned = monitoring.classify_proposal(
            {
                **common,
                "proposal_id": "PINNED",
                "normalized_public_url": "https://github.com/example/repo/blob/abcdef1234567890/README.md",
            }
        )
        self.assertEqual(live["monitoring_mode"], "ON_CHANGE")
        self.assertEqual(live["rule"], "LIVE_PROJECT_OR_REPOSITORY_PAGE")
        self.assertEqual(pinned["monitoring_mode"], "ARCHIVAL_STATIC")
        self.assertEqual(pinned["rule"], "IMMUTABLE_GIT_OBJECT")

    def test_who_publication_does_not_inherit_ictrp_recurring_semantics(self) -> None:
        publication = monitoring.classify_proposal(
            {
                "proposal_id": "WHO-PUB",
                "normalized_public_url": "https://www.who.int/publications/i/item/example",
                "linked_evidence": [
                    {
                        "evidence_id": "EV-WHO-PUB",
                        "system": "Synthetic",
                        "evidence_type": "PUBLICATION",
                        "title": "WHO technical publication",
                    }
                ],
            }
        )
        registry = monitoring.classify_proposal(
            {
                "proposal_id": "WHO-ICTRP",
                "normalized_public_url": "https://trialsearch.who.int/Trial2.aspx?TrialID=NCT00000000",
                "linked_evidence": [
                    {
                        "evidence_id": "EV-WHO-TRIAL",
                        "system": "Synthetic",
                        "evidence_type": "TRIAL REGISTRY RECORD",
                        "title": "WHO ICTRP trial record",
                    }
                ],
            }
        )
        self.assertEqual(publication["monitoring_mode"], "ARCHIVAL_STATIC")
        self.assertEqual(publication["rule"], "DATED_PUBLICATION_OR_EVENT_ARTIFACT")
        self.assertEqual(registry["monitoring_mode"], "RECURRING")
        self.assertEqual(registry["rule"], "LIVE_TRIAL_REGISTRY")

    def test_unknown_mutability_fails_conservatively_to_on_change(self) -> None:
        result = monitoring.classify_proposal(
            {
                "proposal_id": "X",
                "normalized_public_url": "https://example.org/object",
                "linked_evidence": [
                    {
                        "evidence_id": "EV-X",
                        "system": "Synthetic",
                        "evidence_type": "OTHER",
                        "title": "Unclassified object",
                    }
                ],
            }
        )
        self.assertEqual(result["monitoring_mode"], "ON_CHANGE")
        self.assertIsNone(result["recommended_interval"])
        self.assertEqual(result["rule"], "CONSERVATIVE_ON_CHANGE_FALLBACK")

    def test_projection_validator_rejects_authority_crossing(self) -> None:
        projection = _projection()
        projection["sources"][0]["monitor_status"] = "ACTIVE"
        with self.assertRaisesRegex(monitoring.ProspectiveMonitoringError, "authority boundary"):
            monitoring.validate_projection(projection)

    def test_outputs_are_deterministic_and_machine_readable(self) -> None:
        projection = _projection()
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = monitoring.write_outputs(projection, Path(first_dir))
            second = monitoring.write_outputs(projection, Path(second_dir))
            for kind in ("json", "csv", "markdown"):
                self.assertEqual(Path(first[kind]).read_bytes(), Path(second[kind]).read_bytes())
            payload = json.loads(Path(first["json"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["prospective_population"]["source_identity_count"], 33)
            markdown = Path(first["markdown"]).read_text(encoding="utf-8")
            self.assertIn("NONCANONICAL PROJECTION", markdown)
            self.assertIn("Namespace-eligible source identities: 33", markdown)

    def test_cli_writes_three_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            code = monitoring.main(
                [
                    "--manifest",
                    str(MANIFEST_PATH),
                    "--schema",
                    str(SCHEMA_PATH),
                    "--namespace-policy",
                    str(POLICY_PATH),
                    "--output-dir",
                    output_dir,
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue((Path(output_dir) / "legacy-source-prospective-monitoring.json").is_file())
            self.assertTrue((Path(output_dir) / "legacy-source-prospective-monitoring.csv").is_file())
            self.assertTrue((Path(output_dir) / "legacy-source-prospective-monitoring.md").is_file())


if __name__ == "__main__":
    unittest.main()
