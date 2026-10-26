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

## Prospective replacement reference: a fully specified nested SRS design

The new `scripts/patstat_prospective_two_phase_srs.py` is **an executable
reference for a future probability sampling plan**, not a retroactive
completion of the historical selection procedure. It requires a fixed,
known population size `N_h` for each disjoint stratum, a first-stage
equal-probability sample without replacement of size `n_h`, and an
independently randomized second-stage equal-probability subsample without
replacement of size `m_h` from the selected first-stage IDs
(`N_h >= n_h >= m_h >= 2`). Both selection mechanisms must be documented
and reproducible, including all strata, units and fixed sample sizes.

The initial `f` label and retrieved-pool indicator `p` are observed for
the entire first-stage sample; the reference `y` label is observed for the
second-stage subsample. All three are binary. For stratum `h`, the
difference-estimator totals are:

```text
T_y(h) = N_h [ mean_s(f) + mean_r(y-f) ]
T_z(h) = N_h [ mean_s(f*p) + mean_r((y-f)*p) ]
```

Here `s` denotes phase 1, `r` phase 2 and `z=y*p`. The estimator
is design-unbiased for each finite-population total **under the assumed
sampling design**. This does not make any model label a human reference
standard; the validity of `y` is a separate empirical requirement.

The unbiased covariance estimator for the two totals, calculated from
values observed on `r`, is:

```text
Vhat_ab(h) = N_h^2 [
    (1 - n_h/N_h) * s_cov_r(y_a,y_b) / n_h
  + (1 - m_h/n_h) * s_cov_r(e_a,e_b) / m_h
]
e_y = y-f ; e_z = (y-f)*p
```

Each sample covariance uses denominator `m_h-1`. Independent strata
contribute additive variance/covariance components. The provisional
retrieval-ratio estimator `R=T_z/T_y` receives a **first-order
delta-method variance**:

```text
Vhat(R) = [ Vhat(T_z) + R^2 Vhat(T_y)
            - 2*R*Covhat(T_y,T_z) ] / T_y^2
```

A zero/nonpositive estimated denominator is treated as an undefined
ratio. A positive denominator alone is not a coverage guarantee:
near-zero denominators, post-stratification beyond this design,
nonresponse, unequal sampling probabilities, dependence across strata,
and reference-label error require additional methods.

The unittest suite exhaustively enumerates **90 nested samples** in a
six-unit synthetic population (`n=4,m=2`). Exact finite-population
variance values are `Var(T_y)=6`, `Var(T_z)=3.3`, and
`Cov(T_y,T_z)=3.9`; the average of the implemented unbiased variance
and covariance estimates equals these values. The suite also exercises
two independent strata, all-in-pool ratio covariance, and invalid
identifiers/design inputs.

**External methodological context:** Statistics Canada, *Double
Sampling* (Hidiroglou, Survey Methodology 27(2), 2001),
https://www150.statcan.gc.ca/n1/pub/12-001-x/2001002/article/6091-eng.pdf ,
and the R `survey` package's documented two-phase probability-design
requirements, https://search.r-project.org/CRAN/refmans/survey/html/twophase.html .

No historical PATSTAT data are fed to this reference; the old point
estimate, uncertainty interval and retrieval-coverage ratio remain
unverified. Replacing them requires a governed prospective sample,
a sound independent reference standard, and an authorized new baseline.

## Unbounded difference-estimator ratios: explicit invalidity diagnostics

The prospective reference is not a constrained estimator. Even when true
reference-positive retrieved families are a subset of true reference-positive
families, the *estimated* numerator and denominator can be noisy enough to
produce a negative ratio, a ratio above one, or a nonpositive estimated
denominator. Clipping a ratio to `[0,1]` would silently conceal the sampling
problem and distort uncertainty.

Exact enumeration of the same six-family, 90-outcome nested SRS fixture shows
**12 ratios above the logical one bound** and **19 undefined ratios due to
nonpositive estimated denominators**. The other **59** are inside `[0,1]`
without thereby becoming calibrated confidence statements.

The reference implementation now returns
`estimated_retrieval_ratio_diagnostic` with one of three fail-visible
states: `UNDEFINED_NONPOSITIVE_ESTIMATED_DENOMINATOR`,
`OUTSIDE_LOGICAL_ZERO_TO_ONE_RANGE_REQUIRES_STATISTICAL_REVIEW`, or
`IN_RANGE_ESTIMATE_NOT_VALIDATED_POPULATION_COVERAGE`. It does **not**
clamp the raw point estimate, impute a zero denominator or infer actual
PATSTAT retrieval coverage. These states are mechanically tested across
all 90 samples. Defensible constrained-ratio inference may require larger
samples, a suitable logit/Fieller or joint interval design, and independent
reference-label validity.
