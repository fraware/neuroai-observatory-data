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

## Layout

```text
schemas/                 JSON Schema for release descriptors and future record types
releases/                Release descriptors (metadata + manifest references)
fixtures/                Synthetic public examples only; never production captures
scripts/                 Deterministic SHA-256 manifest generation and verification
docs/                    Branch protection and signed-release policy
WORKBENCH_VERSION        Pinned compatible neuroai-workbench package version
```

## Releases

1. Place canonical public records under a versioned release directory.
2. Run `python scripts/generate_manifest.py <release-root> releases/<tag>/SHA256SUMS.txt`.
3. Author or update `releases/<tag>/release-descriptor.json` against `schemas/release-descriptor.schema.json`.
4. Open a reviewed pull request; merge to `main`.
5. Create an immutable annotated tag and signed GitHub release per [docs/signed-release-policy.md](docs/signed-release-policy.md).

## Workbench coupling

Import and validation adapters in `fraware/neuroai-workbench` consume tagged releases from this repository. The pinned workbench version is recorded in `WORKBENCH_VERSION`.
