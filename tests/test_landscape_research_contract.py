from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_landscape_research_contract.py"
SPEC = importlib.util.spec_from_file_location("d1_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def load_document() -> dict[str, object]:
    return json.loads(
        (ROOT / "curation" / "LANDSCAPE_RESEARCH_CONTRACT_v0.1.json").read_text(
            encoding="utf-8"
        )
    )


def load_schema() -> dict[str, object]:
    return json.loads(
        (ROOT / "schemas" / "landscape-research-contract-v0.1.schema.json").read_text(
            encoding="utf-8"
        )
    )


class LandscapeResearchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_document()
        cls.schema = load_schema()

    def test_contract_validates_as_pre_g1_fail_closed(self) -> None:
        validator.validate_document(
            copy.deepcopy(self.document),
            copy.deepcopy(self.schema),
            ROOT,
        )

    def test_g1_approval_cannot_be_synthesized(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["governance"]["g1_approved"] = True
        with self.assertRaisesRegex(validator.ValidationError, "g1_approved"):
            validator.validate_document(broken, self.schema, ROOT)

    def test_governance_binding_cannot_appear_while_unapproved(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["governance"]["governance_disposition_id"] = "G1-DECISION-001"
        with self.assertRaisesRegex(
            validator.ValidationError,
            "must not name a disposition id",
        ):
            validator.validate_document(broken, self.schema, ROOT)

    def test_all_seven_questions_must_remain_present(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["questions"].pop()
        with self.assertRaisesRegex(validator.ValidationError, "seven controlled IDs"):
            validator.validate_document(broken, self.schema, ROOT)

    def test_deliverable_binding_cannot_drop_question_coverage(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["deliverables"][0]["question_bindings"].remove("RQ-07")
        with self.assertRaisesRegex(
            validator.ValidationError,
            "bind all seven research questions",
        ):
            validator.validate_document(broken, self.schema, ROOT)

    def test_claim_class_cannot_reference_unknown_evidence_rule(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["claim_classes"][0]["allowed_evidence_rules"].append("INVENTED_RULE")
        with self.assertRaisesRegex(
            validator.ValidationError,
            "unknown evidence rule",
        ):
            validator.validate_document(broken, self.schema, ROOT)

    def test_proxy_only_inclusion_boundary_cannot_be_weakened(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["classification_semantics"][
            "proxy_only_cannot_establish_inclusion"
        ] = False
        with self.assertRaisesRegex(
            validator.ValidationError,
            "proxy_only_cannot_establish_inclusion",
        ):
            validator.validate_document(broken, self.schema, ROOT)

    def test_product_patent_relation_must_remain_separately_evidenced(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["identity_contract"][
            "product_patent_relation_requires_separate_evidence"
        ] = False
        with self.assertRaisesRegex(
            validator.ValidationError,
            "product_patent_relation_requires_separate_evidence",
        ):
            validator.validate_document(broken, self.schema, ROOT)

    def test_s3_containment_cannot_be_weakened(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["containment"]["s3_private_labels_allowed_in_public_s2"] = True
        with self.assertRaisesRegex(
            validator.ValidationError,
            "s3_private_labels_allowed_in_public_s2",
        ):
            validator.validate_document(broken, self.schema, ROOT)

    def test_schema_digest_binding_fails_closed_on_tamper(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["integrity"]["schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            validator.ValidationError,
            "schema_sha256 binding mismatch",
        ):
            validator.validate_document(broken, self.schema, ROOT)

    def test_repository_relative_paths_are_sanitized(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["integrity"]["documentation_paths"] = ["../docs/escape.md"]
        with self.assertRaisesRegex(
            validator.ValidationError,
            "unsafe repository-relative path",
        ):
            validator.validate_document(broken, self.schema, ROOT)

    def test_cli_reports_failure_for_invalid_artifact(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["source_classes"]["open_world_discovery"].append("INVENTED_CLASS")
        with tempfile.TemporaryDirectory() as td:
            artifact_path = Path(td) / "artifact.json"
            schema_path = Path(td) / "schema.json"
            artifact_path.write_text(
                json.dumps(broken, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            schema_path.write_text(
                json.dumps(self.schema, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            code = validator.main(
                ["--artifact", str(artifact_path), "--schema", str(schema_path)]
            )
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
