#!/usr/bin/env python3
"""Recompute the two headline numbers from the CSVs in this folder. Stdlib only.

    python3 reproduce.py

Expected:  corpus relevant 49,671   pool recall 67.0%

The design in one paragraph. We cannot read 69 million abstracts, so a classifier
scores all of them, the score is cut into 9 strata, and a fixed number of families is
judged in each (the top three strata are small enough to judge completely). A stratum's
count is then N_h * (share judged relevant). That is the "cheap" estimate. The cheap
judge is a 26B local model and it is more lenient than the written rubric, so a second,
stronger judge re-reads a probability subsample and the difference (y - f) is added back
per stratum. The correction is design-unbiased whatever the cheap model does: the model's
quality only affects how wide the interval is, not where the point estimate sits.
"""
import csv, math, pathlib
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent      # so it runs from any directory
rows = lambda name: csv.DictReader((HERE / name).open())

REL = lambda v: 1.0 if v == "2" else 0.0     # 0 = not, 1 = borderline, 2 = relevant

N = {}
for r in rows("strata.csv"):
    N[r["stratum"]] = int(r["N_families"])

cheap, strat = {}, {}
for r in rows("judged_sample.csv"):
    if r["neuro"] == "":                     # 4 unparsed verdicts, treated as missing
        continue
    cheap[r["docdb_family_id"]] = REL(r["neuro"])
    strat[r["docdb_family_id"]] = r["stratum"]

gold = {r["docdb_family_id"]: REL(r["gold_neuro"]) for r in rows("gold_labels.csv")}
pool = {r["docdb_family_id"] for r in rows("pool_frame.csv")}


def total(members):
    """Prediction-powered total over `members` (a set of family ids, or None for all).

    Mirrors pilot/ppi.py: when restricting to a subset, the cheap label is masked to 0
    outside it, and the rectifier is post-stratified on that same masked label.
    """
    keep = lambda fid: 1.0 if (members is None or fid in members) else 0.0

    by_h = defaultdict(list)
    for fid, v in cheap.items():
        by_h[strat[fid]].append(fid)

    T, var = 0.0, 0.0
    for h, ids in by_h.items():
        n = len(ids)
        f = {fid: cheap[fid] * keep(fid) for fid in ids}
        mean_f = sum(f.values()) / n

        rect = 0.0
        for c in (0.0, 1.0):
            n_c = sum(1 for v in f.values() if v == c)
            cell = [gold[fid] * keep(fid) - f[fid]
                    for fid in ids if fid in gold and f[fid] == c]
            if n_c and cell:
                rect += (n_c / n) * (sum(cell) / len(cell))

        T += N[h] * (mean_f + rect)
        fpc = 1 - n / N[h] if N[h] > n else 0.0
        var += N[h] ** 2 * fpc * mean_f * (1 - mean_f) / n
    return T, math.sqrt(var)


corpus, sd = total(None)
pool_rel, _ = total(pool)
print(f"corpus relevant   {corpus:>10,.0f}   (cheap-only would be "
      f"{sum(N[h] * sum(v for f_, v in cheap.items() if strat[f_] == h) / sum(1 for f_ in cheap if strat[f_] == h) for h in N):,.0f})")
print(f"pool relevant     {pool_rel:>10,.0f}   of {len(pool):,} retrieved families")
print(f"pool recall           {100 * pool_rel / corpus:>5.1f}%")
print(f"missed            {corpus - pool_rel:>10,.0f}   relevant families the queries never saw")
