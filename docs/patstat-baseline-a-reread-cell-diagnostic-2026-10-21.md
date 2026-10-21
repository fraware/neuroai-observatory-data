# PATSTAT Baseline A: first-stage and stronger-model reread diagnostic

**Status: exploratory mechanical analysis; noncanonical.** This document accompanies
the read-only script in `scripts/audit_patstat_model_rereads.py` and the
independent audit governed by issue #220.

## Source and exact scope

The inputs are the existing public repository's frozen `strata.csv`,
`judged_sample.csv`, and historically named `gold_labels.csv`.
The latter contains **333 stronger-model rereads**, not human gold labels.

Run from the S2 repository root:

```shell
python -m scripts.audit_patstat_model_rereads \
  --data-dir patent-evidence-extract \
  --output /tmp/patstat-reread-audit.json
```

The new audit records raw-byte SHA-256 values, verifies that reread family IDs,
strata and first-model labels match the first-stage sample, and enumerates all
27 stratum-by-first-model-label cells. Its regression suite includes synthetic
mismatched-label cases and historical source checks.

## Independently reconstructed evidence

- Nine strata sum to **69,273,903** English-abstract patent families.
- The first-stage sample has **235,738** distinct families.
- The committed sample has **two** empty `neuro` labels, leaving **235,736**
  labeled rows. This is consistent with the prior independent Baseline A
  audit; the historical description of four empty labels is unsupported by
  this extract.
- All **333** stronger-model rereads match a first-stage family identifier,
  stratum and original first-model label.
- Across 27 possible original-label sampling cells, 18 have observed
  rereads and nine have none. **Four of the nine zero-reread cells contain
  first-stage labeled families:** stratum 5 / label 1 (5 families),
  stratum 6 / label 1 (152), stratum 7 / label 1 (72), and
  stratum 8 / label 1 (17). This is **246 sampled borderline-label
  families without a stronger-model reread in their exact three-class
  cells**. The other five zero-reread cells contain no first-stage cases.
- Three-class model agreement has Cohen's kappa approximately 0.4691;
  binary label-2-versus-rest agreement has kappa approximately 0.5361.

The 246 figure is an observed count in the original first-stage sample.
It is not a population estimate. **Zero three-class rereads does not imply
the historical binary correction used zero observations:** the published
reproducer pools original label 0 and label 1 into the same binary-negative
cell. This distinction must be preserved when studying correction-cell
assumptions.

## Interpretation and outstanding statistical work

The explicit original-label cell occupancy is useful for diagnosing
post-stratification assumptions and sensitivity to alternative correction
cells. It **does not** establish the historical second-stage probability
allocation, design-unbiasedness, or the claimed confidence interval.

Independent validation still needs the original selection/partitioning
code and inclusion probabilities, complete variance and covariance
calculation, a justified human reference standard, and a legal
redistribution determination (separate issue #210). Baseline A remains
a preliminary model-anchored estimate and does not establish D3/G2/G5
passage or publication authority.


## Independent mathematical diagnostic: incomplete variance expression

The historical `patent-evidence-extract/reproduce.py` computes a corrected
point total using stronger-model residual rereads. Its displayed variance
accumulator is built from first-stage cheap-label Bernoulli variability:
`N_h**2 * (1-n_h/N_h) * mean_f*(1-mean_f)/n_h`, summed across
strata. That expression contains no second-stage correction variance and
cannot justify uncertainty for the corrected point total or its ratio by
itself.

A fully specified *synthetic* counterexample in
`scripts/patstat_ppi_variance_counterexample.py` demonstrates the missing
component without using PATSTAT rows. In a 20-element synthetic stratum,
the first-stage model labels are a constant zero, the first stage is a
census, and the exact reference values comprise ten ones and ten zeros.
All 4-element, simple-random-without-replacement correction samples are
exhaustively enumerated (4,845 samples). The corrected estimator is
design-unbiased for 10, with exact variance `400/19 ≈ 21.0526`.
The cheap-only variance expression is **zero**. A nominal interval formed
from that zero variance covers the true total on only
`2025/4845 ≈ 41.8%` of the 4,845 possible correction samples.

The finite-population identity is checked independently against
`N²(1-m/N)S²/m` with the finite-population variance denominator `N−1`.
The experiment demonstrates a class of variance-estimation failures and
does **not** establish that the particular historic PATSTAT second-stage
design was simple random sampling, or that its reported point estimate
was biased. The original correction sampling probabilities and the
appropriate covariance terms for pool-retrieval ratios remain unverified.

Run:

```sh
python -m scripts.patstat_ppi_variance_counterexample \
  --output /tmp/patstat-variance-counterexample.json
python -m unittest tests.test_patstat_ppi_variance_counterexample -v
```
