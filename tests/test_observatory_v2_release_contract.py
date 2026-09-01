from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "verify_observatory_v2_release.py"
SPEC = importlib.util.spec_from_file_location("verify_observatory_v2_release", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def make_candidate(root: Path, *, entity_id: str = "ORG-1") -> Path:
    records = root / "records"
    migration = root / "migration"
    records.mkdir(parents=True)
    migration.mkdir(parents=True)

    frozen = {
        "V14": "a" * 64,
        "V16": "b" * 64,
        "DELTA16": "c" * 64,
        "V17": "d" * 64,
        "PRIMA17": "e" * 64,
        "SOURCE_REGISTER14": "f" * 64,
        "MONITOR15": "0" * 64,
    }
    gate_descriptor = {
        "release_authorized": False,
        "representational_scope_complete": True,
        "workbench_compatibility_version": "0.3.0.dev0",
        "producer_workbench_commit": "1" * 40,
        "runtime_execution_pin": "2" * 40,
        "observatory_graph_schema_version": "1",
        "s2_predecessor_commit": "3" * 40,
        "inputs": frozen,
    }
    gate_descriptor_sha = verify.sha256_bytes(verify.canonical_json_bytes(gate_descriptor))
    gate_manifest = {
        "descriptor_sha256": gate_descriptor_sha,
        "release_authorized": False,
    }
    gate_manifest["manifest_sha256"] = verify.sha256_bytes(verify.canonical_json_bytes(gate_manifest))
    gate_decision = {
        "schema_version": "1",
        "decision_type": "OBSERVATORY_V2_GATE_A_MECHANICAL_DECISION",
        "decision": verify.MECHANICAL_GATE_A_DECISION,
        "gate_a_complete": True,
        "release_authorized": False,
        "representational_scope_complete": True,
        "native_v2_materialization_complete": False,
        "field_proof_sha256": "4" * 64,
        "gate_a_package_manifest_sha256": gate_manifest["manifest_sha256"],
        "gate_a_package_descriptor_sha256": gate_descriptor_sha,
        "producer_workbench_commit": "1" * 40,
        "runtime_execution_pin": "2" * 40,
        "s2_predecessor_commit": "3" * 40,
        "observatory_graph_schema_version": "1",
        "boundary": "test mechanical Gate-A decision",
    }
    gate_decision["decision_sha256"] = verify.record_sha256(gate_decision, "decision_sha256")
    write_json(migration / "gate-a-descriptor.json", gate_descriptor)
    write_json(migration / "gate-a-manifest.json", gate_manifest)
    write_json(migration / "gate-a-decision.json", gate_decision)

    graph_rows = {
        "entities.jsonl": {"object_class": "Entity", "entity_id": entity_id},
        "sources.jsonl": {"object_class": "Source", "source_id": "SRC-1"},
    }
    for filename, expected_class in verify.OBJECT_CLASS_BY_FILE.items():
        row = graph_rows.get(filename)
        payload = b"" if row is None else (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
        (records / filename).write_bytes(payload)
        self_class = row.get("object_class") if row else expected_class
        assert row is None or self_class == expected_class

    for filename in verify.MIGRATION_FILES:
        path = migration / filename
        if not path.exists():
            path.write_text("{}\n", encoding="utf-8")

    file_entries = [
        {
            "path": relative,
            "sha256": verify.sha256_bytes((root / relative).read_bytes()),
        }
        for relative in sorted(verify.CANDIDATE_FILE_PATHS)
    ]
    content_sha = verify.sha256_bytes(verify.canonical_json_bytes(file_entries))
    candidate_id = f"OBS-V2-CAND-{content_sha[:20].upper()}"
    descriptor = {
        "schema_version": "1",
        "release_type": "OBSERVATORY_V2_S2_CANDIDATE",
        "release_tag": "data-v0.3.0-observatory-v2-candidate",
        "candidate_id": candidate_id,
        "state": "NONCANONICAL_CANDIDATE",
        "canonical_publication_state": "NOT_AUTHORIZED",
        "release_authorized": False,
        "published": False,
        "record_counts": {
            "Entity": 1,
            "Source": 1,
            "Observation": 0,
            "Assertion": 0,
            "Event": 0,
            "Relationship": 0,
            "Candidate": 0,
            "ReopeningDecision": 0,
        },
        "candidate_content_sha256": content_sha,
        "workbench_compatibility_version": "0.3.0.dev0",
        "producer_workbench_commit": "1" * 40,
        "runtime_execution_pin": "2" * 40,
        "observatory_graph_schema_version": "1",
        "s2_predecessor": {
            "release_tag": "data-v0.1.0-public-governing",
            "commit": "3" * 40,
        },
        "frozen_inputs": frozen,
        "migration_proof": {
            "field_proof_sha256": gate_decision["field_proof_sha256"],
            "gate_a_decision_sha256": gate_decision["decision_sha256"],
            "gate_a_manifest_sha256": gate_manifest["manifest_sha256"],
            "gate_a_descriptor_sha256": gate_descriptor_sha,
            "native_candidate_manifest_sha256": "7" * 64,
        },
        "boundary": "test noncanonical S2 candidate",
    }
    manifest = {
        "schema_version": "1",
        "candidate_id": candidate_id,
        "candidate_content_sha256": content_sha,
        "files": file_entries,
        "descriptor_sha256": verify.sha256_bytes(verify.canonical_json_bytes(descriptor)),
        "release_authorized": False,
        "published": False,
        "boundary": "test noncanonical S2 candidate",
    }
    manifest["manifest_sha256"] = verify.sha256_bytes(verify.canonical_json_bytes(manifest))
    write_json(root / "descriptor.json", descriptor)
    write_json(root / "manifest.json", manifest)
    return root


def authorize(root: Path, *, decision: str = "AUTHORIZE") -> dict[str, object]:
    candidate = verify.verify_candidate(root)
    record: dict[str, object] = {
        "schema_version": "1",
        "authorization_type": "OBSERVATORY_V2_S2_OPERATOR_AUTHORIZATION",
        "authorization_id": "OBSAUTH-0123456789ABCDEF0123",
        "recorded_at": "2026-09-01T08:00:00Z",
        "recorded_by": verify.DESIGNATED_OPERATOR,
        "candidate_reference": candidate["candidate_reference"],
        "decision": decision,
        "decision_rationale": "Test explicit operator decision.",
        "boundary": "test authorization boundary",
    }
    record["authorization_sha256"] = verify.record_sha256(record, "authorization_sha256")
    write_json(root / "governance/authorizations/authorization.json", record)
    return record


def publish(root: Path, authorization: dict[str, object]) -> dict[str, object]:
    candidate = verify.verify_candidate(root)
    record: dict[str, object] = {
        "schema_version": "1",
        "publication_type": "OBSERVATORY_V2_S2_PUBLICATION",
        "publication_id": "OBSPUB-0123456789ABCDEF0123",
        "recorded_at": "2026-09-01T08:01:00Z",
        "recorded_by": verify.DESIGNATED_OPERATOR,
        "authorization_reference": {
            "authorization_id": authorization["authorization_id"],
            "authorization_sha256": authorization["authorization_sha256"],
        },
        "candidate_reference": candidate["candidate_reference"],
        "publication_evidence": {
            "reference": "public-ref:test-release",
            "sha256": candidate["manifest_sha256"],
        },
        "automatic_publication_performed": False,
        "boundary": "test publication boundary",
    }
    record["publication_sha256"] = verify.record_sha256(record, "publication_sha256")
    write_json(root / "governance/publication.json", record)
    return record


class ObservatoryV2ReleaseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = make_candidate(Path(self.temp.name) / "release")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_candidate_verifies_without_conferring_publication(self) -> None:
        report = verify.verify_release(self.root)
        self.assertTrue(report["valid"])
        self.assertFalse(report["published"])
        public = verify.verify_release(self.root, require_published=True)
        self.assertFalse(public["valid"])
        self.assertIn("governance/publication.json is missing", public["errors"])

    def test_exact_authorize_and_publish_chain_verifies(self) -> None:
        authorization = authorize(self.root)
        publication = publish(self.root, authorization)
        report = verify.verify_release(self.root, require_published=True)
        self.assertTrue(report["valid"])
        self.assertTrue(report["published"])
        self.assertEqual(report["authorization_id"], authorization["authorization_id"])
        self.assertEqual(report["publication_id"], publication["publication_id"])

    def test_withhold_cannot_satisfy_publication(self) -> None:
        authorization = authorize(self.root, decision="WITHHOLD")
        publish(self.root, authorization)
        report = verify.verify_release(self.root, require_published=True)
        self.assertFalse(report["valid"])
        self.assertIn("publication requires exactly one active AUTHORIZE record", report["errors"])

    def test_extra_manifest_path_fails_closed(self) -> None:
        extra = self.root / "migration/unexpected.json"
        write_json(extra, {"unexpected": True})
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"].append(
            {
                "path": "migration/unexpected.json",
                "sha256": verify.sha256_bytes(extra.read_bytes()),
            }
        )
        write_json(self.root / "manifest.json", manifest)
        report = verify.verify_release(self.root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("outside governed allowlist" in error for error in report["errors"]))

    def test_wrong_graph_class_fails_closed(self) -> None:
        (self.root / "records/entities.jsonl").write_text(
            '{"object_class":"Source","source_id":"SRC-WRONG"}\n',
            encoding="utf-8",
        )
        report = verify.verify_release(self.root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("expected object_class Entity" in error for error in report["errors"]))

    def test_gate_a_decision_tamper_fails_closed(self) -> None:
        decision_path = self.root / "migration/gate-a-decision.json"
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        decision["decision"] = "WITHHOLD"
        write_json(decision_path, decision)
        report = verify.verify_release(self.root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("Gate-A decision" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
