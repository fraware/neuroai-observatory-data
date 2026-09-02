from __future__ import annotations
import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from tests.test_su_trials_human_review_staging import FakeAPI,projection
import stage_su_trials_human_review as stage
class IdempotencyTests(unittest.TestCase):
 def test_same_projection_cannot_be_staged_twice(self):
  with tempfile.TemporaryDirectory() as pd,tempfile.TemporaryDirectory() as wd:
   projection(Path(pd));api=FakeAPI();wb=stage.WorkbenchAPI(api.store_query,api.execute_discovery_query);stage.stage_projection(Path(pd),Path(wd),workbench_api=wb)
   with self.assertRaisesRegex(ValueError,'PROJECTION_ALREADY_STAGED'):stage.stage_projection(Path(pd),Path(wd),workbench_api=wb)
   self.assertEqual(api.calls,1)
if __name__=='__main__':unittest.main()
