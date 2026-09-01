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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def sha(path: Path) -> str:
    return verify.sha256_bytes(path.read_bytes())


def make_candidate(root: Path) -> Path:
    records = root / "records"
    migration = root / "migration"
    records.mkdir(parents=True)
    migration.mkdir(parents=True)

    graph_rows = {
        "entities.jsonl": [{"object_class": "Entity", "entity_id": "ORG-1"}],
        "sources.jsonl": [{"object_class": "Source", "source_id": "SRC-1"}],
        "events.jsonl": [{"object_class": "Event", "event_id": "EVT-1"}],
        "candidates.jsonl": [{"object_class": "Candidate", "candidate_id": "CAND-1"}],
    }
    for filename, object_class in verify.OBJECT_CLASS_BY_FILE.items():
        rows = graph_rows.get(filename, [])
        if rows:
            assert all(row["object_class"] == object_class for row in rows)
            write_jsonl(records / filename, rows)
        else:
            (records / filename).write_bytes(b"")

    sidecar_rows = {
        "entity-predecessor-traces.jsonl": [{"trace": "entity"}],
        "preserved-organizations.jsonl": [{"preserved": "organization"}],
        "source-predecessor-traces.jsonl": [{"trace": "source"}],
        "predecessor-observation-evidence.jsonl": [{"evidence": "transport-unresolved"}],
        "event-predecessor-traces.jsonl": [{"trace": "event"}],
        "candidate-predecessor-traces.jsonl": [{"trace": "candidate"}],
        "identity-resolution-history.jsonl": [{"history": i} for i in range(26)],
        "regional-expansion-history.jsonl": [{"history": i} for i in range(13)],
    }
    for filename, rows in sidecar_rows.items():
        write_jsonl(migration / filename, rows)

    for filename in verify.GATE_A_ROOT_FILE_MAP:
        write_json(migration / filename, {"preserved": filename})

    frozen = {
        "V14": "a" * 64,
        "V16": "b" * 64,
        "DELTA16": "c" * 64,
        "V17": "d" * 64,
        "PRIMA17": "e" * 64,
        "SOURCE_REGISTER14": "f" * 64,
        "MONITOR15": "0" * 64,
    }
    native_descriptor = {
        "schema_version": "1",
        "package_type": "OBSERVATORY_V2_PREDECESSOR_MIGRATION_CANDIDATE",
        "state": "NONCANONICAL_CANDIDATE",
        "release_authorized": False,
        "native_v2_materialization_complete": False,
        "mechanical_verification": "PASS",
        "counts": {
            "native_entities": 1,
            "native_sources": 1,
            "native_capital_events": 1,
            "native_change_candidates": 1,
            "native_candidate_objects": 4,
            "preserved_identity_resolution_history": 26,
            "preserved_regional_expansion_history": 13,
        },
        "workbench_compatibility_version": "0.3.0.dev0",
        "producer_workbench_commit": "1" * 40,
        "runtime_execution_pin": "2" * 40,
        "observatory_graph_schema_version": "1",
        "s2_predecessor_commit": "3" * 40,
        "boundary": "test native candidate",
    }
    write_json(migration / "native-candidate-descriptor.json", native_descriptor)
    native_entries = [
        {"path": source, "sha256": sha(root / target)}
        for source, target in sorted(verify.NATIVE_CANDIDATE_FILE_MAP.items())
    ]
    native_manifest = {
        "files": native_entries,
        "descriptor_sha256": verify.sha256_bytes(verify.canonical_json_bytes(native_descriptor)),
        "release_authorized": False,
        "native_v2_materialization_complete": False,
        "boundary": "test native candidate",
    }
    native_manifest["manifest_sha256"] = verify.record_sha256(native_manifest, "manifest_sha256")
    write_json(migration / "native-candidate-manifest.json", native_manifest)

    gate_descriptor = {
        "schema_version": "1",
        "package_type": "OBSERVATORY_V2_GATE_A_MIGRATION_CHECKPOINT",
        "state": "NONCANONICAL_CANDIDATE",
        "release_authorized": False,
        "representational_scope_complete": True,
        "workbench_compatibility_version": "0.3.0.dev0",
        "producer_workbench_commit": "1" * 40,
        "runtime_execution_pin": "2" * 40,
        "observatory_graph_schema_version": "1",
        "s2_predecessor_commit": "3" * 40,
        "inputs": frozen,
        "native_candidate_manifest_sha256": sha(migration / "native-candidate-manifest.json"),
        "native_candidate_descriptor_sha256": sha(migration / "native-candidate-descriptor.json"),
        "native_candidate_manifest_identity": native_manifest["manifest_sha256"],
        "boundary": "test Gate-A package",
    }
    write_json(migration / "gate-a-descriptor.json", gate_descriptor)
    gate_manifest = {
        "files": [
            {"path": source, "sha256": sha(root / target)}
            for source, target in sorted(verify.GATE_A_ROOT_FILE_MAP.items())
        ],
        "subpackages": [
            {
                "path": "native-candidate",
                "manifest_file_sha256": sha(migration / "native-candidate-manifest.json"),
                "manifest_identity": native_manifest["manifest_sha256"],
            }
        ],
        "descriptor_sha256": verify.sha256_bytes(verify.canonical_json_bytes(gate_descriptor)),
        "release_authorized": False,
        "representational_scope_complete": True,
        "boundary": "test Gate-A package",
    }
    gate_manifest["manifest_sha256"] = verify.record_sha256(gate_manifest, "manifest_sha256")
    write_json(migration / "gate-a-manifest.json", gate_manifest)

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
        "gate_a_package_descriptor_sha256": gate_manifest["descriptor_sha256"],
        "producer_workbench_commit": "1" * 40,
        "runtime_execution_pin": "2" * 40,
        "s2_predecessor_commit": "3" * 40,
        "observatory_graph_schema_version": "1",
        "boundary": "test mechanical Gate-A decision",
    }
    gate_decision["decision_sha256"] = verify.record_sha256(gate_decision, "decision_sha256")
    write_json(migration / "gate-a-decision.json", gate_decision)

    file_entries = [
        {"path": relative, "sha256": sha(root / relative)}
        for relative in sorted(verify.CANDIDATE_FILE_PATHS)
    ]
    content_sha = verify.sha256_bytes(verify.canonical_json_bytes(file_entries))
    candidate_id = f"OBS-V2-CAND-{content_sha[:20].upper()}"
    descriptor = {
        "schema_version": "1",
        "release_type": "OBSERVATORY_V2_S2_CANDIDATE",
        "release_tag": "data-v0.3.0-observatory-v2",
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
            "Event": 1,
            "Relationship": 0,
            "Candidate": 1,
            "ReopeningDecision": 0,
        },
        "candidate_content_sha256": content_sha,
        "workbench_compatibility_version": "0.3.0.dev0",
        "producer_workbench_commit": "1" * 40,
        "runtime_execution_pin": "2" * 40,
        "observatory_graph_schema_version": "1",
        "s2_predecessor": {"release_tag": "data-v0.1.0-public-governing", "commit": "3" * 40},
        "frozen_inputs": frozen,
        "migration_proof": {
            "field_proof_sha256": gate_decision["field_proof_sha256"],
            "gate_a_decision_sha256": gate_decision["decision_sha256"],
            "gate_a_manifest_sha256": gate_manifest["manifest_sha256"],
            "gate_a_descriptor_sha256": gate_manifest["descriptor_sha256"],
            "native_candidate_manifest_sha256": sha(migration / "native-candidate-manifest.json"),
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
    manifest["manifest_sha256"] = verify.record_sha256(manifest, "manifest_sha256")
    write_json(root / "descriptor.json", descriptor)
    write_json(root / "manifest.json", manifest)
    return root


def relaunder_top_level(root: Path) -> None:
    descriptor = json.loads((root / "descriptor.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    entries = [
        {"path": relative, "sha256": sha(root / relative)}
        for relative in sorted(verify.CANDIDATE_FILE_PATHS)
    ]
    content_sha = verify.sha256_bytes(verify.canonical_json_bytes(entries))
    candidate_id = f"OBS-V2-CAND-{content_sha[:20].upper()}"
    descriptor["candidate_content_sha256"] = content_sha
    descriptor["candidate_id"] = candidate_id
    write_json(root / "descriptor.json", descriptor)
    manifest["candidate_id"] = candidate_id
    manifest["candidate_content_sha256"] = content_sha
    manifest["files"] = entries
    manifest["descriptor_sha256"] = verify.sha256_bytes(verify.canonical_json_bytes(descriptor))
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = verify.sha256_bytes(verify.canonical_json_bytes(manifest))
    write_json(root / "manifest.json", manifest)


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
        self.assertTrue(report["valid"], report["errors"])
        self.assertFalse(report["published"])
        public = verify.verify_release(self.root, require_published=True)
        self.assertFalse(public["valid"])
        self.assertIn("governance/publication.json is missing", public["errors"])

    def test_exact_authorize_and_publish_chain_verifies(self) -> None:
        authorization = authorize(self.root)
        publication = publish(self.root, authorization)
        report = verify.verify_release(self.root, require_published=True)
        self.assertTrue(report["valid"], report["errors"])
        self.assertTrue(report["published"])
        self.assertEqual(report["authorization_id"], authorization["authorization_id"])
        self.assertEqual(report["publication_id"], publication["publication_id"])

    def test_withhold_cannot_satisfy_publication(self) -> None:
        authorization = authorize(self.root, decision="WITHHOLD")
        publish(self.root, authorization)
        report = verify.verify_release(self.root, require_published=True)
        self.assertFalse(report["valid"])
        self.assertIn("publication requires exactly one active AUTHORIZE record", report["errors"])

    def test_history_sidecar_cannot_be_laundered_by_recomputing_s2_manifest(self) -> None:
        path = self.root / "migration/identity-resolution-history.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + '{"injected":true}\n', encoding="utf-8")
        relaunder_top_level(self.root)
        report = verify.verify_candidate(self.root)
        self.assertFalse(report["valid"])
        self.assertIn(
            "native-candidate copied file digest mismatch: identity-resolution-history.jsonl",
            report["errors"],
        )

    def test_root_preservation_file_cannot_be_laundered(self) -> None:
        path = self.root / "migration/residual-predecessor-state.json"
        write_json(path, {"preserved": "tampered"})
        relaunder_top_level(self.root)
        report = verify.verify_candidate(self.root)
        self.assertFalse(report["valid"])
        self.assertIn("Gate-A copied file digest mismatch: residual-predecessor-state.json", report["errors"])

    def test_graph_record_cannot_be_laundered(self) -> None:
        path = self.root / "records/entities.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + '{"object_class":"Entity","entity_id":"ORG-X"}\n', encoding="utf-8")
        descriptor = json.loads((self.root / "descriptor.json").read_text(encoding="utf-8"))
        descriptor["record_counts"]["Entity"] = 2
        write_json(self.root / "descriptor.json", descriptor)
        relaunder_top_level(self.root)
        report = verify.verify_candidate(self.root)
        self.assertFalse(report["valid"])
        self.assertIn("native-candidate copied file digest mismatch: entities.jsonl", report["errors"])

    def test_native_manifest_substitution_fails_closed(self) -> None:
        path = self.root / "migration/native-candidate-manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["boundary"] = "substituted"
        value["manifest_sha256"] = verify.record_sha256(value, "manifest_sha256")
        write_json(path, value)
        relaunder_top_level(self.root)
        report = verify.verify_candidate(self.root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("native-candidate manifest" in error for error in report["errors"]))

    def test_missing_history_file_fails_fixed_surface(self) -> None:
        (self.root / "migration/regional-expansion-history.jsonl").unlink()
        report = verify.verify_candidate(self.root)
        self.assertFalse(report["valid"])
        self.assertTrue(any("regional-expansion-history.jsonl" in error for error in report["errors"]))

    def test_nonempty_absent_native_class_fails(self) -> None:
        (self.root / "records/assertions.jsonl").write_text("\n", encoding="utf-8")
        relaunder_top_level(self.root)
        report = verify.verify_candidate(self.root)
        self.assertFalse(report["valid"])
        self.assertIn("assertions.jsonl must be exactly empty for this migrated candidate", report["errors"])


if __name__ == "__main__":
    unittest.main()
