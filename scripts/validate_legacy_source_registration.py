#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas" / "legacy-source-registration-proposals.schema.json"
DEFAULT_MANIFEST = ROOT / "curation" / "legacy_assessment_source_registration_proposals_v0.1.json"


class ValidationError(ValueError):
    pass


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise ValidationError(f"Unsupported schema type: {expected}")


def _validate(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    if expected is not None:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, item) for item in allowed):
            raise ValidationError(f"{path}: expected type {allowed}, got {type(value).__name__}")

    if "const" in schema and value != schema["const"]:
        raise ValidationError(f"{path}: expected constant {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{path}: value {value!r} not in enum")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise ValidationError(f"{path}: string shorter than {min_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            raise ValidationError(f"{path}: {value!r} does not match {pattern!r}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise ValidationError(f"{path}: array has fewer than {min_items} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate(item, item_schema, f"{path}[{index}]")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ValidationError(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child in value.items():
                child_schema = properties.get(key)
                if child_schema is None:
                    if schema.get("additionalProperties") is False:
                        raise ValidationError(f"{path}: unexpected property {key!r}")
                    continue
                _validate(child, child_schema, f"{path}.{key}")


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any]) -> None:
    _validate(manifest, schema)

    proposals = manifest["proposals"]
    proposal_ids = [proposal["proposal_id"] for proposal in proposals]
    if len(set(proposal_ids)) != len(proposal_ids):
        raise ValidationError("$.proposals: proposal_id values must be unique")
    expected_ids = [f"LEGACY-SRC-PROP-{index:03d}" for index in range(1, len(proposals) + 1)]
    if proposal_ids != expected_ids:
        raise ValidationError("$.proposals: proposal_id values must be deterministically contiguous and sorted")

    for index, proposal in enumerate(proposals):
        path = f"$.proposals[{index}]"
        requirements = proposal["impacted_requirement_ids"]
        if requirements != sorted(set(requirements)):
            raise ValidationError(f"{path}: impacted_requirement_ids must be sorted and unique")
        if proposal["impacted_requirement_count"] != len(requirements):
            raise ValidationError(f"{path}: impacted_requirement_count does not match requirement IDs")

        action = proposal["action"]
        if action == "REGISTER_NEW_SOURCE":
            if proposal["requested_source_id"] is not None or proposal["existing_source_id"] is not None:
                raise ValidationError(f"{path}: new-source proposal must not assign a canonical source ID")
            if not proposal["normalized_public_url"] and not proposal["checksum"]:
                raise ValidationError(f"{path}: new-source proposal requires an exact URL or checksum")
        elif action == "REGISTER_MISSING_EXPLICIT_SOURCE":
            if not proposal["requested_source_id"]:
                raise ValidationError(f"{path}: missing-explicit-source proposal requires requested_source_id")
            source_record = proposal.get("proposed_source_record")
            if not isinstance(source_record, dict):
                raise ValidationError(f"{path}: missing-explicit-source proposal requires proposed_source_record")
            if source_record.get("source_id") != proposal["requested_source_id"]:
                raise ValidationError(f"{path}: proposed source record ID must equal requested_source_id")
        elif action == "REUSE_EXISTING_SOURCE":
            if not proposal["existing_source_id"]:
                raise ValidationError(f"{path}: reuse proposal requires existing_source_id")
        elif action == "CURATION_REQUIRED":
            if proposal["existing_source_id"] is not None or proposal["requested_source_id"] is not None:
                raise ValidationError(f"{path}: curation-only proposal must not assign source identity")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate noncanonical legacy source-registration proposals")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_manifest(manifest, schema)
    print(f"validated {len(manifest['proposals'])} legacy source-registration proposals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
