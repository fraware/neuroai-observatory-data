from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_pre_g2_d4_pilot_readiness_aggregate import (
    D4PilotExecutionError,
    build_pilot_readiness_aggregate,
)
from tests.test_pre_g2_d4_pilot_execution import PILOT_KEY, _write_pilot


def _rewrite_packet_and_digest(
    root: Path,
    manifest: dict[str, object],
    index: int,
    packet: dict[str, object],
) -> None:
    path = root / "packets" / f"packet-{index:03d}.json"
    raw = (json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    packet_manifest = manifest["packet_manifest"]
    assert isinstance(packet_manifest, list)
    entry = packet_manifest[index]
    assert isinstance(entry, dict)
    entry["packet_sha256"] = hashlib.sha256(raw).hexdigest()


class D4PilotExecutionContainmentHardeningTests(unittest.TestCase):
    def test_unsupported_source_class_is_rejected_even_if_semantic_validator_would_not_check_enum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            path = root / "packets" / "packet-000.json"
            packet = json.loads(path.read_text(encoding="utf-8"))
            packet["evidence_packet"]["evidence_refs"][0]["source_class"] = "UNSUPPORTED_SECRET_SOURCE_CLASS"
            _rewrite_packet_and_digest(root, manifest, 0, packet)
            with self.assertRaises(D4PilotExecutionError) as caught:
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)
            self.assertNotIn("UNSUPPORTED_SECRET_SOURCE_CLASS", str(caught.exception))

    def test_semantic_validator_identifier_diagnostics_are_not_propagated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            path = root / "packets" / "packet-000.json"
            packet = json.loads(path.read_text(encoding="utf-8"))
            secret_ref = "SECRET_CONTROLLED_EVIDENCE_REF"
            packet["exact_object_binding"]["identity_basis_refs"] = [secret_ref]
            for record in packet["reviewer_records"]:
                record["exact_object_binding"]["identity_basis_refs"] = [secret_ref]
            _rewrite_packet_and_digest(root, manifest, 0, packet)
            with self.assertRaises(D4PilotExecutionError) as caught:
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)
            self.assertNotIn(secret_ref, str(caught.exception))
            self.assertEqual(
                str(caught.exception),
                "controlled packet failed merged D4 semantic validation",
            )

    def test_invalid_claim_scope_is_rejected_before_aggregation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            path = root / "packets" / "packet-000.json"
            packet = json.loads(path.read_text(encoding="utf-8"))
            packet["evidence_packet"]["evidence_refs"][0]["claim_scopes"] = ["UNSUPPORTED_SCOPE"]
            _rewrite_packet_and_digest(root, manifest, 0, packet)
            with self.assertRaises(D4PilotExecutionError):
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)

    def test_malformed_digest_is_rejected_before_semantic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _ = _write_pilot(root)
            path = root / "packets" / "packet-000.json"
            packet = json.loads(path.read_text(encoding="utf-8"))
            packet["evidence_packet"]["evidence_refs"][0]["content_sha256"] = "not-a-digest"
            evidence = packet["evidence_packet"]
            canonical = json.dumps(
                evidence,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            evidence_sha = hashlib.sha256(canonical).hexdigest()
            for record in packet["reviewer_records"]:
                record["evidence_packet_sha256"] = evidence_sha
            _rewrite_packet_and_digest(root, manifest, 0, packet)
            with self.assertRaises(D4PilotExecutionError):
                build_pilot_readiness_aggregate(manifest, root / "packets", PILOT_KEY)


if __name__ == "__main__":
    unittest.main()
