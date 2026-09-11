from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_pre_g2_d3_challenge_pilot_readiness import (
    derive_readiness_aggregate,
    pilot_membership_commitment,
    run_builder,
)
from scripts.check_pre_g2_d3_challenge_pilot_final_disjointness import (
    _canonical_sha256,
    compute_disjointness_audit,
)
from scripts.evaluate_pre_g2_d3_challenge_pilot_readiness import (
    D3ChallengePilotReadinessError,
    evaluate_pilot_readiness,
)
from scripts.select_pre_g2_d3_challenge_held_out import (
    D3ChallengeSelectionError,
    candidate_pool_commitment,
    run_selector,
    select_candidates,
)
from tests.test_pre_g2_d3_patent_review_packet import _packet, _refresh_digest

PILOT_KEY = b"synthetic-d3-pilot-key"
POOL_KEY = b"synthetic-d3-pool-key"
CALIBRATION_SHA = "d" * 64


def _pilot_packet(
    index: int,
    *,
    state: str,
    primary: str,
    secondary: str,
    final: str | None,
) -> dict[str, object]:
    packet = _packet(
        candidate_role="PILOT_DEVELOPMENT",
        state=state,
        primary=primary,
        secondary=secondary,
        final=final,
        held_out_eligible=False,
    )
    binding = packet["exact_patent_binding"]
    assert isinstance(binding, dict)
    binding["controlled_family_ref"] = f"S3-PILOT-FAMILY-{index:04d}"
    for record in packet["reviewer_records"]:
        record["exact_patent_binding"] = copy.deepcopy(binding)
        record["reviewer_ref"] = (
            f"{record['reviewer_ref']}-{index:04d}"
        )
    _refresh_digest(packet)
    return packet


def _pilot_packets() -> list[dict[str, object]]:
    packets: list[dict[str, object]] = []
    for index in range(20):
        packets.append(
            _pilot_packet(
                index,
                state="AGREE",
                primary="INCLUDE",
                secondary="INCLUDE",
                final="INCLUDE",
            )
        )
    for index in range(20, 40):
        packets.append(
            _pilot_packet(
                index,
                state="AGREE",
                primary="EXCLUDE",
                secondary="EXCLUDE",
                final="EXCLUDE",
            )
        )
    for index in range(40, 54):
        packets.append(
            _pilot_packet(
                index,
                state="AGREE",
                primary="BORDERLINE",
                secondary="BORDERLINE",
                final="BORDERLINE",
            )
        )
    for index in range(54, 57):
        packets.append(
            _pilot_packet(
                index,
                state="ADJUDICATED",
                primary="INCLUDE",
                secondary="BORDERLINE",
                final="BORDERLINE",
            )
        )
    for index in range(57, 60):
        packets.append(
            _pilot_packet(
                index,
                state="DISAGREE_UNADJUDICATED",
                primary="INCLUDE",
                secondary="BORDERLINE",
                final=None,
            )
        )
    return packets


def _write_pilot(root: Path) -> tuple[dict[str, object], Path]:
    packet_root = root / "packets"
    packet_root.mkdir(parents=True)
    entries: list[dict[str, str]] = []
    family_refs: list[str] = []
    for index, packet in enumerate(_pilot_packets()):
        path = packet_root / f"packet-{index:04d}.json"
        raw = (
            json.dumps(
                packet,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        path.write_bytes(raw)
        entries.append(
            {
                "controlled_packet_ref": path.name,
                "packet_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        family_refs.append(
            str(packet["exact_patent_binding"]["controlled_family_ref"])
        )
    manifest: dict[str, object] = {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PATENT_V0_1",
        "protocol_id": "PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1",
        "pilot_round_id": "SYNTHETIC-D3-PILOT-001",
        "state": "COMPLETE_ROUND_NO_EXTENSION",
        "pilot_membership_commitment": pilot_membership_commitment(
            family_refs,
            PILOT_KEY,
        ),
        "pilot_membership_commitment_scheme": "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1",
        "reviewer_training_record_sha256": "1" * 64,
        "exposure_register_sha256": "2" * 64,
        "prior_exposure_disjointness_audit_sha256": "3" * 64,
        "packet_manifest": entries,
    }
    return manifest, packet_root


NON_ENGLISH = ["fr", "de", "es", "ja", "ko", "zh", "pt", "it"]
JURISDICTIONS = ["US", "EP", "JP", "KR", "CN", "FR", "DE", "GB"]
ALL_STRATA = [
    "GRAY_CAPABILITY",
    "MISSING_OR_SHORT_ABSTRACT",
    "MULTI_JURISDICTION",
    "MULTI_YEAR",
    "MULTILINGUAL",
    "SEMANTICALLY_DECEPTIVE_NEGATIVE",
]


def _candidate(index: int) -> dict[str, object]:
    language = NON_ENGLISH[index % len(NON_ENGLISH)]
    jurisdiction_a = JURISDICTIONS[index % len(JURISDICTIONS)]
    jurisdiction_b = JURISDICTIONS[(index + 1) % len(JURISDICTIONS)]
    # Every synthetic candidate carries the MISSING_OR_SHORT_ABSTRACT construct,
    # so the text-availability metadata must remain mechanically compatible.
    text = "MISSING_ABSTRACT" if index % 2 == 0 else "SHORT_ABSTRACT"
    return {
        "candidate_id": f"S3-CANDIDATE-FAMILY-{index:04d}",
        "construct_strata": list(ALL_STRATA),
        "source_languages": ["en", language],
        "jurisdictions": [jurisdiction_a, jurisdiction_b],
        "text_availability": text,
        "query_pool_provenance": (
            "OUTSIDE_QUERY_POOL"
            if index % 2 == 0
            else "IN_QUERY_POOL"
        ),
        "exact_family_identity_resolved": True,
        "exposure_status": "NO_KNOWN_EXPOSURE_REVIEWED",
        "semantic_validation_passed": True,
        "human_confirmed_construct_tags": True,
        "pilot_or_development_exposed": False,
    }


def _candidate_pool(count: int = 300) -> dict[str, object]:
    pool: dict[str, object] = {
        "schema_version": "0.1",
        "benchmark_id": "PRE_G2_PATENT_V0_1",
        "protocol_id": "PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1",
        "human_calibration_disposition_sha256": CALIBRATION_SHA,
        "candidate_pool_id": "SYNTHETIC-D3-POOL-001",
        "candidate_pool_commitment": "0" * 64,
        "candidate_pool_commitment_scheme": "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1",
        "candidate_pool_frozen": True,
        "candidates": [_candidate(index) for index in range(count)],
    }
    pool["candidate_pool_commitment"] = candidate_pool_commitment(
        pool,
        POOL_KEY,
    )
    return pool


def _attestation(
    manifest: dict[str, object],
    pool: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "namespace_id": "D3_DOCDB_SIMPLE_PATENT_FAMILY_ID_V1",
        "state": "HUMAN_CONTROLLED_NAMESPACE_BINDING_RECORDED",
        "pilot_round_id": manifest["pilot_round_id"],
        "pilot_membership_commitment": manifest[
            "pilot_membership_commitment"
        ],
        "candidate_pool_id": pool["candidate_pool_id"],
        "candidate_pool_commitment": pool[
            "candidate_pool_commitment"
        ],
        "human_family_resolution_provenance_sha256": "4" * 64,
        "authority": {
            "family_resolution_truth_established": False,
            "g2_passed": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "assessment_effect": "NONE",
        },
    }


class D3ChallengeSamplingCalibrationTests(unittest.TestCase):
    def test_derived_pilot_aggregate_passes_without_agreement_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, packet_root = _write_pilot(Path(tmp))
            aggregate, result = derive_readiness_aggregate(
                manifest,
                packet_root,
                PILOT_KEY,
            )
            self.assertEqual(aggregate["total_items"], 60)
            self.assertEqual(
                aggregate["primary_secondary_exact_agreement_count"],
                54,
            )
            self.assertEqual(
                aggregate["unresolved_disagreement_count"],
                3,
            )
            self.assertTrue(result["quantitative_gate_passed"])
            self.assertFalse(result["agreement_is_automated_gate"])
            self.assertFalse(result["population_generalizable"])

    def test_readiness_has_no_raw_agreement_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, packet_root = _write_pilot(Path(tmp))
            aggregate, _ = derive_readiness_aggregate(
                manifest,
                packet_root,
                PILOT_KEY,
            )
            aggregate["primary_secondary_exact_agreement_count"] = 0
            aggregate["adjudicated_disagreement_count"] = 60
            aggregate["unresolved_disagreement_count"] = 0
            aggregate["resolved_disposition_counts"] = {
                "ABSTAIN": 0,
                "BORDERLINE": 20,
                "EXCLUDE": 20,
                "INCLUDE": 20,
            }
            matrix = {
                label: {
                    other: 0
                    for other in (
                        "ABSTAIN",
                        "BORDERLINE",
                        "EXCLUDE",
                        "INCLUDE",
                    )
                }
                for label in (
                    "ABSTAIN",
                    "BORDERLINE",
                    "EXCLUDE",
                    "INCLUDE",
                )
            }
            matrix["INCLUDE"]["BORDERLINE"] = 20
            matrix["BORDERLINE"]["EXCLUDE"] = 20
            matrix["EXCLUDE"]["INCLUDE"] = 20
            aggregate["primary_secondary_confusion_matrix"] = matrix
            result = evaluate_pilot_readiness(aggregate)
            self.assertTrue(result["quantitative_gate_passed"])
            self.assertEqual(result["agreement_count"], 0)

    def test_readiness_fails_on_unresolved_boundary_or_stratum_shortfall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, packet_root = _write_pilot(Path(tmp))
            aggregate, _ = derive_readiness_aggregate(
                manifest,
                packet_root,
                PILOT_KEY,
            )
            for mutation in (
                ("unresolved_disagreement_count", 7),
                ("resolved_disposition_counts", {
                    "ABSTAIN": 0,
                    "BORDERLINE": 9,
                    "EXCLUDE": 20,
                    "INCLUDE": 28,
                }),
                ("required_stratum_counts", {
                    **aggregate["required_stratum_counts"],
                    "GRAY_CAPABILITY": 9,
                }),
            ):
                with self.subTest(field=mutation[0]):
                    report = copy.deepcopy(aggregate)
                    report[mutation[0]] = mutation[1]
                    if mutation[0] == "unresolved_disagreement_count":
                        report["adjudicated_disagreement_count"] = 0
                        report["primary_secondary_exact_agreement_count"] = 53
                        report["resolved_disposition_counts"] = {
                            "ABSTAIN": 0,
                            "BORDERLINE": 13,
                            "EXCLUDE": 20,
                            "INCLUDE": 20,
                        }
                        matrix = report[
                            "primary_secondary_confusion_matrix"
                        ]
                        matrix["BORDERLINE"]["BORDERLINE"] -= 1
                        matrix["BORDERLINE"]["INCLUDE"] += 1
                    result = evaluate_pilot_readiness(report)
                    self.assertFalse(result["quantitative_gate_passed"])

    def test_builder_rejects_packet_digest_mutation_and_path_traversal_generically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, packet_root = _write_pilot(root)
            manifest_path = root / "manifest.json"
            key_path = root / "pilot.key"
            key_path.write_bytes(PILOT_KEY)

            first = packet_root / manifest["packet_manifest"][0][
                "controlled_packet_ref"
            ]
            first.write_text("{}", encoding="utf-8")
            manifest_path.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            status, result, message = run_builder(
                manifest_path,
                packet_root,
                key_path,
            )
            self.assertEqual(status, 1)
            self.assertIsNone(result)
            self.assertIn("controlled D3 challenge pilot execution failed", message)
            self.assertNotIn("S3-PILOT-FAMILY", message)

            manifest, packet_root = _write_pilot(root / "fresh")
            manifest["packet_manifest"][0]["controlled_packet_ref"] = "../escape.json"
            manifest_path = root / "fresh-manifest.json"
            manifest_path.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            status, _, message = run_builder(
                manifest_path,
                packet_root,
                key_path,
            )
            self.assertEqual(status, 1)
            self.assertNotIn("escape.json", message)

    def test_selector_is_deterministic_order_invariant_and_satisfies_frozen_coverage(self) -> None:
        pool = _candidate_pool()
        controlled_a, aggregate_a = select_candidates(
            copy.deepcopy(pool),
            POOL_KEY,
        )
        reversed_pool = copy.deepcopy(pool)
        reversed_pool["candidates"] = list(
            reversed(reversed_pool["candidates"])
        )
        self.assertEqual(
            candidate_pool_commitment(reversed_pool, POOL_KEY),
            pool["candidate_pool_commitment"],
        )
        reversed_pool["candidate_pool_commitment"] = pool[
            "candidate_pool_commitment"
        ]
        controlled_b, aggregate_b = select_candidates(
            reversed_pool,
            POOL_KEY,
        )
        self.assertEqual(
            controlled_a["selected_candidate_ids"],
            controlled_b["selected_candidate_ids"],
        )
        self.assertEqual(aggregate_a, aggregate_b)
        self.assertEqual(aggregate_a["selected_count"], 240)
        self.assertGreaterEqual(
            min(aggregate_a["stratum_counts"].values()),
            40,
        )
        self.assertGreaterEqual(
            aggregate_a["missing_abstract_count"],
            16,
        )
        self.assertGreaterEqual(
            aggregate_a["short_abstract_count"],
            16,
        )
        self.assertGreaterEqual(
            aggregate_a["outside_query_pool_count"],
            40,
        )
        self.assertFalse(
            aggregate_a[
                "outside_query_pool_is_population_recall_denominator"
            ]
        )
        self.assertFalse(aggregate_a["population_generalizable"])

    def test_selector_fails_closed_on_forbidden_fields_and_commitment_mutation(self) -> None:
        pool = _candidate_pool()
        pool["candidates"][0]["model_score"] = 0.99
        with self.assertRaises(D3ChallengeSelectionError):
            candidate_pool_commitment(pool, POOL_KEY)
        # The public runner must never surface the controlled candidate identifier.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            pool["candidates"][0]["pilot_or_development_exposed"] = True
            pool["candidate_pool_commitment"] = candidate_pool_commitment(
                pool,
                POOL_KEY,
            )
            pool_path = root / "pool.json"
            key_path = root / "pool.key"
            pool_path.write_text(json.dumps(pool), encoding="utf-8")
            key_path.write_bytes(POOL_KEY)
            status, aggregate, message = run_selector(
                pool_path,
                key_path,
            )
            self.assertEqual(status, 1)
            self.assertIsNone(aggregate)
            self.assertNotIn(
                str(pool["candidates"][0]["candidate_id"]),
                message,
            )

    def test_selector_output_paths_cannot_alias_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = _candidate_pool()
            pool_path = root / "pool.json"
            key_path = root / "pool.key"
            pool_path.write_text(json.dumps(pool), encoding="utf-8")
            key_path.write_bytes(POOL_KEY)
            original_pool = pool_path.read_bytes()
            original_key = key_path.read_bytes()
            for output in (pool_path, key_path):
                with self.subTest(output=output.name):
                    status, aggregate, _ = run_selector(
                        pool_path,
                        key_path,
                        controlled_error_output=output,
                    )
                    self.assertEqual(status, 1)
                    self.assertIsNone(aggregate)
                    self.assertEqual(pool_path.read_bytes(), original_pool)
                    self.assertEqual(key_path.read_bytes(), original_key)

    def test_selector_fails_conservatively_when_frozen_quota_support_is_insufficient(self) -> None:
        pool = _candidate_pool()
        for candidate in pool["candidates"]:
            candidate["query_pool_provenance"] = "IN_QUERY_POOL"
        pool["candidate_pool_commitment"] = candidate_pool_commitment(
            pool,
            POOL_KEY,
        )
        with self.assertRaises(D3ChallengeSelectionError):
            select_candidates(pool, POOL_KEY)

    def test_pilot_final_disjointness_zero_and_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, packet_root = _write_pilot(root)
            pool = _candidate_pool()
            attestation = _attestation(manifest, pool)
            _, summary = compute_disjointness_audit(
                manifest,
                packet_root,
                PILOT_KEY,
                pool,
                POOL_KEY,
                attestation,
                _canonical_sha256(attestation),
            )
            self.assertTrue(summary["overlap_zero"])
            self.assertEqual(summary["overlap_count"], 0)
            self.assertFalse(summary["public_zero_knowledge_proof"])

            overlap_pool = _candidate_pool()
            overlap_pool["candidates"][0]["candidate_id"] = (
                "S3-PILOT-FAMILY-0000"
            )
            overlap_pool["candidate_pool_commitment"] = (
                candidate_pool_commitment(
                    overlap_pool,
                    POOL_KEY,
                )
            )
            overlap_attestation = _attestation(
                manifest,
                overlap_pool,
            )
            controlled, summary = compute_disjointness_audit(
                manifest,
                packet_root,
                PILOT_KEY,
                overlap_pool,
                POOL_KEY,
                overlap_attestation,
                _canonical_sha256(overlap_attestation),
            )
            self.assertFalse(summary["overlap_zero"])
            self.assertEqual(summary["overlap_count"], 1)
            self.assertEqual(
                controlled["overlap_family_refs"],
                ["S3-PILOT-FAMILY-0000"],
            )
            self.assertNotIn(
                "overlap_family_refs",
                summary,
            )

    def test_attestation_digest_and_authority_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, packet_root = _write_pilot(root)
            pool = _candidate_pool()
            attestation = _attestation(manifest, pool)
            with self.assertRaises(Exception):
                compute_disjointness_audit(
                    manifest,
                    packet_root,
                    PILOT_KEY,
                    pool,
                    POOL_KEY,
                    attestation,
                    "0" * 64,
                )
            attestation = _attestation(manifest, pool)
            attestation["authority"]["g2_passed"] = True
            with self.assertRaises(Exception):
                compute_disjointness_audit(
                    manifest,
                    packet_root,
                    PILOT_KEY,
                    pool,
                    POOL_KEY,
                    attestation,
                    _canonical_sha256(attestation),
                )

    def test_readiness_rejects_authority_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, packet_root = _write_pilot(Path(tmp))
            aggregate, _ = derive_readiness_aggregate(
                manifest,
                packet_root,
                PILOT_KEY,
            )
            aggregate["authority"][
                "population_generalization_authority"
            ] = True
            with self.assertRaises(D3ChallengePilotReadinessError):
                evaluate_pilot_readiness(aggregate)


if __name__ == "__main__":
    unittest.main()
