# vNext identity foundation

Identity is controlled separately from entity content.

An external identifier record preserves the value exactly as observed, records a deterministic normalized form, binds provenance to a source observation, and remains namespace-scoped. A normalized identifier can support an entity-resolution candidate; it does not establish entity equivalence by itself.

## Resolution workflow

1. Register an observed identifier without rewriting the source value.
2. Normalize it under a versioned namespace rule.
3. Validate the namespace, syntax, applicable entity type, and provenance.
4. Generate an entity-resolution candidate from exact identifiers, deterministic rules, similarity, graph signals, or manual evidence.
5. Record an explicit human adjudication.
6. When `SAME_ENTITY` is accepted, create a later canonical successor operation. The decision record itself performs no mutation.

Similarity scores, names, shared domains, co-authorship, graph proximity, and other heuristic signals can rank candidates only. `automatic_merge_permitted` and `automatic_mutation_performed` are fixed to `false`.

Conflicting accepted namespace/value assignments remain visible as integrity failures requiring explicit resolution. Historical entity records are never rewritten in place by this layer.

The fixture under `fixtures/vnext/identity-bundle.synthetic.json` contains synthetic identifiers and synthetic entities solely to exercise the contract.
