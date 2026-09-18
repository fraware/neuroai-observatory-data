# PATSTAT Baseline A — independent public-extract audit, 2026-09-18

## Status

This audit is a mechanical reconstruction of the public Baseline A extract on Observatory main
`825f8702cda66dd6b9740f563d2e8fb3e7144f5f`. It is governed by issue #220 and is
independent of the rights review in #210 and the D3 design in #222.

The audit establishes what the committed files themselves support. It does **not** certify the
historical two-stage probability design, prediction-powered inference variance, human label
truth, global patent-population coverage, PATSTAT redistribution rights, G2/G5 passage,
canonical S2 status, publication authority, or assessment effects.

The machine-readable record is
`curation/PATSTAT_BASELINE_A_INDEPENDENT_AUDIT_2026-09-18_v0.1.json`. The executable
reconstruction is `scripts/audit_patstat_baseline_a.py`.

## 1. Exact source binding

The audit binds the current public extract by Git blob identity:

| Artifact | Git blob |
|---|---|
| `ANALYSIS.md` | `4e6ceb36fbfe287eeb78ef0d8ac004725ce7b427` |
| `README.md` | `940ea76931be46cd7ba9d969f0d766ccd13816e1` |
| `strata.csv` | `b5eff1e15d7ccf17a8a1c51388a03ae5a3dc8a00` |
| `judged_sample.csv` | `e10a5af342cf472dac2a8a3e19e16099bc85708d` |
| `gold_labels.csv` | `bc4e1c7cd1b32080d144f1b94828f58b67ac5492` |
| `pool_frame.csv` | `6691dcbf2c77437abf72d0d83494e3154f077b62` |
| `clusters.csv` | `929265475ad76aa4739c579446faab82e87defa0` |
| `reproduce.py` | `702d130e0c3cc553ddde03a590dd1a6b34d897dd` |

The exported tables contain 235,738 first-stage rows, 333 second reads, 118,629 pool rows,
and nine strata. No duplicate family identifiers occur in the three row-level estimator
tables. Every second-read identifier occurs in `judged_sample.csv`, and every exported
`cheap_neuro` value round-trips exactly to the first-stage label.

## 2. Headline point estimates: mechanically reproducible

Running the public estimator semantics independently reproduces:

| Quantity | Independent reconstruction |
|---|---:|
| Cheap-only English-abstract-frame total | 99,719.788 |
| Rectified English-abstract-frame total | 49,671.277 |
| Rectified pool total | 33,277.426 |
| Pool recall ratio | 0.669953 |
| Estimated relevant families outside pool | 16,393.851 |

Rounded to the public presentation, these are 99,720, 49,671, 33,277, 67.0%, and 16,394.

This is a reproduction of the point calculation implemented in `reproduce.py`. It does
not establish that the historical selection probabilities make the estimator design-unbiased,
because the selection mechanism needed for that claim is absent from the public evidence.

## 3. Reread agreement: the reported kappa is reproducible after disambiguation

For the historical binary target `label 2 = relevant`, the 333 second reads yield:

- TP = 51
- FP = 53
- FN = 5
- TN = 224
- precision = 0.4903846
- recall = 0.9107143
- binary Cohen's κ = 0.5360780

The raw three-class 0/1/2 confusion matrix is:

| Cheap \ Strong | 0 | 1 | 2 |
|---|---:|---:|---:|
| 0 | 209 | 0 | 5 |
| 1 | 15 | 0 | 0 |
| 2 | 53 | 0 | 51 |

Three-class Cohen's κ is **0.4690851**. This reproduces the `κ = 0.469` statement in
`ANALYSIS.md`. The document should be read as reporting three-class kappa, whereas the
precision and recall values are binary label-2-versus-rest metrics.

The stronger rereads remain model outputs, not human D3 labels.

## 4. Raw-verdict integrity: the public export does not support the current “four missing” statement

The public `judged_sample.csv` contains exactly **two** rows with empty `neuro` and
`ml` fields:

- family `50277015`, stratum 7, raw verdict `NOT_NO`
- family `55911278`, stratum 6, raw verdict `NOT_BOR_NOML`

The file contains **13** raw verdicts outside the six standard tokens
`NOT_NOML`, `NOT_ML`, `BOR_NOML`, `BOR_ML`, `REL_NOML`, and `REL_ML`.
Eleven of those thirteen rows nevertheless carry parsed labels. Ten use
`NOT_ML   NOT_NOML`; one family, `91282470`, has the conflicting raw string
`REL_ML   NOT_ML` and is exported as `neuro=0, ml=1`.

Accordingly, the current public export does not support the statement in `ANALYSIS.md`
and `README.md` that four malformed outputs are all carried as missing. This audit does
not infer the intended historical parser rule. The exact parser implementation/provenance
is needed to resolve whether the discrepancy originated in parsing, export construction,
or later sanitization.

The impact of the two empty rows is negligible under the public point algorithm. That does
not remove the provenance discrepancy.

## 5. Second-stage design: observed allocation is recoverable; inclusion probabilities are not

The public files reveal the exact observed reread allocation by
`stratum × original cheap_neuro`. They also reveal materially different reread fractions
between original cheap-label cells. Examples include:

- stratum 1: all 6 label-1 rows reread, versus 12 of 19,994 label-0 rows;
- stratum 4: all 2 label-1 and all 16 label-2 rows reread, versus 20 of 24,982 label-0 rows;
- strata 5–8: **zero** label-1 rows reread, even though those strata contain 5, 152, 72,
  and 17 first-stage label-1 rows respectively.

The public `reproduce.py` maps historical labels 0 and 1 into the same binary
`f=0` correction cell. For pool estimation it additionally computes
`f = cheap × pool_membership` and defines correction cells from that masked value.
An out-of-pool cheap positive is consequently assigned to the `f=0` correction cell for
the pool calculation.

That implementation may or may not match the historical `pilot/ppi.py` design. The
public evidence does not contain the eligible second-stage frame, cell denominators at
selection time, item inclusion probabilities, seed, selection code, timing, or
replacement/adaptive semantics needed to decide the question.

Two diagnostics demonstrate that the pool point estimate is sensitive to this unresolved
choice:

| Diagnostic only | Pool total | Recall |
|---|---:|---:|
| Public masked-binary implementation | 33,277.426 | 66.995% |
| Preserve original binary cheap cell before pool masking | 33,780.401 | 68.008% |
| Preserve original three-class cheap cells | 33,772.019 | 68.003% |

These alternatives are **not** certified estimators. They establish that the missing
second-stage design is numerically consequential for the retrieval-recall calculation and
must be recovered before the 67.0% result is treated as independently validated.

## 6. BORDERLINE sensitivity

The historical headline maps label 1 to non-relevant. As a mechanical diagnostic only,
mapping both labels 1 and 2 to relevant while retaining the public algorithm produces:

- corpus total: 49,901.021
- pool total: 33,460.812
- recall: 67.054%

This small numerical movement does not establish compatibility with the current D1
four-way boundary. The stronger-reread file contains no `gold_neuro=1` outcomes, and the
historical rubric/prompt remains incompletely bound. D1's `INCLUDE`, `EXCLUDE`,
`BORDERLINE`, and `ABSTAIN` semantics remain a separate governed construct.

## 7. Uncertainty: neither reported interval follows from the variance visible in the public script

The only variance accumulated by `reproduce.py` is the first-stage cheap-label term

`N_h² × fpc × mean_f × (1 − mean_f) / n_h`.

Independently reconstructing that term yields:

- first-stage-only SD = **3,235.102**
- symmetric 1.96-SD interval around the public point = **[43,330.48, 56,012.08]**

This matches neither published interval:

- README: **[40,256, 57,854]**
- ANALYSIS: **[41,512, 58,192]**

The two published intervals also differ from one another. This audit does not choose one.
The full historical estimator/variance implementation and the exact second-stage
probability design remain necessary. No public evidence currently certifies the uncertainty
of the 67.0% recall ratio.

## 8. Low-score strata: zero observed label-2 events is established; an empty population is not

Strata 0–3 contain **51,034,929** families and **73,000** first-stage draws. The public
extract contains no first-stage label-2 event in those strata, and all 61 stronger rereads
from those strata have `gold_neuro=0`.

That supports the descriptive statement “zero label-2 events were observed in the
exported samples.” It does not establish that the underlying 51.0M-family population is
empty.

For scale only, under an additional independent simple-random-sampling-within-stratum
assumption and treating the model reread target as truth, a one-sided 95% zero-event
binomial bound applied separately to strata 0–3 sums to approximately **6,838 families**.
This is assumption-bound sensitivity analysis, not a certified historical interval. It is
also distinct from the “roughly 8,800” bound stated in `ANALYSIS.md`, whose derivation
is not present in the public folder.

## 9. `pool_frame.csv cluster`: the export defect is now mechanically localized

`clusters.csv` defines exactly the 21 identifiers 0–20. The `cluster` column in
`pool_frame.csv` behaves differently:

- 96,239 rows are blank;
- 22,390 rows are nonblank;
- **zero** nonblank values are in 0–20;
- all nonblank values occur in one contiguous prefix of the file;
- 6,400 equal the same row's `docdb_family_id`;
- every one of the 22,390 nonblank values equals a `docdb_family_id` at file offset
  0, +1, +2, +3, or +4.

The exact offset counts are 6,400, 1,290, 299, 8,432, and 5,969; they sum to 22,390.

This is sufficient to disposition the exported row-level `cluster` field as corrupted or
misaligned relative to the documented 0–20 topic identifiers. The exact root cause remains
unknown without the export code. The field is not consumed by `reproduce.py`, so this
finding does not itself change the 49,671 point calculation. It does block row-level topic
provenance from this column.

## 10. Claim-by-claim reproducibility from the committed public folder

| ANALYSIS.md claim family | Public-folder status |
|---|---|
| 69,273,903-family English-abstract frame | Reconstructible from `strata.csv` |
| 104,742,722 total PATSTAT families | Reported; not independently derivable from this folder |
| 118,629-family query pool | Reconstructible from `pool_frame.csv` |
| Exact 275-query definitions and threshold/configuration | Missing |
| Pilot 400 + 60 blind validation and monotonicity claim | Not independently reconstructible from this folder |
| Historical rubric v1.0-draft and exact prompts | Missing |
| 235,738 first-stage exported rows | Reconstructible |
| “four malformed, all missing” | Not supported by exported row state; see §4 |
| 333 stronger-model rereads | Reconstructible |
| Precision 0.490, recall 0.911 | Reconstructible for label 2 versus rest |
| κ = 0.469 | Reconstructible as three-class kappa |
| 49,671 / 33,277 / 67.0% / 16,394 point outputs | Reconstructible under public script semantics |
| Either published 95% population interval | Not independently reconstructible |
| 67.0% recall interval | Not independently reconstructible |
| Design-unbiasedness of the correction | Not established from public selection provenance |
| Zero observed low-score label-2 events | Reconstructible |
| Low-score population “genuinely empty” | Not established |
| Independent classifier miss count 16,028 | Reported; supporting classifier outputs absent |
| 21 aggregate topic summaries | Present in `clusters.csv` |
| Row-level cluster assignment in `pool_frame.csv` | Corrupted/misaligned |
| Sections 8–9 classification-code/burst results | Not reproducible from this folder, consistent with ANALYSIS.md §11 |

## 11. Remaining evidence needed for scientific disposition

The next external evidence remains exactly the provenance already requested under #243:
the first-stage selection implementation and randomization; the 333-case eligible frame,
selection probabilities and selection code; full `pilot/ppi.py` or equivalent estimator
and interval implementation; exact prompts/model identities/inference settings; the 275
query definitions and pool construction; and the export code or authoritative explanation
for the cluster-field defect.

Until those materials arrive and are independently checked, the scientific state remains
`PARTIAL_INDEPENDENT_AUDIT_BLOCKED_ON_MISSING_PROVENANCE`.

Rights remain separately fail-closed under #210.
