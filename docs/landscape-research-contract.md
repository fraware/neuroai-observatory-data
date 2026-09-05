# Landscape Research Contract

Status: **PRE-G1 draft technical contract.** Technical validation does not approve G1, establish scientific truth, authorize S2 mutation/publication, or alter v4.2 assessment state.

## Purpose

`LANDSCAPE_RESEARCH_CONTRACT_v0.1` is D1 for the NeuroAI Landscape Observatory. It freezes the research questions, unit model, source-universe semantics, claim/evidence ceilings, inclusion and abstention rules, evaluation gates, model/human authority boundaries, containment controls, stopping rules, and downstream assessment-trigger boundary that must be reviewable before G1.

The governing substantive objective is to build and maintain an evidence-governed global NeuroAI landscape that identifies technologies, actors, products and commercialization pathways; detects commercially relevant applications missed by conventional clinical/scientific terminology; maps observed capabilities and deployment contexts to bounded governance concerns; and routes only exact systems with sufficient evidence toward separate v4.2 assessment or reopening review.

## Seven controlling research questions

The contract now encodes the programme's seven substantive questions directly:

1. What identifiable NeuroAI technologies and capabilities are being developed, and how are they changing over time?
2. Which organizations own, develop, finance, supply, commercialize or deploy those capabilities, and where are they located?
3. Which technologies have moved from research or patenting into identifiable products, services or deployments?
4. Which commercially relevant applications are missed when identification begins from conventional clinical/scientific neurotechnology terminology?
5. How concentrated are relevant patents, companies, product classes and capabilities by actor, jurisdiction and application context?
6. Which existing governance concerns are implicated by capabilities already observable in real products or deployment contexts?
7. Which exact systems merit deeper evidence-bounded v4.2 assessment or reopening of an existing assessment dependency?

Six secondary operational questions quantify gray-third recall gain, open-world marginal yield, classifier/subgroup error, patent-product link error, multilingual sensitivity, and unresolved expert disagreement.

## Output-to-question contract

D0 through D18 are represented explicitly with gate and research-question bindings. D1 covers all seven controlling questions. D2 is bound to `RQ-01`, `RQ-04`, `RQ-06`, and `RQ-07`: capability/context taxonomy supports technology characterization, gray-third retrieval, bounded governance mapping, and exact-system characterization for assessment-trigger review; it does not independently establish inclusion, commercialization, or an assessment outcome. D18 alone binds the exact-system assessment-trigger question as its primary research output.

## Discovery-universe semantics

The contract separates:

- **Structured denominated sources**: patent, publication, clinical-trial, grant, and regulatory databases. Their denominator/paging state must be explicit.
- **Open-world protocol channels**: company/product pages, news, conferences, licensed commercial-discovery databases, expert nominations, public-web/media discovery, multilingual web discovery, and snowball/co-mention leads. Their scientific object is the declared protocol, provenance, marginal yield, failure state, and stopping rule—not a global denominator.
- **Mixed multilingual/regional work**: may combine structured and open-world sources, but must preserve the source-specific universe semantics.

A company/product page is therefore not treated as a structured denominator. Source class also does not determine truth; claim strength remains evidence- and review-bounded.

## Inclusion and gray-third semantics

Every candidate is adjudicated as `INCLUDE`, `EXCLUDE`, `BORDERLINE`, or `ABSTAIN`. Incomplete evidence requires abstention; borderline cases require recorded rationale; physiological proxy-only evidence cannot establish inclusion.

"Gray third" is a retrieval and boundary-validation stratum, not a canonical population class. The six controlled search families are attention/vigilance, cognitive/affective state, adaptive interfaces, cognitive enhancement/training, behavioral personalization, and nontraditional sensing form factors. A gray-third hit remains a candidate and follows the same governed disposition path as any other candidate.

## Identity and patent-product concordance

The unit chain remains:

`SOURCE -> OBSERVATION -> CANDIDATE_OR_EXTRACTION -> ASSERTION_OR_RELATIONSHIP_OR_EVENT`

`ORGANIZATION`, `PRODUCT`, `SYSTEM`, and `PATENT` identities remain distinct. Fuzzy names cannot merge identities; unresolved literals are retained; parent/subsidiary and acquisition state are evidenced and time-scoped; patent publication/family identity and exact product/product-family identity stay separate.

Patent-product concordance uses L1-L4 evidence:

- L1: explicit product-patent binding in company/product documentation or authoritative records.
- L2: company attribution plus strong technical/timing evidence.
- L3: multi-source inferred alignment without explicit binding.
- L4: semantic/model similarity only.

L1/L2 links used for report claims require human review. L3 quantitative use requires a validated link-error study. L4 is discovery/ranking only and is excluded from established-link counts.

## Model and human authority

Models may assist retrieval/query expansion, extraction, classification, adjudication support, policy-mapping support, and bounded drafting. Model consensus is never ground truth. Provider/model/version provenance is required. Governed acceptance/rejection, G1 disposition, and publication authority remain attributable human decisions.

Difficult positives, negatives, gray cases, ontology ambiguities, concordance conflicts, and governance-mapping edge cases are prioritized for expert review. Genuine disagreement may remain unresolved.

## Governance mapping

The controlled chain is:

`OBSERVED_PRODUCT_OR_SYSTEM -> CAPABILITY + DEPLOYMENT_CONTEXT -> MECHANISM -> GOVERNANCE_CONCERN -> POLICY_INSTRUMENT_OR_RECOMMENDATION`

Concern classes and mechanisms are human-defined before model assistance. The bounded claim form is:

`could implicate concern {concern} under conditions {conditions} through mechanism {mechanism}`

Predicted company behavior, company intent, inevitable harm, and detailed harmful-use instructions are outside this research contract.

## Evaluation before scale

G2-G5 acceptance logic is machine-represented. Human-adjudicated benchmark labels, a frozen held-out split, inaccessible test membership during tuning, recorded hashes/provenance, precision/recall, calibration, threshold sensitivity, abstention, model disagreement, false-negative analysis, subgroup error, inter-rater agreement, and marginal-yield/coverage analysis are required before production filtering or scale.

Thresholds are predeclared from research requirements, not reverse-engineered to current model performance. Cost optimization follows quality constraints.

## Data and publication boundary

Protected/private labels, held-out membership, private review packets, and licensed/protected raw captures do not enter public S2. Licensed data is subject to purpose limitation, minimization, and redistribution-rights checks. Public claims require permitted evidence or bounded derived assertions.

`candidate != authorization != publication`

Technical validity never crosses that authority boundary.

## Stopping and change control

Open-world discovery stops only under a declared round/channel budget plus marginal-yield and failure-state accounting. Saturation under that protocol cannot establish global completeness. Boundary or term changes require recorded rationale; semantic changes require a versioned successor; expert dispositions do not silently apply; historical control artifacts are not rewritten.

## v4.2 boundary

Landscape evidence may produce a recommendation for exact-system assessment or dependency reopening. The trigger must bind an exact system/configuration and sufficient evidence, carries no assessment effect itself, does not change v4.2 requirement meanings, and requires a separate attributable reopening/assessment decision.

## Validation

The offline validator:

- enforces the strict JSON Schema subset used by D1;
- checks exact D0-D18, question, claim, evidence-rule, source, gray-family, link-tier and G2-G5 registries;
- checks the schema's canonical SHA-256 binding;
- rejects path traversal and unauthorized schema fields;
- fails closed on authority escalation, open-world completeness drift, benchmark leakage, identity collapse, weak-link promotion, and assessment-boundary drift.

The adversarial unit suite exercises these boundaries. The GitHub Actions workflow remains read-only and network-independent.

## G1 disposition

Successful validation means only that the PRE-G1 artifact is internally consistent. G1 may be recorded only after an attributable human decision over the exact D1 and D2 identities. Until then `g1_approved=false` remains mandatory.
