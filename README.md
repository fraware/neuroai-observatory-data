# neuroai-observatory-data

Public canonical observatory data for the NeuroAI Workbench programme (store S2; [ADR-0009](https://github.com/fraware/neuroai-workbench/blob/main/docs/adr/0009-canonical-data-and-evidence-stores.md)).

## Scope

This repository holds **public canonical data only**:

- published machine-readable observatory records permitted for public release;
- credential-free source registries and aliases;
- disposition summaries approved for publication;
- assessment dependency manifests and reopening decisions;
- release manifests, checksums, and release descriptors.

## Explicit exclusions

- No protected evidence, participant records, credentials, licensed captures, or private regulatory material.
- No generated Excel, Word, PDF, or dashboard products (those are store S4).
- No software, normative v4.2 kernel resources, or workbench code (store S1).

## Authority boundary

Checksum verification, schema validation, and signed release mechanics confirm **artifact identity and publication lineage**. They do **not** establish scientific truth, regulatory authorization, clinical value, system conformance, UNESCO endorsement, or substantive assessment authority.

Missing or inaccessible public evidence is typed explicitly; it is never converted into automatic failure by manifest tooling alone.

## vNext intelligence graph

The vNext programme evolves the observatory from an organization-centric corpus into a source-controlled **entity–event–evidence graph** spanning science, clinical and regulatory development, public funding, patents/IP, capital, and neural-data infrastructure.

The architecture is governed by [ADR 0001](docs/adr/0001-vnext-knowledge-graph-architecture.md). Its machine-readable vocabulary skeleton is in [`ontology/vocabulary-v0.1.json`](ontology/vocabulary-v0.1.json), and the initial migration boundaries are recorded in [vNext migration non-goals](docs/migration/vnext-non-goals.md).

The architecture change does not mutate production data or authorize a new governing release. Existing releases remain immutable predecessors.

## Layout

```text
schemas/                 JSON Schema for release descriptors and canonical record types
ontology/                Versioned vNext controlled vocabulary and interoperability mappings
releases/                Release descriptors, records, manifests, and verification material
fixtures/                Synthetic public examples only; never production captures
curation/                Controlled curation and transition records
supplemental_records/    Public supplemental records outside governing release sets
scripts/                 Deterministic build, analysis, SHA-256 manifest, and verification tooling
docs/                    Architecture decisions, migration constraints, governance, and release policy
tests/                   Deterministic and adversarial validation
WORKBENCH_VERSION        Pinned compatible neuroai-workbench package version
```

## Releases

1. Place canonical public records under a versioned release directory (`releases/<tag>/records/` for authorized governing sets).
2. Run `python scripts/generate_manifest.py <release-root> releases/<tag>/SHA256SUMS.txt`.
3. Author or update `releases/<tag>/release-descriptor.json` against `schemas/release-descriptor.schema.json`.
4. Open a reviewed pull request; merge to `main`.
5. Create an immutable annotated tag and signed GitHub release per [docs/signed-release-policy.md](docs/signed-release-policy.md).

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

## Workbench coupling

Import and validation adapters in `fraware/neuroai-workbench` consume tagged releases from this repository. The pinned workbench version is recorded in `WORKBENCH_VERSION`. Publish tooling: `python scripts/publish_observatory_data.py --release-set public-governing-v1` (requires local `NEUROAI_OPS_WORKSPACE`).
