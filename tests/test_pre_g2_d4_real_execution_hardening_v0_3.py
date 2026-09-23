from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_pre_g2_d4_pilot_readiness_aggregate_v0_3 import (
    D4PilotExecutionError,
    build_pilot_readiness_aggregate,
    pilot_membership_commitment,
)
from scripts.evaluate_pre_g2_d4_pilot_readiness_v0_3 import (
    D4PilotReadinessError,
    READINESS_POLICY_ID,
    evaluate_pilot_readiness,
)
from scripts.execute_pre_g2_d4_final_selection_v0_3 import (
    execute_composed_selection,
)
from scripts.select_pre_g2_d4_held_out_v0_3 import (
    D4SelectionError,
    candidate_pool_commitment,
)
from scripts.build_pre_g2_d3_challenge_pilot_readiness_v0_2 import (
    D3ChallengePilotExecutionError,
    pilot_membership_commitment as d3_pilot_membership_commitment,
)
from scripts.select_pre_g2_d3_challenge_held_out_v0_2 import (
    D3ChallengeSelectionError,
    candidate_pool_commitment as d3_candidate_pool_commitment,
)
from tests.test_pre_g2_d4_calibration_selection_composition_v0_2 import (
    _disposition,
    _envelope,
)
from tests.test_pre_g2_d4_pilot_execution import (
    PILOT_KEY,
    POOL_KEY,
    _attestation,
    _candidate_pool,
    _write_pilot,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "curation" / "PRE_G2_D4_PILOT_READINESS_POLICY_2026-09-23_v0.3.json"
BUILDER = ROOT / "scripts" / "build_pre_g2_d4_pilot_readiness_aggregate_v0_3.py"
EVALUATOR = ROOT / "scripts" / "evaluate_pre_g2_d4_pilot_readiness_v0_3.py"
EXECUTOR = ROOT / "scripts" / "execute_pre_g2_d4_final_selection_v0_3.py"
D3_BUILDER = ROOT / "scripts" / "build_pre_g2_d3_challenge_pilot_readiness_v0_2.py"
D3_SELECTOR = ROOT / "scripts" / "select_pre_g2_d3_challenge_held_out_v0_2.py"
D3_EXECUTOR = ROOT / "scripts" / "execute_pre_g2_d3_challenge_final_selection_v0_2.py"
D4_SELECTOR = ROOT / "scripts" / "select_pre_g2_d4_held_out_v0_3.py"


def git_blob_sha1(path: Path) -> str:
    payload = path.read_bytes()
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(framed).hexdigest()  # noqa: S324 - Git object identity only


class D4RealExecutionHardeningV03Tests(unittest.TestCase):
    def _aggregate(self) -> tuple[dict[str, object], dict[str, object], Path, tempfile.TemporaryDirectory[str]]:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        manifest, _ = _write_pilot(root)
        packet_root = root / "packets"
        aggregate = build_pilot_readiness_aggregate(manifest, packet_root, PILOT_KEY)
        return manifest, aggregate, packet_root, tmp

    def test_builder_binds_full_confusion_matrix(self) -> None:
        manifest, aggregate, _, tmp = self._aggregate()
        self.addCleanup(tmp.cleanup)
        self.assertEqual(aggregate["total_items"], 60)
        matrix = aggregate["primary_secondary_confusion_matrix"]
        self.assertEqual(sum(sum(row.values()) for row in matrix.values()), 60)
        self.assertEqual(
            sum(matrix[label][label] for label in matrix),
            aggregate["primary_secondary_exact_agreement_count"],
        )
        result = evaluate_pilot_readiness(aggregate)
        self.assertEqual(result["readiness_policy_id"], READINESS_POLICY_ID)
        self.assertTrue(result["human_calibration_disposition_required"])
        self.assertFalse(result["authority"]["g2_passed"])
        self.assertEqual(manifest["pilot_round_id"], result["pilot_round_id"])

    def test_matrix_is_fail_closed_on_total_and_diagonal_mismatch(self) -> None:
        _, aggregate, _, tmp = self._aggregate()
        self.addCleanup(tmp.cleanup)

        malformed = copy.deepcopy(aggregate)
        malformed["primary_secondary_confusion_matrix"]["INCLUDE"]["EXCLUDE"] -= 1
        with self.assertRaisesRegex(D4PilotReadinessError, "exactly 60"):
            evaluate_pilot_readiness(malformed)

        malformed = copy.deepcopy(aggregate)
        malformed["primary_secondary_confusion_matrix"]["INCLUDE"]["INCLUDE"] -= 1
        malformed["primary_secondary_confusion_matrix"]["EXCLUDE"]["INCLUDE"] += 1
        with self.assertRaisesRegex(D4PilotReadinessError, "diagonal"):
            evaluate_pilot_readiness(malformed)

    def test_commitment_keys_require_at_least_32_bytes(self) -> None:
        item_ids = [f"ITEM-{index:03d}" for index in range(60)]
        with self.assertRaisesRegex(D4PilotExecutionError, "at least 32 bytes"):
            pilot_membership_commitment("ROUND", item_ids, b"x" * 31)
        self.assertEqual(len(pilot_membership_commitment("ROUND", item_ids, b"x" * 32)), 64)

        pool = _candidate_pool()
        with self.assertRaisesRegex(D4SelectionError, "at least 32 bytes"):
            candidate_pool_commitment(pool, b"x" * 31)
        self.assertEqual(len(candidate_pool_commitment(pool, b"x" * 32)), 64)

        family_refs = [f"S3-D3-FAMILY-{index:04d}" for index in range(60)]
        with self.assertRaisesRegex(D3ChallengePilotExecutionError, "at least 32 bytes"):
            d3_pilot_membership_commitment(family_refs, b"x" * 31)
        self.assertEqual(len(d3_pilot_membership_commitment(family_refs, b"x" * 32)), 64)

        d3_pool = {
            "schema_version": "0.1",
            "benchmark_id": "PRE_G2_PATENT_V0_1",
            "protocol_id": "PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1",
            "human_calibration_disposition_sha256": "d" * 64,
            "candidate_pool_id": "SYNTHETIC-D3-POOL",
            "candidate_pool_commitment": "0" * 64,
            "candidate_pool_commitment_scheme": "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1",
            "candidate_pool_frozen": True,
            "candidates": [],
        }
        with self.assertRaisesRegex(D3ChallengeSelectionError, "at least 32 bytes"):
            d3_candidate_pool_commitment(d3_pool, b"x" * 31)

    def test_v03_composed_execution_uses_matrix_bound_readiness(self) -> None:
        manifest, aggregate, packet_root, tmp = self._aggregate()
        self.addCleanup(tmp.cleanup)
        readiness = evaluate_pilot_readiness(aggregate)
        disposition = _disposition(manifest, aggregate, readiness)
        pool = _candidate_pool()
        attestation = _attestation(manifest, pool)
        envelope = _envelope(manifest, disposition, pool, attestation)

        _, public = execute_composed_selection(
            pilot_manifest=manifest,
            packet_root=packet_root,
            pilot_commitment_key=PILOT_KEY,
            calibration_disposition=disposition,
            authorization_envelope=envelope,
            candidate_pool=pool,
            candidate_pool_commitment_key=POOL_KEY,
            identity_namespace_attestation=attestation,
        )
        self.assertEqual(public["execution_type"], "D4_FINAL_SELECTION_COMPOSED_V0_3")
        self.assertTrue(public["execution_preconditions"]["pilot_quantitative_gate_verified"])
        self.assertFalse(public["g2_passed"])

    def test_policy_exactly_binds_current_hardening_implementation(self) -> None:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(policy["governing_issue"], 271)
        self.assertEqual(policy["cryptographic_key_contract"]["minimum_key_bytes"], 32)
        self.assertTrue(policy["aggregate_contract"]["full_primary_secondary_confusion_matrix_required"])
        bindings = policy["implementation_bindings"]
        expected = {
            "d4_builder_v0_3": BUILDER,
            "d4_evaluator_v0_3": EVALUATOR,
            "d4_composed_entrypoint_v0_3": EXECUTOR,
            "d3_pilot_builder_v0_2": D3_BUILDER,
            "d3_selector_v0_2": D3_SELECTOR,
            "d3_composed_entrypoint_v0_2": D3_EXECUTOR,
            "d4_selector_v0_3": D4_SELECTOR,
        }
        for key, path in expected.items():
            self.assertEqual(bindings[key]["git_blob_sha"], git_blob_sha1(path))
        self.assertFalse(policy["authority"]["g2_passed"])
        self.assertFalse(policy["authority"]["publication_authority"])


if __name__ == "__main__":
    unittest.main()
