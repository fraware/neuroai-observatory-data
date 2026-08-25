from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "migration" / "phase4-repository-split-v0.1.json"

EXPECTED_SOURCE_HEAD = "ee51f6fcbd679d2b0ed5aeb4593424543201e496"
EXPECTED_SOURCE_TREE = "c8671f41518ecd259c7c08c25b1aed74aeb896c5"
EXPECTED_SOURCE_BASE = "58a1ed02f5e1d506a3f692b3332dd55d34916f8c"
EXPECTED_ENTRY_COUNT = 46
ALLOWED_DISPOSITIONS = {
    "RETAINED_IN_DATA_REPO",
    "MOVED_TO_WORKBENCH",
    "SUPERSEDED",
    "DELETED_AS_DIAGNOSTIC",
}


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_source_boundary_is_exact_and_destination_binding_remains_pending() -> None:
    manifest = _manifest()

    assert manifest["source_head_sha"] == EXPECTED_SOURCE_HEAD
    assert manifest["source_tree_sha"] == EXPECTED_SOURCE_TREE
    assert manifest["source_base_sha"] == EXPECTED_SOURCE_BASE
    assert manifest["source_compare"] == {
        "ahead_by": 116,
        "behind_by": 0,
        "changed_files": 46,
        "additions": 10171,
        "deletions": 1,
    }
    assert manifest["status"] == "SOURCE_BLOBS_RECONCILED_DESTINATIONS_PENDING"
    assert manifest["blob_reconciliation_state"] == "SOURCE_BLOBS_VERIFIED_DESTINATION_BINDING_PENDING"


def test_every_source_path_is_classified_once() -> None:
    manifest = _manifest()
    entries = manifest["entries"]
    paths = [entry["path"] for entry in entries]

    assert manifest["entry_count"] == EXPECTED_ENTRY_COUNT
    assert len(entries) == EXPECTED_ENTRY_COUNT
    assert len(paths) == len(set(paths))
    assert set(manifest["allowed_dispositions"]) == ALLOWED_DISPOSITIONS
    assert all(entry["disposition"] in ALLOWED_DISPOSITIONS for entry in entries)


def test_every_source_blob_identity_is_bound_to_the_frozen_source_tree() -> None:
    manifest = _manifest()
    entries = manifest["entries"]

    assert manifest["source_blob_reconciliation"]["entry_count"] == EXPECTED_ENTRY_COUNT
    assert manifest["source_blob_reconciliation"]["source_blob_sha_count"] == EXPECTED_ENTRY_COUNT
    assert manifest["source_blob_reconciliation"]["null_source_blob_sha_count"] == 0
    assert all(re.fullmatch(r"[0-9a-f]{40}", entry["original_git_blob_sha"]) for entry in entries)

    by_path = {entry["path"]: entry for entry in entries}
    assert by_path["scripts/acquire_science_candidates.py"]["original_git_blob_sha"] == (
        "5aecc94d943313e94f6dbde2665a7cac085ff911"
    )
    assert by_path["science/discovery-protocol-v0.1.json"]["original_git_blob_sha"] == (
        "0803b1b9aef1f0ace975149dbaad7b031818d263"
    )
    assert by_path["tests/test_science_graph_contract.py"]["original_git_blob_sha"] == (
        "f7060ec78438ac1fcd1312c965916221105bc18d"
    )
    assert "destination commit/blob identities remain pending" in manifest["authority_boundary"]


def test_operational_runtime_and_infrastructure_are_not_retained_in_s2() -> None:
    manifest = _manifest()
    by_path = {entry["path"]: entry for entry in manifest["entries"]}

    moved = {
        "infra/aws-phase4-custody/main.tf",
        "scripts/acquire_science_candidates.py",
        "scripts/acquire_science_candidates_strict.py",
        "scripts/run_science_acquisition.py",
        "scripts/science_http_transport.py",
        "scripts/preflight_science_custody.py",
        "scripts/verify_science_acquisition.py",
        "scripts/verify_science_candidate_provenance.py",
        "scripts/verify_science_retry_custody.py",
    }
    for path in moved:
        assert by_path[path]["disposition"] == "MOVED_TO_WORKBENCH"


def test_publication_contracts_are_retained_in_s2() -> None:
    manifest = _manifest()
    by_path = {entry["path"]: entry for entry in manifest["entries"]}

    retained = {
        "fixtures/vnext/science-acquisition.synthetic.json",
        "identity/namespaces-v0.1.json",
        "schemas/vnext/acquisition-freeze.schema.json",
        "schemas/vnext/science-candidate-record.schema.json",
        "schemas/vnext/source-adapter.schema.json",
        "science/acquisition-rights-decision-v0.1.md",
        "science/adapters-v0.1.json",
        "science/discovery-protocol-v0.1.json",
        "science/query-compilation-v0.1.json",
        "science/query-compilation-v0.2.json",
        "tests/test_science_graph_contract.py",
    }
    for path in retained:
        assert by_path[path]["disposition"] == "RETAINED_IN_DATA_REPO"


def test_split_has_no_unclassified_disposition() -> None:
    manifest = _manifest()
    counts = Counter(entry["disposition"] for entry in manifest["entries"])

    assert sum(counts.values()) == EXPECTED_ENTRY_COUNT
    assert counts["MOVED_TO_WORKBENCH"] > counts["RETAINED_IN_DATA_REPO"]
    assert counts["SUPERSEDED"] >= 1
    assert counts["DELETED_AS_DIAGNOSTIC"] == 1
