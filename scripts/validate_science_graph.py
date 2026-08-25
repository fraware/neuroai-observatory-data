from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[1]
SCHEMAS = ROOT / "schemas" / "vnext"
ADAPTERS = ROOT / "science" / "adapters-v0.1.json"
PROTOCOL = ROOT / "science" / "discovery-protocol-v0.1.json"
SCIENCE_UNIVERSES = ROOT / "source-universes" / "p0" / "science-v0.1.json"
IDENTIFIER_NAMESPACES = ROOT / "identity" / "namespaces-v0.1.json"
SYNTHETIC = ROOT / "fixtures" / "vnext" / "science-acquisition.synthetic.json"

EXPECTED_PROVIDER_UNIVERSE = {
    "CROSSREF": "SU-SCI-CROSSREF",
    "EUROPE_PMC": "SU-SCI-EUROPEPMC",
    "OPENALEX": "SU-SCI-OPENALEX",
}
REQUIRED_SCIENCE_IDENTIFIER_NAMESPACES = {"DOI", "PMID", "PMCID", "OPENALEX_WORK"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        _load(SCHEMAS / name),
        format_checker=FormatChecker(),
    )


ADAPTER_VALIDATOR = _schema("source-adapter.schema.json")
FREEZE_VALIDATOR = _schema("acquisition-freeze.schema.json")
CANDIDATE_VALIDATOR = _schema("science-candidate-record.schema.json")
NAMESPACE_VALIDATOR = _schema("identifier-namespace.schema.json")


def _structural(validator: Draft202012Validator, obj: Any, label: str) -> None:
    errors = sorted(validator.iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        error = errors[0]
        path = ".".join(map(str, error.path)) or "<root>"
        raise ValueError(f"{label}:{path}: {error.message}")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_identifier_namespaces(registry: dict[str, Any]) -> bool:
    if registry.get("status") != "CONTROLLED_VOCABULARY_NOT_IDENTITY_AUTHORITY":
        raise ValueError("identifier namespace authority boundary drift")
    records = registry.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("identifier namespace registry requires records")
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        _structural(NAMESPACE_VALIDATOR, record, record.get("namespace_id", "IDENTIFIER_NAMESPACE"))
        namespace_id = record["namespace_id"]
        if namespace_id in by_id:
            raise ValueError(f"duplicate namespace_id: {namespace_id}")
        by_id[namespace_id] = record

    missing = REQUIRED_SCIENCE_IDENTIFIER_NAMESPACES - set(by_id)
    if missing:
        raise ValueError(f"missing science identifier namespaces: {sorted(missing)}")
    for namespace_id in REQUIRED_SCIENCE_IDENTIFIER_NAMESPACES:
        if "PUBLICATION" not in by_id[namespace_id]["allowed_entity_types"]:
            raise ValueError(f"{namespace_id}: science identifier namespace must allow PUBLICATION")
    return True


def validate_protocol(protocol: dict[str, Any]) -> bool:
    if protocol.get("protocol_id") != "SCIENCE-DISCOVERY-PROTOCOL-V0.1":
        raise ValueError("unexpected protocol_id")
    if protocol.get("schema_version") != "0.1.0":
        raise ValueError("unexpected protocol schema_version")
    if protocol.get("status") != "FROZEN_PROTOCOL_NO_PRODUCTION_ACQUISITION_YET":
        raise ValueError("protocol must remain frozen and explicitly non-production before first acquisition")

    families = protocol.get("query_families")
    if not isinstance(families, list) or not families:
        raise ValueError("protocol requires query families")
    family_ids = [row.get("query_family_id") for row in families]
    if len(family_ids) != len(set(family_ids)):
        raise ValueError("duplicate query_family_id")
    for row in families:
        terms = row.get("discovery_terms")
        if not isinstance(terms, list) or not terms or not all(isinstance(t, str) and t.strip() for t in terms):
            raise ValueError(f"{row.get('query_family_id')}: discovery_terms must be non-empty strings")
        normalized = [t.strip().casefold() for t in terms]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{row.get('query_family_id')}: duplicate discovery term")

    inclusion = protocol.get("candidate_inclusion", {})
    if inclusion.get("relevance_adjudication_required") is not True:
        raise ValueError("candidate relevance adjudication must remain required")
    if inclusion.get("automatic_canonical_inclusion") is not False:
        raise ValueError("protocol cannot permit automatic canonical inclusion")

    dedupe = protocol.get("deduplication", {})
    if dedupe.get("exact_identifier_precedence") != ["DOI", "PMID", "PMCID", "OPENALEX_WORK"]:
        raise ValueError("exact identifier precedence drift")
    if dedupe.get("fuzzy_title_author_matching") != "CANDIDATE_ONLY":
        raise ValueError("fuzzy matching must remain candidate-only")
    if dedupe.get("cross_provider_conflicts") != "PRESERVE_AND_ADJUDICATE":
        raise ValueError("cross-provider conflicts must be preserved")

    policy = protocol.get("provider_policy", {})
    if set(policy.get("required_for_first_candidate_acquisition", [])) != {"CROSSREF", "EUROPE_PMC"}:
        raise ValueError("first acquisition must require Crossref and Europe PMC")
    if policy.get("provider_absence_effect") != "NONE":
        raise ValueError("provider absence cannot have substantive effect")
    return True


def validate_adapters(registry: dict[str, Any], universe_fragment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if registry.get("registry_id") != "SCIENCE-ADAPTER-REGISTRY-V0.1":
        raise ValueError("unexpected adapter registry_id")
    if registry.get("status") != "CONTROLLED_ADAPTER_CONTRACTS_NOT_ACQUISITION_RESULTS":
        raise ValueError("adapter registry authority boundary drift")

    universes = {row["universe_id"]: row for row in universe_fragment.get("records", [])}
    records = registry.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("adapter registry requires records")

    adapter_by_id: dict[str, dict[str, Any]] = {}
    providers: set[str] = set()
    for adapter in records:
        _structural(ADAPTER_VALIDATOR, adapter, adapter.get("adapter_id", "SOURCE_ADAPTER"))
        aid = adapter["adapter_id"]
        if aid in adapter_by_id:
            raise ValueError(f"duplicate adapter_id: {aid}")
        adapter_by_id[aid] = adapter

        provider = adapter["provider"]
        if provider in providers:
            raise ValueError(f"duplicate provider adapter: {provider}")
        providers.add(provider)

        expected_universe = EXPECTED_PROVIDER_UNIVERSE[provider]
        if adapter["source_universe_id"] != expected_universe:
            raise ValueError(f"{aid}: provider/universe mismatch")
        universe = universes.get(expected_universe)
        if universe is None:
            raise ValueError(f"{aid}: missing source universe")
        if universe.get("domain") != "SCIENCE":
            raise ValueError(f"{aid}: non-science universe binding")
        if universe.get("planning_state") != "VERIFIED_INTERFACE":
            raise ValueError(f"{aid}: adapter requires VERIFIED_INTERFACE source universe")
        if adapter["transport"]["base_url"] != universe["interface"]["base_url"]:
            raise ValueError(f"{aid}: adapter base_url differs from source-universe contract")

        mappings = adapter["field_mapping"]
        provider_fields = [m["provider_field"] for m in mappings]
        targets = [m["target_field"] for m in mappings]
        if len(provider_fields) != len(set(provider_fields)):
            raise ValueError(f"{aid}: duplicate provider field mapping")
        if len(targets) != len(set(targets)):
            raise ValueError(f"{aid}: duplicate target field mapping")
        if not any(m["target_field"] == "title" and m["required_for_candidate"] for m in mappings):
            raise ValueError(f"{aid}: title must be required for candidates")

        auth = adapter["transport"]["authentication_class"]
        state = adapter["state"]
        if state == "CREDENTIAL_REQUIRED" and auth != "FREE_API_KEY":
            raise ValueError(f"{aid}: CREDENTIAL_REQUIRED must bind FREE_API_KEY")

    if providers != set(EXPECTED_PROVIDER_UNIVERSE):
        raise ValueError(f"adapter provider set mismatch: {sorted(providers)}")
    return adapter_by_id


def validate_acquisition_bundle(
    bundle: dict[str, Any],
    adapters: dict[str, dict[str, Any]],
    protocol: dict[str, Any],
) -> bool:
    if bundle.get("synthetic") is not True:
        raise ValueError("checked-in fixture must be explicitly synthetic")
    families = {row["query_family_id"] for row in protocol["query_families"]}
    protocol_cutoff = _dt(protocol["evidence_cutoff"])

    freezes = bundle.get("freezes")
    candidates = bundle.get("candidates")
    if not isinstance(freezes, list) or not isinstance(candidates, list):
        raise ValueError("bundle requires freezes and candidates arrays")

    freeze_by_id: dict[str, dict[str, Any]] = {}
    for freeze in freezes:
        _structural(FREEZE_VALIDATOR, freeze, freeze.get("freeze_id", "ACQUISITION_FREEZE"))
        fid = freeze["freeze_id"]
        if fid in freeze_by_id:
            raise ValueError(f"duplicate freeze_id: {fid}")
        freeze_by_id[fid] = freeze

        adapter = adapters.get(freeze["adapter_id"])
        if adapter is None:
            raise ValueError(f"{fid}: unknown adapter")
        if freeze["source_universe_id"] != adapter["source_universe_id"]:
            raise ValueError(f"{fid}: freeze/adapter universe mismatch")
        if freeze["adapter_version"] != adapter["adapter_version"]:
            raise ValueError(f"{fid}: freeze/adapter version mismatch")
        if freeze["protocol_id"] != protocol["protocol_id"]:
            raise ValueError(f"{fid}: freeze/protocol mismatch")
        unknown_families = set(freeze["query_family_ids"]) - families
        if unknown_families:
            raise ValueError(f"{fid}: unknown query families: {sorted(unknown_families)}")
        if _dt(freeze["retrieval_cutoff"]) != protocol_cutoff:
            raise ValueError(f"{fid}: retrieval cutoff differs from frozen protocol")
        if _dt(freeze["created_at"]) < protocol_cutoff:
            raise ValueError(f"{fid}: freeze created before retrieval cutoff")
        if freeze["exhaustion_state"] == "COMPLETE" and freeze.get("continuation_state") not in (None, ""):
            raise ValueError(f"{fid}: complete freeze cannot retain continuation state")

    seen_candidate_ids: set[str] = set()
    candidate_counts = {fid: 0 for fid in freeze_by_id}
    for candidate in candidates:
        _structural(CANDIDATE_VALIDATOR, candidate, candidate.get("candidate_id", "SCIENCE_CANDIDATE"))
        cid = candidate["candidate_id"]
        if cid in seen_candidate_ids:
            raise ValueError(f"duplicate candidate_id: {cid}")
        seen_candidate_ids.add(cid)

        freeze = freeze_by_id.get(candidate["acquisition_freeze_id"])
        if freeze is None:
            raise ValueError(f"{cid}: dangling acquisition freeze")
        adapter = adapters[freeze["adapter_id"]]
        if candidate["provider"] != adapter["provider"]:
            raise ValueError(f"{cid}: candidate provider does not match acquisition adapter")
        if candidate["source_universe_id"] != freeze["source_universe_id"]:
            raise ValueError(f"{cid}: candidate/freeze universe mismatch")
        if not set(candidate["discovery_query_family_ids"]).issubset(set(freeze["query_family_ids"])):
            raise ValueError(f"{cid}: candidate query family not present in acquisition freeze")
        if _dt(candidate["observed_at"]) < _dt(freeze["created_at"]):
            raise ValueError(f"{cid}: candidate observed before acquisition freeze creation")
        candidate_counts[freeze["freeze_id"]] += 1

    for fid, freeze in freeze_by_id.items():
        if freeze["exhaustion_state"] == "COMPLETE" and candidate_counts[fid] != freeze["records_observed"]:
            raise ValueError(f"{fid}: records_observed does not reconcile with candidate records")
        if candidate_counts[fid] > freeze["records_observed"]:
            raise ValueError(f"{fid}: candidate count exceeds records_observed")
    return True


def validate_repository_state() -> bool:
    validate_identifier_namespaces(_load(IDENTIFIER_NAMESPACES))
    protocol = _load(PROTOCOL)
    validate_protocol(protocol)
    adapters = validate_adapters(_load(ADAPTERS), _load(SCIENCE_UNIVERSES))
    validate_acquisition_bundle(_load(SYNTHETIC), adapters, protocol)
    return True


def main() -> None:
    validate_repository_state()
    print("PASS science graph contract: identifier namespaces, adapters, frozen protocol, and synthetic acquisition bundle")


if __name__ == "__main__":
    main()
