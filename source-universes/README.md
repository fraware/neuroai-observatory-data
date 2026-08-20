# vNext source universes

This directory defines controlled acquisition universes for the NeuroAI intelligence graph.

A source-universe record is **planning and control metadata**. It does not establish that any source has been ingested, that any provider statement is true, or that a graph assertion is canonical. Production ingestion requires a separately frozen acquisition record, content-addressed observations, adjudication where required, and a candidate/release lineage.

## Closure rule

Completeness claims are always scoped to a frozen universe. `COMPLETE_WITHIN_FROZEN_QUERY`, `COMPLETE_WITHIN_PROVIDER_RELEASE`, `COMPLETE_WITHIN_DECLARED_REGISTRY`, `COMPLETE_WITHIN_DECLARED_CANDIDATE_SET`, and `COMPLETE_WITHIN_LICENSED_DELIVERY` are the only positive closure claims. `COVERAGE_ONLY_NO_COMPLETENESS` is required for open-world discovery.

Authentication and redistribution rights are independent. An interface can be technically accessible while redistribution remains restricted.

## Registry

`p0-registry-v0.1.json` is the first P0 planning registry. Records with `PROVIDER_SELECTION_PENDING` or `INTERFACE_VERIFICATION_PENDING` cannot be used as frozen production acquisition contracts.

## Coverage-state semantics

Coverage reports deliberately keep processing states separate. `discovered` is the observed population within the declared denominator; `resolved`, `sourced`, `temporally_verified`, and `linked` are independently measured processing states and may overlap. `stale`, `conflicted`, and `inaccessible` remain visible conditions instead of being silently dropped. `excluded` must reconcile to explicit exclusion reasons.

A zero or unavailable denominator requires null rates. A positive denominator requires exact recomputation of every published rate from integer counts.

`coverage-example.synthetic.json` is synthetic contract data only and is never a production coverage claim.
