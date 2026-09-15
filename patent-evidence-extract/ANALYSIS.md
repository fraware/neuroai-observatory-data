# What was done, and what it shows

A summary of the patent analysis behind *Mapping the NeuroAI Frontier*, written for a
collaborator picking the work up. The data in this folder is the evidence for the parts
marked as reproducible below; the rest is recorded in the project repository.

Source throughout: PATSTAT Global, Autumn 2025 edition. The unit is the DOCDB simple
patent family, so one invention counts once however many offices it was filed in.

---

## 1. The problem the design exists to solve

AI-enabled neurotechnology has no classification code, no agreed boundary and no
canonical keyword set. A brain-computer interface for speech restoration, a closed-loop
deep-brain stimulator, a consumer EEG headband and an epilepsy-prediction algorithm are
all plausibly in scope, and no existing CPC class collects them. Anyone who assembles a
patent set for this field is therefore making a definitional claim, usually without
saying so and always without measuring what the claim excluded.

Two consequences follow, and the whole design is built around them. First, a set built
from queries is a sample of unknown completeness, not a census. Second, the inclusion
rule matters more than any modelling choice downstream — so it has to be written down,
applied uniformly, and its sensitivity reported.

## 2. What the corpus is

PATSTAT Autumn 2025 holds **104,742,722** families. Of these, **69,273,903** carry an
English-language abstract, and those are the only ones any text-based method can read.
Every corpus-wide number in this work is a statement about that 69.3M frame, not about
the full 104.7M, and the gap is not random: it falls hardest on offices that do not
supply English abstracts. Where a claim depends on classification codes rather than text,
the code-based analyses use the full record.

## 3. Retrieval, and the honest name for what it produces

275 queries were generated as a deterministic cross-product over the taxonomy axes, each
naming a device modality together with a target. Each query was embedded and matched
against the corpus by cosine similarity above a fixed threshold. This produced a pool of
**118,629 families** — the `pool_frame.csv` in this folder, with the query that found
each one recorded in `found_by_query`.

A stratified sample of 400 across five similarity bands, plus 60 controls drawn from
outside the pool, was judged blind. Relevance declines monotonically with similarity,
without inversion or plateau, which is what licenses using the similarity score as an
instrument later rather than merely as a ranking.

The pool is a candidate set. Calling it the field would be the error the rest of the
design exists to avoid.

## 4. The instrument

A written rubric (v1.0-draft) specifies four inclusion clauses and one tie-break rule:
where a patent sits between categories, ask whether a neural target or a neural signal is
stated in the text; if not, it is not relevant. BORDERLINE is reserved for insufficient
information, not for genuine ambiguity about scope.

Applied strictly, that rule excludes more than it first appears to: generic
electrostimulators and TENS units that never name a nerve, EMG-based rehabilitation
systems (EMG originates in muscle), foot-drop and gastric stimulators described as
targeting tissue. Whether this is the right boundary is a scope decision that is still
open — see §9.

## 5. Two-tier judging

Reading 69 million abstracts is not possible, and a simple random sample of them returns
essentially nothing, because relevant families are roughly seven in every ten thousand.
The design therefore scores the whole corpus with a cheap classifier, cuts the score range
into nine strata, and spends the reading budget where the variance is.

A 26B open-weight model, run locally on four L40S GPUs, judged **235,738** sampled
families against the rubric in about 55 GPU-minutes — `judged_sample.csv` here. Two
outputs of 235,738 were unparseable; a further two were malformed in a different way, and
all four are carried as missing rather than guessed.

A blinded subsample of **333**, post-stratified on (stratum × cheap label), was then
re-judged by a much stronger model against the same rubric, with stratum and machine label
withheld — `gold_labels.csv`. Against those gold labels the cheap judge shows precision
0.490, recall 0.911, κ = 0.469.

That precision looks alarming next to an earlier validation which measured 0.899 on 460
pilot families. The difference is the strong judge, not the local one: the pilot labels
were made against a perimeter held in context, the gold labels against the written rubric
applied literally. The disagreement is definitional before it is technical.

## 6. The estimate

Prediction-powered inference combines the two tiers: cheap labels everywhere, plus a
rectifier — the mean of (strong − cheap) measured on the gold subsample, post-stratified
within cheap-label class. Both terms are design-unbiased, so the point estimate is valid
whatever the cheap model does; model quality enters only through the interval width.

`reproduce.py` in this folder recomputes it from the CSVs with the standard library alone:

| | |
|---|---|
| Relevant families, whole 69.3M corpus | **49,671**  (95% [41,512, 58,192]) |
| Relevant families inside the 118,629 pool | 33,277 |
| **Recall of the query pool** | **67.0%**  (95% [57.2%, 78.6%]) |
| Relevant families the queries never retrieved | **16,394** |

Two features of this deserve attention.

**The correction is large.** Cheap labels alone give a corpus total of 99,720; rectified,
49,671. The 26B judge reads the rubric more permissively than the strong judge does, and
333 double-readings halve the estimate. This is the two-tier design doing exactly what it
was built for, and it is why a single-tier LLM count of a field like this should not be
trusted.

**The low-score region is genuinely empty.** Strata 0 through 3 hold 51.0 million
families, and both judges found zero relevant families in 73,000 draws. Their combined
contribution is bounded above at roughly 8,800. This is the measurement the design existed
to make: it converts "we probably found most of it" into a bound. At a conventional
judgement budget of 400, that bound would have exceeded 500,000 and the exercise would
have settled nothing.

**The missed count converges with an independent method.** A corpus classifier, sharing
no estimation logic with this design, flags 16,028 outside-pool families at high score
against this design's 16,394. Two methods with different failure modes landing within 2%
is the strongest evidence that the query frame misses something real and roughly that
large. It is also the main argument against treating any query-built patent set as the
field.

## 7. Structure: what the field is made of

Clustering the retrieval embeddings (UMAP, then HDBSCAN, labelled by distinguishing terms)
yields 21 topics — `clusters.csv`. The substantive split that emerges, and which recurs
independently below, is between applications that **read** the nervous system and those
that **act** on it. Machine learning has arrived in the reading applications and has
largely not arrived in the delivering ones. AI enters this field through inference, not
through actuation.

## 8. Emergence: burst analysis

The DETECTS method (Dernis, Squicciarini & de Pinho 2016) applies Kleinberg's two-state
burst detection to classification codes, with parameters pinned to the source (s = 2,
γ = 1.0). It dates the onset of a technology's acceleration rather than describing its
level. It was replicated here at three nested levels that differ only in the baseline they
compare against, plus a cross-fertilisation analysis over co-assigned code pairs.

**The field is not bursting.** Against all patenting, the pool's share peaked around 2008
(19.5 families per 10,000) and has declined since, to 12.5 by 2020. Neurotechnology grows
in absolute terms while shrinking as a share of the record. What follows is recomposition,
not a boom, and every other result should be read inside that frame.

**Inside the field, chemistry is leaving and computation is arriving.** Every open-ended
burst is computational — G06N (2019–2022, w=245), G16H health informatics, G06T image
processing. Every closed burst is chemical, pharmacological or classical signal
processing, and all of them finished by the mid-2000s. At group level, neural-network
models (G06N 3) burst open-ended at weight 168 while electrotherapy (A61N 1, 7,891
families) bursts once in 2005–2006 and never again.

**Convergence has a date.** Eight CPC pairs involving G06N burst, and seven of the eight
are still open, every one starting between 2017 and 2020. Among them, `A61B × G06N`
(medical measurement × machine learning, 2019–2022, w=81) is the AI-and-neurotechnology
convergence measured directly, in examiner-assigned codes, using no embedding, no
clustering and no language model. It is an independent instrument for the claim the rest
of this project makes by other means.

**Where AI has and has not arrived.** Taking each application's own families as the
baseline, G06N is the strongest open-ended burst in seven of twelve applications — speech
communication (2018–2022, w=89), epilepsy, hearing restoration, attention monitoring,
neurorehabilitation, Parkinson's, chronic pain. Three applications show no open-ended
burst of any kind, and two of those three are prosthesis control and motor restoration:
the actuation applications. The inference-versus-actuation split, established earlier from
clusters and from a language-model label, reappears here in examiner codes alone, and as a
statement about timing rather than level.

**The check that changes the reading.** G06N tagging expanded across all patenting over
this period, so a within-field G06N burst could simply be the general wave. It is. G06N
bursts open-ended in both series — 2018–2022 inside the pool, 2019–2022 across all
patenting — so the timing of the ML burst inside neurotechnology is not distinctive.

What is distinctive is the level and its trajectory. Neurotechnology carries a large and
persistent ML premium over the economy, but the premium peaked around 2014–2016 at roughly
12× and had compressed to 4.7× by 2022. The field's own ML share still rose over that
period, from 6.6% to 10.7%; the rest of patenting simply rose faster. The defensible claim
is therefore **not** that AI is accelerating into neurotechnology. It is that
neurotechnology was an early and heavy adopter, by a factor of six to twelve through the
2010s, and that the rest of the record has been closing that gap since 2018. Any figure
quoting the within-field burst has to be shown next to the economy-wide one.

## 9. Is neurotechnology a growing part of AI?

No, and the burst analysis dates the turn. Neurotechnology's share of all G06N families
did burst, from 2011 to 2017, roughly doubling to 2.04% in 2014. That burst closed. The
share runs 1.22% in 2018, 0.85% in 2020 and 0.69% in 2022.

It was put to us that this reflects a shift in appropriability — AI increasingly protected
as software and trade secret rather than by patent, rendering neurotechnology less visible
in the record. The data do not support that reading in its strong form, and the
alternative is arithmetically sufficient on its own. Decomposing the ratio: neurotechnology
families carrying G06N grew almost tenfold between 2014 and 2022, from 77 to 759; all G06N
families grew nearly thirtyfold, from 3,773 to 109,305. Neurotechnology did not slow. AI
simply grew about three times faster elsewhere. A field withdrawing into secrecy does not
increase its patented machine-learning output tenfold in eight years.

Two further checks point the same way. The share of neurotechnology families carrying a
computing class rose from 6.5% in 2000 to 22.8% in 2020 before plateauing, so the
algorithmic layer is being patented more rather than less. And the rise in G06N share
appears in every filing bloc — 1.8% to 14.2% for US filings, 0.2% to 11.2% for Chinese —
with no break at 2014 of the kind a US legal shock to software patentability would produce.

The hypothesis survives in a weaker form that patent data cannot adjudicate: the most
valuable models may be held as trade secrets while incremental work is patented, in which
case patents understate the *level* of AI in the field without distorting its *trend*.
That is a limitation of the instrument, not a property of the field.

## 10. What is settled, and what is not

**Settled.** The corpus outside the classifier's attention is empty, measured rather than
assumed. The query pool misses something on the order of 16,000 relevant families, now
confirmed by two independent methods. Recall is around two thirds — not the near-complete
coverage the original design implied, and not the one third the unrectified cheap labels
suggested.

**Not settled, in order of how much it moves the numbers.**

1. *The inclusion rule.* The estimate is more sensitive to how strictly the rubric's
   tie-break is read than to anything else in the pipeline. Five specific categories sit
   between the rubric and the project's own cluster map — intracranial pressure and
   cerebral haemodynamic monitoring, seizure prediction from non-neural signals, binaural
   and audio entrainment, functional electrical stimulation for gait, and enabling physics
   components. Widening clause 1 to cover measurement *of* the nervous system, rather than
   only signals originating *in* it, would resolve the two largest. This needs expert
   sign-off, not a further modelling decision.
2. *Rater validation.* The gold labels come from a single rater applying a draft rubric.
   Repeat-run, order-shuffle and a second model family are outstanding, as is a set of
   roughly 75 expert anchors — which should be spent on the five categories above rather
   than spread evenly.
3. *Stratum 5.* Its upper bound, 32,991, is two thirds of the whole estimate, resting on
   247 cheap positives and 70 gold labels over 1.4 million families. It is the widest
   remaining piece of the interval and the cheapest to narrow.
4. *The burst results are provisional.* Everything in §8 was run on the pool, not on the
   judged-relevant subset, and pool precision runs from 89% in the top similarity band to
   16% in the bottom, so low-similarity noise is included. CPC is available for 94,886 of
   118,629 families (80%), and families are dated by minimum filing year rather than
   earliest priority. The pool census that permits the re-run is complete; the re-run is not.

## 11. Which claims this folder lets you check

`reproduce.py` reproduces §6 exactly — the corpus total, the pool total, recall, and the
cheap-versus-rectified gap — from `strata.csv`, `judged_sample.csv`, `gold_labels.csv` and
`pool_frame.csv`. `abstracts_sample.csv` lets you read the judgements against what was
actually judged; comparing a high-score stratum with a low one shows what the classifier
is responding to. `clusters.csv` carries the §7 topics.

Sections 8 and 9 rest on classification-code series computed over the full PATSTAT record
and are not reproducible from this folder; they require database access. `README.md`
describes each file and its columns.

Bibliographic data and abstract text originate with the EPO and remain subject to the
PATSTAT licence terms.
