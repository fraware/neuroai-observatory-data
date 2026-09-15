# ClinicalTrials.gov first-capture execution control

Status: **PRE-EXECUTION SOFTWARE CONTROL — noncanonical, non-authorizing.**

This control implements the software path required by issues #102/#103 after the current CT.gov onboarding-plan gate. It does not record a real network capture.

## Required gates

A production invocation requires all three of the following:

1. an exact onboarding package with status `NONCANONICAL_CT_GOV_MONITOR_ONBOARDING`;
2. an explicit local first-capture authorization packet satisfying `schemas/ctgov-first-capture-authorization.schema.json`;
3. both CLI `--allow-network` and `NEUROAI_LIVE_COLLECTION=1`.

The authorization packet must cover every approved draft onboarding plan exactly once with `AUTHORIZE_PRIMARY_CAPTURE` or `DEFER`. It is bound to:

- the exact onboarding manifest SHA-256;
- Workbench `854cc9d1c8e24a9e8ae8b21d871329bc3c24c118`;
- collector profile `CTGOV_FIRST_CAPTURE_V0_1`;
- the deterministic profile digest;
- exact draft monitor, Source, NCT, request and PRIMARY-route identities.

Fallback capture, quarantine approval, monitor-registry succession, Source publication, Trial/site creation, assessment mutation and canonical publication remain false.

## Fixed production profile

The executor derives its collector configuration from code. It does not accept caller-supplied transport/profile values for production execution.

The profile is deliberately narrow:

- GET only;
- `PinnedSocketHttpTransport`;
- `application/json` only;
- no redirects;
- 2 MiB response limit;
- decompression ratio at most 20;
- one capture attempt;
- bounded connect/read/total timeouts;
- deterministic configuration SHA-256 including the exact Workbench commit.

The collection request uses `onboarding_manifest_sha256`. A monitor-registry digest is invalid because the draft monitor has not entered a governing registry.

## Capture semantics

For each `AUTHORIZE_PRIMARY_CAPTURE` plan the executor:

1. refuses an operations root inside this repository;
2. materializes the exact Workbench collection request;
3. invokes the Workbench live authorization gate;
4. executes only `https://clinicaltrials.gov/api/v2/studies/{NCT}`;
5. keeps raw response bytes under the operations-root quarantine;
6. requires a persisted root quarantine record in `PENDING_HUMAN_APPROVAL`;
7. checks result/quarantine identity, digest, size and path consistency;
8. requires HTTP 200 and `application/json`;
9. parses the quarantined JSON through the Workbench ClinicalTrials.gov normalizer;
10. requires exact normalized NCT identity;
11. writes a sanitized receipt containing only IDs, digests, sizes, relative quarantine path and bounded status.

A capture whose bytes parse but identify another NCT is retained in quarantine and receives a blocked identity-mismatch receipt. It is not deleted, relabeled or approved.

A successful first capture is refused if the same onboarding-manifest/draft-monitor pair already has a successful receipt in the operations workspace.

## Explicit non-claims

A successful receipt means only that exact authorized public bytes were retrieved through the controlled collector, retained in quarantine and mechanically matched to the expected NCT identity.

It does not establish:

- substantive clinical truth;
- safety or effectiveness;
- quarantine approval;
- monitoring handoff;
- governing monitor creation;
- canonical Source admission;
- Trial or trial-site graph truth;
- assessment effect;
- G0/G2/G3 passage;
- publication authority.

Quarantine disposition and monitoring handoff remain separate human/governance transitions.

## Real execution

The repository contains only software and synthetic/fake-transport tests at this stage. A real first capture under #102/#103 must use a real authorization packet held outside public S2 and an operations root outside the repository. Its resulting operational/S3 evidence must be reviewed separately before any later handoff.
