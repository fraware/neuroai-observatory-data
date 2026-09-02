from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

proof = importlib.import_module("run_pre_g0_b04_publication_authority_proof")


class PreG0B04PublicationAuthorityProofTests(unittest.TestCase):
    def test_full_ephemeral_authority_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            output = root / "proof.json"
            result = proof.execute(
                workspace=workspace,
                output=output,
                workbench_commit=proof.EXPECTED_WORKBENCH_COMMIT,
            )

            self.assertEqual(result["status"], proof.STATUS)
            self.assertEqual(
                result["workbench_commit"], proof.EXPECTED_WORKBENCH_COMMIT
            )
            self.assertTrue(result["candidate"]["candidate_verification_valid"])
            self.assertFalse(result["candidate"]["preview_canonical"])
            self.assertFalse(result["candidate"]["preview_published"])
            self.assertTrue(result["candidate"]["public_loader_refused_candidate_only"])

            self.assertEqual(result["withhold"]["decision"], "WITHHOLD")
            self.assertTrue(result["withhold"]["publication_refused"])
            self.assertEqual(result["authorize"]["decision"], "AUTHORIZE")
            self.assertEqual(
                result["authorize"]["supersedes_authorization_id"],
                result["withhold"]["authorization_id"],
            )
            self.assertTrue(result["authorize"]["authorization_store_valid"])
            self.assertEqual(result["authorize"]["active_authorization_count"], 1)
            self.assertTrue(
                result["authorize"]["public_loader_refused_before_publication"]
            )

            self.assertTrue(result["publication"]["publication_binding_valid"])
            self.assertFalse(result["publication"]["automatic_publication_performed"])
            self.assertFalse(result["publication"]["substantive_publication_performed"])
            self.assertTrue(
                result["public_v1"]["loaded_only_after_publication_binding"]
            )
            self.assertTrue(result["public_v1"]["canonical"])
            self.assertTrue(result["public_v1"]["published"])
            self.assertTrue(result["public_v1"]["release_authorized"])
            self.assertEqual(result["public_v1"]["health_status"], "ok")
            self.assertTrue(result["public_v1"]["read_only"])
            self.assertFalse(result["public_v1"]["writes_supported"])
            self.assertTrue(result["tamper"]["published_loader_refused_tampered_copy"])

            controls = result["controls"]
            self.assertTrue(controls["ephemeral_synthetic_state_only"])
            self.assertTrue(controls["ephemeral_workspace_deleted"])
            self.assertFalse(controls["repository_release_directory_modified"])
            self.assertFalse(controls["substantive_s2_release_authorized"])
            self.assertFalse(controls["substantive_s2_release_published"])
            self.assertFalse(controls["network_used"])
            self.assertFalse(controls["source_data_used"])
            self.assertFalse(workspace.exists())
            self.assertTrue(output.is_file())

            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(persisted, result)
            serialized = json.dumps(persisted, sort_keys=True)
            self.assertNotIn(str(workspace), serialized)
            self.assertNotIn("synthetic-release/records", serialized)

    def test_output_inside_ephemeral_workspace_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            with self.assertRaisesRegex(
                ValueError, "outside the ephemeral synthetic workspace"
            ):
                proof.execute(
                    workspace=workspace,
                    output=workspace / "proof.json",
                    workbench_commit=proof.EXPECTED_WORKBENCH_COMMIT,
                )
            self.assertFalse(workspace.exists())

    def test_wrong_workbench_commit_fails_closed_and_cleans_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            with self.assertRaisesRegex(ValueError, "Workbench commit mismatch"):
                proof.execute(
                    workspace=workspace,
                    output=root / "proof.json",
                    workbench_commit="0" * 40,
                )
            self.assertFalse(workspace.exists())
            self.assertFalse((root / "proof.json").exists())

    def test_synthetic_authority_markers_are_explicit(self) -> None:
        self.assertIn("SYNTHETIC", proof.SYNTHETIC_ENTITY_ID)
        self.assertIn("synthetic", proof.SYNTHETIC_RELEASE_TAG)
        self.assertIn("synthetic-test-only", proof.SYNTHETIC_PUBLICATION_REFERENCE)
        self.assertIn("does not create, authorize, publish", proof.BOUNDARY)


if __name__ == "__main__":
    unittest.main()
