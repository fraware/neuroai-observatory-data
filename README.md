# NeuroAI Observatory Data

Public, versioned evidence records and release artifacts for the [NeuroAI Workbench](https://github.com/fraware/neuroai-workbench).

This repository provides the public data and verification interfaces used by the NeuroAI observatory. It is distinct from the Workbench software and from controlled research evidence that cannot be distributed publicly.

## What is here

- **Published observatory releases** with signed or digest-bound manifests and their public authorization records.
- **Machine-readable schemas** for sources, observations, entities, relationships, and publication lineage.
- **Source registries and public fixtures** supporting reproducible checks.
- **Historical patent research extracts** accompanied by explicit scientific and data-rights limitations. These are research materials, not canonical released estimates.

Data availability in Git is not itself proof of provenance, scientific acceptance, permitted redistribution, clinical validity, or authorization to publish further data.

## Repositories and documentation

| Resource | Purpose |
| --- | --- |
| [NeuroAI Workbench](https://github.com/fraware/neuroai-workbench) | Offline-first assessment software, validation, review, and monitoring |
| [Observatory release contract](docs/observatory-v2-release-contract.md) | Release contents, identity, and verification rules |
| [Landscape research contract](docs/landscape-research-contract.md) | Definitions and methodological safeguards for research outputs |
| [Public data-rights review](docs/patstat-public-extract-rights-containment-2026-09-18.md) | Containment and unresolved PATSTAT licensing questions |

## Repository layout

```text
releases/                 Published records and release manifests
schemas/                  Public machine-readable contracts
scripts/                  Verification utilities
fixtures/                 Synthetic or explicitly public reference inputs
docs/                     Public release, research and data-handling references
patent-evidence-extract/  Historical exploratory research; see limitations below
WORKBENCH_VERSION         Workbench compatibility reference
```

## Verify a release

The historical public governing release is located at `releases/data-v0.1.0-public-governing/`. Verify its recorded files with:

```bash
python scripts/verify_manifest.py \
  releases/data-v0.1.0-public-governing/records \
  releases/data-v0.1.0-public-governing/SHA256SUMS.txt
```

The graph-native Observatory v2 release format is documented in the [release contract](docs/observatory-v2-release-contract.md). For a candidate directory:

```bash
python scripts/verify_observatory_v2_release.py releases/<tag>
```

Where a release claims publication authority, require and verify its authorization and publication records:

```bash
python scripts/verify_observatory_v2_release.py releases/<tag> --require-published
```

Verification confirms file integrity and record consistency under the declared rules. It does **not** independently establish the accuracy of scientific conclusions or the legal right to redistribute a dataset.

## Scientific and data-rights limitations

The [historical patent extract](patent-evidence-extract/README.md) contains model-generated classifications and selected EPO/PATSTAT-derived information. It is a preliminary analysis of a specified English-abstract sampling frame—not a complete patent census or a human-validated reference standard. The original sampling and uncertainty methods remain under independent review.

**The exact rights applicable to the Autumn 2025 PATSTAT delivery and the public redistribution status of relevant fields have not been verified.** Files already visible in the public repository should not be assumed to have an affirmative redistribution clearance. See the [rights containment review](docs/patstat-public-extract-rights-containment-2026-09-18.md) for the file-level risk assessment.

Observatory product totals, classification performance, and population estimates need explicit definitions, independent evidence and competent human review. No GitHub check, published file, or automated release command substitutes for those requirements.

## Security and contributions

Do not open issues or pull requests containing participant or neural data, credentials, private reviewer material, protected source captures, or licensed content lacking redistribution clearance. Use [Workbench security guidance](https://github.com/fraware/neuroai-workbench/blob/main/SECURITY.md) for vulnerability reporting.

Propose data corrections with the affected public source, record identity, reason for correction, and verifiable provenance. Existing published records must preserve their historical lineage; a correction should be represented by a reviewable successor.
