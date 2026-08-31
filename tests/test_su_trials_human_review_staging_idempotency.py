from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
for path in (SCRIPTS, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_su_trials_recorded_replay as replay
import stage_su_trials_human_review as staging
import test_su_trials_human_review_staging as base


class SUTrialsHumanReviewStagingIdempotencyTests(unittest.TestCase):
    def test_same_projection_cannot_create_duplicate_review_queue(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            workspace = Path(workspace_td)
            base._write_projection(projection)
            fake = base.FakeWorkbench()

            first = staging.stage_projection(projection, workspace, workbench_api=fake.api)
            self.assertEqual(first["status"], "STAGED_FOR_HUMAN_ACCEPTANCE")
            self.assertEqual(len(fake.calls), 1)

            with self.assertRaisesRegex(ValueError, "PROJECTION_ALREADY_STAGED"):
                staging.stage_projection(projection, workspace, workbench_api=fake.api)
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(len(fake.queries), 1)

    def test_review_index_records_exact_current_identity_index_digest(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            workspace = Path(workspace_td)
            base._write_projection(projection)
            fake = base.FakeWorkbench()

            result = staging.stage_projection(projection, workspace, workbench_api=fake.api)
            review = json.loads(Path(result["review_index_path"]).read_text(encoding="utf-8"))
            current = replay.build_known_nct_source_index()
            expected_digest = staging._digest(dict(sorted(current["nct_to_source"].items())))

            self.assertEqual(review["current_known_nct_index_sha256"], expected_digest)
            self.assertEqual(result["current_known_nct_index_sha256"], expected_digest)
            self.assertEqual(review["current_known_ctgov_nct_count"], len(current["nct_to_source"]))
            self.assertEqual(review["materialized_source_namespace_count"], 248)

    def test_multiple_indexes_for_same_manifest_fail_as_corrupt_operational_state(self) -> None:
        with tempfile.TemporaryDirectory() as projection_td, tempfile.TemporaryDirectory() as workspace_td:
            projection = Path(projection_td)
            workspace = Path(workspace_td)
            base._write_projection(projection)
            fake = base.FakeWorkbench()

            result = staging.stage_projection(projection, workspace, workbench_api=fake.api)
            first_index = Path(result["review_index_path"])
            duplicate_index = first_index.with_name("DRUN-ffffffffffffffffffffffffffffffff.json")
            shutil.copyfile(first_index, duplicate_index)

            with self.assertRaisesRegex(ValueError, "DUPLICATE_OPERATIONAL_STAGING_STATE"):
                staging.stage_projection(projection, workspace, workbench_api=fake.api)
            self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
