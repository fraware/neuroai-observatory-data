# ADR 0001 — vNext NeuroAI entity–event–evidence graph

**Status:** Proposed for acceptance in issue #36  
**Parent programme:** #35  
**Decision scope:** Public canonical observatory data (`S2`) and the records required to build it  
**Production-data effect:** None

## Context

The existing observatory establishes a controlled public-data surface with immutable releases, source monitoring, provenance, lifecycle state, candidate refreshes, and explicit authority boundaries. Its historical corpus is intentionally organization-heavy. The next programme phase needs to represent the field as a connected, temporally explicit intelligence graph spanning organizations, people, systems, products, models, datasets, publications, trials, grants, patent families, regulatory events, safety events, capital events, facilities, and other material objects.

Increasing record volume without changing the data model would preserve the current organization-centric limitation. The vNext architecture therefore makes evidence-backed assertions, typed relationships, events, source observations, and declared source universes first-class records. The change must preserve all predecessor releases and the existing separation between software, public canonical data, protected evidence, generated artifacts, and immutable archive material.

This ADR fixes the authority model and graph semantics that later schemas and migrations must implement. It does not authorize a production migration, a new canonical release, or any substantive scientific, clinical, regulatory, safety, conformance, institutional, or UNESCO conclusion.

## Decision

### 1. Use six typed programme layers

The vNext observatory uses the following storage and authority layers.

| Layer | Name | Function | Authority |
| --- | --- | --- | --- |
| S0 | Source-universe definitions | Versioned scope, query or inclusion rules, cadence, rights class, denominator logic, and coverage semantics | Configuration authority only |
| S1 | Source observations | Retrieval metadata, immutable source state, hashes, normalized source records, and custody references | Source-state evidence; not canonical truth |
| S2 | Canonical graph | Accepted entities, assertions, relationships, events, identity bindings, and release state | Public canonical observatory state |
| S3 | Protected/licensed references | Metadata, digests, custody state, and controlled pointers for material that may not be redistributed | Out-of-repository evidence custody |
| S4 | Derived intelligence | Coverage reports, counts, graph measures, trends, translation indicators, gap indicators, and watchlists | Recomputable analytical output |
| S5 | Human products | CSV/Parquet exports, reports, dashboards, notebooks, policy products, and release packages | Generated presentation layer |

No S4 or S5 record may silently mutate S2. No S1 observation may become S2 merely because it was retrieved successfully.

### 2. Separate source observations from canonical assertions

A `SOURCE_OBSERVATION` records what an identified source exposed at an identified retrieval state. It establishes content identity and provenance. It does not by itself establish that the source statement is scientifically correct, legally dispositive, clinically adequate, complete, or applicable to another system.

An `ASSERTION` is the atomic canonical claim unit. It binds a subject, predicate, object or typed value, provenance, evidence state, temporal scope, and governance state. Material canonical relationships and events must be supported by one or more assertions or by an equivalent provenance-bearing record defined in a later schema.

The architecture prohibits a single scalar confidence score from replacing typed evidence, provenance, conflict, accessibility, or adjudication state.

### 3. Treat relationships and events as first-class records

A `RELATIONSHIP` is a typed edge between canonical objects. It has its own identity, temporal scope, provenance, and lifecycle.

An `EVENT` represents a materially time-bounded occurrence such as a regulatory decision, financing, grant award, trial status transition, safety action, partnership, acquisition, publication update, dataset release, or patent legal-status change.

Graph connectivity does not create substantive authority. A path such as `SYSTEM → TRIAL → PUBLICATION → REGULATORY_EVENT` is an evidence-navigation structure, not a proof of safety, efficacy, authorization outside the exact decision, or assessment conformance.

### 4. Use stable local identity and auditable external bindings

Every canonical object receives a stable observatory identifier that is independent of any provider identifier. External identifiers such as ROR, ORCID, DOI, PMID/PMCID, NCT, UDI, CIK, patent publication/application/family identifiers, and dataset identifiers are represented as typed bindings.

Automatic exact-identifier matches may create resolution candidates under later rules. Approximate or fuzzy matching may never silently merge canonical identities. Ambiguous matches remain explicit resolution cases until adjudicated.

A canonical identity merge, split, or supersession must be represented as a reviewable state transition with preserved predecessor identity.

### 5. Use bitemporal semantics

The graph distinguishes two time axes.

**Valid time** describes when a state or claim applies in the external world, using `valid_from` and `valid_to` where known.

**Transaction time** describes when the observatory accepted or superseded a canonical record, using an acceptance timestamp and successor lineage defined by later schemas.

Source retrieval time is separate from both. `retrieved_at` records when S1 observed a source state; it does not substitute for valid time or canonical acceptance time.

Unknown time bounds remain unknown. Missing dates must not be invented to satisfy schema convenience.

### 6. Preserve typed evidence states

The initial controlled evidence vocabulary is:

- `OFFICIAL_PRIMARY_SOURCE`
- `PEER_REVIEWED_SOURCE`
- `REGISTRY_SOURCE`
- `COMPANY_STATED`
- `SECONDARY_CORROBORATED`
- `SECONDARY_ONLY`
- `CONFLICTED`
- `INACCESSIBLE`
- `UNRESOLVED`
- `SUPERSEDED`

These states describe provenance and evidentiary condition. They do not assign universal evidentiary weight. Later domain adapters may add source-specific metadata without silently redefining these states.

### 7. Preserve explicit rights and custody classes

Every source universe and source observation must support an explicit rights/custody class:

- `PUBLIC_OPEN`
- `PUBLIC_TERMS`
- `LICENSED`
- `PROTECTED`
- `UNKNOWN`

`LICENSED`, `PROTECTED`, and unresolved `UNKNOWN` material must not be copied into public Git history unless a separate rights decision explicitly permits the exact fields and bytes. Public graph records may retain permitted metadata, content digests, and controlled custody pointers.

### 8. Define completeness against declared source universes

The observatory does not claim unbounded global completeness.

A `SOURCE_UNIVERSE` defines a reproducible discovery surface with a version, inclusion/exclusion rules, exact query or extraction configuration, cadence, rights class, primary identifiers, denominator logic, and known blind spots.

Coverage claims are valid only against an identified source-universe version. A release may state, for example, that all returned records under a frozen ClinicalTrials.gov NeuroAI query were processed. It may not transform that claim into “all NeuroAI trials globally” unless the declared universe itself warrants that statement.

### 9. Make change append-only

Historical governing releases remain immutable.

Corrections, new evidence, changed source states, identity changes, and changed relationships create successor records or successor releases. Production data must never be rewritten in place merely to present a cleaner history.

A later schema may permit mutable working files during candidate construction, but canonical release lineage remains append-only and reproducible.

### 10. Keep derived intelligence non-authoritative

A `DERIVED_INDICATOR` must identify its input release or content digests, algorithm/version, parameters, and generation time. Examples include publication velocity, network centrality, translation lag, funding totals, geographic concentration, patent-family counts, or evidence-gap indicators.

Derived indicators may prioritize review or support analysis. They cannot establish assessment findings, scientific truth, regulatory authorization, clinical safety, legal status beyond the underlying official record, or institutional endorsement.

### 11. Preserve the assessment boundary

The observatory answers what entities, evidence, events, and relationships exist within declared source universes and how they changed.

The v4.2 assessment system answers what evidence supports for an exact system boundary.

Observatory prominence, publication volume, funding, patent count, graph centrality, commercial visibility, or dataset scale cannot compensate for an unresolved exact-system identity, an applicable P0 failure, missing P0 evidence, an unsupported principal claim, an absent prohibited-inference boundary, or an unauthorized decision.

Accepted observatory changes may create assessment reopening candidates. They do not mutate assessments automatically.

### 12. Keep interoperability as an export concern

The internal canonical model remains the programme authority. Later work may expose JSON-LD, PROV-O, RO-Crate, RDF, Parquet, or graph-database projections. Those projections must be generated from canonical records and must not introduce stronger semantics than the internal record supports.

The vNext architecture does not require a graph database. Canonical records remain content-addressable, reviewable files suitable for deterministic release and independent verification.

## Initial canonical object catalogue

The first schema family will support these object types:

- `ORGANIZATION`
- `PERSON`
- `SYSTEM`
- `PRODUCT`
- `MODEL`
- `DATASET`
- `PUBLICATION`
- `TRIAL`
- `GRANT`
- `PATENT_FAMILY`
- `PATENT_DOCUMENT`
- `FACILITY`
- `REGULATORY_EVENT`
- `SAFETY_EVENT`
- `FUNDING_EVENT`
- `PARTNERSHIP_EVENT`
- `SOURCE`
- `SOURCE_OBSERVATION`
- `ASSERTION`
- `RELATIONSHIP`
- `DERIVED_INDICATOR`

Additional object types require a versioned vocabulary change.

## Initial record lifecycle

Later schemas will implement at least these resolution/lifecycle states where applicable:

- `CANDIDATE`
- `ACCEPTED`
- `REJECTED`
- `CONFLICTED`
- `UNRESOLVED`
- `SUPERSEDED`
- `WITHDRAWN`

State transitions must preserve authorship or authority metadata and predecessor lineage where the transition affects canonical state.

## Migration constraints

The first migration from predecessor organization records must be loss-aware.

Existing record identifiers, source references, verification states, bounded summaries, current/historical status, jurisdiction, and predecessor lineage must remain recoverable. The migration must produce a reconciliation report and must not infer new organizations, systems, relationships, funding, trials, or scientific conclusions from text similarity alone.

The predecessor release remains independently verifiable after migration.

## Rejected alternatives

### Keep an organization-centric table and add more columns

Rejected because science, trials, patents, grants, datasets, financing, regulation, and system-level evidence are many-to-many and temporally changing. Adding columns would hide provenance and force repeated or lossy values.

### Store a property graph as the only source of truth

Rejected because database-specific state would weaken content-addressed releases, diff review, independent verification, and long-term portability. Graph databases may be generated indexes.

### Treat each source document as one fact record

Rejected because documents contain multiple claims with different scopes, temporal validity, and evidentiary states.

### Use automated confidence scores as the main epistemic control

Rejected because a scalar obscures source class, conflict, access, exact-system applicability, and adjudication status.

### Merge public and licensed intelligence

Rejected because redistribution rights and public reproducibility differ. Licensed enrichment may contribute controlled metadata or review candidates but cannot leak restricted fields into public releases.

### Rewrite predecessor releases into the new model

Rejected because it would destroy the audit trail. vNext creates successor records and migration mappings.

## Consequences

The repository gains a larger schema surface and stronger referential-integrity requirements. Ingestion adapters must separate acquisition, normalization, entity-resolution proposals, assertion/event proposals, adjudication, and release. Cross-domain intelligence becomes possible without allowing graph-derived conclusions to outrun the evidence.

The first implementation PR after this ADR will add fail-closed schemas for entities, assertions, relationships, events, and source observations. It must not migrate production records until the schema and integrity tests are accepted.
