# vNext migration non-goals

This document constrains the initial NeuroAI knowledge-graph migration. It applies to issue #35 and the implementation sequence governed by ADR 0001.

## No predecessor rewrite

Existing governing releases, historical releases, curation records, and supplemental records remain unchanged. vNext creates mappings and successor records. It does not edit historical bytes to make the archive resemble the new model.

## No production migration in the architecture PR

The architecture-lock change introduces the ADR and vocabulary skeleton only. It does not create a vNext canonical release, change the current public pointer, authorize the v2.3 development candidate, or alter assessment state.

## No inference-by-schema

A new graph type does not authorize new facts. The migration must not infer a system, product, partnership, trial link, funding relationship, patent relationship, dataset dependency, or person role solely because the new schema has a field for it.

## No silent identity merge

Name similarity, domain similarity, shared addresses, overlapping authors, or provider suggestions may produce resolution candidates. They cannot merge canonical identities without the explicit resolution workflow defined by later implementation.

## No flattening of source and truth

Company statements, registry submissions, peer-reviewed evidence, official regulatory records, secondary reporting, inaccessible evidence, conflicts, and unresolved material remain distinguishable. A successful retrieval does not imply acceptance of the source claim.

## No protected or restricted licensed payloads in public Git

Protected evidence and restricted licensed fields remain in their existing custody domain. Public records may contain permitted identifiers, rights metadata, digests, and controlled references where allowed.

## No generated product as master input

Excel, Word, PDF, dashboards, notebooks, CSV analytics, and graph-database indexes are generated views. They do not replace canonical machine-readable records as the source of truth.

## No automatic assessment mutation

An accepted observatory change may create a reopening candidate. It cannot rewrite a v4.2 finding or decision automatically.

## No global-completeness claim

The first vNext release will report coverage against declared source universes. It will not claim exhaustive global discovery unless a future source-universe definition can support that exact claim.

## No scalar confidence shortcut

The programme will not replace evidence states, provenance, conflicts, accessibility, identity resolution, or authority decisions with an opaque confidence score.

## No graph-database dependency

A graph database may be generated for search or analysis. Canonical public data must remain reproducible from portable, content-addressable release records.

## No cross-domain layer until domain provenance is stable

Science, clinical/regulatory, public-funding, patent/IP, capital, and neural-data adapters should establish their own source contracts and frozen universes before cross-domain analytics are promoted to canonical release products.
