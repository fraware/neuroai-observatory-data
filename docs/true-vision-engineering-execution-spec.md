# NeuroAI Observatory True-Vision Engineering Execution Specification

Status: **ACTIVE ENGINEERING EXECUTION SPECIFICATION — living control document, non-authorizing.**

Version: **v0.1**

Initial repository baseline for this version: `fraware/neuroai-observatory-data@9cd32e616d6bf1aebd85bab6c6564ca777117205`

Companion Workbench baseline observed during authoring: `fraware/neuroai-workbench@854cc9d1c8e24a9e8ae8b21d871329bc3c24c118`

Last substantive status snapshot in this version: **2026-09-13**

---

## 1. Purpose

This document is the engineering execution control for completing the NeuroAI Landscape Observatory programme.

It exists because the programme spans two repositories, multiple evidence stores, human governance events, statistical evaluation, licensed-data boundaries, scheduled operations, public release mechanics, and exact-system assessment. Individual PRs and issue threads are necessary implementation records, but they are not a substitute for one stable end-to-end execution specification.

Engineers SHOULD start here when resuming programme work. This document defines:

- the target end state;
- the store and authority boundaries that MUST remain invariant;
- the dependency graph from the current PRE-G2 state through G12;
- exact acceptance conditions for each gate;
- the real-world evidence events that code alone cannot manufacture;
- the artifacts and reviews required at each stage;
- rules for PRs, successor state, observability, and evidence retention;
- the distinction between software readiness, execution evidence, human disposition, scientific adequacy, authorization, and publication;
- the final acceptance conditions for saying that the first complete true-vision cycle has been achieved.

This document MUST NOT be interpreted as an authorization record. It does not pass a gate, approve a benchmark, establish source truth, clear rights, authorize S2 mutation, authorize publication, or modify v4.2 assessment state.

---

## 2. Normative language and authority order

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are normative for engineering work under this specification.

When sources disagree, use this order:

1. **Fresh live repository state** for mutable engineering facts: exact `main` SHAs, merged code, current workflow behavior, open issues, run status, and current files.
2. **`curation/CURRENT_EXECUTION_CONTROL.json` and its referenced immutable successor** for current programme-control state.
3. **Exact immutable governance/protocol artifacts** referenced by the current successor for gate semantics, benchmark constraints, dispositions, bindings, and historical evidence.
4. **This document** for the integrated engineering execution plan and resumption procedure.
5. Historical snapshots, old issue descriptions, transfer notes, and archived branches only for provenance or lineage.

A stale SHA or status written in this document MUST NOT override a newer exact live state. When a mutable fact changes, the engineer MUST update the appropriate immutable successor/control pointer and SHOULD update this document if the change affects the execution plan.

---

## 3. True-vision end state

The programme is complete for its **first governed end-to-end cycle** only when the following capabilities hold together:

### 3.1 Living global discovery

The system continuously discovers and refreshes relevant:

- organizations;
- products and systems;
- patents and patent families;
- trials;
- publications;
- grants;
- regulatory records;
- commercially relevant gray/nontraditional applications;
- deployment and commercialization evidence.

Structured source universes MUST preserve denominator/paging state where such a denominator exists. Open-world programmes MUST report protocol coverage, discovery channels, languages, jurisdictions, marginal yield, failure state, and stopping rule. Open-world saturation MUST NOT be represented as a global census.

### 3.2 Evidence truth separated from interpretation

Source bytes/records, observations, extracted candidates, assertions, relationships, and human dispositions MUST remain distinguishable.

Every canonical claim or link MUST be traceable to:

`source -> observation -> transformation/extraction -> disposition -> release identity`

Retrieval success, schema validity, hashes, workflow success, or model agreement establish mechanics and identity; they do not establish substantive truth.

### 3.3 Candidate-first automation

Automated systems MAY retrieve, extract, classify, rank, resolve candidate identities, propose links, or draft bounded interpretations.

Automated systems MUST NOT silently create:

- canonical entities;
- accepted relationships;
- assessment findings;
- human benchmark truth;
- publication authority.

### 3.4 Temporal graph integrity

Observation time and asserted valid time MUST remain distinct. New evidence MUST create successor state. Historical predecessors MUST remain reconstructable. Corrections MUST NOT silently overwrite prior truth.

### 3.5 Measured discovery and model quality

Before production filtering or scale, the programme MUST have frozen human-adjudicated held-out benchmarks and measure at least:

- precision;
- recall;
- calibration where meaningful;
- threshold sensitivity;
- abstention/uncertainty;
- model disagreement;
- false-negative behavior;
- subgroup error;
- multilingual behavior;
- gray-zone behavior;
- cost.

Challenge-set metrics MUST NOT be promoted into population estimates when the design does not support population inference.

### 3.6 Identity and concordance rigor

Organization, product, system, patent publication, patent family, assignee, subsidiary, and parent identities MUST remain explicit.

Name similarity, embedding similarity, common terminology, or model confidence MUST NOT silently merge identities.

Patent-product links MUST carry evidence tiers. Weak inferred links MUST NOT enter established-link quantitative analyses without a validated error study.

### 3.7 Bounded governance mapping

Governance analysis MUST use the chain:

`observed capability + deployment context -> mechanism -> concern -> relevant policy instrument`

It MUST NOT convert speculative misuse scenarios into predictions of company intent or behavior.

### 3.8 Independent publication boundary

The lifecycle invariant is:

`candidate != technical verification != human disposition != authorization != publication`

The exact graph candidate MUST be bound independently from authorization, and publication MUST be a separate attributable event.

### 3.9 Reproducible public products

Reports, workbooks, dashboards, tables, and figures MUST be deterministic products of an exact authorized S2 release. S4 products MUST NOT add claims that do not exist in the governed S2 evidence state.

### 3.10 Selective exact-system assurance

Landscape prominence or risk salience MAY create a separately attributable assessment trigger. Only a clearly identified system/configuration with sufficient evidence MAY enter or reopen v4.2 assessment. Landscape ranking MUST NOT directly mutate v4.2 findings.

---

## 4. Store architecture and non-crossing boundaries

### S1 — Workbench/code

Repository: `fraware/neuroai-workbench`

Permitted:

- schemas;
- acquisition code;
- projectors;
- replay/runtime proof tooling;
- validators;
- discovery workflows;
- evaluation tooling;
- release compiler logic.

S1 success MUST NOT be treated as scientific truth, human approval, publication authority, or S2 mutation authority.

### S3 — controlled research workspace

Permitted:

- licensed PATSTAT/commercial data;
- protected captures;
- real benchmark membership;
- held-out labels;
- reviewer identities/competence records;
- detailed adjudication packets;
- HMAC keys and commitment preimages;
- detailed failure diagnostics where disclosure would leak held-out data;
- rights-sensitive evidence.

S3 bytes MUST NOT be copied into public S2 unless rights and release rules explicitly permit it.

### S2 — public canonical Observatory

Repository: `fraware/neuroai-observatory-data`

Permitted:

- authorized public entities;
- public sources and observations;
- bounded assertions;
- events and relationships;
- public-safe candidate/reopening metadata;
- release manifests;
- digests and opaque commitments;
- governance records permitted for release.

Repository presence alone MUST NOT imply publication.

### S4 — publication products

Permitted:

- reports;
- analytical workbooks;
- dashboards;
- visualizations;
- policy-facing summaries.

S4 MUST be regenerable from an exact authorized S2 release and recorded toolchain.

### v4.2 assessment workspace

Permitted:

- exact-system evidence;
- requirement findings;
- typed gaps;
- decisions;
- reopening state.

Landscape state MAY trigger assessment review; it MUST NOT substitute for exact-system evidence.

---

## 5. Current execution state at the v0.1 spec snapshot

This section is a **snapshot**, not the authoritative mutable state.

At authoring:

- Observatory `main`: `9cd32e616d6bf1aebd85bab6c6564ca777117205`.
- Workbench `main`: `854cc9d1c8e24a9e8ae8b21d871329bc3c24c118`.
- Current programme pointer: `curation/CURRENT_EXECUTION_CONTROL.json`.
- Current immutable successor: `curation/PROGRAMME_EXECUTION_STATE_2026-09-13_PRE_G2_CURRENT_SUCCESSOR.json`.
- G0: `BLOCKED_NOT_PASSED`.
- G1: `APPROVE` for the exact bound D1/D2 identities only.
- G2: not passed.
- G5: not passed.
- S2 canonical mutation authority: false.
- publication authority: false.
- PATSTAT rights clearance: false.
- population-generalization authority: false.
- Phase 4 online-first default authorization: false.
- v4.2 assessment effect: none.

Open blocking work represented by live issues at this snapshot:

- Workbench #287 — controlled live/replay equivalence and interruption proof.
- Observatory #224 — SRC-14-021 / SONA successor-domain adjudication.
- Observatory #222 — D3 patent benchmark.
- Observatory #223 — D4 product benchmark.
- Observatory #220 — PATSTAT Baseline A scientific audit.
- Observatory #210 — PATSTAT redistribution/containment rights review.

Current PRE-G2 controls are substantially implemented. The dominant remaining work is **real execution, human evidence, provenance, rights review, measured research performance, and downstream governed release**.

---

## 6. Critical-path dependency graph

The main programme chain is:

```text
Workbench Phase-3 external proof ----+
                                      |
SRC-14-021 lifecycle resolution ------+--> qualifying scheduled due-cycle --> G0
                                      |
                                      +-----------------------------------------+
                                                                                |
G1 exact D1/D2 approval [already passed] ---------------------------------------+
                                                                                |
D3 real pilot -> calibration -> frozen membership -> labels -> freeze ----------+
                                                                                +--> G2
D4 real pilot -> calibration -> frozen membership -> labels -> freeze ----------+
                                                                                |
PATSTAT provenance + probability audit + rights -------------------------------+
                                                                                |
G2 --> G3 structured pilot --> G4 company/product pilot --> G5 evaluation
   --> G6 expert boundary review / methodology v1 freeze
   --> G7 scale acquisition
   --> G8 identity/concordance validation
   --> G9 governance crosswalk
   --> G10 Observatory v2 exact candidate
   --> G11 human authorization + separate S2 publication
   --> G12 report/workbook + exact-system assessment triggers
   --> final true-vision acceptance audit
```

Parallelism is allowed when a downstream result does not depend on an unresolved upstream decision. In particular, benchmark construction, PATSTAT provenance intake, rights review, and bounded replay research MAY progress while G0 remains blocked.

No engineer should optimize for PR count. Progress is measured by removal of a real dependency, creation of admissible evidence, or passage of a governed gate.

---

## 7. Immediate execution stage A — complete Workbench Phase-3 external proof

### Objective

Produce the first real hosted external proof for the already-merged online-first Phase-3 runtime semantics.

### Current control

Workbench:

- issue: #287;
- workflow: `.github/workflows/phase3-external-proof.yml`;
- required branch: `main`;
- fixed source: `SRC-PR-002`;
- fixed reference target: ClinicalTrials.gov / `NCT04676854`;
- live origin: `https://clinicaltrials.gov`;
- confirmation input: `AUTHORIZE_ONE_CT_GOV_PHASE3_LIVE_REQUEST`.

### Execution

The workflow MUST be manually dispatched against current Workbench `main`.

Reference CLI invocation:

```bash
gh workflow run phase3-external-proof.yml \
  --repo fraware/neuroai-workbench \
  --ref main \
  -f confirm_external_live=AUTHORIZE_ONE_CT_GOV_PHASE3_LIVE_REQUEST
```

The run MUST:

1. check out the exact dispatched `main` SHA;
2. construct a run-scoped acquisition policy and authorization;
3. perform one bounded live capture;
4. record full target/source accounting;
5. replay the exact captured result with zero network collection attempts;
6. verify live/replay projection equivalence;
7. verify zero canonical S2 mutation;
8. rerun the interruption/recovery adversarial suite;
9. prove the repository worktree remained clean;
10. upload only the sanitized proof bundle;
11. keep capture/quarantine bytes out of the uploaded public artifact.

### Required retained evidence

Record at minimum:

- GitHub workflow run ID and attempt;
- event = `workflow_dispatch`;
- exact Workbench SHA;
- policy digest;
- authorization digest;
- registry/configuration digests;
- live run ID;
- replay run ID;
- result ID;
- runtime proof ID and semantic digest;
- workflow conclusion;
- artifact identity;
- reviewer disposition.

### Pass rule

Workflow success alone is necessary but not sufficient. A human/attributable review MUST confirm that the expected semantic claims were actually established by the exact run.

Only then may the programme record Phase-3 reviewed-complete state.

### Forbidden shortcuts

Do not:

- change the workflow trigger merely to create a run;
- substitute a synthetic CI test;
- substitute local replay for a hosted external proof;
- upload captured source bytes that the workflow intentionally quarantines;
- infer Phase-4 authorization from Phase-3 success;
- infer G0 or G2 passage from this proof.

---

## 8. Immediate execution stage B — finish G0 operational readiness

### Objective

Establish a trustworthy exact execution baseline with healthy live-scale operational behavior.

### Remaining blocker

The current known blocker is `SRC-14-021`, governed by Observatory issue #224.

The historical SONA route is unavailable. A candidate successor route has been observed, but a route change MUST NOT be made from self-assertion, DNS failure, or convenience alone.

### Required source-lifecycle resolution

Acceptable resolution requires evidence that satisfies the governed lifecycle/source-identity rules. Preferred evidence is an authoritative SONA or independently attributable partner/officer confirmation that binds the organization identity to the successor route.

If successor identity is established:

1. retain the historical route and evidence;
2. append a successor source-universe state;
3. bind the exact evidence used;
4. change routing only through the normal governed mechanism;
5. do not rewrite predecessor source records.

If successor identity is not established, retain the unresolved/degraded state unless a deliberate governance decision changes the operational-health semantics. Such a change would be a substantive governance decision, not an engineering convenience fix.

### Required scheduled proof

After the blocker is legitimately resolved, the programme MUST obtain a **normal scheduled operational due-cycle** under the current exact code/data state.

The qualifying due-cycle MUST demonstrate:

- scheduled trigger, not a manual surrogate;
- exact source-universe binding;
- complete source accounting;
- correct partial-source semantics;
- retry/resume correctness;
- retained diagnostics;
- no silent lifecycle count drift;
- no authority escalation;
- correct run manifest;
- successful post-transition invariants.

A green manual run is not a substitute for the scheduled criterion if the gate explicitly requires schedule evidence.

### G0 exit package

The G0 successor SHOULD bind:

- exact Observatory `main` SHA;
- exact Workbench runtime SHA/package;
- qualifying scheduled run ID;
- source-universe identity/digest;
- source-health summary;
- retry/resume proof identities;
- Phase-3 proof identity if relevant to the healthy path;
- explicit G0 human/governance disposition if the current control model requires one;
- unchanged G1/G2 authority boundaries.

### G0 pass meaning

G0 establishes operational readiness of the exact baseline. It does not establish benchmark adequacy, population inference, publication authority, scientific truth, or v4.2 assessment outcomes.

---

## 9. Immediate execution stage C — PATSTAT Baseline A provenance, probability audit, and rights

PATSTAT has two independent tracks:

```text
scientific validity != redistribution/legal clearance
```

Neither track can substitute for the other.

### 9.1 Provenance intake

Current status file:

`curation/PATSTAT_BASELINE_A_PROVENANCE_INTAKE_STATUS_2026-09-12_v0.1.json`

Current declared state: `WAITING_FOR_PROVENANCE`.

Six required provenance components remain explicit:

1. `HISTORICAL_JUDGES_AND_RUBRIC`
2. `FIRST_STAGE_PROBABILITY_DESIGN`
3. `SECOND_STAGE_333_DESIGN`
4. `ESTIMATOR_AND_UNCERTAINTY`
5. `RETRIEVAL_POOL_CONSTRUCTION`
6. `EXPORT_CLARIFICATION`

Each component MUST be supported by enough exact evidence to reconstruct the historical process. The programme MUST NOT treat a narrative recollection as equivalent to executable or auditable design evidence when exact implementation details matter.

### 9.2 Scientific reconstruction

Once provenance is available, engineers/researchers MUST independently reconstruct:

- the target population/frame;
- the nine first-stage strata;
- `N_h` and `n_h`;
- certainty/exhaustive cells;
- inclusion probabilities;
- seed/randomization procedure;
- deduplication unit;
- the exact 333-case second-stage eligibility frame;
- second-stage cell counts and inclusion probabilities;
- replacement/adaptation semantics if any;
- the estimator implementation;
- correction formula;
- uncertainty method;
- finite-population corrections where applicable;
- interval construction;
- retrieval-pool construction;
- query definitions/version/time;
- pool-to-probability-frame relationship;
- malformed/missing verdict handling.

The historical machine-generated labels MUST remain identified as machine-generated. They MUST NOT be relabeled as human gold.

The historical `49,671` estimated relevant-family total and approximately `67%` retrieval recall MUST remain unvalidated until this audit establishes them.

### 9.3 Rights review

Issue #210 remains an independent blocker for any public redistribution of PATSTAT-derived material.

The rights disposition MUST state, at minimum:

- source/licence class;
- permitted research use;
- permitted derived statistics;
- prohibited raw/row-level redistribution;
- whether identifiers or transformed fields may enter S2;
- retention requirements;
- whether public aggregate evidence is allowed;
- review authority and date;
- exact material reviewed.

If rights remain unclear, protected PATSTAT evidence stays in S3. Public S2 may contain only what the rights disposition explicitly permits.

### 9.4 Exit condition

PATSTAT is ready for downstream scientific use only when the exact required provenance is available, the estimator/retrieval claims have been independently audited to the intended inference scope, and rights have been separately disposed for the public-release surface being proposed.

---

## 10. Immediate execution stage D — build the real D3 patent benchmark

### Governing role

D3 challenge evidence role:

`CHALLENGE_CONSTRUCT_COVERAGE`

It is a non-probability challenge design. Its raw class balance and error rates MUST NOT be interpreted as population prevalence or global retrieval recall.

Population inference belongs to the separate probability-audit track.

### Current control artifacts

- `curation/PRE_G2_D3_PATENT_CHALLENGE_PROTOCOL_2026-09-11_v0.1.json`
- `curation/PRE_G2_D3_CHALLENGE_SAMPLING_CALIBRATION_PROTOCOL_2026-09-11_v0.1.json`
- `curation/PRE_G2_D3_CALIBRATION_SELECTION_COMPOSITION_2026-09-11_v0.1.json`

Current state: software/control composition exists; no real pilot, final membership, final labels, D3 freeze, or benchmark-adequacy finding exists.

### 10.1 Real pilot

Run one complete **60-family** pilot round.

Requirements include:

- all 60 items independently double reviewed;
- pilot excluded from final held-out eligibility;
- at least 10 items per required controlled patent stratum;
- at least 10 resolved INCLUDE;
- at least 10 resolved EXCLUDE;
- at least 10 resolved BORDERLINE;
- no more than 6 unresolved disagreements;
- zero semantic validation failures;
- zero evidence-binding failures;
- zero reviewer-reference collisions;
- raw four-way agreement reported, not used as an automated competence threshold;
- full primary/secondary confusion accounting;
- immutable preservation of a failed round;
- no extension of a failed round to manufacture passage.

Real packet bytes, reviewer records, membership, and keys stay in S3.

### 10.2 Human calibration disposition

After the quantitative readiness calculation, an attributable human calibration authority MUST review:

- disagreement classes;
- INCLUDE/EXCLUDE reversals;
- BORDERLINE and ABSTAIN use;
- rationale quality;
- rubric ambiguity;
- reviewer training and qualification provenance;
- blinding exceptions;
- per-stratum disagreement patterns;
- unresolved cases;
- evidence-binding issues.

Only an exact `APPROVE` disposition bound to the real pilot artifacts may unlock final selection.

Approval means only that the exact selection precondition is satisfied. It does not itself establish reviewer competence, benchmark adequacy, G2, G5, rights clearance, population inference, publication authority, or assessment authority.

### 10.3 Frozen candidate pool and deterministic final selection

Before final labels:

1. construct the real S3 candidate pool;
2. validate exact family identity and eligibility;
3. freeze the pool;
4. compute the keyed HMAC commitment;
5. bind the human calibration disposition digest;
6. prove pilot/final disjointness under the attested family namespace;
7. run the composed selection entrypoint.

Final D3 membership is exactly **240 unique patent families**.

The current protocol additionally requires:

- at least 40 items per required patent challenge stratum;
- multilingual minimum 40;
- 8 non-English target languages with at least 4 items per counted language;
- multi-jurisdiction minimum 40;
- 8 target jurisdictions with at least 4 items per counted jurisdiction;
- missing-or-short abstract minimum 40;
- missing-abstract minimum 16;
- short-abstract minimum 16;
- outside-query-pool challenge minimum 40.

Selection MUST occur before final human labels are visible to the selector. Model predictions, scores, prompts, thresholds, historical machine labels, or final errors MUST NOT drive final membership.

### 10.4 Final human reference labels and freeze

After exact membership is frozen:

- independently double review every final held-out case as required by the protocol;
- preserve INCLUDE / EXCLUDE / BORDERLINE / ABSTAIN semantics;
- adjudicate genuine disagreements under the declared protocol;
- do not coerce unresolved disagreement into false consensus;
- preserve exact evidence packet bindings and chronology;
- retain reviewer/exposure provenance in S3;
- produce public-safe opaque commitments and aggregate coverage evidence;
- freeze D3 using the Workbench/public contract mechanism.

No tuning process may access final held-out labels.

---

## 11. Immediate execution stage E — build the real D4 product benchmark

### Governing role

D4 evidence role:

`CHALLENGE_CONSTRUCT_COVERAGE`

D4 is deliberately enriched for difficult product/gray-boundary cases. It is not a population sample.

Required construct strata are:

- `AMBIGUOUS_BIOSIGNAL`
- `CLINICAL`
- `CONSUMER`
- `ENTERTAINMENT_XR`
- `MULTI_JURISDICTION`
- `MULTILINGUAL`
- `NONTRADITIONAL_FORM_FACTOR`
- `RESEARCH`
- `WELLNESS`
- `WORKPLACE`

### Current control artifacts

- `curation/PRE_G2_D4_PRODUCT_CHALLENGE_PROTOCOL_2026-09-08_v0.1.json`
- `curation/PRE_G2_D4_SAMPLING_CALIBRATION_PROTOCOL_2026-09-09_v0.1.json`
- `curation/PRE_G2_D4_CALIBRATION_SELECTION_COMPOSITION_2026-09-12_v0.1.json`
- `curation/PRE_G2_D4_PILOT_READINESS_POLICY_2026-09-12_v0.2.json`
- `curation/HUMAN_D4_AGREEMENT_GATE_DISPOSITION_2026-09-12_v0.1.json`

The v0.2 successor explicitly removes raw exact agreement as an automated readiness threshold while retaining it as mandatory human-review evidence.

### 11.1 Real pilot

Run exactly **60** pilot items.

Current v0.2 automated readiness controls require:

- exactly 60 pilot items;
- exactly 60 independently double-labeled items;
- at least 6 items per controlled stratum;
- at least 10 resolved INCLUDE;
- at least 10 resolved EXCLUDE;
- at least 10 resolved BORDERLINE;
- no more than 3 unresolved disagreements;
- zero semantic validation failures;
- zero reviewer-reference collisions;
- zero evidence-binding failures;
- rationale for every blinding exception;
- zero pilot items eligible for final held-out membership.

Raw exact agreement count and rate MUST still be computed and reported, but MUST NOT be used as an automated gate.

### 11.2 Mandatory human calibration review

The human reviewer MUST inspect at least:

- the full 4x4 primary/secondary confusion matrix;
- raw exact agreement count/rate;
- construct-conditioned disagreement;
- INCLUDE/EXCLUDE reversals;
- BORDERLINE/ABSTAIN disagreements;
- adjudication burden;
- unresolved disagreement;
- reviewer training/qualification provenance;
- blinding exceptions;
- rationale quality;
- rubric ambiguity.

Only a real, attributable, exact-binding `APPROVE` disposition may unlock final selection.

### 11.3 Frozen pool and final selection

After approval:

1. freeze the exact pre-label candidate pool in S3;
2. compute its keyed commitment;
3. bind the calibration disposition;
4. create/validate the final-selection authorization envelope;
5. validate namespace identity;
6. prove zero pilot/final overlap;
7. execute the approved v0.2 composed final-selection path.

Final D4 membership is exactly **240 unique items**.

Allocation floors include:

- at least 24 items per controlled stratum;
- multilingual minimum 24;
- at least 6 distinct non-English source languages;
- at least 3 items per counted non-English language;
- multi-jurisdiction minimum 24;
- at least 6 distinct jurisdictions;
- at least 3 items per counted jurisdiction.

These are challenge-coverage design constraints, not population-power or prevalence-precision calculations.

### 11.4 Final labeling and freeze

Final labels are collected only after membership is frozen.

Every final held-out candidate MUST receive the protocol-required independent human review, adjudication state, rationale, exact object identity binding, evidence binding, exposure review, and rights containment review.

D4 freeze MUST produce the required public commitments/coverage reports without exposing real held-out membership or labels.

---

## 12. G2 — evaluation-set gate

### Purpose

G2 turns D3 and D4 from software scaffolding into real governed evaluation evidence.

### Prerequisites

- G1 remains valid for the exact D1/D2 identities.
- Real D3 benchmark frozen.
- Real D4 benchmark frozen.
- Human review/adjudication provenance complete.
- Held-out membership and labels protected from model/prompt/threshold tuning.
- Multilingual and gray/borderline coverage represented.
- Rights/containment review complete for the benchmark surfaces.

### G2 pass criteria

G2 MAY pass only if:

- positive, negative, and borderline cases are actually present;
- reference labels are human adjudications, not model consensus;
- held-out membership is frozen and content-addressed/committed;
- label/adjudication provenance is frozen;
- exposure/contamination accounting is complete;
- the benchmark roles are explicit;
- D3 population-audit evidence remains separated from D3 challenge evidence;
- unresolved cases remain typed, not forced;
- public artifacts expose only permitted aggregates/commitments.

### G2 output

Create an immutable human G2 disposition binding the exact D3 and D4 frozen identities.

The G2 record MUST state explicitly what is and is not authorized. G2 itself does not publish S2, pass G5, establish population inference, or authorize Phase 4.

---

## 13. G3 — structured-source discovery pilot

### Objective

Demonstrate reproducible discovery against structured/denominated sources before scaling.

At minimum the pilot scope SHOULD cover the programme's structured source classes:

- patents;
- publications;
- clinical trials;
- grants;
- regulation.

### Engineering requirements

For each source:

- pin source registry/version;
- pin query/configuration;
- record execution mode;
- record denominator or paging state when meaningful;
- bind source and observation timestamps;
- retain response/capture provenance according to rights class;
- project into candidate-only outputs;
- preserve source-specific failure state;
- support replay;
- measure exact source/target accounting;
- prevent any path from candidate generation to automatic S2 acceptance.

### Exit evidence

Each source-specific projector MUST produce a reproducible candidate/coverage output from the retained replay material or a permitted exact source snapshot.

G3 passes only when identity, denominator semantics, candidate-only behavior, and replay are demonstrated with no authority escalation.

---

## 14. G4 — company/product open-world discovery pilot

### Objective

Demonstrate the nonstructured discovery protocol on a bounded real sample before production scale.

### Required pilot

Run approximately **50–100 candidate organizations/products** spanning:

- clinical;
- consumer;
- workplace;
- research;
- non-US / multilingual contexts;
- gray/nontraditional discovery channels where applicable.

### Every candidate MUST retain

- discovery programme ID;
- seed/channel;
- query/search family;
- language;
- jurisdiction;
- discovery round;
- source class;
- observed-at time;
- exact source/evidence references;
- initial identity state;
- deduplication result;
- human disposition state when adjudicated;
- failure/unknown state.

### Coverage accounting

Per round/channel/language/jurisdiction record:

- candidates discovered;
- unique candidates after deduplication;
- adjudicated relevant/borderline/excluded if available;
- incremental unique yield;
- source failures;
- retry state;
- marginal yield;
- reason to continue or stop.

### Pass criteria

G4 passes when:

- provenance is complete;
- deduplication is explicit and auditable;
- open-world completeness is not claimed;
- marginal discovery yield is measurable;
- failures are categorized;
- gray/non-English acquisition paths are represented;
- the output remains candidate-only.

---

## 15. G5 — model and discovery-system evaluation

### Inputs

G5 MUST use the exact frozen G2 benchmarks and predeclared evaluation plans.

### Required evaluation families

Measure, where applicable:

- precision;
- recall;
- F1 or other declared summary metrics;
- calibration;
- threshold sensitivity;
- abstention/uncertainty;
- four-way routing behavior;
- model disagreement;
- false-negative rate and error taxonomy;
- subgroup error by language/jurisdiction/construct;
- gray-zone sensitivity;
- missing/short-text behavior;
- cost and latency;
- retrieval-system marginal yield;
- concordance/link error where a model is used for linking.

### Statistical separation

D3 challenge metrics describe the frozen challenge distribution only.

Population-level patent inference MUST use the probability-audit design and estimator if, and only if, that design has been validated for the relevant estimand.

### Pass rule

Predeclared thresholds MUST be evaluated as written. Thresholds MUST NOT be rewritten after seeing held-out performance merely to create a pass.

If a system misses a broad-role threshold but performs adequately in a narrower role, the programme MAY explicitly narrow its production role and record that scope.

### Required result

Create a versioned evaluation dossier containing:

- benchmark identities;
- model/provider/version/configuration identities;
- prompt or classifier configuration;
- evaluation code identity;
- metrics;
- confidence/uncertainty where valid;
- subgroup results;
- failure analysis;
- threshold decision;
- permitted production role;
- explicit non-claims.

---

## 16. G6 — expert boundary review and methodology v1 freeze

### Purpose

Resolve or explicitly preserve the hardest semantic boundaries before scaling.

### Review packet SHOULD include

- difficult D3/D4 cases;
- gray-third candidates;
- multilingual ambiguity;
- identity-resolution disputes;
- patent-product concordance disputes;
- governance-mapping edge cases;
- systematic G5 error classes;
- source-class claim-ceiling disputes.

### Expert outputs

Every reviewed item MUST produce one of:

- accepted disposition;
- rejected disposition;
- taxonomy/rule revision;
- request for stronger evidence;
- explicitly unresolved state.

Consensus is not required. Genuine disagreement MAY remain unresolved.

### Change control

Any semantic change to D1/D2-derived taxonomy, inclusion rules, claim ceilings, or search semantics MUST be versioned. Historical artifacts MUST remain immutable.

G6 passes when the methodology used for scale is frozen as **methodology v1** and unresolved boundaries are explicit.

---

## 17. G7 — production-scale acquisition

### Objective

Run the validated methodology at production scale.

### Structured acquisition

For structured sources, retain:

- exact source/version;
- query;
- denominator/paging state;
- run manifest;
- source coverage;
- retries;
- partial-source state;
- execution cost;
- model version if classification is applied;
- retained/replayable evidence according to rights class.

### Open-world acquisition

For company/product/gray/multilingual programmes, retain:

- seed strategy;
- channel inventory;
- query packs;
- language/jurisdiction strata;
- round-by-round marginal yield;
- deduplication;
- failure accounting;
- stopping-rule evidence.

### Scale constraint

Scale MUST NOT outrun evaluation. A model/filter MAY only be used in the production role justified by G5.

### Exit condition

G7 passes when production acquisition is reproducible and the full provenance, coverage, cost, model, and source-health records exist.

---

## 18. G8 — identity resolution and concordance

### Objective

Construct a reliable cross-object graph without silent merges.

### Identity rules

Engineers MUST preserve distinct identity classes for:

- organization;
- subsidiary/parent;
- product;
- product family;
- exact system/configuration;
- patent publication;
- patent family;
- assignee;
- inventor where needed for the research question.

Unknown and ambiguous identities remain explicit.

### Patent-product relationship evidence tiers

The research contract uses L1-L4 semantics:

- **L1**: explicit product-patent binding in authoritative/company/product documentation.
- **L2**: company attribution plus strong technical/timing evidence.
- **L3**: multi-source inferred alignment without explicit binding.
- **L4**: semantic/model similarity only.

L4 is discovery/ranking only.

L3 MUST NOT enter established-link quantitative claims unless a validated link-error study justifies the use.

L1/L2 report-facing links require human review under the declared contract.

### G8 evaluation

Perform sampled audits of:

- entity merges;
- alias handling;
- parent/subsidiary state;
- patent-family resolution;
- product-version resolution;
- inferred links.

Record measured error rates and error classes.

G8 passes when quantitative analyses exclude weak candidate-only links and link error is measured.

---

## 19. G9 — capability/context/governance crosswalk

### Required mapping chain

```text
OBSERVED PRODUCT OR SYSTEM
        ->
CAPABILITY + DEPLOYMENT CONTEXT
        ->
MECHANISM
        ->
GOVERNANCE CONCERN
        ->
POLICY INSTRUMENT / RECOMMENDATION
```

### Engineering/research controls

- concern classes and mechanisms MUST be versioned;
- model-assisted mapping MUST retain model provenance;
- observed evidence MUST be distinguishable from inferred mapping;
- conditions/uncertainty MUST be explicit;
- unsupported predictions of company intent MUST be prohibited;
- harmful-use detail beyond the research need MUST not be introduced.

### Validation

Expert/policy collaborators MUST review a sample sufficiently broad to expose systematic mapping errors and boundary confusion.

G9 passes when mappings are bounded, mechanism-based, and supported by the exact observed capability/context evidence.

---

## 20. G10 — compile the Observatory v2 successor candidate

### Input rule

Only accepted, rights-permitted evidence may be compiled into the public candidate.

### Required graph classes

The stable S2 candidate surface is defined by `docs/observatory-v2-release-contract.md` and includes:

- entities;
- sources;
- observations;
- assertions;
- events;
- relationships;
- candidates;
- reopening decisions;
- governed migration/predecessor traces;
- Gate-A lineage.

### Candidate requirements

The compiler MUST:

- bind the exact S1 producer commit;
- bind runtime execution identity where required;
- bind exact S2 predecessor;
- preserve immutable predecessor state;
- preserve temporal semantics;
- validate referential integrity;
- validate object classes;
- bind all candidate file digests;
- contain no prohibited S3 bytes;
- keep candidate state explicitly noncanonical/unpublished.

### Pass meaning

G10 is mechanical candidate completion. It MUST NOT be described as publication.

---

## 21. G11 — authorization and publication

### Authorization

A designated human authority reviews the **exact candidate identity** and records either:

- `AUTHORIZE`; or
- `WITHHOLD`.

Authorization MUST bind the exact candidate and MUST remain separate from candidate bytes.

### Publication

Publication occurs only after an active matching `AUTHORIZE` record exists.

The separate publication record MUST bind:

- exact candidate;
- exact active authorization;
- publication evidence;
- publication-evidence digest;
- immutable release identity.

Run:

```bash
python scripts/verify_observatory_v2_release.py releases/<tag>
python scripts/verify_observatory_v2_release.py releases/<tag> --require-published
```

Independent S2 verification MUST pass.

### Forbidden shortcuts

Do not:

- flip candidate booleans in place;
- treat manifest validity as authorization;
- infer authorization from repository merge;
- auto-publish as a side effect of candidate generation;
- include protected S3 evidence;
- edit a published candidate in place.

Corrections require a successor release.

---

## 22. G12 — public products and exact-system assessment triggers

### S4 publication products

Generate the landscape report, analytical workbook, and dashboard/reproducible visual products from the exact G11 release.

Every table/figure/narrative claim MUST be traceable to:

- exact S2 release;
- underlying graph records;
- evidence/provenance;
- transformation code/version.

The build SHOULD be reproducible in a clean environment.

### Assessment triggers

Separately identify exact systems/configurations that meet the criteria for deeper v4.2 review.

Each trigger MUST:

- identify the exact system/configuration;
- bind the supporting S2 evidence;
- explain the reason for trigger/reopening;
- carry no assessment effect itself;
- require a separate attributable assessment/reopening decision.

### G12 pass

G12 passes when public products reproduce from the exact published release and assessment triggers are separately attributable and evidence-bound.

---

## 23. Final true-vision acceptance audit

Do not declare the first complete true-vision cycle complete until all of the following are simultaneously demonstrated.

### Operational

- Scheduled monitoring/discovery executes reproducibly.
- Failure attribution distinguishes source, transport, projector, policy, and lifecycle state.
- Retry/resume is exact.
- Partial-source state is explicit.
- Run manifests are retained.

### Coverage

- Structured universes retain denominator/paging state.
- Open-world programmes retain seed/channel/language/jurisdiction coverage.
- Marginal yield and stopping rules are recorded.
- No unsupported global-completeness claim appears.

### Provenance

Every canonical assertion/link traces to exact:

- source;
- observation;
- transformation;
- disposition;
- release identity.

### Temporal integrity

- observation time and valid time are distinct;
- predecessor states are immutable;
- successor changes are reconstructable.

### Evaluation

- held-out benchmark identities are frozen;
- human label/adjudication provenance is frozen;
- subgroup/error analysis exists;
- uncertainty/abstention behavior is characterized before scale;
- challenge and probability evidence roles remain separate.

### Multilingual and gray recall

- non-English discovery is explicit;
- gray-third discovery is explicit;
- incremental yield is measured;
- error is measured;
- evidence is not anecdotal only.

### Identity/concordance

- explicit identity state exists;
- weak merges are prevented;
- product-patent links have evidence tiers;
- inferred-link error is measured.

### Governance mapping

- mappings are capability/context/mechanism based;
- mappings are bounded and reviewed;
- predicted company intent is absent.

### Publication authority

- candidate, technical validation, human disposition, authorization, and publication are exact-bound and semantically distinct.

### Reproducibility

- public report/workbook/dashboard rebuilds from the exact authorized S2 release;
- output figures/tables match;
- tool versions are recorded.

### Assessment boundary

- only exact systems with sufficient identity/evidence enter or reopen v4.2;
- landscape ranking never mutates assessment findings automatically.

### Data governance

- licensed/private bytes remain contained;
- public material is rights-permitted;
- held-out membership/labels and controlled reviewer data remain protected.

### Continuity

A new engineer/operator MUST be able to reconstruct current state from:

- this document;
- `curation/CURRENT_EXECUTION_CONTROL.json`;
- its referenced successor;
- exact main SHAs;
- issue/disposition records;
- run manifests;
- release/governance records;

without depending on chat history or informal memory.

Completion of this audit marks the **first fully governed realization of the true vision**. The Observatory then becomes an ongoing operational/research system; completion is not the end of monitoring.

---

## 24. Engineering resumption runbook

Every engineer or new execution session MUST begin with this sequence.

### Step 1 — resolve current control

Read:

`curation/CURRENT_EXECUTION_CONTROL.json`

Then read the referenced:

`current_programme_execution_state`

Do not begin from an old issue summary or old chat state.

### Step 2 — fresh-read both repository heads

Record current `main` SHAs for:

- `fraware/neuroai-workbench`
- `fraware/neuroai-observatory-data`

Compare them to the bindings in the current execution successor.

A difference is not automatically an error; determine whether it represents newer merged work that requires a new execution successor.

### Step 3 — inspect open blocking issues

At minimum inspect the issues named by the current successor. Determine whether any have closed, changed semantics, or gained real evidence since the successor was written.

### Step 4 — inspect hosted run evidence

For gates that depend on hosted execution, inspect the actual GitHub Actions runs and exact head SHA. Do not infer a run from workflow existence.

### Step 5 — classify the next action

Every action should be classified as one of:

- software/control implementation;
- real external execution;
- source/provenance acquisition;
- human benchmark review;
- human governance disposition;
- scientific evaluation;
- rights/legal review;
- candidate compilation;
- authorization;
- publication.

If a gate is blocked on a real-world event, writing more control scaffolding is not automatically progress.

### Step 6 — execute the first unresolved dependency

Prefer the earliest dependency whose resolution produces admissible evidence or unlocks downstream work.

### Step 7 — after substantive change

After each substantive repo change:

1. validate locally/offline where applicable;
2. open a focused PR;
3. keep unrelated semantic changes separate;
4. require the exact PR head checks to pass;
5. merge only the reviewed exact head;
6. fresh-read resulting `main`;
7. inspect post-merge run evidence;
8. if programme-control state changed, append a new immutable successor;
9. atomically advance `CURRENT_EXECUTION_CONTROL.json`;
10. never rewrite historical successor records.

---

## 25. PR and change-control discipline

### One semantic delta per PR

Do not combine unrelated repairs simply because both are currently red.

Examples of changes that SHOULD remain separate:

- transport behavior;
- source lifecycle semantics;
- authorization semantics;
- benchmark statistical design;
- rights containment;
- publication mechanics.

### Exact-head validation

A PR is mergeable only when the checks observed on the final exact head satisfy the requirements of that semantic change.

If the head moves, re-evaluate the new head.

### Append-only governance

Historical:

- execution successors;
- human dispositions;
- source-lifecycle decisions;
- benchmark protocols;
- publication records;

MUST NOT be rewritten to make the current state cleaner.

Changes occur through successors.

### No evidence inflation

The following transitions are prohibited without the corresponding real event:

- workflow exists -> workflow ran;
- workflow ran -> human review completed;
- pilot software exists -> real pilot exists;
- model labels exist -> human gold exists;
- schema validates -> scientific validity;
- source is reachable -> source identity is verified;
- candidate exists -> authorized;
- authorized -> published;
- publication -> v4.2 finding;
- challenge metrics -> population inference;
- scientific validity -> redistribution rights.

---

## 26. Evidence/event taxonomy for engineering records

Use explicit evidence types in issues, successors, and PR descriptions.

### SOFTWARE_CONTROL

Code/schema/tests exist and pass for declared behavior.

Does not imply real execution.

### HOSTED_EXECUTION_EVIDENCE

An exact hosted run occurred with retained identity and artifacts.

Does not imply human scientific/governance approval.

### SOURCE_IDENTITY_EVIDENCE

Evidence attributable to an authoritative or independently credible source establishes identity/lifecycle state to the required level.

### HUMAN_REVIEW_EVIDENCE

Real reviewers produced dispositions/rationales over exact bound packets.

### HUMAN_GOVERNANCE_DISPOSITION

An attributable authorized decision binds exact evidence/artifact identities.

### SCIENTIFIC_EVALUATION_EVIDENCE

A declared analysis over frozen evidence establishes metrics/uncertainty within its stated inference scope.

### RIGHTS_DISPOSITION

An attributable review defines permitted/prohibited use and redistribution.

### RELEASE_CANDIDATE

Exact verified noncanonical S2 candidate.

### RELEASE_AUTHORIZATION

Separate exact decision over one candidate.

### PUBLICATION_EVENT

Separate evidence that the authorized release became the public canonical release.

### ASSESSMENT_TRIGGER / ASSESSMENT_DECISION

Landscape trigger and v4.2 assessment authority remain separate events.

---

## 27. Observability and run-manifest requirements

Any operational or research run used as gate evidence SHOULD record, as applicable:

- run ID;
- run attempt;
- event type;
- start/end timestamps;
- repository SHA;
- package/build identity;
- configuration digest;
- policy digest;
- source registry digest;
- source IDs;
- target IDs/counts;
- expected source count;
- attempted source count;
- successful source count;
- failed source count;
- skipped/not-due count;
- partial-source state;
- retry count;
- resume lineage;
- network mode;
- model/provider/version/configuration;
- capture/replay identities;
- output digests;
- evidence-role classification;
- S2 mutation flag;
- authority flags;
- cost where relevant.

Gate evidence MUST preserve enough information to reproduce or independently verify the claimed behavior.

---

## 28. Issue/PR completion rule

An issue SHOULD close only when its declared outcome has actually been reached.

A merged preparatory control PR does not automatically close a scientific/governance issue if real evidence is still missing.

For each open programme issue, maintain a clear distinction between:

- control implemented;
- real inputs acquired;
- execution completed;
- human disposition completed;
- scientific interpretation completed;
- gate state changed.

---

## 29. Current next-actions queue

This queue is intentionally short and ordered by real dependency value. Re-read live state before acting.

1. Execute and review the Workbench Phase-3 external proof for issue #287.
2. Obtain admissible SRC-14-021/SONA identity-lifecycle evidence; if positive, append the route successor and obtain the next qualifying normal scheduled due-cycle for G0.
3. Obtain the six-component PATSTAT provenance package and execute the scientific reconstruction; separately finish PATSTAT rights review.
4. Execute the real S3 D3 60-family pilot, human calibration, frozen 240-family selection, final labeling, and D3 freeze.
5. Execute the real S3 D4 60-item pilot, human calibration, frozen 240-item selection, final labeling, and D4 freeze.
6. Assemble exact frozen D3+D4 evidence and record a real human G2 disposition.
7. Continue sequentially through G3-G12 under the gate contracts in this specification.

If an item is externally blocked, proceed with independent parallel work that does not prejudge the blocked outcome.

---

## 30. Definition of engineering success

Engineering success is not the number of PRs merged.

A change is valuable when it does at least one of the following:

- removes a proven implementation defect;
- creates reproducible execution evidence;
- acquires previously missing provenance;
- creates real human reference evidence;
- resolves an identity/lifecycle uncertainty;
- establishes a measured scientific result within a valid inference design;
- resolves rights/containment;
- passes a governed gate;
- improves traceability, reproducibility, or authority separation;
- creates an exact governed public release or reproducible product.

The programme's controlling engineering principle is:

> Fix what is proven broken. Measure before scaling. Preserve authority boundaries. Advance research in parallel. Publish only from exact, attributable, evidence-bound state.
