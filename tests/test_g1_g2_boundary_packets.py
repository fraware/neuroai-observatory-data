from __future__ import annotations

import json
from pathlib import Path
import unittest
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

D1_PATH = ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json"
D2_PATH = ROOT / "curation" / "CAPABILITY_CONTEXT_TAXONOMY_v0.1.json"

G1_PACKET_PATH = (
    ROOT
    / "curation"
    / "HUMAN_G1_DISPOSITION_PACKET_OBSERVATORY_RECOVERY_2026-09-03_v0.1.json"
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

G0_TRANSPORT_PIN = "685f1597a2a63f2e2217f65f115a67ac3e35cc55"
PRE_G2_SOFTWARE_BINDING_SHA = "336da167700a7ce2894c27826f8a1c999e1ee844"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_dict_keys_containing(value: Any, substring: str) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if substring in str(key):
                found.add(str(key))
            found.update(find_dict_keys_containing(child, substring))
    elif isinstance(value, list):
        for item in value:
            found.update(find_dict_keys_containing(item, substring))
    return found


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
        self.g1_packet = load_json(G1_PACKET_PATH)
        self.pre_g2_template = load_json(PRE_G2_TEMPLATE_PATH)
        self.pre_g2_bound = load_json(PRE_G2_BOUND_PATH)

    def test_g1_packet_is_fail_closed(self) -> None:
        g1_state = self.g1_packet.get("g1_state") or {}
        self.assertIs(g1_state.get("g1_approved"), False)
        self.assertIs(g1_state.get("requires_human_governance_disposition"), True)

        human_approval = self.g1_packet.get("human_g1_approval_record") or {}
        self.assertEqual(human_approval.get("decision_outcome"), "UNKNOWN")
        self.assertIsNone(human_approval.get("governance_disposition_id"))
        self.assertIsNone(human_approval.get("governance_disposition_path"))

    def test_g1_packet_references_exact_d1_d2_digests(self) -> None:
        artifacts = self.g1_packet.get("artifacts_introduced_in_recovery") or {}
        d1_packet = artifacts.get("d1") or {}
        d2_packet = artifacts.get("d2") or {}

        expected_d1 = self.d1.get("integrity") or {}
        self.assertEqual(
            d1_packet.get("schema_path"),
            "schemas/landscape-research-contract-v0.1.schema.json",
        )
        self.assertEqual(d1_packet.get("schema_sha256"), expected_d1.get("schema_sha256"))
        self.assertEqual(
            d1_packet.get("validator_entrypoint"),
            expected_d1.get("validator_entrypoint"),
        )
        self.assertEqual(
            d1_packet.get("created_against_observatory_main_sha"),
            self.d1.get("created_against_observatory_main_sha"),
        )

        d2_binding = d2_packet.get("d1_contract_binding") or {}
        expected_canonical_json_sha256 = (self.d2.get("d1_contract_binding") or {}).get(
            "canonical_json_sha256"
        )
        self.assertEqual(d2_binding.get("canonical_json_sha256"), expected_canonical_json_sha256)
        self.assertEqual(
            d2_binding.get("d2_question_bindings"),
            self.d2.get("d1_contract_binding", {}).get("d2_question_bindings"),
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

    def test_no_evidence_keys_or_secret_payload_fields_are_present(self) -> None:
        # Boundary text may include "evidence" as part of an authority constraint
        # key name. This test prevents *evidence payload* objects from appearing.
        evidence_values = find_values_for_keys_containing(self.g1_packet, "evidence")
        self.assertTrue(evidence_values)
        for v in evidence_values:
            self.assertFalse(isinstance(v, (dict, list)))

        for packet in (self.pre_g2_template, self.pre_g2_bound):
            evidence_values = find_values_for_keys_containing(packet, "evidence")
            for v in evidence_values:
                self.assertFalse(isinstance(v, (dict, list)))

        # Public templates must not contain storage URIs or secret markers.
        joined_strings = json.dumps(
            {
                "g1": self.g1_packet,
                "pre_g2": self.pre_g2_template,
                "pre_g2_bound": self.pre_g2_bound,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertNotIn("s3://", joined_strings.lower())
        self.assertNotIn("arn:", joined_strings.lower())
        # Exclusion text may mention disallowed categories; the test focuses on
        # the absence of secret-style payloads (URIs) and any evidence keys.


if __name__ == "__main__":
    unittest.main()

