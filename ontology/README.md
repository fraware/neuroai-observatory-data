# vNext observatory vocabulary

This directory contains the machine-readable vocabulary used to constrain the vNext NeuroAI entity–event–evidence graph.

`vocabulary-v0.1.json` is an architecture skeleton associated with ADR 0001. It enumerates initial object types, record kinds, evidence states, rights classes, resolution states, temporal semantics, and authority rules.

It is **not** a production ontology release and creates no canonical data authority. PR 2 will bind the accepted vocabulary to JSON Schemas and fail-closed integrity tests. Later interoperability work may generate JSON-LD, PROV-O, RDF, RO-Crate, Parquet, or graph-database projections from the canonical records without changing the internal authority model.
