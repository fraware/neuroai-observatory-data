#!/usr/bin/env python3
"""Build one deterministic graph-native Observatory-v2 S2 candidate from Gate-A output."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

RECORD_SOURCE_MAP = {
    "entities.jsonl": "entities.jsonl",
    "sources.jsonl": "sources.jsonl",
    "events.jsonl": "events.jsonl",
    "candidates.jsonl": "candidates.jsonl",
}
EMPTY_RECORD_FILES = (
    "observations.jsonl",
    "assertions.jsonl",
    "relationships.jsonl",
    "reopening-decisions.jsonl",
)
NATIVE_MIGRATION_FILES = (
    "entity-predecessor-traces.jsonl",
    "preserved-organizations.jsonl",
    "source-predecessor-traces.jsonl",
    "predecessor-observation-evidence.jsonl",
    "event-predecessor-traces.jsonl",
    "candidate-predecessor-traces.jsonl",
    "identity-resolution-history.jsonl",
    "regional-expansion-history.jsonl",
)
ROOT_MIGRATION_FILES = (
    "v16-adjudication-state.json",
    "v17-successor-lineage.json",
    "residual-predecessor-state.json",
    "duplicate-container-proofs.json",
)
BOUNDARY = (
    "Immutable noncanonical Observatory-v2 S2 candidate generated from one exact Gate-A package. "
    "Candidate validity establishes artifact/lineage integrity only and confers no publication authority."
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_verifier() -> ModuleType:
    path = Path(__file__).resolve().with_name("verify_observatory_v2_release.py")
    spec = importlib.util.spec_from_file_location("verify_observatory_v2_release_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_exact(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def build_candidate(
    gate_a_output: Path,
    output: Path,
    *,
    release_tag: str,
    predecessor_release_tag: str,
) -> dict[str, Any]:
    verifier = load_verifier()
    package = gate_a_output / "gate-a-package"
    native = package / "native-candidate"
    decision_path = gate_a_output / "gate-a-decision.json"
    gate_descriptor = load_json(package / "descriptor.json")
    gate_manifest = load_json(package / "manifest.json")
    native_descriptor = load_json(native / "descriptor.json")
    decision = load_json(decision_path)

    if decision.get("decision") != verifier.MECHANICAL_GATE_A_DECISION or decision.get("gate_a_complete") is not True:
        raise ValueError("Gate-A decision is not mechanical PASS")
    if decision.get("release_authorized") is not False:
        raise ValueError("Gate-A decision must not authorize publication")
    if gate_descriptor.get("s2_predecessor_commit") != decision.get("s2_predecessor_commit"):
        raise ValueError("Gate-A predecessor commit binding mismatch")
    if gate_manifest.get("manifest_sha256") != decision.get("gate_a_package_manifest_sha256"):
        raise ValueError("Gate-A decision manifest binding mismatch")

    if output.exists():
        shutil.rmtree(output)
    (output / "records").mkdir(parents=True)
    (output / "migration").mkdir(parents=True)

    for target_name, source_name in RECORD_SOURCE_MAP.items():
        copy_exact(native / source_name, output / "records" / target_name)
    for target_name in EMPTY_RECORD_FILES:
        (output / "records" / target_name).write_bytes(b"")
    for name in NATIVE_MIGRATION_FILES:
        copy_exact(native / name, output / "migration" / name)
    for name in ROOT_MIGRATION_FILES:
        copy_exact(package / name, output / "migration" / name)
    copy_exact(package / "descriptor.json", output / "migration/gate-a-descriptor.json")
    copy_exact(package / "manifest.json", output / "migration/gate-a-manifest.json")
    copy_exact(decision_path, output / "migration/gate-a-decision.json")
    copy_exact(native / "descriptor.json", output / "migration/native-candidate-descriptor.json")
    copy_exact(native / "manifest.json", output / "migration/native-candidate-manifest.json")

    file_entries = [
        {"path": relative, "sha256": verifier.sha256_bytes((output / relative).read_bytes())}
        for relative in sorted(verifier.CANDIDATE_FILE_PATHS)
    ]
    content_sha = verifier.sha256_bytes(verifier.canonical_json_bytes(file_entries))
    candidate_id = f"OBS-V2-CAND-{content_sha[:20].upper()}"

    counts = native_descriptor.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("native-candidate counts are missing")
    record_counts = {
        "Entity": counts.get("native_entities"),
        "Source": counts.get("native_sources"),
        "Observation": 0,
        "Assertion": 0,
        "Event": counts.get("native_capital_events"),
        "Relationship": 0,
        "Candidate": counts.get("native_change_candidates"),
        "ReopeningDecision": 0,
    }
    if sum(int(value) for value in record_counts.values()) != counts.get("native_candidate_objects"):
        raise ValueError("native-candidate object counts do not reconcile")

    descriptor = {
        "schema_version": "1",
        "release_type": "OBSERVATORY_V2_S2_CANDIDATE",
        "release_tag": release_tag,
        "candidate_id": candidate_id,
        "state": "NONCANONICAL_CANDIDATE",
        "canonical_publication_state": "NOT_AUTHORIZED",
        "release_authorized": False,
        "published": False,
        "record_counts": record_counts,
        "candidate_content_sha256": content_sha,
        "workbench_compatibility_version": gate_descriptor["workbench_compatibility_version"],
        "producer_workbench_commit": gate_descriptor["producer_workbench_commit"],
        "runtime_execution_pin": gate_descriptor["runtime_execution_pin"],
        "observatory_graph_schema_version": str(gate_descriptor["observatory_graph_schema_version"]),
        "s2_predecessor": {
            "release_tag": predecessor_release_tag,
            "commit": gate_descriptor["s2_predecessor_commit"],
        },
        "frozen_inputs": gate_descriptor["inputs"],
        "migration_proof": {
            "field_proof_sha256": decision["field_proof_sha256"],
            "gate_a_decision_sha256": decision["decision_sha256"],
            "gate_a_manifest_sha256": gate_manifest["manifest_sha256"],
            "gate_a_descriptor_sha256": gate_manifest["descriptor_sha256"],
            "native_candidate_manifest_sha256": gate_descriptor["native_candidate_manifest_sha256"],
        },
        "boundary": BOUNDARY,
    }
    manifest = {
        "schema_version": "1",
        "candidate_id": candidate_id,
        "candidate_content_sha256": content_sha,
        "files": file_entries,
        "descriptor_sha256": verifier.sha256_bytes(verifier.canonical_json_bytes(descriptor)),
        "release_authorized": False,
        "published": False,
        "boundary": BOUNDARY,
    }
    manifest["manifest_sha256"] = verifier.sha256_bytes(verifier.canonical_json_bytes(manifest))
    (output / "descriptor.json").write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = verifier.verify_candidate(output)
    if report.get("valid") is not True:
        raise ValueError(f"built S2 candidate failed independent verification: {report.get('errors')}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-a-output", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--predecessor-release-tag", required=True)
    args = parser.parse_args(argv)
    report = build_candidate(
        args.gate_a_output,
        args.output,
        release_tag=args.release_tag,
        predecessor_release_tag=args.predecessor_release_tag,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
