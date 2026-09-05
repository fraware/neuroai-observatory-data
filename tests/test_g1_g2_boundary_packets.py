from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

D1_PATH = ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json"
D2_PATH = ROOT / "curation" / "CAPABILITY_CONTEXT_TAXONOMY_v0.1.json"
D1_SCHEMA_PATH = ROOT / "schemas" / "landscape-research-contract-v0.1.schema.json"
D2_SCHEMA_PATH = ROOT / "schemas" / "capability-context-taxonomy-v0.1.schema.json"
HISTORICAL_G1_PACKET_PATH = (
    ROOT
    / "curation"
    / "HUMAN_G1_DISPOSITION_PACKET_OBSERVATORY_RECOVERY_2026-09-03_v0.1.json"
)
CURRENT_REVIEW_BINDING_PATH = (
    ROOT
    / "curation"
    / "PRE_G1_D1_D2_REVIEW_BINDING_D1_CONSTRUCT_VALIDITY_2026-09-05_v0.1.json"
)
PRE_G2_TEMPLATE_PATH = (
    ROOT
    / "curation"
    / "PUBLIC_PRE_G2_S2_BINDINGS_TEMPLATE_OBSERVATORY_RECOVERY_2026-09-03_v0.1.json"
)
PRE_G2_BOUND_PATH = (
    ROOT
    / "curation"
    / "PUBLIC_PRE_G2_S2_BINDINGS_OBSERVATORY_RECOVERY_2026-09-03_BOUND_v0.1.json"
)

HISTORICAL_G1_PACKET_ID = "HUMAN-G1-DISP-PACKET-2026-09-03-v0.1"
HISTORICAL_D1_SCHEMA_SHA256 = (
    "8dc3f15cc8c9857b9c0457b36810600a2789e9d3b34d0facbf45f0143de3ed25"
)
HISTORICAL_D1_CANONICAL_SHA256 = (
    "fcd438c51d7af813ee10b31928090dc45f172630dccc5c9e704a5ce32086c09d"
)
HISTORICAL_D2_QUESTION_BINDINGS = ["RQ-02", "RQ-04", "RQ-05", "RQ-06"]

G0_TRANSPORT_PIN = "685f1597a2a63f2e2217f65f115a67ac3e35cc55"
PRE_G2_SOFTWARE_BINDING_SHA = "336da167700a7ce2894c27826f8a1c999e1ee844"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def find_values_for_keys_containing(value: Any, substring: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if substring in str(key):
                found.append(child)
            found.extend(find_values_for_keys_containing(child, substring))
    elif isinstance(value, list):
        for item in value:
            found.extend(find_values_for_keys_containing(item, substring))
    return found


class G1G2BoundaryPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.d1 = load_json(D1_PATH)
        self.d2 = load_json(D2_PATH)
        self.historical_g1 = load_json(HISTORICAL_G1_PACKET_PATH)
        self.current_binding = load_json(CURRENT_REVIEW_BINDING_PATH)
        self.pre_g2_template = load_json(PRE_G2_TEMPLATE_PATH)
        self.pre_g2_bound = load_json(PRE_G2_BOUND_PATH)

    def test_historical_g1_packet_remains_fail_closed_and_historical(self) -> None:
        self.assertEqual(self.historical_g1.get("packet_id"), HISTORICAL_G1_PACKET_ID)
        g1_state = self.historical_g1.get("g1_state") or {}
        self.assertIs(g1_state.get("g1_approved"), False)
        self.assertIs(g1_state.get("requires_human_governance_disposition"), True)

        human_approval = self.historical_g1.get("human_g1_approval_record") or {}
        self.assertEqual(human_approval.get("decision_outcome"), "UNKNOWN")
        self.assertIsNone(human_approval.get("governance_disposition_id"))
        self.assertIsNone(human_approval.get("governance_disposition_path"))

        artifacts = self.historical_g1.get("artifacts_introduced_in_recovery") or {}
        historical_d1 = artifacts.get("d1") or {}
        historical_d2_binding = ((artifacts.get("d2") or {}).get("d1_contract_binding") or {})
        self.assertEqual(
            historical_d1.get("schema_sha256"),
            HISTORICAL_D1_SCHEMA_SHA256,
        )
        self.assertEqual(
            historical_d2_binding.get("canonical_json_sha256"),
            HISTORICAL_D1_CANONICAL_SHA256,
        )
        self.assertEqual(
            historical_d2_binding.get("d2_question_bindings"),
            HISTORICAL_D2_QUESTION_BINDINGS,
        )

    def test_current_review_binding_is_fail_closed(self) -> None:
        self.assertEqual(
            self.current_binding.get("record_type"),
            "PRE_G1_D1_D2_REVIEW_BINDING",
        )
        self.assertEqual(self.current_binding.get("status"), "PRE_G1_DRAFT_BINDING")
        governance = self.current_binding.get("governance") or {}
        for key in (
            "g1_approved",
            "g2_passed",
            "canonical_s2_authority",
            "publication_authority",
            "mutation_authority",
        ):
            self.assertIs(governance.get(key), False)
        self.assertEqual(governance.get("assessment_effect"), "NONE")
        self.assertIs(
            governance.get("requires_attributable_human_g1_disposition"),
            True,
        )
        self.assertIsNone(governance.get("governance_disposition_id"))
        self.assertIsNone(governance.get("governance_disposition_path"))

    def test_current_review_binding_preserves_historical_predecessor(self) -> None:
        predecessor = self.current_binding.get("predecessor_record") or {}
        self.assertEqual(
            predecessor.get("path"),
            "curation/HUMAN_G1_DISPOSITION_PACKET_OBSERVATORY_RECOVERY_2026-09-03_v0.1.json",
        )
        self.assertEqual(predecessor.get("packet_id"), HISTORICAL_G1_PACKET_ID)
        self.assertIs(predecessor.get("preserved_unchanged"), True)
        self.assertEqual(
            predecessor.get("relationship"),
            "HISTORICAL_PREDECESSOR_PRESENTATION_ONLY",
        )

    def test_current_review_binding_references_exact_current_d1(self) -> None:
        binding = self.current_binding.get("d1") or {}
        self.assertEqual(binding.get("artifact_id"), self.d1.get("artifact_id"))
        self.assertEqual(binding.get("version"), self.d1.get("version"))
        self.assertEqual(
            binding.get("created_against_observatory_main_sha"),
            self.d1.get("created_against_observatory_main_sha"),
        )
        self.assertEqual(
            binding.get("canonical_json_sha256"),
            canonical_json_sha256(self.d1),
        )
        self.assertEqual(binding.get("git_blob_sha"), git_blob_sha(D1_PATH))
        self.assertEqual(
            binding.get("schema_canonical_json_sha256"),
            (self.d1.get("integrity") or {}).get("schema_sha256"),
        )
        self.assertEqual(
            binding.get("schema_git_blob_sha"),
            git_blob_sha(D1_SCHEMA_PATH),
        )

    def test_current_review_binding_references_exact_current_d2(self) -> None:
        binding = self.current_binding.get("d2") or {}
        self.assertEqual(binding.get("artifact_id"), self.d2.get("artifact_id"))
        self.assertEqual(binding.get("version"), self.d2.get("version"))
        self.assertEqual(
            binding.get("created_against_observatory_main_sha"),
            self.d2.get("created_against_observatory_main_sha"),
        )
        self.assertEqual(
            binding.get("canonical_json_sha256"),
            canonical_json_sha256(self.d2),
        )
        self.assertEqual(binding.get("git_blob_sha"), git_blob_sha(D2_PATH))
        self.assertEqual(
            binding.get("schema_git_blob_sha"),
            git_blob_sha(D2_SCHEMA_PATH),
        )
        self.assertEqual(
            binding.get("d1_contract_binding"),
            self.d2.get("d1_contract_binding"),
        )

        d1_deliverables = self.d1.get("deliverables") or []
        d2_row = next(
            row for row in d1_deliverables
            if row.get("deliverable_id") == "D2"
        )
        self.assertEqual(
            (self.d2.get("d1_contract_binding") or {}).get("canonical_json_sha256"),
            canonical_json_sha256(self.d1),
        )
        self.assertEqual(
            (self.d2.get("d1_contract_binding") or {}).get("d2_question_bindings"),
            d2_row.get("question_bindings"),
        )

    def test_pre_g2_template_keeps_unknowns_unresolved(self) -> None:
        self.assertEqual(self.pre_g2_template.get("unknown_state_marker"), "UNKNOWN")

        contract_ctx = self.pre_g2_template.get("contract_context") or {}
        g1_dep = contract_ctx.get("g1_dependency") or {}
        self.assertIs(g1_dep.get("g1_approved"), False)
        self.assertIs(g1_dep.get("requires_human_governance_disposition"), True)

        placeholders = self.pre_g2_template.get("s2_public_schema_placeholders") or {}
        for value in placeholders.values():
            self.assertEqual(value, "UNKNOWN")

        workbench_placeholders = self.pre_g2_template.get(
            "workbench_public_provenance_placeholders"
        ) or {}
        for value in workbench_placeholders.values():
            self.assertEqual(value, "UNKNOWN")

    def test_pre_g2_bound_keeps_fail_closed_authority(self) -> None:
        authority = self.pre_g2_bound.get("authority_boundary") or {}
        self.assertIs(authority.get("g2_passed"), False)
        self.assertIs(authority.get("canonical_s2_authority"), False)
        self.assertIs(authority.get("publication_authority"), False)
        self.assertEqual(authority.get("assessment_effect"), "NONE")

        g1_dep = (self.pre_g2_bound.get("contract_context") or {}).get("g1_dependency") or {}
        self.assertIs(g1_dep.get("g1_approved"), False)

        g0_pin = self.pre_g2_bound.get("g0_transport_pin") or {}
        self.assertEqual(g0_pin.get("workbench_sha"), G0_TRANSPORT_PIN)

        software = self.pre_g2_bound.get("workbench_software_binding") or {}
        self.assertEqual(
            software.get("workbench_software_binding_sha"),
            PRE_G2_SOFTWARE_BINDING_SHA,
        )
        self.assertIs(software.get("not_g0_transport_pin"), True)
        self.assertIs(software.get("does_not_replace_g0_pin"), True)
        self.assertNotEqual(
            software.get("workbench_software_binding_sha"),
            g0_pin.get("workbench_sha"),
        )

        public = self.pre_g2_bound.get("public_bindables") or {}
        self.assertEqual(public.get("schema_version"), "0.1")
        self.assertEqual(
            public.get("commitment_scheme"),
            "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1",
        )
        self.assertEqual(public.get("freeze_manifest_type"), "BENCHMARK_FREEZE")
        self.assertEqual(public.get("run_manifest_type"), "HELD_OUT_EVALUATION_RUN")
        self.assertEqual(public.get("export_policy"), "AGGREGATE_ONLY")

        benchmarks = public.get("benchmarks") or []
        self.assertEqual(len(benchmarks), 2)
        ids = {b.get("benchmark_id") for b in benchmarks}
        self.assertEqual(ids, {"PRE_G2_PATENT_V0_1", "PRE_G2_PRODUCT_V0_1"})
        schema_ids = {b.get("schema_id") for b in benchmarks}
        self.assertEqual(
            schema_ids,
            {
                "urn:neuroai:benchmark:patent:public-contract:v0.1",
                "urn:neuroai:benchmark:product:public-contract:v0.1",
            },
        )
        for bench in benchmarks:
            self.assertEqual(bench.get("state"), "DRAFT_UNFROZEN")
            self.assertIs(bench.get("g2_passed"), False)
            self.assertIs(bench.get("canonical_s2_authority"), False)
            self.assertIs(bench.get("publication_authority"), False)
            self.assertEqual(bench.get("assessment_effect"), "NONE")

    def test_no_evidence_payload_or_secret_storage_fields_are_added(self) -> None:
        for packet in (
            self.historical_g1,
            self.current_binding,
            self.pre_g2_template,
            self.pre_g2_bound,
        ):
            evidence_values = find_values_for_keys_containing(packet, "evidence")
            for value in evidence_values:
                self.assertFalse(isinstance(value, (dict, list)))

        joined_strings = json.dumps(
            {
                "historical_g1": self.historical_g1,
                "current_binding": self.current_binding,
                "pre_g2": self.pre_g2_template,
                "pre_g2_bound": self.pre_g2_bound,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertNotIn("s3://", joined_strings.lower())
        self.assertNotIn("arn:", joined_strings.lower())


if __name__ == "__main__":
    unittest.main()
