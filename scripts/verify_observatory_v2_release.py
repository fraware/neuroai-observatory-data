#!/usr/bin/env python3
"""Independently verify one graph-native Observatory-v2 S2 release directory.

This verifier intentionally uses only the Python standard library. It does not import
neuroai-workbench: S1 produces migration artifacts, while S2 independently checks the
immutable candidate surface, transitive Gate-A/native-candidate lineage, and optional
operator authorization/publication binding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

BOUNDARY = (
    "S2 independent release verification establishes artifact identity and publication lineage only. "
    "It does not establish scientific truth, clinical or regulatory authorization, conformance, "
    "institutional endorsement, or global completeness."
)
DESIGNATED_OPERATOR = "fraware"
MECHANICAL_GATE_A_DECISION = "PASS_REPRESENTATIONAL_MIGRATION_MECHANICALLY_COMPLETE"
FROZEN_INPUT_ROLES = frozenset(
    {"V14", "V16", "DELTA16", "V17", "PRIMA17", "SOURCE_REGISTER14", "MONITOR15"}
)
OBJECT_CLASS_BY_FILE = {
    "entities.jsonl": "Entity",
    "sources.jsonl": "Source",
    "observations.jsonl": "Observation",
    "assertions.jsonl": "Assertion",
    "events.jsonl": "Event",
    "relationships.jsonl": "Relationship",
    "candidates.jsonl": "Candidate",
    "reopening-decisions.jsonl": "ReopeningDecision",
}
MIGRATION_FILES = frozenset(
    {
        "entity-predecessor-traces.jsonl",
        "preserved-organizations.jsonl",
        "source-predecessor-traces.jsonl",
        "predecessor-observation-evidence.jsonl",
        "event-predecessor-traces.jsonl",
        "candidate-predecessor-traces.jsonl",
        "identity-resolution-history.jsonl",
        "regional-expansion-history.jsonl",
        "v16-adjudication-state.json",
        "v17-successor-lineage.json",
        "residual-predecessor-state.json",
        "duplicate-container-proofs.json",
        "gate-a-descriptor.json",
        "gate-a-manifest.json",
        "gate-a-decision.json",
        "native-candidate-descriptor.json",
        "native-candidate-manifest.json",
    }
)
CANDIDATE_FILE_PATHS = frozenset(
    {f"records/{filename}" for filename in OBJECT_CLASS_BY_FILE}
    | {f"migration/{filename}" for filename in MIGRATION_FILES}
)
GATE_A_ROOT_FILE_MAP = {
    "duplicate-container-proofs.json": "migration/duplicate-container-proofs.json",
    "residual-predecessor-state.json": "migration/residual-predecessor-state.json",
    "v16-adjudication-state.json": "migration/v16-adjudication-state.json",
    "v17-successor-lineage.json": "migration/v17-successor-lineage.json",
}
NATIVE_CANDIDATE_FILE_MAP = {
    "candidate-predecessor-traces.jsonl": "migration/candidate-predecessor-traces.jsonl",
    "candidates.jsonl": "records/candidates.jsonl",
    "entities.jsonl": "records/entities.jsonl",
    "entity-predecessor-traces.jsonl": "migration/entity-predecessor-traces.jsonl",
    "event-predecessor-traces.jsonl": "migration/event-predecessor-traces.jsonl",
    "events.jsonl": "records/events.jsonl",
    "identity-resolution-history.jsonl": "migration/identity-resolution-history.jsonl",
    "predecessor-observation-evidence.jsonl": "migration/predecessor-observation-evidence.jsonl",
    "preserved-organizations.jsonl": "migration/preserved-organizations.jsonl",
    "regional-expansion-history.jsonl": "migration/regional-expansion-history.jsonl",
    "source-predecessor-traces.jsonl": "migration/source-predecessor-traces.jsonl",
    "sources.jsonl": "records/sources.jsonl",
}
NATIVE_GRAPH_COUNT_FIELDS = {
    "Entity": "native_entities",
    "Source": "native_sources",
    "Event": "native_capital_events",
    "Candidate": "native_change_candidates",
}
EMPTY_NATIVE_CLASSES = frozenset({"Observation", "Assertion", "Relationship", "ReopeningDecision"})


class VerificationError(ValueError):
    """Raised for malformed verifier inputs."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def record_sha256(record: dict[str, Any], field: str) -> str:
    return sha256_bytes(canonical_json_bytes({key: value for key, value in record.items() if key != field}))


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return value


def is_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def safe_release_path(release_dir: Path, raw_path: str) -> Path:
    logical = PurePosixPath(raw_path)
    if logical.is_absolute() or not logical.parts or ".." in logical.parts or logical.as_posix() != raw_path:
        raise VerificationError(f"unsafe candidate file path: {raw_path}")
    root = release_dir.resolve()
    target = release_dir.joinpath(*logical.parts)
    if not target.resolve(strict=False).is_relative_to(root):
        raise VerificationError(f"candidate file escapes release root: {raw_path}")
    return target


def graph_file_count(path: Path, expected_class: str) -> tuple[int, list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return 0, [f"missing graph record file: {path.name}"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return 0, [f"cannot read graph record file {path.name}: {exc}"]
    count = 0
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        count += 1
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name}:{line_number}: graph record must be an object")
        elif value.get("object_class") != expected_class:
            errors.append(
                f"{path.name}:{line_number}: expected object_class {expected_class}, got {value.get('object_class')!r}"
            )
    return count, errors


def candidate_reference(descriptor: dict[str, Any], manifest: dict[str, Any]) -> dict[str, str]:
    predecessor = descriptor.get("s2_predecessor")
    if not isinstance(predecessor, dict):
        raise VerificationError("candidate predecessor reference is missing")
    return {
        "candidate_id": str(descriptor.get("candidate_id") or ""),
        "release_tag": str(descriptor.get("release_tag") or ""),
        "manifest_sha256": str(manifest.get("manifest_sha256") or ""),
        "descriptor_sha256": str(manifest.get("descriptor_sha256") or ""),
        "candidate_content_sha256": str(descriptor.get("candidate_content_sha256") or ""),
        "workbench_compatibility_version": str(descriptor.get("workbench_compatibility_version") or ""),
        "producer_workbench_commit": str(descriptor.get("producer_workbench_commit") or ""),
        "runtime_execution_pin": str(descriptor.get("runtime_execution_pin") or ""),
        "observatory_graph_schema_version": str(descriptor.get("observatory_graph_schema_version") or ""),
        "s2_predecessor_release_tag": str(predecessor.get("release_tag") or ""),
        "s2_predecessor_commit": str(predecessor.get("commit") or ""),
    }


def _manifest_entries(manifest: dict[str, Any], *, label: str) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    result: dict[str, str] = {}
    raw_entries = manifest.get("files")
    if not isinstance(raw_entries, list):
        return {}, [f"{label} files manifest is missing"]
    for item in raw_entries:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            errors.append(f"{label} file entry is invalid")
            continue
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path or path in result or not is_hex(digest, 64):
            errors.append(f"{label} file entry identity is invalid")
            continue
        result[path] = digest
    return result, errors


def verify_gate_a_lineage(release_dir: Path, descriptor: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        gate_descriptor_path = release_dir / "migration/gate-a-descriptor.json"
        gate_manifest_path = release_dir / "migration/gate-a-manifest.json"
        decision_path = release_dir / "migration/gate-a-decision.json"
        native_descriptor_path = release_dir / "migration/native-candidate-descriptor.json"
        native_manifest_path = release_dir / "migration/native-candidate-manifest.json"
        gate_descriptor = load_object(gate_descriptor_path, "Gate-A descriptor")
        gate_manifest = load_object(gate_manifest_path, "Gate-A manifest")
        decision = load_object(decision_path, "Gate-A decision")
        native_descriptor = load_object(native_descriptor_path, "native-candidate descriptor")
        native_manifest = load_object(native_manifest_path, "native-candidate manifest")
    except VerificationError as exc:
        return [str(exc)]

    if decision.get("decision_sha256") != record_sha256(decision, "decision_sha256"):
        errors.append("Gate-A decision digest mismatch")
    if decision.get("decision_type") != "OBSERVATORY_V2_GATE_A_MECHANICAL_DECISION":
        errors.append("Gate-A decision type mismatch")
    if decision.get("decision") != MECHANICAL_GATE_A_DECISION:
        errors.append("Gate-A decision is not mechanical PASS")
    if decision.get("gate_a_complete") is not True:
        errors.append("Gate-A decision does not close the mechanical gate")
    if decision.get("release_authorized") is not False:
        errors.append("Gate-A decision improperly authorizes publication")
    if decision.get("representational_scope_complete") is not True:
        errors.append("Gate-A decision lost representational completeness")
    if decision.get("native_v2_materialization_complete") is not False:
        errors.append("Gate-A decision improperly claims full native materialization")

    controlled_gate_manifest = {key: value for key, value in gate_manifest.items() if key != "manifest_sha256"}
    gate_manifest_identity = sha256_bytes(canonical_json_bytes(controlled_gate_manifest))
    gate_descriptor_identity = sha256_bytes(canonical_json_bytes(gate_descriptor))
    if gate_manifest.get("manifest_sha256") != gate_manifest_identity:
        errors.append("Gate-A manifest identity mismatch")
    if gate_manifest.get("descriptor_sha256") != gate_descriptor_identity:
        errors.append("Gate-A descriptor identity mismatch")
    if decision.get("gate_a_package_manifest_sha256") != gate_manifest_identity:
        errors.append("Gate-A decision/manifest binding mismatch")
    if decision.get("gate_a_package_descriptor_sha256") != gate_descriptor_identity:
        errors.append("Gate-A decision/descriptor binding mismatch")

    gate_entries, gate_entry_errors = _manifest_entries(gate_manifest, label="Gate-A")
    errors.extend(gate_entry_errors)
    if set(gate_entries) != set(GATE_A_ROOT_FILE_MAP):
        errors.append("Gate-A root file surface mismatch")
    for source_name, candidate_path in GATE_A_ROOT_FILE_MAP.items():
        path = release_dir / candidate_path
        if path.is_file() and gate_entries.get(source_name) != sha256_bytes(path.read_bytes()):
            errors.append(f"Gate-A copied file digest mismatch: {source_name}")

    subpackages = gate_manifest.get("subpackages")
    if not isinstance(subpackages, list) or len(subpackages) != 1 or not isinstance(subpackages[0], dict):
        errors.append("Gate-A native-candidate subpackage declaration mismatch")
        subpackage: dict[str, Any] = {}
    else:
        subpackage = subpackages[0]
        if subpackage.get("path") != "native-candidate":
            errors.append("Gate-A native-candidate subpackage path mismatch")

    native_manifest_file_sha = sha256_bytes(native_manifest_path.read_bytes())
    native_descriptor_file_sha = sha256_bytes(native_descriptor_path.read_bytes())
    controlled_native_manifest = {key: value for key, value in native_manifest.items() if key != "manifest_sha256"}
    native_manifest_identity = sha256_bytes(canonical_json_bytes(controlled_native_manifest))
    native_descriptor_identity = sha256_bytes(canonical_json_bytes(native_descriptor))
    if native_manifest.get("manifest_sha256") != native_manifest_identity:
        errors.append("native-candidate manifest identity mismatch")
    if native_manifest.get("descriptor_sha256") != native_descriptor_identity:
        errors.append("native-candidate descriptor identity mismatch")
    if subpackage.get("manifest_file_sha256") != native_manifest_file_sha:
        errors.append("Gate-A native-candidate manifest file binding mismatch")
    if subpackage.get("manifest_identity") != native_manifest_identity:
        errors.append("Gate-A native-candidate manifest identity binding mismatch")
    if gate_descriptor.get("native_candidate_manifest_sha256") != native_manifest_file_sha:
        errors.append("Gate-A descriptor native-candidate manifest file binding mismatch")
    if gate_descriptor.get("native_candidate_descriptor_sha256") != native_descriptor_file_sha:
        errors.append("Gate-A descriptor native-candidate descriptor file binding mismatch")
    if gate_descriptor.get("native_candidate_manifest_identity") != native_manifest_identity:
        errors.append("Gate-A descriptor native-candidate manifest identity mismatch")

    native_entries, native_entry_errors = _manifest_entries(native_manifest, label="native-candidate")
    errors.extend(native_entry_errors)
    if set(native_entries) != set(NATIVE_CANDIDATE_FILE_MAP):
        errors.append("native-candidate governed file surface mismatch")
    for source_name, candidate_path in NATIVE_CANDIDATE_FILE_MAP.items():
        path = release_dir / candidate_path
        if path.is_file() and native_entries.get(source_name) != sha256_bytes(path.read_bytes()):
            errors.append(f"native-candidate copied file digest mismatch: {source_name}")

    for filename, object_class in OBJECT_CLASS_BY_FILE.items():
        if object_class in EMPTY_NATIVE_CLASSES:
            path = release_dir / "records" / filename
            if path.is_file() and path.read_bytes() != b"":
                errors.append(f"{filename} must be exactly empty for this migrated candidate")

    native_counts = native_descriptor.get("counts")
    candidate_counts = descriptor.get("record_counts")
    if not isinstance(native_counts, dict) or not isinstance(candidate_counts, dict):
        errors.append("native/S2 record count lineage is missing")
    else:
        for object_class, native_field in NATIVE_GRAPH_COUNT_FIELDS.items():
            if candidate_counts.get(object_class) != native_counts.get(native_field):
                errors.append(f"native/S2 {object_class} count binding mismatch")
        if sum(int(candidate_counts.get(name, 0)) for name in OBJECT_CLASS_BY_FILE.values()) != native_counts.get(
            "native_candidate_objects"
        ):
            errors.append("native/S2 total object count binding mismatch")
        if native_counts.get("preserved_identity_resolution_history") != 26:
            errors.append("native-candidate identity-resolution history count mismatch")
        if native_counts.get("preserved_regional_expansion_history") != 13:
            errors.append("native-candidate regional-expansion history count mismatch")

    for field in ("producer_workbench_commit", "runtime_execution_pin", "s2_predecessor_commit"):
        if decision.get(field) != gate_descriptor.get(field):
            errors.append(f"Gate-A decision {field} binding mismatch")
    if str(decision.get("observatory_graph_schema_version") or "") != str(
        gate_descriptor.get("observatory_graph_schema_version") or ""
    ):
        errors.append("Gate-A graph-schema binding mismatch")

    candidate_bindings = {
        "workbench_compatibility_version": gate_descriptor.get("workbench_compatibility_version"),
        "producer_workbench_commit": gate_descriptor.get("producer_workbench_commit"),
        "runtime_execution_pin": gate_descriptor.get("runtime_execution_pin"),
        "observatory_graph_schema_version": str(gate_descriptor.get("observatory_graph_schema_version") or ""),
    }
    for field, expected in candidate_bindings.items():
        observed = str(descriptor.get(field) or "") if field == "observatory_graph_schema_version" else descriptor.get(field)
        if observed != expected:
            errors.append(f"candidate/Gate-A {field} binding mismatch")
    predecessor = descriptor.get("s2_predecessor")
    if not isinstance(predecessor, dict) or predecessor.get("commit") != gate_descriptor.get("s2_predecessor_commit"):
        errors.append("candidate/Gate-A S2 predecessor commit mismatch")

    proof = descriptor.get("migration_proof")
    if not isinstance(proof, dict):
        errors.append("candidate migration_proof is missing")
    else:
        bindings = {
            "field_proof_sha256": decision.get("field_proof_sha256"),
            "gate_a_decision_sha256": decision.get("decision_sha256"),
            "gate_a_manifest_sha256": gate_manifest_identity,
            "gate_a_descriptor_sha256": gate_descriptor_identity,
            "native_candidate_manifest_sha256": native_manifest_file_sha,
        }
        for field, expected in bindings.items():
            if proof.get(field) != expected:
                errors.append(f"candidate migration proof {field} binding mismatch")

    frozen_inputs = descriptor.get("frozen_inputs")
    if not isinstance(frozen_inputs, dict) or set(frozen_inputs) != FROZEN_INPUT_ROLES:
        errors.append("candidate must bind exactly seven frozen input roles")
    else:
        for role, digest in frozen_inputs.items():
            if not is_hex(digest, 64):
                errors.append(f"invalid frozen input digest for {role}")
        if frozen_inputs != gate_descriptor.get("inputs"):
            errors.append("candidate frozen-input binding differs from Gate-A descriptor")
    return sorted(set(errors))


def verify_candidate(release_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        descriptor = load_object(release_dir / "descriptor.json", "candidate descriptor")
        manifest = load_object(release_dir / "manifest.json", "candidate manifest")
    except VerificationError as exc:
        return {"valid": False, "errors": [str(exc)], "published": False}

    if descriptor.get("schema_version") != "1" or manifest.get("schema_version") != "1":
        errors.append("candidate schema version mismatch")
    if descriptor.get("release_type") != "OBSERVATORY_V2_S2_CANDIDATE":
        errors.append("candidate release_type mismatch")
    if descriptor.get("state") != "NONCANONICAL_CANDIDATE":
        errors.append("candidate state mismatch")
    if descriptor.get("canonical_publication_state") != "NOT_AUTHORIZED":
        errors.append("candidate canonical publication state mismatch")
    if descriptor.get("release_authorized") is not False or descriptor.get("published") is not False:
        errors.append("candidate descriptor must remain unauthorized and unpublished")
    if manifest.get("release_authorized") is not False or manifest.get("published") is not False:
        errors.append("candidate manifest must remain unauthorized and unpublished")

    if manifest.get("descriptor_sha256") != sha256_bytes(canonical_json_bytes(descriptor)):
        errors.append("candidate descriptor digest mismatch")
    controlled_manifest = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != sha256_bytes(canonical_json_bytes(controlled_manifest)):
        errors.append("candidate manifest identity mismatch")

    for field, length in (
        ("producer_workbench_commit", 40),
        ("runtime_execution_pin", 40),
        ("candidate_content_sha256", 64),
    ):
        if not is_hex(descriptor.get(field), length):
            errors.append(f"candidate {field} is malformed")
    if not str(descriptor.get("workbench_compatibility_version") or "").strip():
        errors.append("candidate Workbench compatibility version is missing")
    if not str(descriptor.get("observatory_graph_schema_version") or "").strip():
        errors.append("candidate graph schema version is missing")
    predecessor = descriptor.get("s2_predecessor")
    if not isinstance(predecessor, dict) or not str(predecessor.get("release_tag") or "").strip():
        errors.append("candidate predecessor release identity is missing")
    elif not is_hex(predecessor.get("commit"), 40):
        errors.append("candidate predecessor commit is malformed")

    proof = descriptor.get("migration_proof")
    if not isinstance(proof, dict):
        errors.append("candidate migration_proof is missing")
    else:
        required_proof_fields = {
            "field_proof_sha256",
            "gate_a_decision_sha256",
            "gate_a_manifest_sha256",
            "gate_a_descriptor_sha256",
            "native_candidate_manifest_sha256",
        }
        if set(proof) != required_proof_fields:
            errors.append("candidate migration_proof field set mismatch")
        for field in required_proof_fields:
            if not is_hex(proof.get(field), 64):
                errors.append(f"candidate migration proof {field} is malformed")

    file_entries = manifest.get("files")
    observed_entries: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(file_entries, list):
        errors.append("candidate files manifest is missing")
    else:
        for item in file_entries:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"} or not isinstance(item.get("path"), str):
                errors.append("candidate file entry is invalid")
                continue
            raw_path = item["path"]
            if raw_path in seen:
                errors.append(f"duplicate candidate file path: {raw_path}")
                continue
            seen.add(raw_path)
            if raw_path not in CANDIDATE_FILE_PATHS:
                errors.append(f"candidate file outside governed allowlist: {raw_path}")
                continue
            try:
                file_path = safe_release_path(release_dir, raw_path)
            except VerificationError as exc:
                errors.append(str(exc))
                continue
            if not file_path.is_file():
                errors.append(f"candidate file missing: {raw_path}")
                continue
            observed = sha256_bytes(file_path.read_bytes())
            if item.get("sha256") != observed:
                errors.append(f"candidate file digest mismatch: {raw_path}")
            observed_entries.append({"path": raw_path, "sha256": observed})

    if seen != CANDIDATE_FILE_PATHS:
        errors.append(
            "candidate file surface mismatch: "
            f"missing={sorted(CANDIDATE_FILE_PATHS - seen)}, extra={sorted(seen - CANDIDATE_FILE_PATHS)}"
        )
    observed_entries.sort(key=lambda item: item["path"])
    content_sha = sha256_bytes(canonical_json_bytes(observed_entries))
    if manifest.get("candidate_content_sha256") != content_sha or descriptor.get("candidate_content_sha256") != content_sha:
        errors.append("candidate content identity mismatch")
    expected_candidate_id = f"OBS-V2-CAND-{content_sha[:20].upper()}"
    if descriptor.get("candidate_id") != expected_candidate_id or manifest.get("candidate_id") != expected_candidate_id:
        errors.append("candidate_id does not match content identity")

    expected_counts: dict[str, int] = {}
    for filename, object_class in OBJECT_CLASS_BY_FILE.items():
        count, class_errors = graph_file_count(release_dir / "records" / filename, object_class)
        expected_counts[object_class] = count
        errors.extend(class_errors)
    if descriptor.get("record_counts") != expected_counts:
        errors.append("candidate record-count reconciliation mismatch")
    errors.extend(verify_gate_a_lineage(release_dir, descriptor))
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "candidate_id": descriptor.get("candidate_id"),
        "manifest_sha256": manifest.get("manifest_sha256"),
        "candidate_reference": candidate_reference(descriptor, manifest),
        "published": False,
        "boundary": BOUNDARY,
    }


def load_authorizations(release_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    root = release_dir / "governance" / "authorizations"
    if not root.exists():
        return [], []
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            records.append(load_object(path, f"authorization {path.name}"))
        except VerificationError as exc:
            errors.append(str(exc))
    return records, errors


def verify_authorizations(release_dir: Path, expected_candidate_ref: dict[str, str]) -> dict[str, Any]:
    records, errors = load_authorizations(release_dir)
    index: dict[str, dict[str, Any]] = {}
    superseded_counts: dict[str, int] = {}
    for record in records:
        auth_id = str(record.get("authorization_id") or "")
        if not auth_id or auth_id in index:
            errors.append("authorization identifiers must be non-empty and unique")
            continue
        index[auth_id] = record
        if record.get("schema_version") != "1" or record.get("authorization_type") != "OBSERVATORY_V2_S2_OPERATOR_AUTHORIZATION":
            errors.append(f"{auth_id}: authorization type/schema mismatch")
        if record.get("recorded_by") != DESIGNATED_OPERATOR:
            errors.append(f"{auth_id}: wrong designated operator")
        if record.get("decision") not in {"AUTHORIZE", "WITHHOLD"} or not str(record.get("decision_rationale") or "").strip():
            errors.append(f"{auth_id}: decision/rationale invalid")
        if record.get("candidate_reference") != expected_candidate_ref:
            errors.append(f"{auth_id}: candidate binding mismatch")
        if record.get("authorization_sha256") != record_sha256(record, "authorization_sha256"):
            errors.append(f"{auth_id}: authorization digest mismatch")
        prior = record.get("supersedes_authorization_id")
        if prior:
            superseded_counts[str(prior)] = superseded_counts.get(str(prior), 0) + 1

    for auth_id, record in index.items():
        prior_id = str(record.get("supersedes_authorization_id") or "")
        if prior_id:
            prior = index.get(prior_id)
            if prior is None:
                errors.append(f"{auth_id}: supersession target missing")
            elif prior.get("candidate_reference") != record.get("candidate_reference"):
                errors.append(f"{auth_id}: supersession changes candidate binding")
        visited: set[str] = set()
        cursor = auth_id
        while cursor:
            if cursor in visited:
                errors.append("authorization supersession cycle detected")
                break
            visited.add(cursor)
            current = index.get(cursor)
            cursor = str(current.get("supersedes_authorization_id") or "") if current else ""
    if any(count != 1 for count in superseded_counts.values()):
        errors.append("an authorization is superseded more than once")

    superseded = set(superseded_counts)
    active = [record for auth_id, record in index.items() if auth_id not in superseded]
    if len(active) > 1:
        errors.append("candidate has multiple active authorizations")
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "records": records,
        "active": active,
    }


def verify_publication(release_dir: Path, candidate_report: dict[str, Any]) -> dict[str, Any]:
    errors = list(candidate_report.get("errors") or [])
    if candidate_report.get("valid") is not True:
        errors.append("candidate is invalid")
    expected_ref = candidate_report.get("candidate_reference")
    if not isinstance(expected_ref, dict):
        return {"valid": False, "errors": sorted(set(errors + ["candidate reference missing"])), "published": False}

    authorization_report = verify_authorizations(release_dir, expected_ref)
    errors.extend(authorization_report["errors"])
    active = authorization_report["active"]
    publication_path = release_dir / "governance" / "publication.json"
    if not publication_path.is_file():
        errors.append("governance/publication.json is missing")
        return {"valid": False, "errors": sorted(set(errors)), "published": False}
    try:
        publication = load_object(publication_path, "publication record")
    except VerificationError as exc:
        return {"valid": False, "errors": sorted(set(errors + [str(exc)])), "published": False}

    if len(active) != 1 or active[0].get("decision") != "AUTHORIZE":
        errors.append("publication requires exactly one active AUTHORIZE record")
        authorization = None
    else:
        authorization = active[0]
    if publication.get("schema_version") != "1" or publication.get("publication_type") != "OBSERVATORY_V2_S2_PUBLICATION":
        errors.append("publication type/schema mismatch")
    if publication.get("recorded_by") != DESIGNATED_OPERATOR:
        errors.append("publication wrong designated operator")
    if publication.get("automatic_publication_performed") is not False:
        errors.append("publication must record automatic_publication_performed=false")
    if publication.get("candidate_reference") != expected_ref:
        errors.append("publication candidate binding mismatch")
    if publication.get("publication_sha256") != record_sha256(publication, "publication_sha256"):
        errors.append("publication digest mismatch")
    if authorization is not None:
        expected_auth_ref = {
            "authorization_id": authorization.get("authorization_id"),
            "authorization_sha256": authorization.get("authorization_sha256"),
        }
        if publication.get("authorization_reference") != expected_auth_ref:
            errors.append("publication authorization binding mismatch")
    evidence = publication.get("publication_evidence")
    if not isinstance(evidence, dict):
        errors.append("publication evidence missing")
    else:
        reference = str(evidence.get("reference") or "")
        if not reference.startswith("public-ref:") or reference == "public-ref:":
            errors.append("publication evidence requires non-empty public-ref:")
        if not is_hex(evidence.get("sha256"), 64):
            errors.append("publication evidence digest malformed")

    if authorization is not None:
        for record in authorization_report["records"]:
            if record.get("supersedes_authorization_id") == authorization.get("authorization_id"):
                errors.append("published authorization cannot be superseded")
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "published": not errors,
        "candidate_id": candidate_report.get("candidate_id"),
        "manifest_sha256": candidate_report.get("manifest_sha256"),
        "authorization_id": authorization.get("authorization_id") if authorization else None,
        "publication_id": publication.get("publication_id"),
        "boundary": BOUNDARY,
    }


def verify_release(release_dir: Path, *, require_published: bool = False) -> dict[str, Any]:
    candidate = verify_candidate(release_dir)
    if not require_published:
        return candidate
    return verify_publication(release_dir, candidate)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--require-published", action="store_true")
    args = parser.parse_args(argv)
    report = verify_release(args.release_dir, require_published=args.require_published)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
