# Phase 4 durable acquisition custody architecture v0.1

**Status:** provisioning specification; no production custody environment is asserted by this document  
**Scope:** frozen Phase 4 Crossref/Europe PMC acquisition  
**Related controls:** #48 validation infrastructure, #49 durable custody, `science/production-acquisition-runbook.md`, `science/acquisition-rights-decision-v0.1.md`

This document translates the Phase 4 custody invariants into deployable storage and execution requirements. It is intentionally provider-neutral. A cloud vendor, region, retention period, and operator identity must be selected and recorded before #49 can close.

## 1. Required execution/storage separation

The production topology must contain two distinct roots:

1. **Repository checkout / executable code root** — may be ephemeral and reproducible from the reviewed commit.
2. **Custody root** — persistent storage whose lifetime is independent of the process, shell, notebook, CI job, or compute instance executing the acquisition.

The custody root must never resolve inside the Git repository. Production raw provider responses must never be committed to Git.

A recommended deployment shape is:

```text
reviewed repository commit
        |
        v
short-lived acquisition host/process
        |
        +---- outbound HTTPS ----> Crossref / Europe PMC
        |
        v
mounted durable POSIX custody filesystem
        |
        +---- raw/sha256/**
        +---- units/**
        +---- executions/**
        +---- run-manifest.json
        +---- verification products
        |
        v
independent backup/versioning layer
```

The mounted custody filesystem should normally be an encrypted persistent block/filesystem service with documented durability, not an ephemeral container layer. Direct object-store FUSE mounts are acceptable only after their rename, read-after-write, metadata, and restart semantics have been demonstrated to satisfy the acquisition code's filesystem assumptions.

## 2. Filesystem semantics required by the current implementation

The acquisition implementation uses ordinary `Path` operations, content-addressed files, and same-directory temporary files followed by `os.replace`. The selected custody filesystem must therefore provide:

- stable paths across process restart;
- same-filesystem atomic replacement semantics for temporary-to-final renames;
- read-after-write consistency for files and directory entries;
- reliable file length and byte-for-byte reads immediately after write;
- no transparent mutation, transcoding, compression, line-ending conversion, or content deduplication that changes returned bytes;
- preservation of filenames containing SHA-256 digests and long execution identifiers;
- enough inode/object capacity for many small manifest files plus raw response objects;
- correct behavior for concurrent read verification while one acquisition writer is active.

The production procedure should use a **single acquisition writer** per custody root. Independent verifiers may read concurrently, but two acquisition processes must not write the same result state unless a separate concurrency protocol is introduced and reviewed.

## 3. Raw object integrity model

Every received HTTP response body is retained under a content-addressed path of the form:

```text
raw/sha256/<first-two-hex>/<sha256>.json
```

The storage layer must guarantee that:

- an existing digest path cannot be silently replaced with different bytes;
- a verifier can read the exact stored bytes and recompute the recorded SHA-256;
- raw objects survive acquisition-process termination and later host/session restart;
- backup/restore preserves filenames and exact byte content;
- administrative repair does not rewrite raw objects in place.

If a digest-path collision check detects different bytes at an existing content-addressed path, the acquisition must stop. The operator must investigate the storage layer; the conflicting object must not be overwritten to make verification pass.

## 4. Recommended persistence tiers

A compliant implementation should use two durability tiers:

### Tier A — primary custody filesystem

Purpose: active acquisition, resume, and verification.

Required properties:

- encrypted at rest;
- persistent independently of compute lifecycle;
- mounted at a fixed documented path;
- strong filesystem semantics described above;
- restricted write permissions;
- automated snapshot/backup support;
- monitoring for capacity exhaustion and I/O errors.

Examples of suitable classes, subject to provider-specific validation, include persistent encrypted block volumes or managed POSIX filesystems. The architecture does not require a specific cloud provider.

### Tier B — independent backup/versioning layer

Purpose: protect the evidence package from operator error, primary-volume loss, or accidental deletion.

Required properties:

- separate failure domain from the primary execution host;
- versioning or immutable snapshots where available;
- checksum-preserving backup and restore;
- restricted deletion privileges;
- retention policy at least as long as the Phase 4 audit requirement.

A backup is not a substitute for the active custody filesystem. The acquisition code must still operate on storage satisfying the current POSIX-path assumptions.

## 5. Access-control model

Define at least three logical roles:

1. **Acquisition writer** — may create/update active custody state and raw objects through the reviewed acquisition process.
2. **Verifier/auditor** — read-only access to all custody artifacts and snapshots; no mutation permission.
3. **Custody administrator** — infrastructure-level operations such as snapshot/restore and access policy; should not be the normal acquisition identity.

Recommended controls:

- least-privilege identities rather than shared credentials;
- MFA/strong authentication for administrative access where supported;
- deletion of raw objects and immutable execution snapshots restricted to a narrow administrative role;
- audit logging for mount/volume configuration and destructive operations;
- no provider credentials embedded in the repository or custody artifacts; the frozen v0.2 public API path requires none.

## 6. Retention and deletion policy

Before production retrieval, record:

- retention period for raw response custody;
- retention period for execution snapshots and verification products;
- backup frequency;
- snapshot/version retention;
- deletion authority;
- procedure for a rights/legal hold;
- secure-destruction procedure when retention expires.

The default engineering posture should be to retain raw custody at least through scientific adjudication and any public-release review derived from that acquisition. A specific legal or institutional retention period is not asserted here.

## 7. Capacity planning

Do not estimate total storage by adding overlapping query-unit provider denominators. Those denominators are not a deduplicated corpus size.

Capacity must be sized from either:

- a provider-supported response-size/corpus estimate applicable to the frozen queries; or
- the exact two-provider scoped pilot defined in the production runbook.

After the pilot, record at minimum:

- raw bytes received by provider;
- number of HTTP response objects;
- normalized candidate bytes;
- manifest/verification overhead;
- peak active working-space usage;
- observed amplification from execution snapshots and backups.

Use those observed values to construct a conservative full-plan storage bound with an explicit safety margin. The bound remains an operational estimate, not a literature-count claim.

## 8. Preflight acceptance test

Before any live provider pilot, perform a storage-only preflight on the selected custody root:

1. create a synthetic byte payload;
2. write it through the same atomic-write path used by the acquisition implementation;
3. terminate the writing process after the write completes;
4. start a fresh process/session and confirm the file remains present;
5. recompute SHA-256 and byte count;
6. create an execution-style directory tree and verify rename/replacement behavior;
7. snapshot/backup the custody root;
8. restore to a separate verification location;
9. confirm all test bytes, paths, and hashes are identical;
10. verify that the read-only auditor identity cannot mutate the restored or primary evidence.

Destroy only the synthetic preflight artifacts after evidence has been recorded.

## 9. Acquisition interruption/restart drill

The live two-provider pilot must include the recovery test already required by the production runbook and #49.

The drill must demonstrate, on the chosen durable store, that:

- responses received before termination remain in `raw/sha256/**`;
- incomplete unit state is not promoted to COMPLETE;
- restart archives incomplete prior state before clean retry;
- previously COMPLETE units can be reused without a provider request;
- reuse is recorded as `REUSED_COMPLETE_RESULT`;
- a new invocation receives its own execution identity when the execution evidence differs;
- all independent custody/provenance verifiers still pass after restart;
- the immutable execution snapshot and referenced raw objects remain readable after the acquisition host/process is destroyed and recreated.

The drill must not use production release eligibility as its success criterion. Technical recovery and public release authority are separate controls.

## 10. Rights-aware storage boundary

`science/acquisition-rights-decision-v0.1.md` currently classifies:

- minimized Crossref raw/normalized metadata as `PUBLIC_REDISTRIBUTION_PERMITTED` under stated conditions;
- raw Europe PMC responses as `INTERNAL_CUSTODY_ONLY`;
- normalized Europe PMC record-level fields as `PER_RECORD_OR_CASE_REVIEW`;
- mixed-provider immutable execution snapshots as internal custody objects.

Therefore the primary and backup custody systems must be able to restrict Europe PMC raw/record-level material even if a later Crossref-only derivative is published elsewhere. Do not solve release packaging by making the entire custody root public.

## 11. Required operational record

Before closing #49, record the following values in an issue comment or dedicated deployment record:

```text
execution commit:
cloud/on-prem provider:
region / physical location:
primary custody storage class:
primary custody path / volume identifier:
backup/versioning class:
encryption-at-rest state:
acquisition writer identity:
read-only verifier identity:
custody administrator identity:
retention policy:
backup frequency:
capacity allocated:
preflight evidence location:
interruption/restart drill execution ID(s):
post-restart verification envelope ID:
```

Do not place secrets, access tokens, private keys, or provider credentials in that record.

## 12. #49 closure criterion

Issue #49 may close only after a real environment—not this design document alone—demonstrates all of the following:

1. custody storage persists independently of the execution host/session;
2. raw content-addressed response bytes survive interruption/restart;
3. filesystem semantics satisfy the current implementation's atomic-write and verification assumptions;
4. a backup/restore check preserves exact bytes and paths;
5. access controls separate writer, verifier, and administrative capabilities;
6. the two-provider scoped pilot and recovery drill complete with independently verifiable evidence;
7. the resulting mixed-provider package remains release-ineligible and rights-restricted as required.

Until those conditions are demonstrated, #49 remains an open production-acquisition blocker.
