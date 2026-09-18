from __future__ import annotations

import unittest

from scripts.build_pre_g2_d3_challenge_pilot_readiness import (
    D3ChallengePilotExecutionError,
)
from scripts.build_pre_g2_d3_challenge_pilot_readiness_v0_2 import (
    _require_strong_commitment_key as require_d3_pilot_key,
)
from scripts.build_pre_g2_d4_pilot_readiness_aggregate import (
    D4PilotExecutionError,
)
from scripts.build_pre_g2_d4_pilot_readiness_aggregate_v0_2 import (
    _require_strong_commitment_key as require_d4_pilot_key,
)
from scripts.execute_pre_g2_d3_challenge_final_selection_v0_2 import (
    D3ComposedFinalSelectionError,
    _require_strong_commitment_keys as require_d3_composed_keys,
)
from scripts.execute_pre_g2_d4_final_selection_v0_3 import (
    D4ComposedFinalSelectionError,
    _require_strong_commitment_keys as require_d4_composed_keys,
)


class PreG2HmacKeyStrengthTests(unittest.TestCase):
    def test_d3_pilot_successor_rejects_short_keys_and_accepts_32_bytes(self) -> None:
        for key in (b"k", b"k" * 31):
            with self.subTest(key_length=len(key)):
                with self.assertRaisesRegex(
                    D3ChallengePilotExecutionError,
                    "at least 32 bytes",
                ):
                    require_d3_pilot_key(key)
        require_d3_pilot_key(b"k" * 32)

    def test_d4_pilot_successor_rejects_short_keys_and_accepts_32_bytes(self) -> None:
        for key in (b"k", b"k" * 31):
            with self.subTest(key_length=len(key)):
                with self.assertRaisesRegex(
                    D4PilotExecutionError,
                    "at least 32 bytes",
                ):
                    require_d4_pilot_key(key)
        require_d4_pilot_key(b"k" * 32)

    def test_d3_composed_successor_checks_both_commitment_keys(self) -> None:
        with self.assertRaisesRegex(
            D3ComposedFinalSelectionError,
            "at least 32 bytes",
        ):
            require_d3_composed_keys(b"k" * 31, b"p" * 32)
        with self.assertRaisesRegex(
            D3ComposedFinalSelectionError,
            "at least 32 bytes",
        ):
            require_d3_composed_keys(b"k" * 32, b"p" * 31)
        require_d3_composed_keys(b"k" * 32, b"p" * 32)

    def test_d4_composed_successor_checks_both_commitment_keys(self) -> None:
        with self.assertRaisesRegex(
            D4ComposedFinalSelectionError,
            "at least 32 bytes",
        ):
            require_d4_composed_keys(b"k" * 31, b"p" * 32)
        with self.assertRaisesRegex(
            D4ComposedFinalSelectionError,
            "at least 32 bytes",
        ):
            require_d4_composed_keys(b"k" * 32, b"p" * 31)
        require_d4_composed_keys(b"k" * 32, b"p" * 32)


if __name__ == "__main__":
    unittest.main()
