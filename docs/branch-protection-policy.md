# Branch protection policy

This document records required GitHub controls for `fraware/neuroai-observatory-data`. Committed policy text does not activate controls; an administrator must apply them in GitHub.

## Target branch

- Default branch: `main`

## Required controls

1. Require pull requests for every change to `main`.
2. Require at least one approving review.
3. Require Code Owner review for paths listed in `CODEOWNERS`.
4. Dismiss stale approvals when new commits are pushed.
5. Require branches to be up to date before merge.
6. Require linear history.
7. Block force pushes and branch deletion on `main`.
8. Do not grant routine bypass authority.

## Release tags

- Protect tags matching `data-v*`.
- Tags are immutable once published; corrections require a new tag and successor release descriptor.
- Tag creation is limited to maintainers after reviewed merge to `main`.

## Authority boundary

Branch protection governs publication workflow integrity. It does not establish scientific truth, regulatory authorization, or substantive assessment authority.
