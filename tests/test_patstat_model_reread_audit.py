"""Regression tests for descriptive PATSTAT reread diagnostics.

Only historical model-to-model agreement is evaluated; no human ground
truth, licensed source export or population-inference claim is created.
"""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_patstat_model_rereads import (
    RereadAuditError,
    build_diagnostic,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "patent-evidence-extract"


class PatstatRereadAuditTests(unittest.TestCase):
    def test_historical_descriptive_checks(self) -> None:
        result = build_diagnostic(HISTORICAL)
        self.assertEqual(result["english_abstract_frame_families"], 69273903)
        self.assertEqual(result["historical_first_model_sample_n_from_strata"], 235738)
        self.assertEqual(result["stronger_model_reread_count"], 333)
        self.assertEqual(result["strata_count"], 9)
        self.assertEqual(result["status"], "DESCRIPTIVE_MODEL_COMPARISON_ONLY")
        matrix = result["stronger_model_rows_by_first_model_columns"]
        self.assertEqual(matrix["2"]["2"], 51)
        self.assertEqual(matrix["2"]["0"], 5)
        self.assertEqual(matrix["0"]["2"], 53)
        self.assertEqual(sum(sum(row.values()) for row in matrix.values()), 333)
        binary = result["binary_stronger_model_as_reference_only"]
        self.assertEqual((binary["tp"], binary["fp"], binary["fn"], binary["tn"]), (51, 53, 5, 224))
        self.assertAlmostEqual(binary["precision"], 51 / 104)
        self.assertAlmostEqual(binary["recall"], 51 / 56)
        self.assertAlmostEqual(binary["cohen_kappa"], 0.5360780169100694)
        self.assertAlmostEqual(result["three_class_cohen_kappa"], 0.46908511149452886)
        self.assertEqual(len(result["observed_stratum_by_first_label_cells"]), 27)
        self.assertEqual(len(result["zero_observed_reread_cells"]), 9)
        sample = result["first_stage_exact_cell_audit"]
        self.assertIsNotNone(sample)
        self.assertEqual(sample["actual_first_stage_sample_rows"], 235738)
        self.assertEqual(sample["missing_first_model_verdict_rows"], 4)
        self.assertEqual(sample["reread_ids_exactly_matched_to_original_sample"], 333)
        self.assertEqual(
            sum(cell["first_stage_count"] for cell in sample["first_stage_cell_counts"]),
            235734,
        )
        self.assertEqual(len(sample["first_stage_cell_counts"]), 27)
        self.assertTrue(
            all(cell["first_stage_count"] > 0 for cell in sample["nonempty_first_stage_cells_with_zero_observed_rereads"])
        )
        self.assertIn("Human reference labels or D3 validation", result["not_established"])

    def _fixture(self, root: Path) -> None:
        with (root / "strata.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["stratum", "N_families", "n_judged"])
            for i in range(9):
                writer.writerow([i, 100, 10])
        with (root / "gold_labels.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["docdb_family_id", "stratum", "gold_neuro", "cheap_neuro"])
            writer.writerow([100, 1, 2, 2])
            writer.writerow([101, 1, 0, 2])
            writer.writerow([102, 2, 2, 0])

    def test_fixture_confusion_and_nonterminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            self._fixture(p)
            result = build_diagnostic(p)
            self.assertEqual(result["stronger_model_reread_count"], 3)
            self.assertEqual(
                tuple(result["binary_stronger_model_as_reference_only"][k] for k in ("tp", "fp", "fn", "tn")),
                (1, 1, 1, 0),
            )
            self.assertEqual(len(result["zero_observed_reread_cells"]), 25)
            out = p / "report.json"
            self.assertEqual(main(["--data-dir", str(p), "--output", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())["status"], "DESCRIPTIVE_MODEL_COMPARISON_ONLY")


    def test_first_stage_exact_id_and_cell_join_on_synthetic_data(self) -> None:
        """A reread must correspond to an original first-stage ID, class and stratum."""
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            self._fixture(p)
            gold = p / "gold_labels.csv"
            rows = gold.read_text(encoding="utf-8")
            rows = rows.replace("100,1,2,2", "110,1,2,2")
            rows = rows.replace("101,1,0,2", "111,1,0,2")
            rows = rows.replace("102,2,2,0", "120,2,2,0")
            gold.write_text(rows, encoding="utf-8")
            with (p / "judged_sample.csv").open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["docdb_family_id", "stratum", "neuro"])
                for stratum in range(9):
                    for j in range(10):
                        fid = 100 + stratum * 10 + j
                        label = "2" if fid in {110, 111} else "0"
                        writer.writerow([fid, stratum, label])
            audit = build_diagnostic(p)["first_stage_exact_cell_audit"]
            self.assertIsNotNone(audit)
            self.assertEqual(audit["actual_first_stage_sample_rows"], 90)
            self.assertEqual(audit["reread_ids_exactly_matched_to_original_sample"], 3)
            self.assertEqual(audit["missing_first_model_verdict_rows"], 0)
            self.assertGreater(len(audit["nonempty_first_stage_cells_with_zero_observed_rereads"]), 0)
            # Changing only a first-stage label must fail even though all IDs still exist.
            sample_path = p / "judged_sample.csv"
            sample_path.write_text(
                sample_path.read_text(encoding="utf-8").replace("110,1,2", "110,1,0"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RereadAuditError, "not bound"):
                build_diagnostic(p)

    def test_duplicate_family_id_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            self._fixture(p)
            with (p / "gold_labels.csv").open("a", encoding="utf-8") as f:
                f.write("100,3,0,0\n")
            with self.assertRaisesRegex(RereadAuditError, "duplicate"):
                build_diagnostic(p)

    def test_unknown_label_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            self._fixture(p)
            f = p / "gold_labels.csv"
            f.write_text(f.read_text().replace("100,1,2,2", "100,1,9,2"))
            with self.assertRaisesRegex(RereadAuditError, "Malformed"):
                build_diagnostic(p)

    def test_bad_stratum_sampling_bounds_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            self._fixture(p)
            f = p / "strata.csv"
            f.write_text(f.read_text().replace("0,100,10", "0,100,101"))
            with self.assertRaisesRegex(RereadAuditError, "sampling bounds"):
                build_diagnostic(p)

    def test_missing_stratum_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            self._fixture(p)
            f = p / "strata.csv"
            f.write_text(f.read_text().replace("8,100,10\n", ""))
            with self.assertRaisesRegex(RereadAuditError, "nine-stratum"):
                build_diagnostic(p)


if __name__ == "__main__":
    unittest.main()
