# Phase 4 production acquisition runbook

This runbook defines the operational sequence for executing the frozen Phase 4 Crossref/Europe PMC acquisition without weakening the request-identity, custody, resume, verification, rights, or scientific-authority boundaries implemented on `vnext-science-graph`.

It is an execution procedure, not evidence that an acquisition has occurred. No command in this document authorizes a public release or converts provider retrieval into NeuroAI relevance, scientific validity, canonical identity, or open-world completeness.

## Frozen execution target

The only executable Phase 4 compilation is `SCIENCE-QUERY-COMPILATION-V0.2`.

Expected deterministic plan identity:

- plan ID: `SCIENCE-QUERY-PLAN-A9B8B8999861882C4BC7`
- SHA-256: `a9b8b8999861882c4bc78b27f40f48e476f7cafbbb347b00a0a6cd897406db56`
- query units: 768
- Crossref query units: 384
- Europe PMC query units: 384

The historical v0.1 compilation remains reproducible control state and is not acquisition-eligible.

## Preconditions

Do not start a live provider acquisition until all of the following are true:

1. The exact branch/head intended for execution has passed the Phase 4 validator/compiler/test sequence in an approved environment. Hosted validation infrastructure is tracked in #48.
2. The acquisition output root is on durable external storage satisfying #49. It must not be inside the Git repository or on ephemeral session storage.
3. The operator has confirmed that automatic HTTP redirects are disabled. The production entrypoint enforces `FAIL_CLOSED_NO_AUTO_FOLLOW`.
4. The execution environment can reach only the intended public Crossref and Europe PMC interfaces without a proxy or middleware that silently rewrites the effective endpoint, request parameters, or User-Agent identity.
5. The operator has reviewed `science/acquisition-rights-decision-v0.1.md` and confirmed that it still applies to the exact frozen request fields. Raw Europe PMC responses remain `INTERNAL_CUSTODY_ONLY`, normalized Europe PMC record-level fields remain `PER_RECORD_OR_CASE_REVIEW`, and the mixed-provider package must retain the global release-ineligible state.
6. The durable output root has a documented retention/access policy and sufficient capacity. Capacity must be based on observed evidence or provider-supported estimates; overlapping query-unit denominators must not be summed as a corpus-size estimate.

## 1. Pin and record the code state

Record the repository commit that will execute the acquisition.

```bash
git rev-parse HEAD
git status --short
```

The working tree must contain no unreviewed modifications to the Phase 4 protocol, compilation, adapters, schemas, acquisition/verification scripts, source-universe contracts, runbook, or rights decision.

If the execution commit differs from the reviewed PR head, re-run the full validation sequence before continuing.

## 2. Reproduce the frozen query plan

Compile the plan to a path outside the repository:

```bash
python scripts/compile_science_queries.py \
  --output /path/outside/repository/science-query-plan-v0.2.json
```

Independently inspect the resulting identity:

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path('/path/outside/repository/science-query-plan-v0.2.json')
plan = json.loads(path.read_text(encoding='utf-8'))
print(plan['plan_id'])
print(plan['plan_sha256'])
print(plan['unit_count'])
print(plan['provider_counts'])
PY
```

Stop unless the values are exactly:

```text
SCIENCE-QUERY-PLAN-A9B8B8999861882C4BC7
a9b8b8999861882c4bc78b27f40f48e476f7cafbbb347b00a0a6cd897406db56
768
{'CROSSREF': 384, 'EUROPE_PMC': 384}
```

Do not edit and re-hash a plan in order to make it pass. The acquisition and verification layers reject a different internally consistent plan identity.

## 3. Validate the exact execution state

Use Python 3.12 with `jsonschema[format]==4.26.0`. The exact checkout must be clean and must equal the reviewed commit.

Run the workflow-equivalent sequence:

```bash
python scripts/validate_vnext_core.py
python -m unittest tests/test_vnext_core_contract.py -v
python scripts/validate_science_graph.py
python scripts/compile_science_queries.py \
  --output /path/outside/repository/science-query-plan-v0.2.json
python -m unittest \
  tests/test_science_graph_contract.py \
  tests/test_science_query_compilation.py \
  tests/test_science_acquisition.py \
  tests/test_science_response_custody.py \
  tests/test_science_acquisition_verification.py \
  tests/test_science_candidate_provenance.py \
  tests/test_science_retry_custody.py \
  tests/test_science_http_transport.py \
  tests/test_run_science_acquisition.py \
  tests/test_science_custody_preflight.py \
  tests/test_phase4_custody_terraform_contract.py \
  tests/test_phase4_validation_harness.py \
  -v
```

For an auditable exact-head evidence package, use the strict validation harness with a new empty evidence directory outside the repository:

```bash
EXPECTED_COMMIT="$(git rev-parse HEAD)"
VALIDATION_EVIDENCE_DIR="/path/outside/repository/phase4-validation-$EXPECTED_COMMIT"

python scripts/run_phase4_validation.py \
  --repo-root "$(git rev-parse --show-toplevel)" \
  --evidence-dir "$VALIDATION_EVIDENCE_DIR" \
  --expected-commit "$EXPECTED_COMMIT"
```

The harness fails closed if the checkout differs from the full expected SHA, the worktree is dirty, the runtime differs from the declared Python/dependency contract, the evidence directory is inside the repository or already populated, the frozen query-plan identity drifts, or any declared validation command fails. Preserve the resulting report and step stdout/stderr digests as validation evidence.

A validator/test failure is a stop condition. A hosted job that fails before any workflow step is instantiated is not a validator/test failure and is not a pass.

## 4. Verify durable custody before network retrieval

Let `CUSTODY_ROOT` be a durable path outside the repository. Confirm that it remains accessible across process/session restart before using it for provider retrieval.

At minimum, the environment must preserve:

- `raw/sha256/**` content-addressed response bytes;
- `units/<query_unit_id>/result.json` and candidate JSONL;
- incomplete-attempt archives;
- `run-manifest.json` and `dedup-report.json`;
- retry-custody, candidate, coverage, provenance, and verification products;
- `executions/<execution_id>/` snapshots.

Do not use `/tmp`, a disposable notebook/session directory, or a repository subdirectory for production custody.

The repository includes a provider-neutral storage-semantic preflight using the same atomic-write primitive as the acquisition engine. Run the preparation stage on the selected durable root:

```bash
python scripts/preflight_science_custody.py prepare \
  --custody-root "$CUSTODY_ROOT"
```

Record the returned `preflight_id`. The preparation stage writes synthetic evidence only; it is not a provider acquisition.

Terminate the preparation process. In a fresh process/session, and after any host/session restart required by the selected deployment design, verify persistence and exact bytes:

```bash
python scripts/preflight_science_custody.py verify-persistence \
  --custody-root "$CUSTODY_ROOT" \
  --preflight-id "$PREFLIGHT_ID"
```

The command verifies the content-addressed test payloads, manifest digest, byte counts, nested paths, and final state of a same-path `os.replace` operation. Its report explicitly does not claim that a restart happened; the operator must provide that execution-context evidence separately.

After a real backup/recovery point has been created, restore the synthetic preflight tree to a separate durable location and compare the restored paths and bytes:

```bash
python scripts/preflight_science_custody.py compare-restore \
  --primary-root "$CUSTODY_ROOT" \
  --restored-root "$RESTORED_CUSTODY_ROOT" \
  --preflight-id "$PREFLIGHT_ID"
```

Under the intended read-only verifier/auditor identity, capture the mutation-boundary report to an evidence location that is **outside** the read-only custody mount:

```bash
VERIFIER_EVIDENCE_DIR="/path/outside/custody/verifier-evidence"
mkdir -p "$VERIFIER_EVIDENCE_DIR"

python scripts/preflight_science_custody.py assert-read-only \
  --custody-root "$CUSTODY_ROOT" \
  --preflight-id "$PREFLIGHT_ID" \
  > "$VERIFIER_EVIDENCE_DIR/read-only-verification.json"
```

A successful report has status `READ_ONLY_MUTATION_BOUNDARY_VERIFIED` and records five independently blocked operation classes: create, existing-file write, truncate, rename, and delete. The command first revalidates the preflight manifest, executes all five probes, restores the original synthetic bytes when a misconfiguration permits a destructive probe and restoration remains possible, and revalidates the manifest before accepting the result. Any permitted mutation fails the command. Preserve the report, its SHA-256, and independent evidence identifying the verifier role/session that executed it. The report does not itself establish IAM provenance, administrator separation, backup immutability, or provider acquisition.

If the AWS reference deployment is selected, `infra/aws-phase4-custody/` provisions the intended Regional encrypted EFS and AWS Backup topology. Terraform configuration or successful provisioning is not itself #49 evidence; the exact storage preflight, restore comparison, identity test, and live recovery drill remain mandatory.

## 5. Execute a two-provider scoped pilot

The pilot verifies the complete production path against one deterministic query unit from each required provider while keeping the scope explicit.

Pilot query units:

- Crossref: `QUNIT-CROSSREF-4A10006D6D32E6E889D5`
- Europe PMC: `QUNIT-EUROPE_PMC-109422C08331E6C38F9D`

Both correspond to `QF-NEURAL-INTERFACE`, discovery term `brain-computer interface`, publication-date window 2015-01-01 through 2015-12-31.

Run only through the gated production entrypoint:

```bash
python scripts/run_science_acquisition.py \
  --plan /path/outside/repository/science-query-plan-v0.2.json \
  --output-dir "$CUSTODY_ROOT" \
  --query-unit-id QUNIT-CROSSREF-4A10006D6D32E6E889D5 \
  --query-unit-id QUNIT-EUROPE_PMC-109422C08331E6C38F9D
```

Do not substitute `scripts/acquire_science_candidates.py` as the production entrypoint. The gated runner is responsible for the no-auto-follow transport, strict retry-response custody, independent verification, persisted provenance verification, and verification envelope.

A successful two-unit pilot is still a scoped acquisition. `selected_is_full_plan` and `full_plan_complete` must remain false.

## 6. Inspect and independently re-verify the scoped pilot

Inspect, at minimum:

- `run-manifest.json`;
- `retry-custody-verification.json`;
- `candidate-provenance-verification.json`;
- `candidate-manifest.json`;
- `coverage-index.json`;
- `verification-envelope.json`;
- the two selected unit `result.json` files;
- all raw custody pointers referenced by those results.

Then independently rerun the verifiers against the same persisted state:

```bash
python scripts/verify_science_retry_custody.py \
  --plan /path/outside/repository/science-query-plan-v0.2.json \
  --run-dir "$CUSTODY_ROOT"

python scripts/verify_science_acquisition.py \
  --plan /path/outside/repository/science-query-plan-v0.2.json \
  --run-dir "$CUSTODY_ROOT"

python scripts/verify_science_candidate_provenance.py \
  --run-dir "$CUSTODY_ROOT"
```

The gated runner already invokes the relevant verification layers; these commands are an explicit operator-side reproduction check.

Stop on any digest mismatch, missing raw object, request/cursor mismatch, attempt-sequence mismatch, provider-total drift, incomplete query unit, provenance failure, or release-boundary mutation.

## 7. Perform interruption/recovery verification

Before expanding to the full plan, verify that the chosen durable environment preserves evidence through process interruption and restart.

The recovery check must establish that:

- raw objects already received remain at their recorded content-addressed paths;
- incomplete state is retained/auditable and is not promoted to COMPLETE;
- the next run archives incomplete attempts before a clean retry;
- already-COMPLETE results may be reused without issuing a new provider request;
- reuse is recorded as `REUSED_COMPLETE_RESULT`, never as a fresh acquisition;
- a new execution receives a distinct `execution_id` when invocation timing/evidence differs, even if the final `result_state_id` is unchanged;
- independent verification still succeeds after restart.

Record this evidence on #49 before a full-plan run.

## 8. Expand to the full frozen plan

Only after the scoped two-provider pilot and recovery check pass may the same durable custody root be expanded to the complete frozen plan:

```bash
python scripts/run_science_acquisition.py \
  --plan /path/outside/repository/science-query-plan-v0.2.json \
  --output-dir "$CUSTODY_ROOT"
```

Existing verified COMPLETE pilot units may be reused. The execution manifest must distinguish reused units from units retrieved during the full-plan invocation.

If any unit ends PARTIAL or FAILED, the run is not a complete frozen-plan acquisition. Resolve/retry the affected units through the same gated entrypoint; do not edit result state manually.

`full_plan_complete=true`, if eventually obtained and independently verified, means only that all 768 frozen query units reconciled to their provider-reported denominators. It does not mean the NeuroAI literature is complete in an open-world sense, and overlapping query-unit totals must not be summed into a global literature denominator.

## 9. Preserve the verified evidence package

For every execution, preserve the immutable `executions/<execution_id>/` snapshot and all referenced raw content-addressed objects. Record the execution ID, result-state ID, plan identity, verification-envelope ID, and custody location in the operational audit record.

Do not mutate raw objects or historical execution snapshots to repair a later inconsistency. A corrected acquisition is a new execution/evidence state.

## 10. Apply the artifact-level rights decision before any public release

The engineering/data-governance decision is recorded in `science/acquisition-rights-decision-v0.1.md`. Technical verification and internal durable custody do not expand those permissions.

For the frozen v0.2 plan:

- minimized Crossref raw responses and normalized `DOI,title,published` derivatives are `PUBLIC_REDISTRIBUTION_PERMITTED` under the conditions in the rights decision;
- raw Europe PMC `lite` response bytes are `INTERNAL_CUSTODY_ONLY`;
- normalized Europe PMC record-level fields are `PER_RECORD_OR_CASE_REVIEW`;
- aggregate project-generated verification facts may be public only when they contain no provider-derived fields whose classification is more restrictive;
- immutable mixed-provider execution snapshots remain internal custody objects.

The mixed-provider acquisition must therefore continue to report `NOT_RELEASE_ELIGIBLE_UNTIL_DURABLE_CUSTODY_AND_RIGHTS_REVIEW`. Do not change that flag merely because one provider's minimized metadata is cleared.

A later Crossref-only public derivative may be considered only after #49 is satisfied and the derivative is independently verified to contain exclusively the fields/classes cleared by the rights decision. Such a derivative remains a discovery-candidate artifact, not a relevance-adjudicated or canonical scientific dataset.

Any release including Europe PMC record-level material requires the additional provider/legal/source-specific authority defined by the rights decision.

## Stop conditions

Stop the production procedure immediately if any of the following occurs:

- code or plan identity differs from the reviewed frozen state;
- acquisition output resolves inside the repository or to ephemeral storage;
- the transport follows redirects or changes the frozen client/request identity;
- any received HTTP response cannot be placed in content-addressed custody;
- a query denominator changes during traversal;
- cursor progression or provider response structure violates the frozen contract;
- candidate normalization or raw provenance cannot be independently reproduced;
- retry-attempt evidence is missing, reordered, or fails request/cursor binding;
- the storage preflight, post-restart persistence check, restore comparison, or read-only identity check fails;
- a scoped run is being represented as full-plan complete;
- overlapping query totals are being aggregated as a global denominator;
- a release is proposed for an artifact class that is not explicitly `PUBLIC_REDISTRIBUTION_PERMITTED` under the current rights decision;
- the rights decision no longer matches the exact provider fields, access method, or terms in force.
