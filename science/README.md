# vNext science graph

The science layer converts provider-specific literature retrieval into reproducible discovery candidates. It does not convert search results into canonical scientific claims.

The pipeline is:

`frozen discovery protocol -> deterministic provider query compilation -> provider adapter -> acquisition freeze -> provider-attributed candidate -> raw-response provenance verification -> exact-identifier resolution candidate -> relevance adjudication -> later canonical graph projection`

Cross-provider metadata is preserved until identity resolution is explicit. DOI, PMID, PMCID, and `OPENALEX_WORK` identifiers use the vNext identity namespace contract. Similar title or author strings can create a resolution candidate only; they cannot authorize a canonical merge.

## Frozen first-acquisition scope

`discovery-protocol-v0.1.json` fixes six query families and the 2015-01-01 through 2026-08-20 priority window. `query-compilation-v0.1.json` fixes how that protocol is compiled for the first credential-free providers, Crossref and Europe PMC.

The priority window is partitioned into inclusive calendar-year query units. Every discovery term is compiled separately for every window and provider. This produces 768 deterministic query units: 384 Crossref and 384 Europe PMC. Partitioning bounds cursor walks, supports exact resume/retry, and prevents one long traversal from being mistaken for an immutable provider snapshot.

Each query-unit request identity binds the provider, endpoint, parameters, client identity, query family, exact discovery term, date window, adapter, and source universe. The v0.1 client identity uses public unauthenticated access and the fixed User-Agent `neuroai-observatory-data/0.1 (+https://github.com/fraware/neuroai-observatory-data)`. No email identity, polite-pool enrollment, credential, or authenticated access is claimed by this compilation.

Crossref uses `query.title`, bounded `from-pub-date` / `until-pub-date` filters, 1,000-row cursor pages, and the provider-reported `total-results` as the query-unit denominator. `query.title` is a scored textual query; membership is discovery metadata, not an exact phrase assertion.

Europe PMC searches each frozen phrase in title or abstract within a bounded `FIRST_PDATE` interval, uses `resultType=core`, JSON, 1,000-row cursor pages, and `hitCount` as the query-unit denominator. Its `source` database code and `id` are both part of the adapter's required provider-native identity surface; the provenance verifier fails closed if captured Europe PMC records omit the source code or if one bare id is observed under multiple source databases in the same acquisition bundle.

Because terms overlap, there is no additive aggregate denominator across all query units. A deduplicated union is a derived view. `COMPLETE` is meaningful only for an individual frozen query unit whose traversal reconciles exactly to its provider-reported denominator, or for the full plan only when every unit is complete.

## Acquisition and custody boundary

`scripts/compile_science_queries.py` produces a deterministic, hashed request plan. Compiling a plan sends no network request and creates no acquisition evidence.

`scripts/acquire_science_candidates.py` is the explicit live runner. It:

- refuses to place acquisition output inside the Git repository;
- uses serial HTTP retrieval with retry/backoff for transient failures;
- content-addresses raw response bytes by SHA-256 outside Git;
- records request identity, cursor in/out, response digests, byte counts, selected provider headers, provider totals, and observation times;
- fails a query unit closed if the provider denominator changes, the cursor stalls before the denominator is reached, a page is unexpectedly empty, required candidate fields are missing, or a transport/parser error prevents exact exhaustion;
- issues a coverage report only for a complete query unit;
- emits exact-identifier deduplication candidates without fuzzy matching or canonical merges;
- distinguishes scoped acquisition from full-plan completion;
- marks all acquisition output `NOT_RELEASE_ELIGIBLE_UNTIL_DURABLE_CUSTODY_AND_RIGHTS_REVIEW`.

`scripts/verify_science_acquisition.py` independently re-hashes the frozen plan, candidate JSONL files, raw custody bytes, deduplication report, query-unit state, generated freezes, and coverage records. It reconstructs deterministic `candidate-manifest.json` and `coverage-index.json` products only after those checks pass. Candidate counts are explicitly occurrence counts across overlapping query units, not unique-publication counts.

`scripts/verify_science_candidate_provenance.py` verifies that every candidate's `source_record_sha256` and `observed_at` resolve back to an exact record inside a content-addressed captured provider response. This creates a cryptographic bridge from normalized discovery candidates back to raw provider custody without putting provider bytes in Git.

Raw provider responses remain outside Git. A checked-in acquisition freeze may later record request identity, provider/source state, response-manifest digest, exhaustion state, observed count, and the content-addressed storage class only after raw custody is durable and redistribution/publication rights have been reviewed.

The first protocol prioritizes 2015 through the declared evidence cutoff for operational acquisition, then backfills 2000–2014 and earlier work in separate immutable freezes. Priority windows control work order and do not rank scientific importance.

`STATUS=FROZEN_PROTOCOL_NO_PRODUCTION_ACQUISITION_YET` remains intentional until a real provider acquisition has been executed, raw bytes have durable custody, and the resulting manifests have been independently validated. CI tests acquisition, custody, and provenance mechanics using fake transports only; it deliberately performs no live provider retrieval.
