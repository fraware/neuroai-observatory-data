# neuroai-observatory-data

Public canonical observatory data for the NeuroAI Workbench programme (store S2; [ADR-0009](https://github.com/fraware/neuroai-workbench/blob/main/docs/adr/0009-canonical-data-and-evidence-stores.md)).

## Scope

This repository holds **public canonical data only**:

- published machine-readable observatory records permitted for public release;
- credential-free source registries and aliases;
- disposition summaries approved for publication;
- assessment dependency manifests and reopening decisions;
- release manifests, checksums, release descriptors, and public publication-lineage records.

## Explicit exclusions

- No protected evidence, participant records, credentials, licensed captures, or private regulatory material.
- No generated Excel, Word, PDF, or dashboard products (those are store S4).
- No software, normative v4.2 kernel resources, or workbench code (store S1).

## Authority boundary

Checksum verification, schema validation, and signed release mechanics confirm **artifact identity and publication lineage**. They do **not** establish scientific truth, regulatory authorization, clinical value, system conformance, UNESCO endorsement, or substantive assessment authority.

Missing or inaccessible public evidence is typed explicitly; it is never converted into automatic failure by manifest tooling alone.

For Observatory v2, three states are deliberately separate:

```text
candidate != authorization != publication
```

A candidate descriptor remains permanently non-authoritative. Explicit authorization and publication are separate immutable governance records; no candidate boolean, schema pass, manifest digest, repository presence, or successful test independently confers publication authority.

## Layout

```text
schemas/                 JSON Schema for release and governance records
releases/                Versioned public release directories
fixtures/                Synthetic public examples only; never production captures
scripts/                 Deterministic manifest and release verification
scripts/verify_observatory_v2_release.py
                         Independent S2 verifier for graph-native Observatory v2 releases
docs/                    Release, branch-protection, and signed-publication policy
WORKBENCH_VERSION        Pinned compatible neuroai-workbench package version
```

## Observatory v2 graph-native release contract

The first graph-native release family uses this stable shape:

```text
releases/<tag>/
  descriptor.json
  manifest.json
  records/
    entities.jsonl
    sources.jsonl
    observations.jsonl
    assertions.jsonl
    events.jsonl
    relationships.jsonl
    candidates.jsonl
    reopening-decisions.jsonl
  migration/
    entity-predecessor-traces.jsonl
    preserved-organizations.jsonl
    source-predecessor-traces.jsonl
    predecessor-observation-evidence.jsonl
    event-predecessor-traces.jsonl
    candidate-predecessor-traces.jsonl
    v16-adjudication-state.json
    v17-successor-lineage.json
    residual-predecessor-state.json
    duplicate-container-proofs.json
    gate-a-descriptor.json
    gate-a-manifest.json
    gate-a-decision.json
  governance/
    authorizations/*.json
    publication.json
```

The 21 candidate files under `records/` and `migration/` are the immutable candidate surface. Governance records are deliberately outside that candidate manifest so explicit authorization never rewrites candidate bytes.

Candidate verification:

```bash
python scripts/verify_observatory_v2_release.py releases/<tag>
```

Require an exact active `AUTHORIZE` record plus matching publication record:

```bash
python scripts/verify_observatory_v2_release.py releases/<tag> --require-published
```

The verifier is standard-library-only and intentionally independent of `neuroai-workbench`. S1 produces the candidate; S2 recomputes its identities, validates the fixed file surface and graph classes, re-checks Gate-A lineage, and verifies publication binding independently.

See [docs/observatory-v2-release-contract.md](docs/observatory-v2-release-contract.md).

## Legacy/current governing releases

### data-v0.1.0-public-governing

First authorized public governing release (`public-governing-v1`):

- `source_monitor_registry_v1.5.json` (224 sources)
- `canonical_observatory_release_v1.4.json`
- `canonical_live_refresh_release_v1.6.json`
- `adjudicated_delta_v1.6.json`
- `canonical_successor_snapshot_v1.7.json`
- `public_disposition_summary.json` (includes residual `AMB-003`)

Records live under `releases/data-v0.1.0-public-governing/records/` and are mirrored under `fixtures/` for discovery. Verify:

```bash
python scripts/verify_manifest.py releases/data-v0.1.0-public-governing/records releases/data-v0.1.0-public-governing/SHA256SUMS.txt
```

The existing v2.3 development candidate remains a historical development projection and does not define the graph-native Observatory-v2 release contract.

## Workbench coupling

Import and validation adapters in `fraware/neuroai-workbench` consume tagged releases from this repository. The pinned compatible package line is recorded in `WORKBENCH_VERSION`; exact producer commit, runtime execution pin, graph schema generation, S2 predecessor commit, frozen predecessor inputs, and Gate-A proof identities are additionally bound by each Observatory-v2 candidate descriptor.
