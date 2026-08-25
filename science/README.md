# vNext science graph

The science layer converts provider-specific literature retrieval into reproducible discovery candidates. It does not convert search results into canonical scientific claims.

The pipeline is:

`frozen discovery protocol -> deterministic provider query compilation -> provider adapter -> acquisition freeze -> provider-attributed candidate -> raw-response provenance verification -> exact-identifier resolution candidate -> relevance adjudication -> later canonical graph projection`

Cross-provider metadata is preserved until identity resolution is explicit. DOI, PMID, PMCID, and `OPENALEX_WORK` identifiers use the vNext identity namespace contract. Similar title or author strings can create a resolution candidate only; they cannot authorize a canonical merge.

## Frozen first-acquisition scope

`discovery-protocol-v0.1.json` fixes six query families and the 2015-01-01 through 2026-08-20 priority window. `query-compilation-v0.1.json` fixes how that protocol is compiled for the first credential-free providers, Crossref and Europe PMC.

The priority window is partitioned into inclusive calendar-year query units. Every discovery term is compiled separately for every window and provider. This produces 768 deterministic query units: 384 Crossref and 384 Europe PMC. Partitioning bounds cursor walks, supports unit-level retry, and prevents one long traversal from being mistaken for an immutable provider snapshot.

The exact v0.1 compiled plan identity is:

- plan ID: `SCIENCE-QUERY-PLAN-CE2A8D1C0377A2E960B3`
- SHA-256: `ce2a8d1c0377a2e960b31eab194bf93bd87f350be2f788abc315a079092c504e`

The acquisition runner and verifier both reject a different internally rehashed plan. A truncated, reordered, or modified query set therefore cannot impersonate the frozen Phase 4 plan merely by recomputing its own hash.

Each query-unit request identity binds the provider, endpoint, parameters, client identity, query family, exact discovery term, date window, adapter, and source universe. The v0.1 client identity uses public unauthenticated access and the fixed User-Agent `neuroai-observatory-data/0.1 (+https://github.com/fraware/neuroai-observatory-data)`. No email identity, credential, or authenticated access is claimed by this compilation. A live transport whose User-Agent differs from the frozen identity is rejected before retrieval.

Crossref uses `query.title`, bounded `from-pub-date` / `until-pub-date` filters, 1,000-row cursor pages, and the provider-reported `total-results` as the query-unit denominator. `query.title` is a scored textual query; membership is discovery metadata, not an exact phrase assertion. Crossref candidate identity requires a usable DOI.

Europe PMC searches each frozen phrase in title or abstract within a bounded `FIRST_PDATE` interval, uses `resultType=core`, JSON, 1,000-row cursor pages, and `hitCount` as the query-unit denominator. Europe PMC provider identity is the source-aware pair `source + id`; the bare `id` is not treated as globally unique across Europe PMC source databases. Two records with the same bare id under different source codes remain distinct provider records until later identity resolution.

Because terms overlap, there is no additive aggregate denominator across all query units. A deduplicated union is a derived view. `COMPLETE` is meaningful only for an individual frozen query unit whose traversal reconciles exactly to its provider-reported denominator, or for the full plan only when every frozen unit is complete.

## Request and observation time

For each successful response returned to page processing, request time is recorded before transport and observation time after the response returns. Candidate `observed_at` is therefore an observation timestamp, not a request-start timestamp.

## Acquisition and custody boundary

`scripts/compile_science_queries.py` produces the deterministic, hashed request plan. Compiling a plan sends no network request and creates no acquisition evidence.

`scripts/acquire_science_candidates.py` contains the underlying query-unit, normalization, resume, freeze, coverage, and exact-identifier deduplication mechanics. Its original retry helper records only the HTTP 200 response returned to page processing; it is therefore not, by itself, the approved production entrypoint for Phase 4.

`scripts/acquire_science_candidates_strict.py` wraps those mechanics with attempt-level custody. For each logical page request it records every `HttpResult` returned by the transport before retry/termination logic can discard it. Each returned HTTP response body is content-addressed by SHA-256 outside Git and bound to logical-request index, attempt index, request/observation times, request-URL digest, cursor input, HTTP status, selected headers, byte count, and raw custody pointer. Transport exceptions that yield no HTTP response are recorded as attempt metadata without fabricating response bytes. Existing COMPLETE results that predate strict retry custody are rejected rather than silently reused.

`scripts/science_http_transport.py` disables automatic redirect following. Redirects are therefore returned as explicit HTTP responses, preserved by the strict custody layer, and fail closed instead of silently changing the effective endpoint.

`scripts/run_science_acquisition.py` is the gated execution entrypoint. It requires the no-auto-follow redirect policy, runs the strict acquisition path, independently verifies retry-response custody, runs the existing acquisition and provider-record provenance verifiers, writes the deterministic candidate/coverage products, and binds those verification products in `verification-envelope.json`. That envelope remains explicitly not release-authorized.

The underlying acquisition mechanics:

- refuse to place acquisition output inside the Git repository;
- validate the exact frozen plan and every query-unit request identity before retrieval;
- use serial HTTP retrieval with retry/backoff for transient failures;
- content-address successful page responses before provider parsing, preserving invalid-JSON, provider-contract, and denominator-drift responses that reach page processing;
- record request identity, cursor state, response digests, byte counts, selected provider headers, provider totals, and observation times;
- fail a query unit closed if the provider denominator changes, the cursor stalls before the denominator is reached, a page is unexpectedly empty, required provider identity/title fields are missing, or a transport/parser error prevents exact exhaustion;
- issue a coverage report only for a complete query unit;
- emit exact-identifier deduplication candidates without fuzzy matching or canonical merges;
- distinguish scoped acquisition from full-plan completion;
- reject unknown query-unit selections instead of silently dropping them;
- verify previously complete result, candidate-file, and raw-byte custody before reuse;
- archive incomplete attempts before a clean unit retry and archive prior run state before a new run is written;
- mark all acquisition output `NOT_RELEASE_ELIGIBLE_UNTIL_DURABLE_CUSTODY_AND_RIGHTS_REVIEW`.

`scripts/verify_science_retry_custody.py` independently reconstructs the attempt chain, verifies each returned HTTP response body against content-addressed custody, checks request URL and cursor binding, enforces monotone attempt sequencing, and requires every successful logical page request to terminate in one HTTP 200 response bound to the corresponding page response.

`scripts/verify_science_acquisition.py` independently validates the exact frozen plan, run identity, query-unit accounting, raw-response manifest, content-addressed bytes, request/cursor chain, provider-parsed page evidence, freeze/candidate/coverage schemas, candidate-file hashes, deduplication accounting, and release/canonical authority boundaries. Coverage and exact-identifier deduplication outputs are independently recomputed from verified acquisition state rather than trusted as supplied. It reconstructs deterministic `candidate-manifest.json` and `coverage-index.json` products only after those checks pass. Candidate counts are explicitly occurrence counts across overlapping query units, not unique-publication counts.

`scripts/verify_science_candidate_provenance.py` reconstructs provider records from the captured raw responses and requires each candidate object to reproduce exactly from its provider-native identity, source-record hash, observation time, and raw provider record. For Europe PMC, the check is explicitly source-aware. The acquisition verifier incorporates this provenance verification and binds its verification identity and digest into the candidate manifest.

These checks establish acquisition, custody, and provenance properties only. They do not establish NeuroAI relevance, scientific validity, canonical identity, or release authority.

### Pre-production verification status

Issue #46 tracks the attempt-level retry-response custody requirement. The strict custody implementation, no-auto-follow transport, independent retry verifier, and adversarial test surface are now present on the Phase 4 branch. The issue remains open because the exact current repository head has not produced a successful remote test execution: repository Actions jobs are still failing before any workflow step is instantiated. Production acquisition must not be represented as satisfying #46 until the exact implementation has been executed successfully in a suitable validation environment and the issue acceptance criteria are checked against that evidence.

Raw provider responses remain outside Git. A checked-in acquisition freeze may later record request identity, provider/source state, response-manifest digest, exhaustion state, observed count, and the content-addressed storage class only after raw custody is durable and redistribution/publication rights have been reviewed.

## Historical backfill and status

The first protocol prioritizes 2015 through the declared evidence cutoff for operational acquisition, then backfills 2000–2014 and earlier work in separate immutable freezes. Priority windows control work order and do not rank scientific importance.

`STATUS=FROZEN_PROTOCOL_NO_PRODUCTION_ACQUISITION_YET` remains intentional until a real provider acquisition has been executed in an approved environment, raw bytes have durable custody, all required verification layers have passed, and rights review has been completed. CI is designed to test contracts, compilation, acquisition mechanics, failed-response custody, retry-response custody, fail-closed redirect behavior, verification, and provenance using synthetic/fake transports only; it deliberately performs no live provider retrieval.
