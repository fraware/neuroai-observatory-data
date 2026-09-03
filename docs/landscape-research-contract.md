# Landscape Research Contract

Status: **PRE-G1 draft technical contract; not a G1 approval, not a publication authorization, and not new G0 execution evidence**.

## Purpose

`LANDSCAPE_RESEARCH_CONTRACT_v0.1` is the machine-readable D1 contract for bounded NeuroAI landscape research. It exists to keep discovery, extraction, taxonomy work, and later governance review aligned around one controlled set of questions, units, evidence rules, interpretation limits, and containment boundaries.

The contract remains technical-only. It does not authorize G0 or G1, repin Workbench, mutate canonical S2 state, publish findings, or claim complete coverage of the NeuroAI landscape.

## Hard External Blocker

Workbench PR `#267` remains an external gate. Until that PR is merged and independently verified on Workbench `main`, this repository must not:

- repin Workbench SHA for recovery work;
- claim fresh G0 execution evidence;
- advance any execution-state successor on the basis of unverified external changes.

This D1 implementation therefore prepares PRE-G1 contract readiness only. It does not change Workbench pins or execution ledgers.

## Controlled Questions

The contract fixes seven controlling research questions. Together they govern:

- bounded identity and boundary discovery;
- capability and deployment characterization;
- separately evidenced product-patent and organization-product relations;
- claim-class to evidence-rule mapping with maximum interpretation ceilings;
- explicit inclusion, exclusion, borderline, and abstention behavior;
- evaluation-before-scale requirements;
- protected-data, approval, and publication boundaries.

D1 binds all seven questions. D2 is expected to bind the subset concerned with controlled taxonomy, bounded interpretation, abstention, and evaluation readiness.

## Core Boundaries

The contract encodes these fail-closed rules:

- `g1_approved=false` and all authority flags remain false;
- a later human disposition must bind the exact approved artifact identity before G1 can pass;
- `candidate != authorization != publication` remains explicit;
- open-world discovery can trigger review, but not canonical claim creation;
- proxy-only or incomplete evidence must preserve abstention or borderline handling;
- organization, product, and patent identities stay distinct unless separately evidenced;
- S3 private labels, held-out membership, private review packets, and licensed/protected raw capture cannot enter public S2.

## Validation Model

Validation is intentionally offline and deterministic:

- JSON Schema enforces structural shape and allowed enums;
- `scripts/validate_landscape_research_contract.py` enforces semantic invariants, schema digest binding, deliverable/question coverage, authority limits, and repository-relative path safety;
- adversarial unit tests verify fail-closed behavior for authority escalation, missing question coverage, evidence-rule drift, path traversal, containment weakening, and integrity tampering;
- the GitHub Actions workflow runs with read-only permissions and no network-dependent steps.

## D2 Alignment Expectations

The open D2 PR should remain subordinate to this contract. In practice that means D2 must continue to:

- keep `g1_approved=false` and require later exact human governance binding;
- treat taxonomy assignment as distinct from inclusion;
- preserve explicit `UNKNOWN` and review-required states;
- keep proxy-only physiological sensing supporting-only;
- keep multilingual aliases distinct from canonical IDs;
- keep capability-context mapping bounded and non-predictive.

Once D1 lands, D2 should be checked for explicit references to the final D1 artifact identity and any terminology that should be normalized to D1 wording such as `WITHHOLD` versus `withhold`, bounded relation language, and approval/disposition semantics.
