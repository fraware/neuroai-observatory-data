# Observatory v2 S2 release contract

Status: **contract and independent verifier; no production v2 candidate is committed by this change**.

## Purpose

Store S2 is the public data authority for the NeuroAI Observatory. Store S1 (`neuroai-workbench`) produces graph-native candidate bytes after mechanical Gate-A completion; S2 independently verifies those bytes and records explicit publication lineage.

The controlling lifecycle invariant is:

```text
candidate != authorization != publication
```

Candidate integrity proves identity. Authorization records one designated operator decision over one exact candidate. Publication binds one active authorization to one explicit public publication event/evidence record.

## Candidate immutability

A candidate descriptor and manifest always retain:

```text
state = NONCANONICAL_CANDIDATE
canonical_publication_state = NOT_AUTHORIZED
release_authorized = false
published = false
```

These fields are never flipped in place. Publication status is derived only from separate governance records.

## Exact candidate surface

The immutable candidate manifest contains exactly 21 files.

Eight stable graph-class files:

```text
records/entities.jsonl
records/sources.jsonl
records/observations.jsonl
records/assertions.jsonl
records/events.jsonl
records/relationships.jsonl
records/candidates.jsonl
records/reopening-decisions.jsonl
```

Ten governed predecessor-state files:

```text
migration/entity-predecessor-traces.jsonl
migration/preserved-organizations.jsonl
migration/source-predecessor-traces.jsonl
migration/predecessor-observation-evidence.jsonl
migration/event-predecessor-traces.jsonl
migration/candidate-predecessor-traces.jsonl
migration/v16-adjudication-state.json
migration/v17-successor-lineage.json
migration/residual-predecessor-state.json
migration/duplicate-container-proofs.json
```

Three Gate-A lineage files:

```text
migration/gate-a-descriptor.json
migration/gate-a-manifest.json
migration/gate-a-decision.json
```

Empty graph classes use zero-byte JSONL files. This keeps the public object-file contract stable as native graph coverage expands.

The verifier rejects missing files, extra manifested files, duplicate paths, absolute paths, parent traversal, paths resolving outside the release root, file-digest substitution, malformed JSONL records, or records whose `object_class` does not match the file.

## Identity hierarchy

The candidate binds independent identity dimensions rather than collapsing them:

- S2 release tag;
- candidate content digest;
- candidate manifest digest;
- candidate descriptor digest;
- Workbench compatibility package line;
- exact Workbench producer commit;
- exact runtime execution pin;
- graph schema generation;
- S2 predecessor release tag and exact commit;
- seven frozen predecessor input SHA-256 identities;
- corrected field-proof digest;
- Gate-A package manifest and descriptor identities;
- Gate-A mechanical-decision identity;
- native-candidate manifest identity.

The candidate ID is derived from the candidate content digest.

## Gate-A requirement

S2 admission requires the separate mechanical decision:

```text
PASS_REPRESENTATIONAL_MIGRATION_MECHANICALLY_COMPLETE
```

The independent verifier checks that this decision:

- is content-addressed;
- binds the copied Gate-A descriptor and manifest;
- records `gate_a_complete=true`;
- records `release_authorized=false`;
- records `representational_scope_complete=true`;
- records `native_v2_materialization_complete=false`;
- binds the same producer commit, runtime pin, S2 predecessor commit, and graph schema generation;
- binds the field-proof identity used by the S2 descriptor.

A Gate-A package without the separate PASS decision is insufficient for S2 candidate publication.

## Explicit operator authorization

Authorization records live under:

```text
governance/authorizations/*.json
```

Each record binds the exact candidate reference and records one decision:

```text
AUTHORIZE
WITHHOLD
```

The current designated operator key is `fraware`. Supersession is permitted only over the same exact candidate. One candidate may have at most one active authorization. Supersession cycles or multiple superseders fail verification.

An authorization is not publication.

## Publication

Publication is one separate record:

```text
governance/publication.json
```

A valid publication requires:

- an otherwise valid candidate;
- exactly one active `AUTHORIZE` record;
- exact authorization ID and digest binding;
- exact candidate-reference equality;
- non-empty `public-ref:` publication evidence;
- a SHA-256 publication-evidence digest;
- `automatic_publication_performed=false`.

Published candidate bytes and their authorization are immutable in place. Corrections require a successor release.

## Independent verification

Candidate integrity:

```bash
python scripts/verify_observatory_v2_release.py releases/<tag>
```

Published-release integrity:

```bash
python scripts/verify_observatory_v2_release.py releases/<tag> --require-published
```

The verifier is pure Python standard library. It intentionally does not import `neuroai-workbench`, so S2 recomputes release identity independently from S1.

## Schema files

Declarative contracts:

```text
schemas/observatory-v2-release-descriptor.schema.json
schemas/observatory-v2-release-manifest.schema.json
schemas/observatory-v2-authorization.schema.json
schemas/observatory-v2-publication.schema.json
```

The executable verifier remains the controlling cross-file integrity check because JSON Schema alone cannot recompute hashes, inspect filesystem path resolution, verify Gate-A digest chains, or determine active authorization state.

## S3 exclusion

No protected S3 capture, credential, private regulatory material, participant data, or licensed evidence byte is part of the candidate or governance file surface. Public S2 records may contain public source references and bounded provenance state only.

## Authority boundary

Successful verification establishes artifact identity and publication lineage. It does not establish scientific truth, clinical validity, regulatory authorization, system conformance, institutional endorsement, UNESCO endorsement, or global completeness.
