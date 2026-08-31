# Current public governing state to Observatory v2 migration specification

Status: **noncanonical migration design; no successor authorization**

This specification governs the first deterministic projection of the current `data-v0.1.0-public-governing` records into the Observatory v2 object model. It does not authorize a v2 canonical release and does not permit editing the predecessor records.

## Source-of-truth input

The migration input is the immutable current public governing release:

```text
releases/data-v0.1.0-public-governing/records/
  source_monitor_registry_v1.5.json
  canonical_observatory_release_v1.4.json
  canonical_live_refresh_release_v1.6.json
  adjudicated_delta_v1.6.json
  canonical_successor_snapshot_v1.7.json
  public_disposition_summary.json
```

Supplemental records may be used only when the current effective-source projection already treats them as part of the programme input lineage. Their contribution must be reported separately from the six governing release records.

## Non-negotiable migration rules

1. Do not edit or regenerate the predecessor files in place.
2. Do not invent missing dates, amounts, identifiers, jurisdictions, evidence states, source links, or assessment states.
3. Preserve source identifiers and source-class semantics exactly unless a reviewed crosswalk explicitly records a successor identifier.
4. Preserve every current claim boundary and prohibited-inference statement. A v2 representation may strengthen a boundary but may not silently weaken it.
5. Preserve incomplete date precision. A year such as `2026` must not become `2026-01-01`; a date such as `2026-07-29` must not become an invented midnight timestamp.
6. Preserve current distinctions between company announcement, regulatory record, publication, preprint, media corroboration, registry metadata, and other source/evidence classes.
7. Preserve predecessor/current/reopening lineage.
8. Preserve missing/inaccessible/unresolved states as typed uncertainty, never as automatic failure.
9. Do not copy protected or non-redistributable source bytes into S2.
10. Generated v2 records remain noncanonical until a separate release decision authorizes a successor.
11. A historical predecessor field without record-level source linkage or knowledge time may be preserved only through an explicit migrated-predecessor unresolved state; migration must not silently manufacture ordinary v2 provenance.

## Target object families

Current data maps into these target families:

```text
ENTITY
SOURCE
OBSERVATION
ASSERTION
RELATIONSHIP
EVENT
ASSESSMENT_DEPENDENCY
REOPENING_DECISION
DISPOSITION_OR_PROVENANCE
LEGACY_PRESERVATION_RECORD
```

`LEGACY_PRESERVATION_RECORD` is a migration safety valve, not the desired end state. It may retain a meaningful predecessor field or record that has not yet received a semantically exact v2 mapping. It must include the original release, file, record locator, original field/value digest, and reason no normalized mapping was applied.

## High-level family mapping

| Predecessor family | Primary v2 representation |
| --- | --- |
| organization-array entries | stable `ENTITY` identity plus bounded `ASSERTION` records for descriptive/time-varying fields; assertions retain exact source IDs when present and use explicit migrated-predecessor unresolved linkage/time only when the predecessor lacks them |
| organization resolution | identity-resolution `DISPOSITION_OR_PROVENANCE`; successor/alias relationships where applicable |
| regional expansion | provenance/discovery disposition plus organization/geography assertions |
| capital and ownership events | `EVENT`; ownership/control only as separate source-supported relationship/assertion |
| representative model records | model `ENTITY` plus publication/checkpoint/license/dataset-lineage assertions |
| model/dataset registry objects | registry/benchmark `ENTITY` or event/assertion records; aggregate counts preserved as source-reported values |
| trial-site relationships | `RELATIONSHIP` with explicit source evidence and boundary |
| participant-authority relationships | typed `RELATIONSHIP`/`ASSERTION` with holder, scope, source and boundary |
| supplier dependencies | typed `RELATIONSHIP` with system-specific versus capability-only distinction preserved |
| source records | `SOURCE`; a migration observation may be created only for an actual predecessor retrieval/inspection time supported by the record |
| source monitor registry | non-substantive monitoring configuration; source references remain separate from canonical assertions |
| live-refresh source checks | `OBSERVATION` or migration provenance when an actual retrieval was recorded |
| new refresh sources | `SOURCE` plus associated `OBSERVATION` where supported |
| change candidates | noncanonical/candidate provenance; no automatic canonical assertion |
| adjudicated regulatory/market changes | `EVENT` and/or bounded `ASSERTION` |
| adjudicated model changes | model `ENTITY` plus bounded assertions |
| governance/leadership changes | `EVENT` |
| reopening decisions | `REOPENING_DECISION` |
| no-change confirmations | observation comparison/provenance, not a broad absence-of-event assertion |
| withheld claims | release/provenance boundary records; preserve wording |
| successor assessment delta | assessment dependency/reopening/provenance objects; exact assessment remains governed by Workbench semantics |
| public migration disposition summary | `DISPOSITION_OR_PROVENANCE`; no substantive truth authority |

## Observation creation rule

The migration must not manufacture a source observation merely because a source URL is present.

An `OBSERVATION` can be created from predecessor data only when the predecessor records an actual retrieval, inspection, source check, or equivalent observation time/outcome.

For baseline source records with `retrieved`, the migrated observation may use that predecessor retrieval date with preserved precision and migration provenance. If the predecessor does not contain exact retrieval bytes/hash, `content_sha256` remains null and capture state reflects the evidence actually present.

## Assertion creation rule

A v2 assertion must preserve the predecessor's supported interpretation and boundary.

Example transformation for a source-linked predecessor:

```text
legacy organization field:
  current_status = ACTIVE_OR_CURRENTLY_REPRESENTED
  source_ids = [SRC-0001]
  last_verified = 2026-07-29
  claim_boundary = ...

v2:
  subject = ORG-0001
  predicate = CURRENT_STATUS
  value = ACTIVE_OR_CURRENTLY_REPRESENTED
  source_linkage_state = SOURCE_LINKED
  source_ids = [SRC-0001]
  knowledge_time_state = EXACT_PREDECESSOR_TIME
  observed_at = { value: 2026-07-29, precision: DATE }
  claim_boundary = exact predecessor boundary
```

The migration must not strengthen the assertion to `ACTIVE_COMPANY`, `COMMERCIALLY_AVAILABLE`, or another interpretation unless that stronger state is separately supported and adjudicated.

### Migrated predecessor without source linkage

Lossless migration must also represent historical predecessor fields for which the old record did not encode source linkage. This exception is migration-only.

```text
source_linkage_state = PREDECESSOR_SOURCE_LINKAGE_UNRESOLVED
source_ids = []
review_state = MIGRATED_PREDECESSOR_STATE
record_state = NONCANONICAL_CANDIDATE
```

If the predecessor also lacks record-level knowledge time:

```text
knowledge_time_state = PREDECESSOR_TIME_UNRESOLVED
observed_at = null
```

This preserves predecessor state. It does **not** convert that state into ordinary source-backed v2 evidence. A later source-backed successor requires ordinary evidence discovery/registration, observation support, adjudication, and release authority.

## Exact v1.4 organization-array checkpoint

The immutable v1.4 `organizations` array contains 223 entries, not 217 array rows:

- 217 organization records;
- 6 entries explicitly reclassified as `NON_ORGANIZATION_PROVENANCE_NODE`;
- 154 source-linked entries, all with record-level `last_verified = 2026-07-29`;
- 69 entries without `source_ids` and without record-level `last_verified`, comprising 63 `LEGACY_ONLY` stubs and the 6 provenance nodes.

The six reclassified entries remain `PROVENANCE_NODE` entities. They must not be silently promoted back into the organization denominator. The 69 source-unresolved entries may be normalized only with the migrated-predecessor unresolved states above.

## Identity rule

Existing canonical IDs remain migration anchors. A v2 entity may preserve an existing `ORG-*`, `MDL-*`, source, event, relationship, or decision ID where the semantic object is unchanged.

If the v2 ontology requires a new identifier, the migration crosswalk must bind old and new IDs explicitly. The predecessor ID remains searchable and reproducible.

Entity identity is separate from descriptive claims. For organization migration, canonical name, aliases and explicit legacy identity linkage belong to the entity object; organization type, role, geography, current status, verification, evidence state, official URL, summary and priority are represented as bounded assertions while the full predecessor payload remains digest-bound for reconciliation.

## Temporal rule

The migration distinguishes:

- source publication/record time;
- predecessor retrieval/verification time;
- event/valid time;
- v2 migration execution time;
- future canonical publication time.

Migration execution time must never be substituted for the date a predecessor fact became valid or was observed. When predecessor knowledge time is absent, it remains unresolved.

## Field accounting proof

The migration verifier must produce deterministic accounting at file, record-family, and field level.

Minimum counters:

```text
input_files
input_records
input_fields
mapped_records
mapped_fields
preserved_legacy_records
preserved_legacy_fields
unmapped_required_fields
invented_values
claim_boundary_losses
source_reference_losses
```

The first candidate may contain explicitly preserved legacy fields, but it cannot be proposed for canonical authorization while meaningful required fields remain silently unmapped.

Hard blockers for a canonical v2 successor:

```text
unmapped_required_fields > 0
invented_values > 0
claim_boundary_losses > 0
source_reference_losses > 0
```

A zero count is a mechanical reconciliation result, not proof that the semantic mapping is scientifically correct. Domain review remains required.

## Record locators

Every migrated object must retain a deterministic predecessor locator sufficient to reconstruct where it came from, for example:

```text
predecessor_release_id
predecessor_file
predecessor_section
predecessor_record_id
predecessor_record_digest
```

For array records without stable IDs, use a deterministic index plus canonical record digest and document the limitation.

## Duplicate and overlap handling

The current governing corpus intentionally repeats some delta content across the v1.6 delta and v1.7 compact successor. Migration must not treat repeated representation as independent real-world events.

Deduplication requires explicit identity based on controlled record/event IDs and predecessor lineage. Matching text alone is insufficient.

## Assessment boundary

The migration may represent assessment identity, dependencies, reopening state, evidence cutoffs, and bounded successor consequences. It must not reinterpret v4.2 findings, collapse assessment decisions into observatory assertions, or infer a new conformance result.

## Validation sequence

1. verify the current governing manifest before migration;
2. load predecessor records without mutation;
3. inventory files, sections, records, fields, IDs, source references, boundaries, and temporal values;
4. apply deterministic mapping rules;
5. emit v2 noncanonical candidate records and field accounting;
6. verify referential integrity;
7. verify no protected/public-boundary violation;
8. compare counts, source references, claim boundaries, and temporal precision;
9. run domain review on representative and high-materiality mappings;
10. only then consider a separate canonical successor release process.

## Current implementation state

The foundation branch now contains two narrow semantic migration slices:

- all 224 v1.4 source records into draft `SOURCE` plus supported migration `OBSERVATION` records;
- all 223 v1.4 organization-array entries into 217 `ORGANIZATION` entities, 6 `PROVENANCE_NODE` entities, and bounded migrated assertions.

Both slices are explicitly noncanonical and hard-code `canonical_successor_ready = false`. The whole-corpus accounting scaffold still reports semantic reconciliation as not executed for the remaining record families. No canonical v2 successor exists.
