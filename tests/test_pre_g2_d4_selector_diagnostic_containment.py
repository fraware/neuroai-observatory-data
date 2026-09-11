from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.select_pre_g2_d4_held_out import select_candidates as parent_select_candidates
from scripts.select_pre_g2_d4_held_out_v0_2 import (
    CONTROLLED_INPUT_FAILURE,
    PUBLIC_CONTROLLED_FAILURE,
    PUBLIC_INTERNAL_FAILURE,
    SUCCESS,
    UNEXPECTED_INTERNAL_FAILURE,
    main,
    run_selector,
)
from tests.test_pre_g2_d4_sampling_calibration import (
    COMMITMENT_KEY,
    _candidate_pool,
    _recommit,
)

SECRET_CANDIDATE = "SYNTHETIC-CANDIDATE-0000"


def _write_inputs(root: Path, pool: dict[str, object] | None = None) -> tuple[Path, Path]:
    pool_path = root / "candidate-pool.json"
    key_path = root / "commitment.key"
    payload = _candidate_pool() if pool is None else pool
    pool_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    key_path.write_bytes(COMMITMENT_KEY)
    return pool_path, key_path


class D4SelectorDiagnosticContainmentTests(unittest.TestCase):
    def test_valid_selection_is_exactly_equivalent_to_v0_1_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            pool_path, key_path = _write_inputs(root, pool)
            controlled_path = root / "s3" / "selected-membership.json"

            expected_controlled, expected_aggregate = parent_select_candidates(copy.deepcopy(pool), COMMITMENT_KEY)
            status, aggregate, public_message = run_selector(
                pool_path,
                key_path,
                controlled_output=controlled_path,
            )

            self.assertEqual(status, SUCCESS)
            self.assertEqual(public_message, "")
            self.assertEqual(aggregate, expected_aggregate)

            controlled = json.loads(controlled_path.read_text(encoding="utf-8"))
            self.assertEqual(controlled, expected_controlled)
            self.assertEqual(controlled["selected_count"], 240)
            self.assertEqual(len(controlled["selected_candidate_ids"]), 240)
            assert aggregate is not None
            self.assertNotIn("selected_candidate_ids", aggregate)
            self.assertNotIn("SYNTHETIC-CANDIDATE-", json.dumps(aggregate, sort_keys=True))

    def test_exposure_failure_is_generic_publicly_and_detailed_only_in_controlled_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            pool["candidates"][0]["pilot_or_development_exposed"] = True
            _recommit(pool)
            pool_path, key_path = _write_inputs(root, pool)
            error_path = root / "s3" / "selector-error.json"

            status, aggregate, public_message = run_selector(
                pool_path,
                key_path,
                controlled_error_output=error_path,
            )
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
            self.assertNotIn(SECRET_CANDIDATE, public_message)

            controlled = json.loads(error_path.read_text(encoding="utf-8"))
            self.assertEqual(controlled["custody"], "S3_CONTROLLED")
            self.assertFalse(controlled["public_output_authority"])
            self.assertIn(SECRET_CANDIDATE, controlled["controlled_detail"])

    def test_unresolved_identity_failure_does_not_escape_public_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            pool["candidates"][0]["exact_object_identity_resolved"] = False
            _recommit(pool)
            pool_path, key_path = _write_inputs(root, pool)
            status, aggregate, public_message = run_selector(pool_path, key_path)
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
            self.assertNotIn(SECRET_CANDIDATE, public_message)

    def test_malformed_candidate_row_is_generic_publicly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            del pool["candidates"][0]["candidate_id"]
            # Keep the previously valid pool commitment. Shape validation must fail
            # before commitment recomputation and the outward boundary must remain generic.
            pool_path, key_path = _write_inputs(root, pool)
            status, aggregate, public_message = run_selector(pool_path, key_path)
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
            self.assertNotIn("SYNTHETIC-CANDIDATE-", public_message)

    def test_quota_failure_is_generic_publicly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            for candidate in pool["candidates"]:
                candidate["construct_strata"] = ["CLINICAL"]
                candidate["source_languages"] = ["en"]
                candidate["jurisdictions"] = ["US"]
            _recommit(pool)
            pool_path, key_path = _write_inputs(root, pool)
            status, aggregate, public_message = run_selector(pool_path, key_path)
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
            self.assertNotIn("SYNTHETIC-CANDIDATE-", public_message)

    def test_wrong_hmac_key_and_commitment_failure_are_generic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool_path, key_path = _write_inputs(root)
            key_path.write_bytes(b"wrong-key")
            status, aggregate, public_message = run_selector(pool_path, key_path)
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
            self.assertNotIn("SYNTHETIC-CANDIDATE-", public_message)

    def test_malformed_json_and_missing_input_path_are_generic(self) -> None:
        for failure in ("malformed", "missing"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                pool_path, key_path = _write_inputs(root)
                if failure == "malformed":
                    pool_path.write_text('{"candidate_id":"SECRET-MALFORMED"', encoding="utf-8")
                else:
                    pool_path.unlink()
                status, aggregate, public_message = run_selector(pool_path, key_path)
                self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
                self.assertIsNone(aggregate)
                self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
                self.assertNotIn(str(pool_path), public_message)
                self.assertNotIn("SECRET-MALFORMED", public_message)

    def test_unexpected_exception_is_contained_and_optionally_retained_in_s3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool_path, key_path = _write_inputs(root)
            error_path = root / "s3" / "unexpected.json"
            secret = "SECRET_INTERNAL_CANDIDATE_ALIAS"
            with patch(
                "scripts.select_pre_g2_d4_held_out_v0_2.select_candidates",
                side_effect=RuntimeError(secret),
            ):
                status, aggregate, public_message = run_selector(
                    pool_path,
                    key_path,
                    controlled_error_output=error_path,
                )
            self.assertEqual(status, UNEXPECTED_INTERNAL_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_INTERNAL_FAILURE)
            self.assertNotIn(secret, public_message)
            controlled = json.loads(error_path.read_text(encoding="utf-8"))
            self.assertEqual(controlled["failure_class"], "UNEXPECTED_INTERNAL_FAILURE")
            self.assertEqual(controlled["controlled_detail"], secret)

    def test_controlled_output_write_failure_remains_generic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool_path, key_path = _write_inputs(root)
            output_path = root / "existing-directory"
            output_path.mkdir()
            status, aggregate, public_message = run_selector(
                pool_path,
                key_path,
                controlled_output=output_path,
            )
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
            self.assertNotIn("SYNTHETIC-CANDIDATE-", public_message)

    def test_controlled_error_write_failure_does_not_replace_public_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            pool["candidates"][0]["pilot_or_development_exposed"] = True
            _recommit(pool)
            pool_path, key_path = _write_inputs(root, pool)
            error_path = root / "existing-directory"
            error_path.mkdir()
            status, aggregate, public_message = run_selector(
                pool_path,
                key_path,
                controlled_error_output=error_path,
            )
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
            self.assertNotIn(SECRET_CANDIDATE, public_message)

    def test_no_controlled_output_path_can_alias_input_or_key_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool_path, key_path = _write_inputs(root)
            original_pool = pool_path.read_bytes()
            original_key = key_path.read_bytes()

            for field in ("controlled_output", "controlled_error_output"):
                for output_path in (pool_path, key_path):
                    with self.subTest(field=field, output_path=output_path.name):
                        kwargs = {field: output_path}
                        status, aggregate, public_message = run_selector(
                            pool_path,
                            key_path,
                            **kwargs,
                        )
                        self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
                        self.assertIsNone(aggregate)
                        self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
                        self.assertEqual(pool_path.read_bytes(), original_pool)
                        self.assertEqual(key_path.read_bytes(), original_key)

    def test_success_and_error_outputs_must_be_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool_path, key_path = _write_inputs(root)
            shared = root / "s3" / "shared.json"
            status, aggregate, public_message = run_selector(
                pool_path,
                key_path,
                controlled_output=shared,
                controlled_error_output=shared,
            )
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            self.assertIsNone(aggregate)
            self.assertEqual(public_message, PUBLIC_CONTROLLED_FAILURE)
            self.assertFalse(shared.exists())

    def test_cli_stdout_never_contains_candidate_id_on_controlled_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            pool["candidates"][0]["pilot_or_development_exposed"] = True
            _recommit(pool)
            pool_path, key_path = _write_inputs(root, pool)
            stdout = io.StringIO()
            argv = [
                "select_pre_g2_d4_held_out_v0_2.py",
                str(pool_path),
                "--commitment-key-file",
                str(key_path),
            ]
            with patch("sys.argv", argv), contextlib.redirect_stdout(stdout):
                status = main()
            self.assertEqual(status, CONTROLLED_INPUT_FAILURE)
            rendered = stdout.getvalue()
            self.assertIn(PUBLIC_CONTROLLED_FAILURE, rendered)
            self.assertNotIn(SECRET_CANDIDATE, rendered)
            self.assertNotIn("SYNTHETIC-CANDIDATE-", rendered)

    def test_wrapper_does_not_mutate_input_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            original = copy.deepcopy(pool)
            pool_path, key_path = _write_inputs(root, pool)
            status, aggregate, _ = run_selector(pool_path, key_path)
            self.assertEqual(status, SUCCESS)
            self.assertIsNotNone(aggregate)
            loaded = json.loads(pool_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, original)


if __name__ == "__main__":
    unittest.main()
