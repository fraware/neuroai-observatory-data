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

    def assertInvalid(self, mutate, pattern: str | None = None) -> None:
        broken = copy.deepcopy(self.document)
        mutate(broken)
        if pattern is None:
            with self.assertRaises(validator.ValidationError):
                validator.validate_document(broken, self.schema, ROOT)
        else:
            with self.assertRaisesRegex(validator.ValidationError, pattern):
                validator.validate_document(broken, self.schema, ROOT)

    def test_reference_contract_validates(self) -> None:
        validator.validate_document(copy.deepcopy(self.document), copy.deepcopy(self.schema), ROOT)

    def test_g1_approval_cannot_be_synthesized(self) -> None:
        self.assertInvalid(lambda d: d["governance"].__setitem__("g1_approved", True), "g1_approved")

    def test_canonical_authority_cannot_be_synthesized(self) -> None:
        self.assertInvalid(lambda d: d["governance"].__setitem__("canonical_authority", True), "canonical_authority")

    def test_publication_authority_cannot_be_synthesized(self) -> None:
        self.assertInvalid(lambda d: d["governance"].__setitem__("publication_authority", True), "publication_authority")

    def test_unapproved_contract_cannot_name_disposition(self) -> None:
        self.assertInvalid(
            lambda d: d["governance"].__setitem__("governance_disposition_id", "G1-001"),
            "must not name",
        )

    def test_all_seven_controlling_questions_are_required(self) -> None:
        self.assertInvalid(lambda d: d["questions"].pop(), "seven controlling IDs")

    def test_controlling_question_text_is_substantive(self) -> None:
        q = {row["question_id"]: row["text"] for row in self.document["questions"]}
        self.assertIn("technologies and capabilities", q["RQ-01"])
        self.assertIn("commercially relevant applications", q["RQ-04"])
        self.assertIn("governance concerns", q["RQ-06"])
        self.assertIn("v4.2 assessment", q["RQ-07"])

    def test_controlling_questions_cannot_be_reclassified_secondary(self) -> None:
        self.assertInvalid(lambda d: d["questions"][0].__setitem__("tier", "SECONDARY"), "must remain PRIMARY")

    def test_secondary_question_parent_must_be_controlled(self) -> None:
        self.assertInvalid(lambda d: d["secondary_questions"][0].__setitem__("parent_question_id", "RQ-99"))

    def test_d0_to_d18_registry_is_complete(self) -> None:
        self.assertEqual([row["deliverable_id"] for row in self.document["deliverables"]], [f"D{i}" for i in range(19)])

    def test_d1_binds_all_seven_questions(self) -> None:
        self.assertInvalid(
            lambda d: next(x for x in d["deliverables"] if x["deliverable_id"]=="D1")["question_bindings"].pop(),
            "bind all seven",
        )

    def test_d2_binding_is_substantive(self) -> None:
        row = next(x for x in self.document["deliverables"] if x["deliverable_id"]=="D2")
        self.assertEqual(row["question_bindings"], ["RQ-01","RQ-04","RQ-06","RQ-07"])

    def test_d2_binding_drift_fails(self) -> None:
        self.assertInvalid(
            lambda d: next(x for x in d["deliverables"] if x["deliverable_id"]=="D2").__setitem__("question_bindings", ["RQ-02"]),
            "D2 substantive",
        )

    def test_d18_is_assessment_trigger_only(self) -> None:
        row = next(x for x in self.document["deliverables"] if x["deliverable_id"]=="D18")
        self.assertEqual(row["question_bindings"], ["RQ-07"])

    def test_claim_cannot_reference_unknown_evidence_rule(self) -> None:
        self.assertInvalid(lambda d: d["claim_classes"][0]["allowed_evidence_rules"].append("INVENTED_RULE"), "unknown evidence rule")

    def test_product_patent_name_only_inference_remains_prohibited(self) -> None:
        def mutate(d):
            row = next(x for x in d["claim_classes"] if x["claim_class_id"]=="CLAIM_PRODUCT_PATENT_RELATION")
            row["prohibited_inferences"].remove("Ownership certainty from shared names alone")
        self.assertInvalid(mutate, "name-only")

    def test_abstention_cannot_be_disabled(self) -> None:
        self.assertInvalid(lambda d: d["classification_semantics"].__setitem__("abstention_required_when_evidence_insufficient", False), "abstention")

    def test_gray_third_is_retrieval_only(self) -> None:
        self.assertInvalid(lambda d: d["classification_semantics"]["gray_third"].__setitem__("retrieval_only", False), "retrieval-only")

    def test_gray_third_cannot_become_canonical_population(self) -> None:
        self.assertInvalid(lambda d: d["classification_semantics"]["gray_third"].__setitem__("canonical_population_class", True), "canonical population")

    def test_gray_family_set_is_exact(self) -> None:
        self.assertInvalid(lambda d: d["classification_semantics"]["gray_third"]["search_families"].pop(), "family set")

    def test_company_product_pages_are_not_structured_denominator(self) -> None:
        self.assertNotIn("COMPANY_PRODUCT_PAGE", self.document["source_classes"]["structured_denominated"])
        self.assertIn("COMPANY_PRODUCT_PAGE", self.document["source_classes"]["open_world_channels"])

    def test_company_product_track_cannot_become_denominated(self) -> None:
        def mutate(d):
            row = next(x for x in d["discovery_tracks"] if x["track_id"]=="TRACK_COMPANIES_PRODUCTS")
            row["universe_type"] = "STRUCTURED_DENOMINATED"
        self.assertInvalid(mutate, "company/product track")

    def test_open_world_marginal_yield_requirement_cannot_be_disabled(self) -> None:
        self.assertInvalid(lambda d: d["source_classes"].__setitem__("open_world_protocol_must_report_stopping_and_marginal_yield", False), "stopping/yield")

    def test_fuzzy_name_match_cannot_merge(self) -> None:
        self.assertInvalid(lambda d: d["identity_contract"].__setitem__("fuzzy_name_match_cannot_merge", False), "fuzzy_name_match")

    def test_patent_publication_family_distinction_cannot_be_removed(self) -> None:
        self.assertInvalid(lambda d: d["identity_contract"].__setitem__("patent_publication_and_family_distinct", False), "patent_publication")

    def test_l4_cannot_be_promoted_to_established_link(self) -> None:
        def mutate(d):
            row = next(x for x in d["patent_product_linkage"]["tiers"] if x["tier"]=="L4")
            row["permitted_use"] = "Established relationship."
        self.assertInvalid(mutate, "L4")

    def test_l3_quantitative_use_requires_error_study(self) -> None:
        self.assertInvalid(lambda d: d["patent_product_linkage"].__setitem__("l3_quantitative_use_requires_validated_error_study", False), "l3_quantitative")

    def test_model_consensus_cannot_be_truth(self) -> None:
        self.assertInvalid(lambda d: d["model_assistance"].__setitem__("model_consensus_is_truth", True), "model consensus")

    def test_human_g1_disposition_remains_required(self) -> None:
        self.assertInvalid(
            lambda d: d["human_review"].__setitem__("g1_requires_attributable_human_disposition_over_exact_d1_d2_identity", False),
            "g1_requires",
        )

    def test_governance_mapping_cannot_allow_predicted_company_behavior(self) -> None:
        self.assertInvalid(lambda d: d["governance_mapping"].__setitem__("predicted_company_behavior_allowed", True), "predicted company behavior")

    def test_production_filter_cannot_precede_held_out_evaluation(self) -> None:
        self.assertInvalid(lambda d: d["evaluation_requirements"].__setitem__("production_filter_before_held_out_evaluation", True), "production filtering")

    def test_held_out_test_membership_cannot_be_exposed_to_tuning(self) -> None:
        self.assertInvalid(lambda d: d["evaluation_requirements"]["held_out_controls"].__setitem__("test_membership_accessible_to_tuning", True), "held-out test membership")

    def test_g2_to_g5_acceptance_logic_is_frozen(self) -> None:
        self.assertInvalid(lambda d: d["evaluation_requirements"]["gate_acceptance"].pop(), "G2-G5")

    def test_s3_labels_cannot_enter_public_s2(self) -> None:
        self.assertInvalid(lambda d: d["containment"].__setitem__("s3_private_labels_allowed_in_public_s2", True), "s3_private")

    def test_licensed_data_requires_purpose_limitation(self) -> None:
        self.assertInvalid(lambda d: d["containment"].__setitem__("licensed_data_requires_purpose_limitation", False), "purpose_limitation")

    def test_redistribution_rights_check_cannot_be_disabled(self) -> None:
        self.assertInvalid(lambda d: d["containment"].__setitem__("redistribution_rights_checked_before_publication", False), "redistribution")

    def test_saturation_cannot_be_global_completeness(self) -> None:
        self.assertInvalid(lambda d: d["stopping_change_control"].__setitem__("global_completeness_from_saturation_allowed", True), "saturation")

    def test_historical_control_artifacts_cannot_be_rewritten(self) -> None:
        self.assertInvalid(lambda d: d["stopping_change_control"].__setitem__("historical_control_artifacts_are_not_rewritten", False), "historical_control")

    def test_assessment_trigger_has_no_assessment_effect(self) -> None:
        self.assertInvalid(lambda d: d["assessment_trigger"].__setitem__("trigger_has_assessment_effect", True), "assessment effect")

    def test_v42_requirement_meanings_cannot_drift(self) -> None:
        self.assertInvalid(lambda d: d["assessment_trigger"].__setitem__("v4_2_requirement_meanings_unchanged", False), "v4_2")

    def test_schema_digest_binding_fails_closed(self) -> None:
        self.assertInvalid(lambda d: d["integrity"].__setitem__("schema_sha256", "0"*64), "schema_sha256")

    def test_repository_relative_paths_are_sanitized(self) -> None:
        self.assertInvalid(lambda d: d["integrity"].__setitem__("documentation_paths", ["../escape.md"]), "unsafe repository-relative path")

    def test_schema_rejects_unknown_top_level_property(self) -> None:
        self.assertInvalid(lambda d: d.__setitem__("unauthorized_extra", True), "additional properties")

    def test_cli_reports_failure_for_invalid_artifact(self) -> None:
        broken = copy.deepcopy(self.document)
        broken["classification_semantics"]["gray_third"]["retrieval_only"] = False
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "artifact.json"
            schema = root / "schema.json"
            artifact.write_text(json.dumps(broken, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            schema.write_text(json.dumps(self.schema, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            code = validator.main(["--artifact", str(artifact), "--schema", str(schema)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
