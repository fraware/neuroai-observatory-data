# PATSTAT public extract — rights/containment review from public evidence, 2026-09-18

## Purpose and status

This document advances issue #210 as far as the currently available public evidence permits.
It is a repository containment analysis, not legal advice and not a finding that any current
file either complies with or violates the applicable PATSTAT contract.

The decisive contract evidence remains unavailable in-repository: the EPO acceptance/order
record for the Autumn 2025 delivery, the terms and amendments actually incorporated into that
contract, any separate written redistribution authorization, and an accountable determination
of whether each row-level extract is an allowed licensee product or prohibited data “as such”.

The machine-readable successor is
`curation/PATSTAT_PUBLIC_EXTRACT_RIGHTS_REVIEW_2026-09-18_PUBLIC_EVIDENCE_SUCCESSOR_v0.2.json`.

## Current first-party EPO evidence

The current EPO database-licensing terms were rechecked on 2026-09-18:

- <https://www.epo.org/en/service-support/ordering/raw-data-terms-and-conditions>
- <https://www.epo.org/en/about-us/observatory-patents-and-technology/observatory-tools/patstat/new-to-patstat>

The published terms materially distinguish four concepts.

First, contract formation depends on the terms accepted for the selected database and the EPO's
acceptance. The current web page is therefore relevant evidence about the EPO's present
licensing framework, not proof of the terms incorporated into a particular Autumn 2025 order.

Second, Article 5.2 permits use of an EPO database for internal purposes and to create the
licensee's own product, including a machine-readable database, publication, or service containing
or based on EPO data. It simultaneously excludes a copy of the database or the data “as such”
from that product definition.

Third, Article 5.4 restricts making the EPO database, a copy, or data as such public and
restricts distribution of data as such unless the EPO has expressly authorized it in writing.
Articles 6.1–6.2 add control and security obligations. Article 10.2 requires the specified EPO
attribution for products and interfaces containing sourced EPO data.

Fourth, Article 17 permits later amendments to the terms. Current web terms alone cannot resolve
which wording and amendments governed the Autumn 2025 delivery.

The current PATSTAT access page independently confirms that PATSTAT Global is available through
several access routes, including a bulk-data product. That fact does not establish the contract
for the specific dataset used here.

## File- and field-level inventory

The public extract is heterogeneous. The rights question should be decided at file and field
level, not by treating every artifact as equivalent.

| File | Source-linked / direct fields | Derived fields | Fail-closed disposition |
|---|---|---|---|
| `ANALYSIS.md` | no row-level source text identified | narrative, tables, aggregate statistics | exact-contract review remains open |
| `README.md` | no row-level source text identified | documentation, aggregate statistics, attribution | exact-contract review remains open |
| `abstracts_sample.csv` | `docdb_family_id`, `title`, `abstract` | `stratum`, `score`, `neuro`, `ml`, `verdict` | highest-priority row-level rights question |
| `judged_sample.csv` | `docdb_family_id` | `stratum`, `score`, `neuro`, `ml`, `verdict` | row-level product/data-as-such determination required |
| `gold_labels.csv` | `docdb_family_id` | `stratum`, `gold_neuro`, `cheap_neuro` | row-level product/data-as-such determination required |
| `pool_frame.csv` | `docdb_family_id`, `earliest_year`, `office`, `family_size`, `g06n` | `bloc`, `similarity`, `ai_score`, `found_by_query`, `band`, `era`, `cluster`, `neuro`, `ml` | high-priority mixed row-level file |
| `strata.csv` | no row-level rows | aggregate sampling bands and counts | candidate aggregate public artifact, subject to contract review |
| `clusters.csv` | no row-level rows | aggregate/model topic output | candidate aggregate public artifact; review `top_terms` separately for expression-level concerns |
| `reproduce.py` | none identified | code only | no EPO row data identified |

“Source-linked” here is a provenance classification, not a legal conclusion that the individual
field is protected or non-redistributable.

## Conservative public profile if containment becomes necessary

If the accountable rights disposition concludes that the present row-level material should leave
the public repository, the smallest useful public scientific representation is already
identifiable.

Public candidates, still subject to exact-contract confirmation, are the estimator code,
aggregate sampling counts, aggregate reread/confusion statistics, approved aggregate topic
summaries, method documentation, and non-reversible provenance commitments. Controlled S3 should
hold direct title/abstract text, family membership lists, row-level source identifiers,
row-level bibliographic/source-derived fields, mixed feature frames linked to those identifiers,
and any licensed raw extraction.

Where reproducibility needs evidence that a controlled row set has not changed, public opaque
digests or commitments are preferable to publishing the row membership itself. Executable tests
should use synthetic or independently licensed fixtures if row-level licensed inputs have to be
contained.

This profile is **precomputed only**. It is not currently authorized for execution.

## Scenario-specific corrective action

### Verified contract or written authorization covers the current public fields

Retain only fields demonstrably inside the verified scope. Preserve the required EPO attribution
and any applicable security/data-protection obligations. Bind the exact contract or authorization
evidence to a successor control. No history rewrite follows merely from receiving clearance.

### Generic product-versus-data-as-such structure applies, with no field-specific authorization

Obtain an accountable product-versus-data-as-such determination for each row-level file. Pending
that determination, the conservative public profile above is the prepared containment target.
The direct-text sample and the mixed row-level pool frame receive the highest priority because
they expose the most source material.

### Verified contract or authoritative EPO response restricts the current row-level publication

Create a normal corrective successor that removes the affected files from the public branch,
retains controlled copies in S3, preserves hashes and aggregate audit evidence, and updates public
references so they no longer imply row-level availability.

Removing a file in a new commit does not remove it from Git history. History rewriting should
occur only if a verified contractual obligation or authoritative legal/licensor instruction
specifically calls for purging historical objects. That decision should not be inferred from the
generic public terms alone.

### Exact contract evidence remains unavailable

Keep `RIGHTS_REVIEW_OPEN_FAIL_CLOSED`. Do not treat public presence, attribution, or derived
scientific value as evidence of redistribution clearance. Any temporary containment decision
should be made by the accountable rights owner using the precomputed public/S3 profile, with the
decision and authority recorded explicitly.

## Minimum unresolved inputs

The review has been narrowed to four decisive inputs:

1. the EPO acceptance/order record for the Autumn 2025 PATSTAT delivery and the terms it incorporated;
2. any amendments notified to the licensee and effective for that delivery;
3. any separate written EPO authorization covering redistribution or public row-level publication;
4. an accountable legal/licensor determination of whether each retained row-level file is an allowed
   licensee product or data as such.

Until those inputs are verified, no file is marked rights-cleared, no deletion or history rewrite
is authorized, and the extract must not be cited as cleared public programme evidence.
