# Signed release and immutable tag policy

Public canonical data releases use immutable tags and signed GitHub releases so independent verifiers can pin artifact identity without trusting working-tree state.

## Tag naming

- Pattern: `data-vMAJOR.MINOR.PATCH[-PRERELEASE]`
- Example bootstrap tag: `data-v0.0.1-bootstrap`

## Release procedure

1. Merge the reviewed pull request to `main`.
2. Confirm `python scripts/verify_manifest.py <release-root> releases/<tag>/SHA256SUMS.txt` passes.
3. Confirm `releases/<tag>/release-descriptor.json` validates against `schemas/release-descriptor.schema.json`.
4. Create an annotated tag on the merge commit.
5. Publish a GitHub release for the tag with:
   - release descriptor JSON attached;
   - `SHA256SUMS.txt` attached;
   - notes listing withheld claims and predecessor tag when applicable.
6. Prefer signed tags and signed release attestations when repository plan and maintainer keys permit.

## Immutability

- Do not move, retag, or overwrite published `data-v*` tags.
- Errata require a successor tag, updated release descriptor, and explicit predecessor reference.
- Generated Excel, Word, PDF, and dashboard products remain outside this repository.

## Verification scope

Manifest verification confirms file identity for the declared release root. It does not validate substantive observatory claims, protected-evidence completeness, or workbench assessment outcomes.

## Workbench coupling

`WORKBENCH_VERSION` records the compatible `neuroai-workbench` package version for import adapters. Updating canonical record shapes may require a coordinated workbench release.
