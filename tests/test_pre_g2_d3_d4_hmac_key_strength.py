from __future__ import annotations

import unittest

from scripts.build_pre_g2_d3_challenge_pilot_readiness import (
    D3ChallengePilotExecutionError,
    pilot_membership_commitment as d3_pilot_membership_commitment,
)
from scripts.build_pre_g2_d4_pilot_readiness_aggregate import (
    D4PilotExecutionError,
    pilot_membership_commitment as d4_pilot_membership_commitment,
)
from scripts.select_pre_g2_d3_challenge_held_out import (
    D3ChallengeSelectionError,
    _hmac_sha256_domain as d3_hmac_sha256_domain,
)
from scripts.select_pre_g2_d4_held_out import (
    D4SelectionError,
    _hmac_sha256_domain as d4_hmac_sha256_domain,
)


class PreG2HmacKeyStrengthTests(unittest.TestCase):
    def test_d3_pilot_membership_rejects_keys_shorter_than_32_bytes(self) -> None:
        family_refs = [f"S3-FAMILY-{index:03d}" for index in range(60)]
        for key in (b"k", b"k" * 31):
            with self.subTest(key_length=len(key)):
                with self.assertRaisesRegex(
                    D3ChallengePilotExecutionError,
                    "at least 32 bytes",
                ):
                    d3_pilot_membership_commitment(family_refs, key)

        digest = d3_pilot_membership_commitment(family_refs, b"k" * 32)
        self.assertEqual(len(digest), 64)

    def test_d3_selection_hmac_rejects_keys_shorter_than_32_bytes(self) -> None:
        for key in (b"k", b"k" * 31):
            with self.subTest(key_length=len(key)):
                with self.assertRaisesRegex(
                    D3ChallengeSelectionError,
                    "at least 32 bytes",
                ):
                    d3_hmac_sha256_domain(key, "TEST-DOMAIN", {"x": 1})

        digest = d3_hmac_sha256_domain(b"k" * 32, "TEST-DOMAIN", {"x": 1})
        self.assertEqual(len(digest), 64)

    def test_d4_pilot_membership_rejects_keys_shorter_than_32_bytes(self) -> None:
        item_ids = [f"S3-ITEM-{index:03d}" for index in range(60)]
        for key in (b"k", b"k" * 31):
            with self.subTest(key_length=len(key)):
                with self.assertRaisesRegex(
                    D4PilotExecutionError,
                    "at least 32 bytes",
                ):
                    d4_pilot_membership_commitment("ROUND-1", item_ids, key)

        digest = d4_pilot_membership_commitment("ROUND-1", item_ids, b"k" * 32)
        self.assertEqual(len(digest), 64)

    def test_d4_selection_hmac_rejects_keys_shorter_than_32_bytes(self) -> None:
        for key in (b"k", b"k" * 31):
            with self.subTest(key_length=len(key)):
                with self.assertRaisesRegex(
                    D4SelectionError,
                    "at least 32 bytes",
                ):
                    d4_hmac_sha256_domain(key, "TEST-DOMAIN", {"x": 1})

        digest = d4_hmac_sha256_domain(b"k" * 32, "TEST-DOMAIN", {"x": 1})
        self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
