from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import tempfile
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

BENCHMARK_ID = "PRE_G2_PATENT_V0_1"
PROTOCOL_ID = "PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1"
FINAL_N = 240
STRATUM_MINIMUM = 40
NON_ENGLISH_LANGUAGE_COUNT = 8
NON_ENGLISH_LANGUAGE_MINIMUM = 4
JURISDICTION_COUNT = 8
JURISDICTION_MINIMUM = 4
MISSING_ABSTRACT_MINIMUM = 16
SHORT_ABSTRACT_MINIMUM = 16
QUERY_OUTSIDE_POOL_MINIMUM = 40

COMMITMENT_SCHEME = "HMAC_SHA256_DOMAIN_CANONICAL_JSON_V1"
POOL_COMMITMENT_DOMAIN = "PRE_G2_D3_CHALLENGE_CANDIDATE_POOL_COMMITMENT_V1"
SELECTION_SEED_DOMAIN = "PRE_G2_D3_CHALLENGE_SELECTION_SEED_V1"
TIE_BREAK_DOMAIN = "PRE_G2_D3_CHALLENGE_SELECTION_TIE_BREAK_V1"
MEMBERSHIP_DOMAIN = "PRE_G2_D3_CHALLENGE_SELECTED_MEMBERSHIP_V1"
PUBLIC_CONTROLLED_FAILURE = (
    "INVALID: controlled D3 challenge selection failed under the pre-label containment boundary"
)
PUBLIC_INTERNAL_FAILURE = (
    "INVALID: internal D3 challenge selector failure contained under the pre-label containment boundary"
)

REQUIRED_STRATA = (
    "GRAY_CAPABILITY",
    "MISSING_OR_SHORT_ABSTRACT",
    "MULTI_JURISDICTION",
    "MULTI_YEAR",
    "MULTILINGUAL",
    "SEMANTICALLY_DECEPTIVE_NEGATIVE",
)
TEXT_AVAILABILITY = {
    "ENGLISH_ABSTRACT",
    "NON_ENGLISH_ABSTRACT_ONLY",
    "SHORT_ABSTRACT",
    "MISSING_ABSTRACT",
    "TITLE_ONLY",
}
QUERY_POOL_PROVENANCE = {
    "IN_QUERY_POOL",
    "OUTSIDE_QUERY_POOL",
    "UNKNOWN",
    "NOT_APPLICABLE",
}
EXPECTED_POOL_KEYS = {
    "schema_version",
    "benchmark_id",
    "protocol_id",
    "human_calibration_disposition_sha256",
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
    "text_availability",
    "query_pool_provenance",
    "exact_family_identity_resolved",
    "exposure_status",
    "semantic_validation_passed",
    "human_confirmed_construct_tags",
    "pilot_or_development_exposed",
}
FORBIDDEN_KEYS = {
    "decision",
    "final_disposition",
    "human_label",
    "human_labels",
    "prediction",
    "predictions",
    "model_prediction",
    "model_predictions",
    "probability_include",
    "probability_positive",
    "model_score",
    "model_scores",
    "prompt",
    "prompts",
    "threshold",
    "thresholds",
    "final_model_error",
    "final_model_errors",
    "cheap_neuro",
    "gold_neuro",
    "verdict",
}


class D3ChallengeSelectionError(ValueError):
    """Raised when controlled D3 challenge selection must fail closed."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise D3ChallengeSelectionError(
            "candidate-pool material must be finite JSON-compatible data"
        ) from exc


def _sha256_domain(domain: str, value: Any) -> str:
    h = hashlib.sha256()
    h.update(domain.encode("utf-8"))
    h.update(b"\0")
    h.update(_canonical_bytes(value))
    return h.hexdigest()


def _hmac_sha256_domain(key: bytes, domain: str, value: Any) -> str:
    if not isinstance(key, bytes) or not key:
        raise D3ChallengeSelectionError(
            "candidate-pool commitment key must be non-empty bytes"
        )
    payload = domain.encode("utf-8") + b"\0" + _canonical_bytes(value)
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _require_exact_keys(mapping: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise D3ChallengeSelectionError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise D3ChallengeSelectionError(f"{field} must be a non-empty string")
    return value


def _require_sha256(value: Any, field: str) -> str:
    text = _require_nonempty_string(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise D3ChallengeSelectionError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise D3ChallengeSelectionError(f"{field} must be a non-empty array")
    result = [
        _require_nonempty_string(item, f"{field}[{index}]")
        for index, item in enumerate(value)
    ]
    if len(result) != len(set(result)):
        raise D3ChallengeSelectionError(f"{field} must contain unique values")
    return result


def _reject_forbidden_fields(value: Any, field: str = "candidate_pool") -> None:
    if isinstance(value, dict):
        forbidden = sorted(set(value).intersection(FORBIDDEN_KEYS))
        if forbidden:
            raise D3ChallengeSelectionError(
                f"{field} contains forbidden post-label/model-development fields: {forbidden}"
            )
        for key, child in value.items():
            _reject_forbidden_fields(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_fields(child, f"{field}[{index}]")


def _is_english(language: str) -> bool:
    normalized = language.strip().lower().replace("_", "-")
    return normalized == "en" or normalized.startswith("en-")


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "construct_strata": sorted(candidate["construct_strata"]),
        "source_languages": sorted(candidate["source_languages"]),
        "jurisdictions": sorted(candidate["jurisdictions"]),
        "text_availability": candidate["text_availability"],
        "query_pool_provenance": candidate["query_pool_provenance"],
        "exact_family_identity_resolved": candidate["exact_family_identity_resolved"],
        "exposure_status": candidate["exposure_status"],
        "semantic_validation_passed": candidate["semantic_validation_passed"],
        "human_confirmed_construct_tags": candidate["human_confirmed_construct_tags"],
        "pilot_or_development_exposed": candidate["pilot_or_development_exposed"],
    }


def candidate_pool_commitment(pool: dict[str, Any], key: bytes) -> str:
    candidates = pool.get("candidates")
    if not isinstance(candidates, list):
        raise D3ChallengeSelectionError(
            "candidates must be an array before commitment can be computed"
        )
    try:
        normalized_candidates = sorted(
            (_normalize_candidate(candidate) for candidate in candidates),
            key=lambda candidate: candidate["candidate_id"],
        )
    except (KeyError, TypeError) as exc:
        raise D3ChallengeSelectionError(
            "candidate pool is malformed and cannot be committed"
        ) from exc
    preimage = {
        "schema_version": pool.get("schema_version"),
        "benchmark_id": pool.get("benchmark_id"),
        "protocol_id": pool.get("protocol_id"),
        "human_calibration_disposition_sha256": pool.get(
            "human_calibration_disposition_sha256"
        ),
        "candidate_pool_id": pool.get("candidate_pool_id"),
        "candidate_pool_commitment_scheme": pool.get(
            "candidate_pool_commitment_scheme"
        ),
        "candidate_pool_frozen": pool.get("candidate_pool_frozen"),
        "candidates": normalized_candidates,
    }
    return _hmac_sha256_domain(
        key,
        POOL_COMMITMENT_DOMAIN,
        preimage,
    )


def _validate_pool(
    pool: dict[str, Any],
    key: bytes,
) -> list[dict[str, Any]]:
    _require_exact_keys(pool, EXPECTED_POOL_KEYS, "candidate_pool")
    _reject_forbidden_fields(pool)
    if pool["schema_version"] != "0.1":
        raise D3ChallengeSelectionError("schema_version must be 0.1")
    if pool["benchmark_id"] != BENCHMARK_ID:
        raise D3ChallengeSelectionError(
            f"benchmark_id must be {BENCHMARK_ID}"
        )
    if pool["protocol_id"] != PROTOCOL_ID:
        raise D3ChallengeSelectionError(
            f"protocol_id must be {PROTOCOL_ID}"
        )
    _require_sha256(
        pool["human_calibration_disposition_sha256"],
        "human_calibration_disposition_sha256",
    )
    _require_nonempty_string(pool["candidate_pool_id"], "candidate_pool_id")
    if pool["candidate_pool_commitment_scheme"] != COMMITMENT_SCHEME:
        raise D3ChallengeSelectionError(
            f"candidate_pool_commitment_scheme must be {COMMITMENT_SCHEME}"
        )
    if pool["candidate_pool_frozen"] is not True:
        raise D3ChallengeSelectionError(
            "candidate_pool_frozen must be true before deterministic selection"
        )
    _require_sha256(
        pool["candidate_pool_commitment"],
        "candidate_pool_commitment",
    )

    candidates_raw = pool["candidates"]
    if not isinstance(candidates_raw, list) or len(candidates_raw) < FINAL_N:
        raise D3ChallengeSelectionError(
            f"candidate pool must contain at least {FINAL_N} candidates"
        )

    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(candidates_raw):
        if not isinstance(raw, dict):
            raise D3ChallengeSelectionError(
                f"candidates[{index}] must be an object"
            )
        _require_exact_keys(
            raw,
            EXPECTED_CANDIDATE_KEYS,
            f"candidates[{index}]",
        )
        candidate_id = _require_nonempty_string(
            raw["candidate_id"],
            f"candidates[{index}].candidate_id",
        )
        if candidate_id in seen_ids:
            raise D3ChallengeSelectionError(
                f"duplicate candidate_id: {candidate_id}"
            )
        seen_ids.add(candidate_id)

        strata = _require_string_list(
            raw["construct_strata"],
            f"candidates[{index}].construct_strata",
        )
        unknown_strata = sorted(set(strata) - set(REQUIRED_STRATA))
        if unknown_strata:
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} has unsupported construct strata: {unknown_strata}"
            )
        languages = _require_string_list(
            raw["source_languages"],
            f"candidates[{index}].source_languages",
        )
        jurisdictions = _require_string_list(
            raw["jurisdictions"],
            f"candidates[{index}].jurisdictions",
        )
        if raw["text_availability"] not in TEXT_AVAILABILITY:
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} has unsupported text_availability"
            )
        if raw["query_pool_provenance"] not in QUERY_POOL_PROVENANCE:
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} has unsupported query_pool_provenance"
            )
        if (
            "MISSING_OR_SHORT_ABSTRACT" in strata
            and raw["text_availability"]
            not in {"MISSING_ABSTRACT", "SHORT_ABSTRACT"}
        ):
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} has inconsistent missing/short-abstract metadata"
            )
        if "MULTI_JURISDICTION" in strata and len(jurisdictions) < 2:
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} has inconsistent multi-jurisdiction metadata"
            )
        if "MULTILINGUAL" in strata and all(
            _is_english(language) for language in languages
        ):
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} has inconsistent multilingual metadata"
            )

        if raw["exact_family_identity_resolved"] is not True:
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} lacks resolved family identity"
            )
        if raw["exposure_status"] != "NO_KNOWN_EXPOSURE_REVIEWED":
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} is not exposure-cleared"
            )
        if raw["semantic_validation_passed"] is not True:
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} has not passed semantic validation"
            )
        if raw["human_confirmed_construct_tags"] is not True:
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} construct tags are not human-confirmed"
            )
        if raw["pilot_or_development_exposed"] is not False:
            raise D3ChallengeSelectionError(
                f"candidate {candidate_id} is pilot/development exposed"
            )

        candidates.append(
            {
                **raw,
                "construct_strata": strata,
                "source_languages": languages,
                "jurisdictions": jurisdictions,
            }
        )

    recomputed = candidate_pool_commitment(pool, key)
    if not hmac.compare_digest(
        recomputed,
        pool["candidate_pool_commitment"],
    ):
        raise D3ChallengeSelectionError(
            "candidate_pool_commitment does not match the exact frozen pre-label pool under the supplied key"
        )
    return candidates


def _selection_seed(commitment: str) -> str:
    return _sha256_domain(SELECTION_SEED_DOMAIN, commitment)


def _tie_break(seed: str, candidate_id: str) -> int:
    return int(
        _sha256_domain(
            TIE_BREAK_DOMAIN,
            {"seed": seed, "candidate_id": candidate_id},
        ),
        16,
    )


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
    eligible = [
        (value, n)
        for value, n in support.items()
        if n >= minimum_support
    ]
    eligible.sort(key=lambda item: (-item[1], item[0]))
    if len(eligible) < count:
        qualifier = (
            "non-English source languages"
            if exclude_english
            else field
        )
        raise D3ChallengeSelectionError(
            f"candidate pool has fewer than {count} {qualifier} with support >= {minimum_support}"
        )
    return [value for value, _ in eligible[:count]]


def _feature_quotas(
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, int], list[str], list[str]]:
    language_targets = _choose_diversity_values(
        candidates,
        "source_languages",
        count=NON_ENGLISH_LANGUAGE_COUNT,
        minimum_support=NON_ENGLISH_LANGUAGE_MINIMUM,
        exclude_english=True,
    )
    jurisdiction_targets = _choose_diversity_values(
        candidates,
        "jurisdictions",
        count=JURISDICTION_COUNT,
        minimum_support=JURISDICTION_MINIMUM,
    )
    quotas = {
        f"STRATUM:{stratum}": STRATUM_MINIMUM
        for stratum in REQUIRED_STRATA
    }
    quotas.update(
        {
            f"LANG:{language}": NON_ENGLISH_LANGUAGE_MINIMUM
            for language in language_targets
        }
    )
    quotas.update(
        {
            f"JURIS:{jurisdiction}": JURISDICTION_MINIMUM
            for jurisdiction in jurisdiction_targets
        }
    )
    quotas["TEXT:MISSING_ABSTRACT"] = MISSING_ABSTRACT_MINIMUM
    quotas["TEXT:SHORT_ABSTRACT"] = SHORT_ABSTRACT_MINIMUM
    quotas["QUERY:OUTSIDE_QUERY_POOL"] = QUERY_OUTSIDE_POOL_MINIMUM
    return quotas, language_targets, jurisdiction_targets


def _candidate_features(
    candidate: dict[str, Any],
    languages: set[str],
    jurisdictions: set[str],
) -> set[str]:
    features = {
        f"STRATUM:{stratum}"
        for stratum in candidate["construct_strata"]
    }
    features.update(
        f"LANG:{language}"
        for language in candidate["source_languages"]
        if language in languages
    )
    features.update(
        f"JURIS:{jurisdiction}"
        for jurisdiction in candidate["jurisdictions"]
        if jurisdiction in jurisdictions
    )
    if candidate["text_availability"] == "MISSING_ABSTRACT":
        features.add("TEXT:MISSING_ABSTRACT")
    if candidate["text_availability"] == "SHORT_ABSTRACT":
        features.add("TEXT:SHORT_ABSTRACT")
    if candidate["query_pool_provenance"] == "OUTSIDE_QUERY_POOL":
        features.add("QUERY:OUTSIDE_QUERY_POOL")
    return features


def _count_selected(
    selected: list[dict[str, Any]],
) -> tuple[
    Counter[str],
    Counter[str],
    Counter[str],
    Counter[str],
    Counter[str],
]:
    strata: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    jurisdictions: Counter[str] = Counter()
    text: Counter[str] = Counter()
    query: Counter[str] = Counter()
    for candidate in selected:
        strata.update(candidate["construct_strata"])
        languages.update(
            language
            for language in candidate["source_languages"]
            if not _is_english(language)
        )
        jurisdictions.update(candidate["jurisdictions"])
        text.update([candidate["text_availability"]])
        query.update([candidate["query_pool_provenance"]])
    return strata, languages, jurisdictions, text, query


def select_candidates(
    pool: dict[str, Any],
    commitment_key: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select exactly 240 D3 challenge candidates deterministically.

    The selector uses only frozen pre-label eligibility and challenge-coverage
    metadata. Failure is conservative and does not prove global infeasibility.
    """

    candidates = _validate_pool(pool, commitment_key)
    quotas, language_targets, jurisdiction_targets = _feature_quotas(
        candidates
    )
    language_target_set = set(language_targets)
    jurisdiction_target_set = set(jurisdiction_targets)
    candidate_features = {
        candidate["candidate_id"]: _candidate_features(
            candidate,
            language_target_set,
            jurisdiction_target_set,
        )
        for candidate in candidates
    }

    support: Counter[str] = Counter()
    for features in candidate_features.values():
        support.update(features)
    for feature, target in quotas.items():
        if support[feature] < target:
            raise D3ChallengeSelectionError(
                f"candidate pool support for {feature} is below the frozen quota"
            )

    seed = _selection_seed(pool["candidate_pool_commitment"])
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    achieved: Counter[str] = Counter()

    while len(selected) < FINAL_N:
        deficits = {
            feature: max(target - achieved[feature], 0)
            for feature, target in quotas.items()
        }
        if all(deficit == 0 for deficit in deficits.values()):
            break

        remaining = [
            candidate
            for candidate in candidates
            if candidate["candidate_id"] not in selected_ids
        ]
        remaining_support: Counter[str] = Counter()
        for candidate in remaining:
            remaining_support.update(
                candidate_features[candidate["candidate_id"]]
            )
        for feature, deficit in deficits.items():
            if deficit > remaining_support[feature]:
                raise D3ChallengeSelectionError(
                    "remaining committed pool cannot satisfy a frozen quota under the current deterministic state"
                )

        ranked: list[
            tuple[Fraction, int, int, str, dict[str, Any]]
        ] = []
        for candidate in remaining:
            features = candidate_features[candidate["candidate_id"]]
            active = [
                feature
                for feature in features
                if deficits.get(feature, 0) > 0
            ]
            if not active:
                continue
            urgency = sum(
                (
                    Fraction(
                        deficits[feature],
                        remaining_support[feature],
                    )
                    for feature in active
                ),
                Fraction(),
            )
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
            raise D3ChallengeSelectionError(
                "no remaining candidate covers an unsatisfied frozen quota"
            )
        ranked.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                item[3],
            )
        )
        chosen = ranked[0][4]
        selected.append(chosen)
        selected_ids.add(chosen["candidate_id"])
        achieved.update(
            candidate_features[chosen["candidate_id"]]
        )

    if len(selected) < FINAL_N:
        remaining = [
            candidate
            for candidate in candidates
            if candidate["candidate_id"] not in selected_ids
        ]
        remaining.sort(
            key=lambda candidate: (
                _tie_break(seed, candidate["candidate_id"]),
                candidate["candidate_id"],
            )
        )
        needed = FINAL_N - len(selected)
        if len(remaining) < needed:
            raise D3ChallengeSelectionError(
                "candidate pool cannot fill exact final membership size"
            )
        selected.extend(remaining[:needed])
        selected_ids.update(
            candidate["candidate_id"]
            for candidate in remaining[:needed]
        )

    if len(selected) != FINAL_N or len(selected_ids) != FINAL_N:
        raise D3ChallengeSelectionError(
            "selection must contain exactly 240 unique candidate IDs"
        )

    (
        stratum_counts,
        language_counts,
        jurisdiction_counts,
        text_counts,
        query_counts,
    ) = _count_selected(selected)
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
    if text_counts["MISSING_ABSTRACT"] < MISSING_ABSTRACT_MINIMUM:
        missing.append("TEXT:MISSING_ABSTRACT")
    if text_counts["SHORT_ABSTRACT"] < SHORT_ABSTRACT_MINIMUM:
        missing.append("TEXT:SHORT_ABSTRACT")
    if (
        query_counts["OUTSIDE_QUERY_POOL"]
        < QUERY_OUTSIDE_POOL_MINIMUM
    ):
        missing.append("QUERY:OUTSIDE_QUERY_POOL")
    if missing:
        raise D3ChallengeSelectionError(
            "deterministic selector did not establish every frozen coverage cell within 240 items; this is not a proof of pool infeasibility"
        )

    sorted_ids = sorted(selected_ids)
    membership_sha256 = _sha256_domain(
        MEMBERSHIP_DOMAIN,
        sorted_ids,
    )
    authority = {
        "final_selection_human_approval_established": False,
        "benchmark_adequacy_established": False,
        "g2_passed": False,
        "canonical_s2_authority": False,
        "publication_authority": False,
        "population_generalization_authority": False,
        "assessment_effect": "NONE",
    }
    controlled_selection = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "human_calibration_disposition_sha256": pool[
            "human_calibration_disposition_sha256"
        ],
        "candidate_pool_id": pool["candidate_pool_id"],
        "candidate_pool_commitment": pool[
            "candidate_pool_commitment"
        ],
        "candidate_pool_commitment_scheme": COMMITMENT_SCHEME,
        "selection_seed_sha256": seed,
        "selected_membership_sha256": membership_sha256,
        "selected_candidate_ids": sorted_ids,
        "selected_count": FINAL_N,
        "selection_used_final_human_labels": False,
        "selection_used_model_outputs_scores_prompts_thresholds_or_final_errors": False,
        "custody": "S3_CONTROLLED",
        "authority": authority,
    }
    aggregate_summary = {
        "schema_version": "0.1",
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "human_calibration_disposition_sha256": pool[
            "human_calibration_disposition_sha256"
        ],
        "candidate_pool_commitment": pool[
            "candidate_pool_commitment"
        ],
        "candidate_pool_commitment_scheme": COMMITMENT_SCHEME,
        "selection_seed_sha256": seed,
        "selected_membership_sha256": membership_sha256,
        "selected_count": FINAL_N,
        "stratum_counts": {
            stratum: stratum_counts[stratum]
            for stratum in REQUIRED_STRATA
        },
        "non_english_language_targets": language_targets,
        "non_english_language_counts": {
            language: language_counts[language]
            for language in language_targets
        },
        "jurisdiction_targets": jurisdiction_targets,
        "jurisdiction_counts": {
            jurisdiction: jurisdiction_counts[jurisdiction]
            for jurisdiction in jurisdiction_targets
        },
        "missing_abstract_count": text_counts[
            "MISSING_ABSTRACT"
        ],
        "short_abstract_count": text_counts[
            "SHORT_ABSTRACT"
        ],
        "outside_query_pool_count": query_counts[
            "OUTSIDE_QUERY_POOL"
        ],
        "outside_query_pool_is_population_recall_denominator": False,
        "population_generalizable": False,
        "quota_satisfaction_established_for_selected_membership": True,
        "global_pool_feasibility_solver_used": False,
        "selection_algorithm": "DETERMINISTIC_CONSERVATIVE_GREEDY_V1",
        "authority": authority,
    }
    return controlled_selection, aggregate_summary


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


def _normalized(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _validate_output_paths(
    candidate_pool_path: Path,
    key_path: Path,
    controlled_output: Path | None,
    controlled_error_output: Path | None,
) -> None:
    inputs = {
        _normalized(candidate_pool_path),
        _normalized(key_path),
    }
    outputs = [
        _normalized(path)
        for path in (
            controlled_output,
            controlled_error_output,
        )
        if path is not None
    ]
    if any(path in inputs for path in outputs):
        raise D3ChallengeSelectionError(
            "controlled output paths must be distinct from selector inputs"
        )
    if len(outputs) != len(set(outputs)):
        raise D3ChallengeSelectionError(
            "controlled success and error output paths must be distinct"
        )


def _controlled_diagnostic(
    error: BaseException,
    *,
    failure_class: str,
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "protocol_id": PROTOCOL_ID,
        "failure_class": failure_class,
        "exception_type": type(error).__name__,
        "controlled_detail": str(error),
        "custody": "S3_CONTROLLED",
        "public_output_authority": False,
    }


def run_selector(
    candidate_pool_path: Path,
    key_path: Path,
    *,
    controlled_output: Path | None = None,
    controlled_error_output: Path | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    try:
        _validate_output_paths(
            candidate_pool_path,
            key_path,
            controlled_output,
            controlled_error_output,
        )
    except D3ChallengeSelectionError:
        return 1, None, PUBLIC_CONTROLLED_FAILURE

    try:
        pool = json.loads(
            candidate_pool_path.read_text(encoding="utf-8")
        )
        if not isinstance(pool, dict):
            raise D3ChallengeSelectionError(
                "candidate-pool root must be an object"
            )
        key = key_path.read_bytes()
        if not key:
            raise D3ChallengeSelectionError(
                "commitment key file must not be empty"
            )
        controlled, aggregate = select_candidates(pool, key)
        if controlled_output is not None:
            _atomic_write_json(
                controlled_output,
                controlled,
            )
        return 0, aggregate, ""
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        D3ChallengeSelectionError,
    ) as exc:
        if controlled_error_output is not None:
            try:
                _atomic_write_json(
                    controlled_error_output,
                    _controlled_diagnostic(
                        exc,
                        failure_class="CONTROLLED_INPUT_OR_SELECTION_FAILURE",
                    ),
                )
            except OSError:
                pass
        return 1, None, PUBLIC_CONTROLLED_FAILURE
    except Exception as exc:
        if controlled_error_output is not None:
            try:
                _atomic_write_json(
                    controlled_error_output,
                    _controlled_diagnostic(
                        exc,
                        failure_class="UNEXPECTED_INTERNAL_FAILURE",
                    ),
                )
            except OSError:
                pass
        return 70, None, PUBLIC_INTERNAL_FAILURE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministically select the PRE-G2 D3 240-family challenge set"
    )
    parser.add_argument("candidate_pool", type=Path)
    parser.add_argument(
        "--commitment-key-file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--controlled-output",
        type=Path,
        default=None,
        help="Optional S3 path for controlled selected membership.",
    )
    parser.add_argument(
        "--controlled-error-output",
        type=Path,
        default=None,
        help="Optional S3 path for detailed controlled diagnostics.",
    )
    args = parser.parse_args()

    status, aggregate, public_message = run_selector(
        args.candidate_pool,
        args.commitment_key_file,
        controlled_output=args.controlled_output,
        controlled_error_output=args.controlled_error_output,
    )
    if status != 0:
        print(public_message)
        return status
    assert aggregate is not None
    print(
        json.dumps(
            aggregate,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
