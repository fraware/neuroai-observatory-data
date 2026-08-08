from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "build_analytical_projection.py"
SPEC = importlib.util.spec_from_file_location("build_analytical_projection", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
projection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(projection)


class AnalyticalProjectionTests(unittest.TestCase):
    def _write_inputs(self, root: Path) -> tuple[Path, Path]:
        records = root / "records"
        supplemental = root / "supplemental"
        records.mkdir()
        supplemental.mkdir()
        v14 = {
            "metadata": {"version": "v1.4", "evidence_cutoff": "2026-07-29"},
            "organizations": [
                {
                    "organization_id": "ORG-1",
                    "canonical_name": "Example NeuroAI",
                    "organization_type": "COMPANY",
                    "verification_state": "CURRENT_VERIFIED",
                    "evidence_state": "OFFICIAL_CURRENT_REPRESENTATION",
                    "official_url": "https://example.org/",
                    "source_ids": ["SRC-1"],
                    "last_verified": "2026-07-29",
                }
            ],
            "sources": [
                {
                    "source_id": "SRC-1",
                    "publisher": "Example NeuroAI",
                    "source_class": "OFFICIAL_COMPANY_PAGE",
                    "url": "https://example.org/",
                    "verification_state": "CURRENT_VERIFIED",
                    "evidence_state": "CURRENT_SOURCE_RETRIEVED",
                }
            ],
            "representative_model_records": [
                {
                    "model_id": "MDL-1",
                    "name": "Example Decoder",
                    "developer": "Example NeuroAI",
                    "source_ids": ["SRC-1"],
                }
            ],
            "supplier_dependency_relationships": [
                {
                    "dependency_id": "DEP-1",
                    "organization": "Example NeuroAI",
                    "supplier": "Example Supplier",
                    "source_ids": ["SRC-1"],
                }
            ],
            "capital_and_ownership_events": [
                {
                    "event_id": "EVT-1",
                    "organization": "Example NeuroAI",
                    "event_date": "2026-07-20",
                    "source_ids": ["SRC-1"],
                }
            ],
        }
        registry = [
            {
                "monitor_id": "MON-1",
                "source_id": "SRC-1",
                "url": "https://example.org/",
                "publisher": "Example NeuroAI",
                "source_class": "OFFICIAL_COMPANY_PAGE",
                "cadence": "WEEKLY",
                "last_successful_retrieval": "2026-07-29",
                "baseline_evidence_state": "CURRENT_SOURCE_RETRIEVED",
                "baseline_verification_state": "CURRENT_VERIFIED",
            },
            {
                "monitor_id": "MON-2",
                "source_id": "SRC-2",
                "url": "https://example.net/",
                "publisher": "Example Registry",
                "source_class": "TRIAL_REGISTRY",
                "cadence": "MONTHLY",
                "last_successful_retrieval": "2026-07-29",
                "baseline_evidence_state": "CURRENT_SOURCE_RETRIEVED",
                "baseline_verification_state": "CURRENT_VERIFIED",
            },
        ]
        v16 = {
            "metadata": {"version": "v1.6", "effective_as_of": "2026-07-29"},
            "new_sources": [
                {
                    "source_id": "SRC-2",
                    "publisher": "Example Registry",
                    "source_class": "TRIAL_REGISTRY",
                    "url": "https://example.net/",
                    "evidence_state": "CURRENT_SOURCE_RETRIEVED",
                }
            ],
        }
        v17 = {
            "metadata": {
                "version": "v1.7",
                "effective_as_of": "2026-07-29",
                "status": "CONTROLLED_SUCCESSOR_SNAPSHOT",
            },
            "successor_effective_counts": {"organizations": 1, "source_records": 3},
            "delta": {
                "regulatory_and_market_events": [
                    {
                        "event_id": "EVT-2",
                        "system": "Example System",
                        "event_date": "2026-07-28",
                        "source_ids": ["SRC-2"],
                    }
                ],
                "model_records": [
                    {
                        "model_id": "MDL-2",
                        "name": "Example Decoder v2",
                        "developer": "Example NeuroAI",
                        "source_ids": ["SRC-1"],
                    }
                ],
            },
            "reopening_decisions": [
                {
                    "decision_id": "ROP-1",
                    "object": "Example assessment",
                    "decision": "REOPEN",
                    "source_ids": ["SRC-2"],
                }
            ],
        }
        prima = [
            {
                "source_id": "SRC-3",
                "title": "Supplemental current source",
                "publisher": "Example Journal",
                "url": "https://journal.example/current",
                "published": "2026-07-25",
                "retrieved": "2026-07-29",
                "source_class": "PEER_REVIEWED_PRIMARY_CLINICAL_STUDY",
                "evidence_state": "PUBLISHED_PRIMARY_STUDY",
            }
        ]
        payloads = {
            "canonical_observatory_release_v1.4.json": v14,
            "source_monitor_registry_v1.5.json": registry,
            "canonical_live_refresh_release_v1.6.json": v16,
            "canonical_successor_snapshot_v1.7.json": v17,
        }
        for name, value in payloads.items():
            (records / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        (supplemental / projection.PRIMA_SOURCE_REGISTER).write_text(
            json.dumps(prima, indent=2) + "\n", encoding="utf-8"
        )
        return records, supplemental

    def test_projection_materializes_baseline_live_and_successor_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records, supplemental = self._write_inputs(root)
            output = root / "analytics"
            manifest = projection.build_projection(
                records,
                output,
                as_of=date(2026, 8, 8),
                supplemental_dir=supplemental,
            )

            by_name = {entry["table"]: entry for entry in manifest["tables"]}
            self.assertEqual(by_name["organizations"]["row_count"], 1)
            self.assertEqual(by_name["sources"]["row_count"], 3)
            self.assertEqual(by_name["source_monitors"]["row_count"], 2)
            self.assertEqual(by_name["events"]["row_count"], 2)
            self.assertEqual(by_name["models"]["row_count"], 2)
            self.assertEqual(by_name["relationships"]["row_count"], 1)
            self.assertEqual(by_name["reopening_decisions"]["row_count"], 1)

            sources = [json.loads(line) for line in (output / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["record_id"] for row in sources], ["SRC-1", "SRC-2", "SRC-3"])
            self.assertEqual(sources[0]["source_release"], "v1.4")
            self.assertEqual(sources[1]["source_release"], "v1.6")
            self.assertEqual(sources[2]["source_release"], "v1.7")
            self.assertTrue(sources[2]["source_section"].startswith("supplemental."))
            self.assertEqual(sources[2]["date"], "2026-07-25")

            health = json.loads((output / "data-health.json").read_text(encoding="utf-8"))
            self.assertEqual(health["source_monitor_freshness"]["counts"], {"CURRENT": 1, "DUE": 1})
            self.assertEqual(
                health["monitor_coverage"],
                {
                    "effective_source_records": 3,
                    "monitored_source_records": 2,
                    "unmonitored_effective_source_count": 1,
                },
            )
            current = json.loads((output / "current-state.json").read_text(encoding="utf-8"))
            self.assertEqual(current["latest_successor"]["version"], "v1.7")
            self.assertEqual(current["analytical_table_row_counts"]["sources"], 3)

    def test_projection_is_deterministic_for_same_as_of(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records, supplemental = self._write_inputs(root)
            first = root / "a"
            second = root / "b"
            one = projection.build_projection(
                records, first, as_of=date(2026, 8, 8), supplemental_dir=supplemental
            )
            two = projection.build_projection(
                records, second, as_of=date(2026, 8, 8), supplemental_dir=supplemental
            )
            self.assertEqual(
                [(item["table"], item["jsonl"]["sha256"], item["csv"]["sha256"]) for item in one["tables"]],
                [(item["table"], item["jsonl"]["sha256"], item["csv"]["sha256"]) for item in two["tables"]],
            )
            self.assertEqual((first / "data-health.json").read_bytes(), (second / "data-health.json").read_bytes())

    def test_materialization_count_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records, supplemental = self._write_inputs(root)
            successor = records / "canonical_successor_snapshot_v1.7.json"
            value = json.loads(successor.read_text(encoding="utf-8"))
            value["successor_effective_counts"]["source_records"] = 4
            successor.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "materialization incomplete"):
                projection.build_projection(
                    records,
                    root / "out",
                    as_of=date(2026, 8, 8),
                    supplemental_dir=supplemental,
                )

    def test_conflicting_source_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records, supplemental = self._write_inputs(root)
            prima_path = supplemental / projection.PRIMA_SOURCE_REGISTER
            prima_path.write_text(
                json.dumps([{"source_id": "SRC-1", "url": "https://conflict.example/"}]), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "Conflicting duplicate source_id"):
                projection.build_projection(
                    records,
                    root / "out",
                    as_of=date(2026, 8, 8),
                    supplemental_dir=supplemental,
                )

    def test_missing_governing_input_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Missing governing input"):
                projection.load_inputs(Path(temp))

    def test_helpers_keep_missingness_explicit(self) -> None:
        self.assertEqual(projection.normalize_url("HTTPS://Example.org/path/#x"), "https://example.org/path")
        self.assertIsNone(projection.parse_date("invalid"))
        row = projection.project_record(
            {"name": "No ID"},
            record_type="example",
            source_release="v-test",
            source_section="examples",
            ordinal=7,
        )
        self.assertEqual(row["record_id"], "examples:00007")
        self.assertIsNone(row["date"])
        self.assertEqual(row["source_ids"], [])


if __name__ == "__main__":
    unittest.main()
