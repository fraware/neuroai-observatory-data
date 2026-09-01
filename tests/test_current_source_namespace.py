from __future__ import annotations

from scripts.current_source_namespace import (
    EXPECTED_PRIMA_IDS,
    materialize_effective_source_namespace,
)


def test_materializes_exact_effective_controlled_namespace() -> None:
    result = materialize_effective_source_namespace()

    assert result["materialized_source_count"] == 248
    assert result["family_counts"] == {
        "V1_4_BASELINE": 224,
        "V1_6_REFRESH": 12,
        "V1_7_PRIMA_SUPPLEMENTAL": 12,
    }
    assert len(result["sources"]) == 248
    assert len({row["source_id"] for row in result["sources"]}) == 248
    assert result["global_completeness_claim"] is False
    assert result["network_execution_performed"] is False
    assert result["migration_performed"] is False
    assert result["canonical_mutation_performed"] is False
    assert result["publication_authority_created"] is False


def test_prima_supplemental_identity_set_is_exact_and_noninvented() -> None:
    result = materialize_effective_source_namespace()
    prima_ids = tuple(
        row["source_id"]
        for row in result["sources"]
        if row["lineage_family"] == "V1_7_PRIMA_SUPPLEMENTAL"
    )

    assert set(prima_ids) == set(EXPECTED_PRIMA_IDS)
    assert "SRC-PR-003" not in prima_ids
    assert "SRC-PR-004" not in prima_ids
    assert "SRC-PR-011" not in prima_ids


def test_namespace_digest_is_deterministic() -> None:
    first = materialize_effective_source_namespace()
    second = materialize_effective_source_namespace()

    assert first["source_id_set_sha256"] == second["source_id_set_sha256"]
    assert first["sources"] == second["sources"]
