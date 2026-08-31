# neuroai-observatory-data

Public canonical observatory data and repository-local deterministic curation/verification tooling for the NeuroAI Workbench programme (store S2; [ADR-0009](https://github.com/fraware/neuroai-workbench/blob/main/docs/adr/0009-canonical-data-and-evidence-stores.md)).

## Authority scope

Canonical authority in this repository belongs only to explicitly authorized, immutable versioned release artifacts under `releases/` together with their manifests and release descriptors.

The repository also contains deterministic scripts, tests, workflows, schemas, curation configuration, synthetic examples, and noncanonical analytical/operational projections needed to build, verify, monitor, or prepare those data releases. Those repository-local tools do not replace reusable Workbench/domain semantics in store S1 and do not become canonical merely because they are committed to `main`.

## Public canonical content

Authorized release sets may contain:

- published machine-readable observatory records permitted for public release;
- credential-free source registries and aliases;
- approved public evidence metadata and dispositions;
- adjudicated deltas permitted for publication;
- assessment dependency manifests and reopening decisions;
- release manifests, checksums, and release descriptors.

## Explicit exclusions

- No protected evidence, participant records, credentials, licensed captures, or private regulatory material.
- No generated Excel, Word, PDF, or dashboard products as master data (those are store S4).
- No normative v4.2 kernel resources or reusable Workbench implementation code (store S1).
- No claim that repository-local scripts, schemas, hashes, tests, or workflow success establish substantive observatory truth.

## Authority boundary

Checksum verification, schema validation, deterministic projections, tests, and signed release mechanics can confirm **artifact identity, internal consistency, and publication lineage** within their declared boundaries. They do **not** establish scientific truth, regulatory authorization, clinical value, system conformance, UNESCO endorsement, global completeness, or substantive assessment authority.

Missing or inaccessible public evidence is typed explicitly; it is never converted into automatic substantive failure by manifest or migration tooling alone.

## Layout

```text
schemas/                 JSON Schema for release descriptors and controlled record contracts
releases/                Authorized releases and explicitly noncanonical development candidates
fixtures/                Discovery mirrors and synthetic public examples; never protected production captures
curation/                Public curation policies, overlays, and proposal/provenance records
scripts/                  Deterministic validation, projection, monitoring, and release-support tooling
tests/                    Tests for repository-specific data/configuration semantics and invariants
docs/                     Data/release/operational documentation
supplemental_records/     Public supplemental records with explicit lineage/boundaries
WORKBENCH_VERSION        Compatible neuroai-workbench package line
```

## Releases

1. Place canonical public records under a versioned release directory (`releases/<tag>/records/` for authorized governing sets).
2. Run `python scripts/generate_manifest.py <release-root> releases/<tag>/SHA256SUMS.txt`.
3. Author or update `releases/<tag>/release-descriptor.json` against `schemas/release-descriptor.schema.json`.
4. Open a reviewed pull request; merge to `main`.
5. Complete the applicable release-authority process.
6. Create an immutable annotated tag and signed GitHub release per [docs/signed-release-policy.md](docs/signed-release-policy.md).

Committing a development candidate, schema, analytical projection, monitor registry proposal, or migration fixture does not authorize canonical publication.

### data-v0.1.0-public-governing

First authorized public governing release (`public-governing-v1`):

- `source_monitor_registry_v1.5.json` (224 sources)
- `canonical_observatory_release_v1.4.json`
- `canonical_live_refresh_release_v1.6.json`
- `adjudicated_delta_v1.6.json`
- `canonical_successor_snapshot_v1.7.json`
- `public_disposition_summary.json` (includes residual `AMB-003`)

Records live under `releases/data-v0.1.0-public-governing/records/` and selected records are mirrored under `fixtures/` for discovery. Verify:

```bash
python scripts/verify_manifest.py releases/data-v0.1.0-public-governing/records releases/data-v0.1.0-public-governing/SHA256SUMS.txt
```

## Observatory v2 foundation

The draft contracts under:

```text
schemas/observatory-v2-assertion.schema.json
schemas/observatory-v1-observation.schema.json
fixtures/v2-foundation/
docs/v1-to-v2-migration-spec.md
```

are **noncanonical design/test scaffolding**. They do not supersede `data-v0.1.0-public-governing` and carry no publication authority.

## Workbench coupling

Import and validation adapters in `fraware/neuroai-workbench` consume tagged releases from this repository. `WORKBENCH_VERSION` records the compatible package line. Specific operational workflows may pin an exact Workbench commit for reproducibility, while individual release descriptors may separately record the Workbench producer identity. These three concepts must not be conflated.

Publish tooling: `python scripts/publish_observatory_data.py --release-set public-governing-v1` (requires local `NEUROAI_OPS_WORKSPACE`).
