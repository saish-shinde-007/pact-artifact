#!/usr/bin/env python3
"""Uncertainty on the headline numbers: item-bootstrap CIs (one resample per replicate,
every pair scored on it) and permutation tests, deterministic by fixed seed. --exclude-ids
audit reruns on the label-audited corpus; --exact-p prints the closed-form p beside the sampled one.
"""
import argparse
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


def exclusion_set(spec):
    """--exclude-ids, same convention as e15.py: a comma-separated id list, or the
    literal 'audit' to take the ids straight from label_audit.audit() so the exclude
    list cannot drift from the audit that justifies it."""
    if not spec:
        return frozenset()
    if spec.strip() == "audit":
        import label_audit
        _items, conf, _stands, exctx = label_audit.audit()
        return frozenset({it["id"] for it, *_ in conf} | {it["id"] for it, *_ in exctx})
    return frozenset(int(x) for x in spec.split(",") if x.strip())


def apply_exclusions(ids, drop, where):
    """Drop `drop` from one section's id universe, printing what went. The two
    sections are filtered separately because their universes differ (E13's is the
    verdict-file intersection, E14's is the whole neutral corpus)."""
    if not drop:
        return ids
    dropped = [i for i in ids if i in drop]
    missing = sorted(drop - set(ids))
    print(f"\n{where}: EXCLUDING {len(dropped)} of {len(ids)} items flagged by the label "
          f"audit\n   {dropped}")
    print("   (clause-grounded and computed blind of verdicts; see label_audit.py)")
    if missing:
        print(f"   !! requested ids absent from this corpus, ignored: {missing}")
    return [i for i in ids if i not in drop]


# ---------------------------------------------------------------- E13
def e13_intervals(rng, drop=frozenset(), exact_p=False):
    truth = {t["id"]: t for t in json.load(open(os.path.join(HERE, "jury_sample.json")))}
    jurors = json.load(open(os.path.join(HERE, "jury_verdicts.json")))["jurors"]
    calls = {j["juror"]: {v["id"]: (1 if v["verdict"] == "VIOLATION" else 0)
                          for v in j["verdicts"] if v["id"] in truth} for j in jurors}
    names = list(calls)
    ids = sorted(set.intersection(*(set(m) for m in calls.values())))
    ids = apply_exclusions(ids, drop, "E13")
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
    if exact_p:
        # The null (error counts fixed, missed items randomised) is hypergeometric;
        # e15.perm_p() is the closed form, and this column audits the sampler.
        # FLOOR = sampled p pinned at 1/(B+1); only the exact column is that small.
        from e15 import perm_p       # import is lazy: e15 imports ci's helpers back
    print(f"   {'pair':<32} {'ratio':>7}  {'95% CI':>18} {'joint':>6} {'p':>9}"
          + (f" {'exact p':>10}" if exact_p else ""))
    # One resample per replicate, every pair scored on it. v1 resampled each pair
    # independently and zip-averaged the columns, which destroyed item covariance
    # and narrowed the mean-ratio CI ([3.3,9.4] published; correct is wider).
    pairs = list(combinations(names, 2))
    rngb = random.Random(SEED + ":e13-pairs")
    pair_boot = {pr: [] for pr in pairs}
    mean_boot = []
    for _ in range(B):
        idx = [rngb.randrange(n) for _ in range(n)]
        vals = []
        for a, b in pairs:
            ea, eb = err[a], err[b]
            ja = sum(ea[j] for j in idx)
            jb = sum(eb[j] for j in idx)
            jj = sum(1 for j in idx if ea[j] and eb[j])
            r = (jj / n) / ((ja / n) * (jb / n)) if ja and jb else None
            if r is not None:
                pair_boot[(a, b)].append(r)
            vals.append(r)
        if all(v is not None for v in vals):
            mean_boot.append(sum(vals) / len(vals))

    ratios_pt = []
    rngp = random.Random(SEED + ":e13-perm")
    for a, b in pairs:
        ea, eb = err[a], err[b]
        joint = sum(1 for x, y in zip(ea, eb) if x and y)
        pa, pb = sum(ea) / n, sum(eb) / n
        pt = (joint / n) / (pa * pb) if pa and pb else float("nan")
        ratios_pt.append(pt)
        lo, hi = ci(pair_boot[(a, b)])

        # Permutation null: error counts fixed, which items each misses randomised.
        ka, kb = sum(ea), sum(eb)
        pos = list(range(n))
        ge = 0
        for _ in range(B):
            sa = set(rngp.sample(pos, ka))
            sb = set(rngp.sample(pos, kb))
            if len(sa & sb) >= joint:
                ge += 1
        p = (ge + 1) / (B + 1)          # add-one, so p is never reported as 0
        star = "" if p >= 0.05 else ("  **" if p < 0.01 else "  *")
        tail = ""
        if exact_p:
            pe = perm_p(n, ka, kb, joint)
            tail = f" {pe:>10.2e}" + ("  FLOOR" if ge == 0 else "")
        print(f"   {a + ' / ' + b:<32} {pt:>6.1f}x  [{lo:>5.1f}, {hi:>5.1f}] {joint:>6} "
              f"{p:>9.4f}{star}{tail}")

    mean_pt = sum(ratios_pt) / len(ratios_pt)
    mlo, mhi = ci(mean_boot)
    print(f"\n   mean ratio {mean_pt:.1f}x, 95% CI [{mlo:.1f}, {mhi:.1f}]")
    frac = sum(1 for m in mean_boot if m > 1.0) / len(mean_boot)
    print(f"   fraction of bootstrap replicates with mean ratio > 1.0 (independence): "
          f"{frac:.4f}")

    print("\nC. Items all models get wrong")
    uni = [i for i in range(n) if all(err[nm][i] for nm in names)]
    # 2B replicates: at B the 97.5th percentile sat on a knife edge between 9/70
    # and 10/70 across seeds.
    rngu = random.Random(SEED + ":e13-uni")
    boot = []
    for _ in range(2 * B):
        idx = [rngu.randrange(n) for _ in range(n)]
        boot.append(sum(1 for j in idx if all(err[nm][j] for nm in names)) / n)
    lo, hi = ci(boot)
    print(f"   {len(uni)} of {n} ({len(uni) / n:.3f}), 95% CI [{lo:.3f}, {hi:.3f}]")
    print(f"   NOTE: {len(uni)} items is a small base. The interval is wide and the")
    print("   'concentrated entirely on contested items' claim rests on those few.")


# ---------------------------------------------------------------- E14
def e14_intervals(rng, drop=frozenset()):
    import e14
    import neutral_detectors as ND
    from jury import sample_jury, tally

    items = e14.ITEMS
    kept = set(apply_exclusions([it["id"] for it in items], drop, "E14"))
    items = [it for it in items if it["id"] in kept]
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude-ids", default="",
                    help="comma-separated item ids to drop (see label_audit.py), or "
                         "'audit' to take them from label_audit directly. Applies to "
                         "BOTH the E13 and the E14 intervals.")
    ap.add_argument("--exact-p", action="store_true",
                    help="add the closed-form (hypergeometric) p next to the simulated "
                         "permutation p, and mark rows pinned at the 1/(B+1) floor")
    args = ap.parse_args()
    drop = exclusion_set(args.exclude_ids)
    rng = random.Random(SEED)
    e13_intervals(rng, drop, args.exact_p)
    e14_intervals(rng, drop)
    print("\nAll intervals are percentile bootstrap over ITEMS, which is the sampling")
    print("unit that would change if the corpus were rewritten. They do NOT cover")
    print("variation from model choice, prompt framing, or policy clause — those are")
    print("single draws here and no interval can speak to them.")


if __name__ == "__main__":
    main()
