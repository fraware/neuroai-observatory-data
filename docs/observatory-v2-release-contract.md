# Observatory v2 S2 release contract

Status: **graph-native release contract with transitive Gate-A verification**.

## Purpose

Store S2 is the public data authority for the NeuroAI Observatory. Store S1 (`neuroai-workbench`) produces graph-native migration artifacts after mechanical Gate-A completion; S2 independently verifies those bytes and records explicit publication lineage.

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

The immutable candidate manifest contains exactly 25 files.

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

Twelve governed predecessor/native-candidate files:

```text
migration/entity-predecessor-traces.jsonl
migration/preserved-organizations.jsonl
migration/source-predecessor-traces.jsonl
migration/predecessor-observation-evidence.jsonl
migration/event-predecessor-traces.jsonl
migration/candidate-predecessor-traces.jsonl
migration/identity-resolution-history.jsonl
migration/regional-expansion-history.jsonl
migration/v16-adjudication-state.json
migration/v17-successor-lineage.json
migration/residual-predecessor-state.json
migration/duplicate-container-proofs.json
```

Five transitive lineage files:

```text
migration/gate-a-descriptor.json
migration/gate-a-manifest.json
migration/gate-a-decision.json
migration/native-candidate-descriptor.json
migration/native-candidate-manifest.json
```

Empty graph classes use zero-byte JSONL files. This keeps the public object-file contract stable as native graph coverage expands.

The verifier rejects missing files, extra manifested files, duplicate paths, absolute paths, parent traversal, paths resolving outside the release root, file-digest substitution, malformed JSONL records, records whose `object_class` does not match the file, or non-empty files for graph classes that the bound native candidate did not materialize.

## Transitive identity hierarchy

The S2 candidate does not trust its own manifest as sufficient evidence. It verifies the complete identity chain:

```text
S2 candidate manifest
  -> copied Gate-A decision
  -> copied Gate-A manifest + descriptor
  -> copied native-candidate manifest + descriptor
  -> exact copied native graph/traces/history files
  -> exact copied root governed-preservation files
```

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
- native-candidate manifest raw-file identity and canonical manifest identity.

The candidate ID is derived from the candidate content digest.

The distinction between raw-file SHA-256 and canonical-JSON identity is deliberate. The Gate-A package records both for the native-candidate subpackage; S2 recomputes both and does not substitute one for the other.

## Preservation completeness

The first migration candidate preserves two history surfaces that are not native graph objects:

```text
identity-resolution-history.jsonl   26 records
regional-expansion-history.jsonl    13 records
```

These 39 records are part of the governed predecessor state and are digest-bound through the native-candidate manifest. Omitting them or changing them while recomputing only the top-level S2 candidate manifest fails closed.

Likewise, the root Gate-A manifest independently binds the v1.6 adjudication state, v1.7 successor lineage, residual predecessor state, and duplicate-container proofs. Recomputing the top-level S2 manifest cannot launder a substitution in any of these files.

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

It additionally verifies that the copied Gate-A manifest binds the copied native-candidate subpackage and root preserved files byte-for-byte.

A Gate-A package without the separate PASS decision is insufficient for S2 publication.

## Deterministic candidate builder

The repository provides:

```bash
python scripts/build_observatory_v2_candidate.py \
  --gate-a-output <executed-gate-a-output> \
  --output releases/<tag> \
  --release-tag <tag> \
  --predecessor-release-tag <published-predecessor-tag>
```

The builder copies the exact bound Gate-A/native-candidate bytes, creates zero-byte files for currently absent graph classes, constructs the content-derived S2 candidate identity, and then invokes the independent S2 verifier. It never creates authorization or publication records.

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

The adversarial contract tests explicitly modify graph records, history sidecars, root preserved state, and the native-candidate manifest and then recompute the top-level S2 candidate identities. Those substitutions must still fail through the transitive lineage chain.

## Schema files

Declarative contracts:

```text
schemas/observatory-v2-release-descriptor.schema.json
schemas/observatory-v2-release-manifest.schema.json
schemas/observatory-v2-authorization.schema.json
schemas/observatory-v2-publication.schema.json
```

The executable verifier remains the controlling cross-file integrity check because JSON Schema alone cannot recompute hashes, inspect filesystem path resolution, verify transitive Gate-A/native-candidate digest chains, or determine active authorization state.

## S3 exclusion

No protected S3 capture, credential, private regulatory material, participant data, or licensed evidence byte is part of the candidate or governance file surface. Public S2 records may contain public source references and bounded provenance state only.

## Authority boundary

Successful candidate verification establishes artifact and migration-lineage integrity. Published-release verification additionally establishes publication lineage. Neither establishes scientific truth, clinical validity, regulatory authorization, system conformance, institutional endorsement, UNESCO endorsement, or global completeness.
