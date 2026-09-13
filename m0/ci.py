#!/usr/bin/env python3
"""PACT — uncertainty on the two headline numbers.

E13 reports a 4.7x joint-error ratio and E14 a jury F1 of 0.256 against its best
member's 0.577. Both are point estimates on 70 items. A reader cannot tell from a
point estimate whether 4.7x is a finding or an artifact of which 70 items we happened
to write, and the paper's own §VII-D shows how much that can matter — screener recall
moves 0.167-0.500 across equally valid splits of the same corpus.

This script puts intervals on the numbers the abstract leads with, and tests the
independence null directly:

  A. bootstrap CIs over items (resample the 70 items with replacement)
  B. permutation test of H0: the two models' errors are independent
     (hold each model's error COUNT fixed, permute WHICH items it errs on)
  C. the E14 jury-vs-best-member gap, paired on items

No new data is collected — this is the uncertainty already implied by the runs in
e13.py and e14.py, made explicit. Deterministic: the PRNG is seeded from a fixed
constant, so the intervals reproduce exactly.

Run: ./.venv/bin/python3 ci.py
"""
import json
import os
import random
from itertools import combinations

B = 20000                       # bootstrap / permutation replicates
SEED = "pact-ci-v1"             # fixed, so every run gives the same intervals
HERE = os.path.dirname(os.path.abspath(__file__))


def pct(xs, q):
    """Percentile of a sorted-able list, linear interpolation."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def ci(xs, alpha=0.05):
    return pct(xs, alpha / 2), pct(xs, 1 - alpha / 2)


def f1(pred, lab):
    tp = sum(1 for p, l in zip(pred, lab) if p == 1 and l == 1)
    fp = sum(1 for p, l in zip(pred, lab) if p == 1 and l == 0)
    fn = sum(1 for p, l in zip(pred, lab) if p == 0 and l == 1)
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return 2 * p * r / (p + r) if p + r else 0.0


# ---------------------------------------------------------------- E13
def e13_intervals(rng):
    truth = {t["id"]: t for t in json.load(open(os.path.join(HERE, "jury_sample.json")))}
    jurors = json.load(open(os.path.join(HERE, "jury_verdicts.json")))["jurors"]
    calls = {j["juror"]: {v["id"]: (1 if v["verdict"] == "VIOLATION" else 0)
                          for v in j["verdicts"] if v["id"] in truth} for j in jurors}
    names = list(calls)
    ids = sorted(set.intersection(*(set(m) for m in calls.values())))
    n = len(ids)
    # err[name][i] = 1 if that model got item i wrong
    err = {nm: [1 if calls[nm][i] != truth[i]["label"] else 0 for i in ids] for nm in names}

    print(f"\nE13 — uncertainty on the independence result ({len(names)} models, {n} items,"
          f" {B} replicates)\n")

    print("A. Per-model error rate, bootstrap 95% CI")
    print(f"   {'juror':<16} {'errors':>7} {'rate':>7}   {'95% CI':>16}")
    for nm in names:
        e = err[nm]
        boot = []
        for _ in range(B):
            idx = [rng.randrange(n) for _ in range(n)]
            boot.append(sum(e[j] for j in idx) / n)
        lo, hi = ci(boot)
        print(f"   {nm:<16} {sum(e):>7} {sum(e) / n:>7.3f}   [{lo:.3f}, {hi:.3f}]")

    print("\nB. Joint-error ratio (observed / independence-expected), with CI and an")
    print("   exact-style permutation test of H0: this pair's errors are independent.")
    print(f"   {'pair':<32} {'ratio':>7}  {'95% CI':>18} {'joint':>6} {'p':>9}")
    ratios_pt, ratio_boots = [], []
    for a, b in combinations(names, 2):
        ea, eb = err[a], err[b]
        joint = sum(1 for x, y in zip(ea, eb) if x and y)
        pa, pb = sum(ea) / n, sum(eb) / n
        exp = pa * pb * n
        pt = (joint / n) / (pa * pb) if pa and pb else float("nan")
        ratios_pt.append(pt)

        boot = []
        for _ in range(B):
            idx = [rng.randrange(n) for _ in range(n)]
            ja = sum(ea[j] for j in idx)
            jb = sum(eb[j] for j in idx)
            jj = sum(1 for j in idx if ea[j] and eb[j])
            if ja and jb:
                boot.append((jj / n) / ((ja / n) * (jb / n)))
        ratio_boots.append(boot)
        lo, hi = ci(boot)

        # permutation null: each model's error COUNT is fixed; which items it misses
        # is independent of the other model. Count joint failures under that null.
        ka, kb = sum(ea), sum(eb)
        pos = list(range(n))
        ge = 0
        for _ in range(B):
            sa = set(rng.sample(pos, ka))
            sb = set(rng.sample(pos, kb))
            if len(sa & sb) >= joint:
                ge += 1
        p = (ge + 1) / (B + 1)          # add-one, so p is never reported as 0
        star = "" if p >= 0.05 else ("  **" if p < 0.01 else "  *")
        print(f"   {a + ' / ' + b:<32} {pt:>6.1f}x  [{lo:>5.1f}, {hi:>5.1f}] {joint:>6} "
              f"{p:>9.4f}{star}")

    mean_pt = sum(ratios_pt) / len(ratios_pt)
    mean_boot = [sum(c) / len(c) for c in zip(*ratio_boots)]
    mlo, mhi = ci(mean_boot)
    print(f"\n   mean ratio {mean_pt:.1f}x, 95% CI [{mlo:.1f}, {mhi:.1f}]")
    frac = sum(1 for m in mean_boot if m > 1.0) / len(mean_boot)
    print(f"   fraction of bootstrap replicates with mean ratio > 1.0 (independence): "
          f"{frac:.4f}")

    print("\nC. Items all models get wrong")
    uni = [i for i in range(n) if all(err[nm][i] for nm in names)]
    boot = []
    for _ in range(B):
        idx = [rng.randrange(n) for _ in range(n)]
        boot.append(sum(1 for j in idx if all(err[nm][j] for nm in names)) / n)
    lo, hi = ci(boot)
    print(f"   {len(uni)} of {n} ({len(uni) / n:.3f}), 95% CI [{lo:.3f}, {hi:.3f}]")
    print(f"   NOTE: {len(uni)} items is a small base. The interval is wide and the")
    print("   'concentrated entirely on contested items' claim rests on those few.")


# ---------------------------------------------------------------- E14
def e14_intervals(rng):
    import e14
    import neutral_detectors as ND
    from jury import sample_jury, tally

    items = e14.ITEMS
    lab = [it["label"] for it in items]
    n = len(items)
    seats = sample_jury(b"e14-seed")[0]

    best_name, best_f1 = "", 0.0
    singles = {}
    for fam in ND.FAMILIES:
        pred = [1 if ND.family_call(fam, it["text"]) else 0 for it in items]
        singles[fam] = pred
        f = f1(pred, lab)
        if f > best_f1:
            best_f1, best_name = f, fam

    states = {}
    for label, asym in (("symmetric 2/3", False), ("+ lone-detector", True)):
        out = []
        for it in items:
            votes = [{"juror": j["id"], "rationale": "r",
                      "verdict": e14.juror_vote(j["family"], it["text"], j["id"])}
                     for j in seats]
            d, _ = tally(votes, asymmetric=asym)
            out.append({"VIOLATION": "violation", "CLEARED": "cleared"}.get(d, "escalated"))
        states[label] = out

    print(f"\n\nE14 — uncertainty on the jury-vs-best-member gap ({n} items, {B} replicates)\n")
    best = singles[best_name]

    for label, st in states.items():
        jury = [1 if s == "violation" else 0 for s in st]
        gap_pt = f1(jury, lab) - f1(best, lab)
        boot = []
        for _ in range(B):
            idx = [rng.randrange(n) for _ in range(n)]
            bl = [lab[j] for j in idx]
            boot.append(f1([jury[j] for j in idx], bl) - f1([best[j] for j in idx], bl))
        lo, hi = ci(boot)
        worse = sum(1 for x in boot if x < 0) / len(boot)
        print(f"   {label:<16} jury F1 {f1(jury, lab):.3f} vs best '{best_name}' "
              f"{best_f1:.3f}")
        print(f"   {'':<16} gap {gap_pt:+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}]")
        print(f"   {'':<16} bootstrap replicates where the jury is WORSE: {worse:.4f}\n")

    # containment: of true violations, what fraction is NOT auto-cleared
    viol_idx = [i for i in range(n) if lab[i] == 1]
    print(f"   containment on the {len(viol_idx)} true violations")
    for label, st in states.items():
        pt = sum(1 for i in viol_idx if st[i] != "cleared") / len(viol_idx)
        boot = []
        for _ in range(B):
            idx = [rng.choice(viol_idx) for _ in range(len(viol_idx))]
            boot.append(sum(1 for j in idx if st[j] != "cleared") / len(idx))
        lo, hi = ci(boot)
        print(f"   {label:<16} {pt:.3f}, 95% CI [{lo:.3f}, {hi:.3f}]")


def main():
    rng = random.Random(SEED)
    e13_intervals(rng)
    e14_intervals(rng)
    print("\nAll intervals are percentile bootstrap over ITEMS, which is the sampling")
    print("unit that would change if the corpus were rewritten. They do NOT cover")
    print("variation from model choice, prompt framing, or policy clause — those are")
    print("single draws here and no interval can speak to them.")


if __name__ == "__main__":
    main()
