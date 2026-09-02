#!/usr/bin/env python3
"""Run the non-production PRE-G0 B04 Observatory-v2 publication authority proof.

All candidate, authorization, publication, and tamper artifacts live only in an
explicit ephemeral workspace that this script deletes before returning. The only
retained artifact is sanitized proof metadata. No substantive S2 release is created,
authorized, or published.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from neuroai_workbench.api.v1 import (
    PublicObservatoryApiError,
    handle_v1_get,
    load_candidate_preview,
    load_published_release,
)
from neuroai_workbench.observatory_publication import (
    ObservatoryPublicationError,
    record_s2_authorization,
    record_s2_publication,
    verify_s2_authorizations,
    verify_s2_publication_binding,
)
from neuroai_workbench.observatory_s2_release import (
    CANDIDATE_FILE_PATHS,
    OBJECT_FILES,
    S2_CANDIDATE_BOUNDARY,
    verify_observatory_v2_s2_candidate,
)
from neuroai_workbench.util import canonical_json_bytes, sha256_bytes

EXPECTED_WORKBENCH_COMMIT = "33414065e53c45221d29209ef4703b6d900781f7"
STATUS = "PRE_G0_B04_NONPRODUCTION_PUBLICATION_AUTHORITY_PROOF"
SYNTHETIC_ENTITY_ID = "ORG-PRE-G0-B04-SYNTHETIC"
SYNTHETIC_RELEASE_TAG = "pre-g0-b04-synthetic"
SYNTHETIC_PREDECESSOR_TAG = "pre-g0-b04-synthetic-predecessor"
SYNTHETIC_PUBLICATION_REFERENCE = "public-ref:pre-g0-b04:synthetic-test-only"
SYNTHETIC_PUBLICATION_EVIDENCE = b"PRE-G0 B04 synthetic publication evidence only; no substantive or public release performed."
BOUNDARY = (
    "This PRE-G0 proof exercises candidate, authorization, publication binding, and public /v1 gating only in "
    "ephemeral synthetic state. It does not create, authorize, publish, mutate, or validate a substantive S2 release; "
    "does not establish scientific, clinical, regulatory, legal, institutional, or conformance truth; and does not pass G0."
)


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _gate_lineage(root: Path) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    migration = root / "migration"
    migration.mkdir(parents=True, exist_ok=True)
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
        "producer_workbench_commit": EXPECTED_WORKBENCH_COMMIT,
        "runtime_execution_pin": EXPECTED_WORKBENCH_COMMIT,
        "observatory_graph_schema_version": "1",
        "s2_predecessor_commit": "0" * 40,
        "inputs": frozen,
    }
    descriptor_sha = sha256_bytes(canonical_json_bytes(gate_descriptor))
    gate_manifest: dict[str, Any] = {
        "descriptor_sha256": descriptor_sha,
        "release_authorized": False,
    }
    gate_manifest["manifest_sha256"] = sha256_bytes(canonical_json_bytes(gate_manifest))
    decision: dict[str, Any] = {
        "schema_version": "1",
        "decision_type": "OBSERVATORY_V2_GATE_A_MECHANICAL_DECISION",
        "decision": "PASS_REPRESENTATIONAL_MIGRATION_MECHANICALLY_COMPLETE",
        "gate_a_complete": True,
        "release_authorized": False,
        "representational_scope_complete": True,
        "native_v2_materialization_complete": False,
        "field_proof_sha256": "4" * 64,
        "gate_a_package_manifest_sha256": gate_manifest["manifest_sha256"],
        "gate_a_package_descriptor_sha256": descriptor_sha,
        "producer_workbench_commit": EXPECTED_WORKBENCH_COMMIT,
        "runtime_execution_pin": EXPECTED_WORKBENCH_COMMIT,
        "s2_predecessor_commit": "0" * 40,
        "observatory_graph_schema_version": "1",
        "boundary": "Synthetic mechanical PRE-G0 B04 test decision only.",
    }
    decision["decision_sha256"] = sha256_bytes(canonical_json_bytes(decision))
    _json(migration / "gate-a-descriptor.json", gate_descriptor)
    _json(migration / "gate-a-manifest.json", gate_manifest)
    _json(migration / "gate-a-decision.json", decision)
    return frozen, gate_manifest, decision


def build_synthetic_candidate(root: Path) -> Path:
    """Build the same minimal candidate surface accepted by the Workbench contract."""
    records = root / "records"
    records.mkdir(parents=True, exist_ok=True)
    frozen, gate_manifest, decision = _gate_lineage(root)

    for filename in OBJECT_FILES:
        payload = b""
        if filename == "entities.jsonl":
            payload = (
                json.dumps(
                    {
                        "object_class": "Entity",
                        "entity_id": SYNTHETIC_ENTITY_ID,
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
        (records / filename).write_bytes(payload)

    for relative in sorted(CANDIDATE_FILE_PATHS):
        path = root / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")

    file_entries = [
        {"path": relative, "sha256": sha256_bytes((root / relative).read_bytes())}
        for relative in sorted(CANDIDATE_FILE_PATHS)
    ]
    content_sha = sha256_bytes(canonical_json_bytes(file_entries))
    candidate_id = f"OBS-V2-CAND-{content_sha[:20].upper()}"
    descriptor = {
        "schema_version": "1",
        "release_type": "OBSERVATORY_V2_S2_CANDIDATE",
        "release_tag": SYNTHETIC_RELEASE_TAG,
        "candidate_id": candidate_id,
        "state": "NONCANONICAL_CANDIDATE",
        "canonical_publication_state": "NOT_AUTHORIZED",
        "release_authorized": False,
        "published": False,
        "record_counts": {
            "Entity": 1,
            "Source": 0,
            "Observation": 0,
            "Assertion": 0,
            "Event": 0,
            "Relationship": 0,
            "Candidate": 0,
            "ReopeningDecision": 0,
        },
        "candidate_content_sha256": content_sha,
        "workbench_compatibility_version": "0.3.0.dev0",
        "producer_workbench_commit": EXPECTED_WORKBENCH_COMMIT,
        "runtime_execution_pin": EXPECTED_WORKBENCH_COMMIT,
        "observatory_graph_schema_version": "1",
        "s2_predecessor": {
            "release_tag": SYNTHETIC_PREDECESSOR_TAG,
            "commit": "0" * 40,
        },
        "frozen_inputs": frozen,
        "migration_proof": {
            "field_proof_sha256": decision["field_proof_sha256"],
            "gate_a_decision_sha256": decision["decision_sha256"],
            "gate_a_manifest_sha256": gate_manifest["manifest_sha256"],
            "gate_a_descriptor_sha256": gate_manifest["descriptor_sha256"],
            "native_candidate_manifest_sha256": "7" * 64,
        },
        "boundary": S2_CANDIDATE_BOUNDARY,
    }
    manifest: dict[str, Any] = {
        "schema_version": "1",
        "candidate_id": candidate_id,
        "candidate_content_sha256": content_sha,
        "files": file_entries,
        "descriptor_sha256": sha256_bytes(canonical_json_bytes(descriptor)),
        "release_authorized": False,
        "published": False,
        "boundary": S2_CANDIDATE_BOUNDARY,
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json_bytes(manifest))
    _json(root / "descriptor.json", descriptor)
    _json(root / "manifest.json", manifest)
    return root


def _expect_public_loader_refusal(release: Path, *, stage: str) -> str:
    try:
        load_published_release(release)
    except PublicObservatoryApiError as exc:
        return type(exc).__name__
    raise AssertionError(
        f"Public loader unexpectedly accepted synthetic release at stage {stage}"
    )


def _expect_publication_refusal(release: Path) -> str:
    try:
        record_s2_publication(
            release,
            publication_evidence={
                "reference": SYNTHETIC_PUBLICATION_REFERENCE,
                "sha256": sha256_bytes(SYNTHETIC_PUBLICATION_EVIDENCE),
            },
            recorded_at="2026-09-02T14:05:00Z",
        )
    except ObservatoryPublicationError as exc:
        return type(exc).__name__
    raise AssertionError("WITHHOLD state unexpectedly allowed publication binding")


def run_proof(*, workspace: Path, workbench_commit: str) -> dict[str, Any]:
    if workbench_commit != EXPECTED_WORKBENCH_COMMIT:
        raise ValueError(
            f"Workbench commit mismatch: expected {EXPECTED_WORKBENCH_COMMIT}, got {workbench_commit}"
        )
    release = build_synthetic_candidate(workspace / "synthetic-release")
    candidate_errors = verify_observatory_v2_s2_candidate(release)
    if candidate_errors:
        raise AssertionError(
            f"Synthetic candidate failed verification: {candidate_errors}"
        )

    preview = load_candidate_preview(release)
    if preview.get("canonical") is not False or preview.get("published") is not False:
        raise AssertionError(
            "Synthetic candidate preview lost noncanonical candidate boundary"
        )
    candidate_only_refusal = _expect_public_loader_refusal(
        release, stage="candidate_only"
    )

    withhold = record_s2_authorization(
        release,
        decision="WITHHOLD",
        decision_rationale="PRE-G0 B04 synthetic proof: withhold before explicit authorization.",
        recorded_at="2026-09-02T14:05:01Z",
    )["authorization"]
    if withhold.get("decision") != "WITHHOLD":
        raise AssertionError("Synthetic WITHHOLD decision was not recorded")
    withhold_publish_refusal = _expect_publication_refusal(release)

    authorize = record_s2_authorization(
        release,
        decision="AUTHORIZE",
        decision_rationale="PRE-G0 B04 synthetic proof: authorize exact ephemeral candidate only.",
        supersedes_authorization_id=str(withhold["authorization_id"]),
        recorded_at="2026-09-02T14:05:02Z",
    )["authorization"]
    auth_report = verify_s2_authorizations(release)
    if auth_report.get("valid") is not True or auth_report.get("active_count") != 1:
        raise AssertionError(f"Synthetic authorization store is invalid: {auth_report}")
    if authorize.get("decision") != "AUTHORIZE":
        raise AssertionError("Synthetic AUTHORIZE decision was not recorded")
    if authorize.get("supersedes_authorization_id") != withhold.get("authorization_id"):
        raise AssertionError(
            "Synthetic AUTHORIZE did not supersede exact WITHHOLD record"
        )

    prepublication_refusal = _expect_public_loader_refusal(
        release, stage="authorized_not_published"
    )
    evidence_sha = sha256_bytes(SYNTHETIC_PUBLICATION_EVIDENCE)
    publication = record_s2_publication(
        release,
        publication_evidence={
            "reference": SYNTHETIC_PUBLICATION_REFERENCE,
            "sha256": evidence_sha,
        },
        recorded_at="2026-09-02T14:05:03Z",
    )["publication"]
    if publication.get("automatic_publication_performed") is not False:
        raise AssertionError(
            "Synthetic publication record claimed automatic publication"
        )
    binding = verify_s2_publication_binding(release)
    if binding.get("valid") is not True:
        raise AssertionError(f"Synthetic publication binding failed: {binding}")

    published = load_published_release(release)
    health = handle_v1_get(published, "/v1/health")
    if not (
        published.get("canonical") is True
        and published.get("published") is True
        and published.get("release_authorized") is True
        and health.get("status") == "ok"
        and health.get("read_only") is True
        and health.get("writes_supported") is False
    ):
        raise AssertionError(
            "Synthetic published /v1 context lost public read-only authority boundary"
        )

    tampered = workspace / "tampered-copy"
    shutil.copytree(release, tampered)
    with (tampered / "records" / "entities.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(
            json.dumps({"object_class": "Entity", "entity_id": "ORG-TAMPER"}) + "\n"
        )
    tamper_refusal = _expect_public_loader_refusal(
        tampered, stage="tampered_published_copy"
    )

    descriptor = json.loads((release / "descriptor.json").read_text(encoding="utf-8"))
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    return {
        "schema_version": "1",
        "status": STATUS,
        "workbench_commit": workbench_commit,
        "candidate": {
            "synthetic_only": True,
            "entity_id": SYNTHETIC_ENTITY_ID,
            "release_tag": SYNTHETIC_RELEASE_TAG,
            "candidate_id": descriptor["candidate_id"],
            "candidate_content_sha256": descriptor["candidate_content_sha256"],
            "manifest_sha256": manifest["manifest_sha256"],
            "candidate_verification_valid": True,
            "preview_canonical": False,
            "preview_published": False,
            "public_loader_refused_candidate_only": True,
            "candidate_only_refusal_type": candidate_only_refusal,
        },
        "withhold": {
            "authorization_id": withhold["authorization_id"],
            "authorization_sha256": withhold["authorization_sha256"],
            "decision": "WITHHOLD",
            "publication_refused": True,
            "refusal_type": withhold_publish_refusal,
        },
        "authorize": {
            "authorization_id": authorize["authorization_id"],
            "authorization_sha256": authorize["authorization_sha256"],
            "decision": "AUTHORIZE",
            "supersedes_authorization_id": withhold["authorization_id"],
            "authorization_store_valid": True,
            "active_authorization_count": 1,
            "public_loader_refused_before_publication": True,
            "prepublication_refusal_type": prepublication_refusal,
        },
        "publication": {
            "publication_id": publication["publication_id"],
            "publication_sha256": publication["publication_sha256"],
            "publication_evidence_reference": SYNTHETIC_PUBLICATION_REFERENCE,
            "publication_evidence_sha256": evidence_sha,
            "publication_binding_valid": True,
            "automatic_publication_performed": False,
            "substantive_publication_performed": False,
        },
        "public_v1": {
            "loaded_only_after_publication_binding": True,
            "canonical": True,
            "published": True,
            "release_authorized": True,
            "health_status": health["status"],
            "read_only": health["read_only"],
            "writes_supported": health["writes_supported"],
        },
        "tamper": {
            "published_loader_refused_tampered_copy": True,
            "refusal_type": tamper_refusal,
        },
        "controls": {
            "ephemeral_synthetic_state_only": True,
            "repository_release_directory_modified": False,
            "substantive_s2_release_authorized": False,
            "substantive_s2_release_published": False,
            "network_used": False,
            "source_data_used": False,
        },
        "boundary": BOUNDARY,
    }


def execute(*, workspace: Path, output: Path, workbench_commit: str) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    output = output.expanduser().resolve()
    if output == workspace or output.is_relative_to(workspace):
        raise ValueError(
            "Sanitized proof output must be outside the ephemeral synthetic workspace"
        )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        proof = run_proof(workspace=workspace, workbench_commit=workbench_commit)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    proof["controls"]["ephemeral_workspace_deleted"] = not workspace.exists()
    if proof["controls"]["ephemeral_workspace_deleted"] is not True:
        raise AssertionError("Synthetic B04 workspace was not deleted")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(proof, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workbench-commit", required=True)
    args = parser.parse_args(argv)
    proof = execute(
        workspace=args.workspace,
        output=args.output,
        workbench_commit=args.workbench_commit,
    )
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
