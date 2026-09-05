# NeuroAI patent evidence — data extract

A sample of the working data behind *Mapping the NeuroAI Frontier*, enough to see how the
data is shaped and how the estimates are produced. Everything here is derived; nothing in
it is needed to reproduce the pipeline itself, which lives in the repository.

Unit of observation throughout is the **DOCDB simple patent family**, not the individual
publication. A family groups the filings of one invention across offices, so counting
families avoids counting the same invention once per country.

Source: PATSTAT Global, Autumn 2025 edition. 104,742,722 families in total; 69,273,903
of them carry an English-language abstract, and those are the ones any text-based method
can see.

> **Rights status — review open.** Issue #210 is the governing rights/containment review
> for this public extract. The exact licence/order terms applicable to the Autumn 2025
> PATSTAT delivery have not yet been verified in-repository, so public presence must not
> be treated as a finding that every row-level field is cleared for redistribution.
> `abstracts_sample.csv` is specifically classified as rights-unresolved because it
> contains title and abstract text originating from the EPO alongside derived labels and
> scores. Other row-level files remain subject to the same file/field-level review.
>
> Under the EPO's currently published database-licensing terms, a licensee may create its
> own product containing or based on EPO data, while the EPO database or data “as such”
> may not be made public or distributed as such without express written authorisation.
> The current terms also require the attribution below for products containing sourced
> EPO data. This repository statement is a containment control, not a legal conclusion
> about the exact contract applicable to this extract.
>
> **This product contains data sourced from EPO databases, © European Patent Organisation.**
>
> Current published terms: https://www.epo.org/en/service-support/ordering/raw-data-terms-and-conditions

> **Scientific status — preliminary Baseline A.** Issue #220 governs scientific integration
> of this extract. The 49,671-family population estimate and 67.0% query-recall estimate
> are preliminary model-anchored point estimates for the 69,273,903-family English-abstract
> sampling frame under the historical rubric. They are not an enumerated set of confirmed
> NeuroAI families, a global patent census, a frozen D3 benchmark, or a G5-validated result.
>
> `judged_sample.csv` was judged by a 26B model. `gold_labels.csv` contains 333 second reads
> by a stronger model; despite the filename, these are **not human gold labels**. The public
> `reproduce.py` reconstructs the headline point estimates, but the extract does not contain
> enough second-stage sampling/estimator evidence to independently certify the README's
> reported confidence interval or uncertainty for the 67.0% recall ratio.
>
> The historical labels are `0 = not relevant`, `1 = borderline`, `2 = relevant`, while
> `reproduce.py` maps only `2` to the headline binary relevant state. The approved Observatory
> research contract preserves `INCLUDE`, `EXCLUDE`, `BORDERLINE`, and `ABSTAIN` as distinct
> governed dispositions. Historical model labels therefore must not be imported as D3 human
> gold or silently reinterpreted as the approved four-way boundary.

---

## Files

### `strata.csv` — the sampling design (9 rows)

A classifier scores all 69.3M families for relevance. The score is cut into 9 strata;
`N_families` is how many families fall in each, `n_judged` how many we actually read.
The top three strata are small enough to have been read completely.

This is the whole trick. Nobody can judge 69 million abstracts, and a simple random
sample of them would return essentially nothing — relevant families are about 7 in every
10,000. Stratifying on a cheap score and over-sampling the top puts the reading budget
where the variance is.

### `judged_sample.csv` — 235,738 judged families

One row per family in the stratified sample.

| column | meaning |
|---|---|
| `stratum` | which of the 9 score bands it was drawn from |
| `score` | the classifier score, 0–1 |
| `neuro` | 0 not relevant, 1 borderline, 2 relevant |
| `ml` | 1 if the family also involves AI/ML |
| `verdict` | the judge's raw output token |

Judged by a 26B open-weight model reading a written rubric, one abstract at a time. Four
rows have a malformed verdict and empty labels; they are dropped as missing rather than
guessed at.

### `gold_labels.csv` — 333 families read twice

A probability subsample re-read by a much stronger model against the same rubric.
`cheap_neuro` is what the 26B model said, `gold_neuro` what the strong model said. The
gap between these two columns is what corrects every number in the study — see below.

The filename is historical. These are stronger-model rereads, not human-adjudicated gold
labels and not the Observatory's D3 reference standard.

### `pool_frame.csv` — 118,629 families found by query

The families retrieved by the original search strategy, with what we know about each:
first filing year, office, bloc, family size, embedding similarity, an AI score, which
query found it, its topic cluster, whether it carries a G06N (machine learning) CPC code,
and — where it also fell into the judged sample — the judge's verdict.

Note the `found_by_query` column. `application:epilepsy` means the family surfaced under
that application-side query; `cross:deep brain stimulation|epilepsy` means it surfaced
under a crossing of two. This is the provenance record, and it is what makes it possible
to ask which parts of the field a given query is responsible for.

The exported `cluster` field is under an open integrity review in issue #220 because rows
inspected in the public extract carry values inconsistent with the 0–20 identifiers in
`clusters.csv`. The field must not be treated as validated row-level cluster provenance
until that export question is resolved. It is not consumed by `reproduce.py`.

### `clusters.csv` — 21 topics

UMAP + HDBSCAN over the embeddings, labelled by the terms that distinguish each cluster.
Descriptive, not an input to any estimate.

### `abstracts_sample.csv` — 396 families with text

Roughly 44 per stratum, with title, abstract and verdict, so the judgements can be read
against what was actually judged. Read stratum 8 and stratum 2 side by side: the
difference between them is what the classifier is picking up.

---

## The estimate, and why it moves

Run:

```
python3 reproduce.py
```

which prints:

```
corpus relevant       49,671   (cheap-only would be 99,720)
pool relevant         33,277   of 118,629 retrieved families
pool recall            67.0%
missed                16,394   relevant families the queries never saw
```

Stdlib only, no dependencies, about a second. It reproduces the historical point estimates
reported by `pilot/ppi.py`. The full `pilot/ppi.py` implementation and second-stage sampling
metadata are not part of this public extract, so that statement is not an independent
reproduction of the full uncertainty calculation.

Two things are worth sitting with.

**The cheap-only number is almost exactly double the corrected one.** Take each stratum's
judged share of relevant families, multiply by that stratum's size, add up: 99,720. Then
correct each stratum by the average (strong − cheap) difference measured on the 333
double-read families, post-stratified within cheap-label class: 49,671. The 26B model is
systematically more permissive than the historical rubric. The public extract supports
reproduction of that point calculation. It does not by itself establish a human reference
standard or independently certify all uncertainty terms for the two-stage estimator.

The README historically reports a 95% interval of 40,256–57,854. That interval remains a
reported result pending the issue #220 estimator audit; `reproduce.py` does not print it,
and the public extract does not expose enough second-stage design information to certify
it independently.

**The queries find an estimated two families in three within the English-abstract frame.**
The pool assembled by keyword and concept search is estimated to contain 33,277 of the
49,671, giving the reported 67.0% point estimate and about 16,394 estimated relevant
families outside the pool. This is methodologically useful evidence against treating a
query-built set as the population. Its uncertainty and reference-standard validity remain
part of the issue #220 audit.

---

## What is not here

- The 81 GB of embedding vectors, and the classifier scores for all 69.3M families.
- Abstract text beyond the 396-family sample.
- The full pipeline and `pilot/ppi.py` estimator implementation referenced above.
- The exact second-stage inclusion probabilities and sampling metadata needed to audit the
  complete uncertainty calculation.
- A human-adjudicated D3 benchmark or any G2/G5 governance disposition.
