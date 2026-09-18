from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

BENCHMARK_ID = "PRE_G2_PRODUCT_V0_1"
PROTOCOL_ID = "PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1"
FINAL_N = 240
STRATUM_MINIMUM = 24
NON_ENGLISH_LANGUAGE_COUNT = 6
NON_ENGLISH_LANGUAGE_MINIMUM = 3
JURISDICTION_COUNT = 6
JURISDICTION_MINIMUM = 3

COMMITMENT_SCHEME = "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1"
POOL_COMMITMENT_DOMAIN = "PRE_G2_D4_CANDIDATE_POOL_COMMITMENT_V1"
SELECTION_SEED_DOMAIN = "PRE_G2_D4_SELECTION_SEED_V1"
TIE_BREAK_DOMAIN = "PRE_G2_D4_SELECTION_TIE_BREAK_V1"
MEMBERSHIP_DOMAIN = "PRE_G2_D4_SELECTED_MEMBERSHIP_V1"

REQUIRED_STRATA = (
    "AMBIGUOUS_BIOSIGNAL",
    "CLINICAL",
    "CONSUMER",
    "ENTERTAINMENT_XR",
    "MULTI_JURISDICTION",
    "MULTILINGUAL",
    "NONTRADITIONAL_FORM_FACTOR",
    "RESEARCH",
    "WELLNESS",
    "WORKPLACE",
)
EXPECTED_POOL_KEYS = {
    "schema_version",
    "benchmark_id",
    "protocol_id",
    "candidate_pool_id",
    "candidate_pool_commitment",
    "candidate_pool_commitment_scheme",
    "candidate_pool_frozen",
    "candidates",
}
EXPECTED_CANDIDATE_KEYS = {
    "candidate_id",
    "construct_strata",
    "source_languages",
    "jurisdictions",
    "exact_object_identity_resolved",
    "exposure_status",
    "semantic_validation_passed",
    "human_confirmed_construct_tags",
    "pilot_or_development_exposed",
}


class D4SelectionError(ValueError):
    """Raised when controlled candidate-pool selection must fail closed."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_domain(domain: str, value: Any) -> str:
    h = hashlib.sha256()
    h.update(domain.encode("utf-8"))
    h.update(b"\0")
    h.update(_canonical_bytes(value))
    return h.hexdigest()


def _hmac_sha256_domain(key: bytes, domain: str, value: Any) -> str:
    if not isinstance(key, bytes) or not key:
        raise D4SelectionError("candidate-pool commitment key must be non-empty bytes")
    payload = domain.encode("utf-8") + b"\0" + _canonical_bytes(value)
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D4SelectionError(f"{field} keys mismatch; missing={missing}, extra={extra}")


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D4SelectionError(f"{field} must be a non-empty string")
    return value


def _require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise D4SelectionError(f"{field} must be a non-empty array")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_require_nonempty_string(item, f"{field}[{index}]"))
    if len(result) != len(set(result)):
        raise D4SelectionError(f"{field} must contain unique values")
    return result


def _is_english(language: str) -> bool:
    normalized = language.strip().lower().replace("_", "-")
    return normalized == "en" or normalized.startswith("en-")


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "construct_strata": sorted(candidate["construct_strata"]),
        "source_languages": sorted(candidate["source_languages"]),
        "jurisdictions": sorted(candidate["jurisdictions"]),
        "exact_object_identity_resolved": candidate["exact_object_identity_resolved"],
        "exposure_status": candidate["exposure_status"],
        "semantic_validation_passed": candidate["semantic_validation_passed"],
        "human_confirmed_construct_tags": candidate["human_confirmed_construct_tags"],
        "pilot_or_development_exposed": candidate["pilot_or_development_exposed"],
    }


def candidate_pool_commitment(pool: dict[str, Any], key: bytes) -> str:
    """Return an order-invariant HMAC commitment for the frozen controlled pool."""

    candidates = pool.get("candidates")
    if not isinstance(candidates, list):
        raise D4SelectionError("candidates must be an array before commitment can be computed")
    try:
        normalized_candidates = sorted(
            (_normalize_candidate(candidate) for candidate in candidates),
            key=lambda candidate: candidate["candidate_id"],
        )
    except (KeyError, TypeError) as exc:
        raise D4SelectionError("candidate pool is malformed and cannot be committed") from exc
    preimage = {
        "schema_version": pool.get("schema_version"),
        "benchmark_id": pool.get("benchmark_id"),
        "protocol_id": pool.get("protocol_id"),
        "candidate_pool_id": pool.get("candidate_pool_id"),
        "candidate_pool_commitment_scheme": pool.get("candidate_pool_commitment_scheme"),
        "candidate_pool_frozen": pool.get("candidate_pool_frozen"),
        "candidates": normalized_candidates,
    }
    return _hmac_sha256_domain(key, POOL_COMMITMENT_DOMAIN, preimage)


def _validate_pool(pool: dict[str, Any], key: bytes) -> list[dict[str, Any]]:
    _require_exact_keys(pool, EXPECTED_POOL_KEYS, "candidate_pool")
    if pool["schema_version"] != "0.1":
        raise D4SelectionError("schema_version must be 0.1")
    if pool["benchmark_id"] != BENCHMARK_ID:
        raise D4SelectionError(f"benchmark_id must be {BENCHMARK_ID}")
    if pool["protocol_id"] != PROTOCOL_ID:
        raise D4SelectionError(f"protocol_id must be {PROTOCOL_ID}")
    _require_nonempty_string(pool["candidate_pool_id"], "candidate_pool_id")
    if pool["candidate_pool_commitment_scheme"] != COMMITMENT_SCHEME:
        raise D4SelectionError(f"candidate_pool_commitment_scheme must be {COMMITMENT_SCHEME}")
    if pool["candidate_pool_frozen"] is not True:
        raise D4SelectionError("candidate_pool_frozen must be true before deterministic selection")
    if not isinstance(pool["candidate_pool_commitment"], str) or len(pool["candidate_pool_commitment"]) != 64:
        raise D4SelectionError("candidate_pool_commitment must be a 64-character lowercase HMAC-SHA-256 digest")
    if any(ch not in "0123456789abcdef" for ch in pool["candidate_pool_commitment"]):
        raise D4SelectionError("candidate_pool_commitment must be lowercase hexadecimal")

    candidates_raw = pool["candidates"]
    if not isinstance(candidates_raw, list) or len(candidates_raw) < FINAL_N:
        raise D4SelectionError(f"candidate pool must contain at least {FINAL_N} candidates")

    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(candidates_raw):
        if not isinstance(raw, dict):
            raise D4SelectionError(f"candidates[{index}] must be an object")
        _require_exact_keys(raw, EXPECTED_CANDIDATE_KEYS, f"candidates[{index}]")
        candidate_id = _require_nonempty_string(raw["candidate_id"], f"candidates[{index}].candidate_id")
        if candidate_id in seen_ids:
            raise D4SelectionError(f"duplicate candidate_id: {candidate_id}")
        seen_ids.add(candidate_id)

        strata = _require_string_list(raw["construct_strata"], f"candidates[{index}].construct_strata")
        unknown_strata = sorted(set(strata) - set(REQUIRED_STRATA))
        if unknown_strata:
            raise D4SelectionError(f"candidate {candidate_id} has unsupported construct strata: {unknown_strata}")
        languages = _require_string_list(raw["source_languages"], f"candidates[{index}].source_languages")
        jurisdictions = _require_string_list(raw["jurisdictions"], f"candidates[{index}].jurisdictions")

        if raw["exact_object_identity_resolved"] is not True:
            raise D4SelectionError(f"candidate {candidate_id} lacks resolved exact-object identity")
        if raw["exposure_status"] != "NO_KNOWN_EXPOSURE_REVIEWED":
            raise D4SelectionError(f"candidate {candidate_id} is not exposure-cleared for held-out selection")
        if raw["semantic_validation_passed"] is not True:
            raise D4SelectionError(f"candidate {candidate_id} has not passed semantic validation")
        if raw["human_confirmed_construct_tags"] is not True:
            raise D4SelectionError(f"candidate {candidate_id} construct tags are not human-confirmed")
        if raw["pilot_or_development_exposed"] is not False:
            raise D4SelectionError(f"candidate {candidate_id} is pilot/development exposed")

        candidates.append(
            {
                **raw,
                "construct_strata": strata,
                "source_languages": languages,
                "jurisdictions": jurisdictions,
            }
        )

    recomputed = candidate_pool_commitment(pool, key)
    if not hmac.compare_digest(recomputed, pool["candidate_pool_commitment"]):
        raise D4SelectionError(
            "candidate_pool_commitment does not match the exact frozen pre-label candidate pool under the supplied key"
        )
    return candidates


def _selection_seed(commitment: str) -> str:
    return _sha256_domain(SELECTION_SEED_DOMAIN, commitment)


def _tie_break(seed: str, candidate_id: str) -> int:
    digest = _sha256_domain(TIE_BREAK_DOMAIN, {"seed": seed, "candidate_id": candidate_id})
    return int(digest, 16)


def _choose_diversity_values(
    candidates: list[dict[str, Any]],
    field: str,
    *,
    count: int,
    minimum_support: int,
    exclude_english: bool = False,
) -> list[str]:
    support: Counter[str] = Counter()
    for candidate in candidates:
        for value in candidate[field]:
            if exclude_english and _is_english(value):
                continue
            support[value] += 1
    eligible = [(value, n) for value, n in support.items() if n >= minimum_support]
    eligible.sort(key=lambda item: (-item[1], item[0]))
    if len(eligible) < count:
        qualifier = "non-English source languages" if exclude_english else field
        raise D4SelectionError(
            f"candidate pool has fewer than {count} {qualifier} with support >= {minimum_support}"
        )
    return [value for value, _ in eligible[:count]]


def _feature_quotas(
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, int], list[str], list[str]]:
    selected_languages = _choose_diversity_values(
        candidates,
        "source_languages",
        count=NON_ENGLISH_LANGUAGE_COUNT,
        minimum_support=NON_ENGLISH_LANGUAGE_MINIMUM,
        exclude_english=True,
    )
    selected_jurisdictions = _choose_diversity_values(
        candidates,
        "jurisdictions",
        count=JURISDICTION_COUNT,
        minimum_support=JURISDICTION_MINIMUM,
    )
    quotas: dict[str, int] = {f"STRATUM:{stratum}": STRATUM_MINIMUM for stratum in REQUIRED_STRATA}
    quotas.update({f"LANG:{language}": NON_ENGLISH_LANGUAGE_MINIMUM for language in selected_languages})
    quotas.update({f"JURIS:{jurisdiction}": JURISDICTION_MINIMUM for jurisdiction in selected_jurisdictions})
    return quotas, selected_languages, selected_jurisdictions


def _candidate_features(candidate: dict[str, Any], languages: set[str], jurisdictions: set[str]) -> set[str]:
    features = {f"STRATUM:{stratum}" for stratum in candidate["construct_strata"]}
    features.update(f"LANG:{language}" for language in candidate["source_languages"] if language in languages)
    features.update(f"JURIS:{jurisdiction}" for jurisdiction in candidate["jurisdictions"] if jurisdiction in jurisdictions)
    return features


def _count_selected(selected: list[dict[str, Any]]) -> tuple[Counter[str], Counter[str], Counter[str]]:
    strata: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    jurisdictions: Counter[str] = Counter()
    for candidate in selected:
        strata.update(candidate["construct_strata"])
        languages.update(language for language in candidate["source_languages"] if not _is_english(language))
        jurisdictions.update(candidate["jurisdictions"])
    return strata, languages, jurisdictions


def select_candidates(pool: dict[str, Any], commitment_key: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select exactly 240 pre-label candidates deterministically and fail closed.

    The selector uses only frozen eligibility/construct/language/jurisdiction metadata.
    It contains no path for human D1 labels, model outputs, scores, prompts,
    thresholds, or final model errors. The quota satisfier is deterministic and
    conservative: failure means this algorithm did not establish a valid 240-item
    allocation for the committed pool; it is not a proof that no feasible allocation
    exists.
    """

    candidates = _validate_pool(pool, commitment_key)
    quotas, language_targets, jurisdiction_targets = _feature_quotas(candidates)
    language_target_set = set(language_targets)
    jurisdiction_target_set = set(jurisdiction_targets)

    candidate_features = {
        candidate["candidate_id"]: _candidate_features(candidate, language_target_set, jurisdiction_target_set)
        for candidate in candidates
    }
    support: Counter[str] = Counter()
    for features in candidate_features.values():
        support.update(features)
    for feature, target in quotas.items():
        if support[feature] < target:
            raise D4SelectionError(f"candidate pool support for {feature} is {support[feature]}, below required {target}")

    seed = _selection_seed(pool["candidate_pool_commitment"])
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    achieved: Counter[str] = Counter()

    while len(selected) < FINAL_N:
        deficits = {feature: max(target - achieved[feature], 0) for feature, target in quotas.items()}
        if all(deficit == 0 for deficit in deficits.values()):
            break

        remaining = [candidate for candidate in candidates if candidate["candidate_id"] not in selected_ids]
        remaining_support: Counter[str] = Counter()
        for candidate in remaining:
            remaining_support.update(candidate_features[candidate["candidate_id"]])
        for feature, deficit in deficits.items():
            if deficit > remaining_support[feature]:
                raise D4SelectionError(
                    f"remaining committed pool cannot satisfy {feature} under the current deterministic selection state"
                )

        ranked: list[tuple[Fraction, int, int, str, dict[str, Any]]] = []
        for candidate in remaining:
            features = candidate_features[candidate["candidate_id"]]
            active = [feature for feature in features if deficits.get(feature, 0) > 0]
            if not active:
                continue
            urgency = sum((Fraction(deficits[feature], remaining_support[feature]) for feature in active), Fraction())
            ranked.append(
                (
                    -urgency,
                    -len(active),
                    _tie_break(seed, candidate["candidate_id"]),
                    candidate["candidate_id"],
                    candidate,
                )
            )
        if not ranked:
            raise D4SelectionError("no remaining candidate covers an unsatisfied frozen quota")
        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        chosen = ranked[0][4]
        selected.append(chosen)
        selected_ids.add(chosen["candidate_id"])
        achieved.update(candidate_features[chosen["candidate_id"]])

    if len(selected) < FINAL_N:
        remaining = [candidate for candidate in candidates if candidate["candidate_id"] not in selected_ids]
        remaining.sort(key=lambda candidate: (_tie_break(seed, candidate["candidate_id"]), candidate["candidate_id"]))
        needed = FINAL_N - len(selected)
        if len(remaining) < needed:
            raise D4SelectionError("candidate pool cannot fill exact final membership size")
        selected.extend(remaining[:needed])
        selected_ids.update(candidate["candidate_id"] for candidate in remaining[:needed])

    if len(selected) != FINAL_N or len(selected_ids) != FINAL_N:
        raise D4SelectionError("selection must contain exactly 240 unique candidate IDs")

    stratum_counts, language_counts, jurisdiction_counts = _count_selected(selected)
    missing: list[str] = []
    for stratum in REQUIRED_STRATA:
        if stratum_counts[stratum] < STRATUM_MINIMUM:
            missing.append(f"STRATUM:{stratum}")
    for language in language_targets:
        if language_counts[language] < NON_ENGLISH_LANGUAGE_MINIMUM:
            missing.append(f"LANG:{language}")
    for jurisdiction in jurisdiction_targets:
        if jurisdiction_counts[jurisdiction] < JURISDICTION_MINIMUM:
            missing.append(f"JURIS:{jurisdiction}")
    if missing:
        raise D4SelectionError(
            "deterministic selector did not establish all frozen quotas within 240 items; "
            f"unsatisfied={sorted(set(missing))}; this is no proof of pool infeasibility"
        )

    sorted_ids = sorted(selected_ids)
    membership_sha256 = _sha256_domain(MEMBERSHIP_DOMAIN, sorted_ids)
    controlled_selection = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "candidate_pool_id": pool["candidate_pool_id"],
        "candidate_pool_commitment": pool["candidate_pool_commitment"],
        "candidate_pool_commitment_scheme": COMMITMENT_SCHEME,
        "selection_seed_sha256": seed,
        "selected_membership_sha256": membership_sha256,
        "selected_candidate_ids": sorted_ids,
        "selected_count": FINAL_N,
        "selection_used_final_human_labels": False,
        "selection_used_model_outputs_scores_prompts_thresholds_or_final_errors": False,
        "custody": "S3_CONTROLLED",
        "authority": {
            "benchmark_adequacy_established": False,
            "g2_passed": False,
            "canonical_s2_authority": False,
            "publication_authority": False,
            "assessment_effect": "NONE",
        },
    }
    aggregate_summary = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "candidate_pool_commitment": pool["candidate_pool_commitment"],
        "candidate_pool_commitment_scheme": COMMITMENT_SCHEME,
        "selection_seed_sha256": seed,
        "selected_membership_sha256": membership_sha256,
        "selected_count": FINAL_N,
        "stratum_counts": {stratum: stratum_counts[stratum] for stratum in REQUIRED_STRATA},
        "non_english_language_targets": language_targets,
        "non_english_language_counts": {language: language_counts[language] for language in language_targets},
        "jurisdiction_targets": jurisdiction_targets,
        "jurisdiction_counts": {jurisdiction: jurisdiction_counts[jurisdiction] for jurisdiction in jurisdiction_targets},
        "population_generalizable": False,
        "quota_satisfaction_established_for_selected_membership": True,
        "global_pool_feasibility_solver_used": False,
        "selection_algorithm": "DETERMINISTIC_CONSERVATIVE_GREEDY_V1",
        "authority": controlled_selection["authority"],
    }
    return controlled_selection, aggregate_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministically select the PRE-G2 D4 240-item held-out challenge set")
    parser.add_argument("candidate_pool", type=Path)
    parser.add_argument(
        "--commitment-key-file",
        type=Path,
        required=True,
        help="S3-controlled HMAC key file used only to verify the frozen candidate-pool commitment.",
    )
    parser.add_argument(
        "--controlled-output",
        type=Path,
        default=None,
        help="Explicit S3 path for the controlled membership payload. Candidate IDs are never printed to stdout.",
    )
    args = parser.parse_args()
    try:
        pool = json.loads(args.candidate_pool.read_text(encoding="utf-8"))
        if not isinstance(pool, dict):
            raise D4SelectionError("candidate-pool root must be an object")
        commitment_key = args.commitment_key_file.read_bytes()
        if not commitment_key:
            raise D4SelectionError("commitment key file must not be empty")
        controlled, aggregate = select_candidates(pool, commitment_key)
        if args.controlled_output is not None:
            args.controlled_output.write_text(
                json.dumps(controlled, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except (OSError, json.JSONDecodeError, D4SelectionError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print(json.dumps(aggregate, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
