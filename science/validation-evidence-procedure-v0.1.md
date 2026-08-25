# Phase 4 validation evidence procedure v0.1

**Status:** operational validation procedure; no passing validation is asserted by this document  
**Scope:** exact-head Phase 4 core/science validation and evidence capture  
**Related controls:** #48, PR #45, `.github/workflows/vnext-core-schema.yml`, `.github/workflows/vnext-science-graph.yml`

This procedure defines a single fail-closed way to collect auditable validation evidence when an approved execution environment is available. It exists to prevent three forms of ambiguity: validating a pull-request merge ref instead of the actual head commit, silently using the wrong Python or schema-validator version, and reporting a command sequence without retaining the exact outputs that support the claim.

## 1. Exact execution contract

The validation environment must satisfy all of the following:

- the checked-out commit is the exact 40-character commit SHA being evaluated;
- the working tree is clean before validation starts;
- Python major/minor is exactly 3.12;
- `jsonschema` is exactly 4.26.0;
- the frozen science query plan reproduces:
  - `SCIENCE-QUERY-PLAN-A9B8B8999861882C4BC7`;
  - SHA-256 `a9b8b8999861882c4bc78b27f40f48e476f7cafbbb347b00a0a6cd897406db56`;
  - 768 query units;
  - 384 Crossref and 384 Europe PMC units;
- validation evidence is written outside the repository checkout;
- a failed command or environment mismatch produces a failed validation report, not a partial pass.

The pull-request workflows explicitly check out the pull-request head SHA and assert the resulting `HEAD` before any validator or test command runs. This avoids treating the platform-generated merge commit as the reviewed source commit.

## 2. Strict evidence collector

`scripts/run_phase4_validation.py` executes the exact core/science sequence and writes a content-addressed evidence package.

From a clean checkout of the commit being evaluated:

```bash
EXPECTED_COMMIT="$(git rev-parse HEAD)"
EVIDENCE_DIR="/path/outside/repository/phase4-validation-${EXPECTED_COMMIT}"

python scripts/run_phase4_validation.py \
  --expected-commit "$EXPECTED_COMMIT" \
  --evidence-dir "$EVIDENCE_DIR"
```

The evidence directory must be empty and must resolve outside the repository. The collector refuses abbreviated commit IDs, a dirty worktree, an incorrect runtime, or an in-repository evidence path.

The collector executes, in order:

1. the vNext core validator;
2. the vNext core adversarial contract tests;
3. the science-graph validator;
4. deterministic compilation of the frozen v0.2 provider query plan;
5. the complete Phase 4 science test module set, including the custody-preflight and validation-harness regression tests.

On success it writes `phase4-validation-report.json` plus byte-preserved stdout/stderr logs for every command. On failure it still writes a failed report when possible and preserves the failed step output or exception traceback.

## 3. Evidence semantics

The validation report records:

- expected and observed commit SHA;
- clean-worktree assertion;
- Python executable and version;
- `jsonschema` version;
- command vectors in execution order;
- start/completion times and durations;
- exit codes;
- byte counts and SHA-256 digests for stdout/stderr logs;
- unit-test counts when the standard library test runner reports them;
- the reproduced frozen query-plan identity;
- a content-derived validation ID and report SHA-256.

The report hash is an integrity identifier, not an identity signature. It establishes that the retained report content has a stable digest; it does not authenticate the machine or operator that produced it.

## 4. Infrastructure validation remains separate

The Python evidence collector does not claim to validate Terraform. If the AWS custody reference is the selected deployment path, execute the separately pinned infrastructure sequence from the exact same reviewed commit:

```bash
terraform fmt -check -recursive infra/aws-phase4-custody
terraform -chdir=infra/aws-phase4-custody init -backend=false -input=false
terraform -chdir=infra/aws-phase4-custody validate
```

The Phase 4 workflow pins Terraform 1.15.8. `infra/aws-phase4-custody/versions.tf` pins both Terraform 1.15.8 and the AWS provider 6.60.0 so provider/tool drift cannot silently satisfy the reference validation gate.

A successful `validate` is structural configuration evidence only. It is not an AWS plan, apply, storage preflight, backup/restore result, or proof that any cloud resource exists.

## 5. #48 acceptance use

Issue #48 may use either the hosted workflow or another explicitly approved execution environment, but the evidence must correspond to the exact current PR head and preserve auditable command-level results. The strict collector is intended to make an alternate execution environment equivalent at the command/evidence layer; it does not itself designate an environment as approved.

A prior pass on an older commit cannot satisfy a newer head. A run under Python 3.13 cannot be relabeled as a Python 3.12 pass. A pre-runner workflow failure with no steps cannot be relabeled as a validator/test failure or pass.

## 6. Authority boundary

Passing this procedure would establish only that the declared software contracts and tests executed successfully for one exact commit in one declared environment. It does not establish:

- a real Crossref or Europe PMC acquisition;
- provider completeness beyond the frozen query contract;
- NeuroAI relevance or scientific validity of discovered records;
- canonical identity or canonical merge authority;
- durable production custody;
- backup/restore success;
- public release eligibility;
- open-world literature completeness.

Those claims remain governed by the separate acquisition, custody, provenance, adjudication, and rights controls.
