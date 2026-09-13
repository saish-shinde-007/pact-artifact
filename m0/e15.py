#!/usr/bin/env python3
"""E15: is juror error correlation lineage or judgment? Within-vendor pairs vs cross-vendor
pairs on the same items under one hashed prompt, with exact hypergeometric independence
tests. --exclude-ids audit reruns on the label-audited corpus.
"""
import argparse
import json
import os
import random
from itertools import combinations
from math import comb

from ci import ci, f1, pct          # same bootstrap/percentile helpers as the paper

HERE = os.path.dirname(os.path.abspath(__file__))
B = 20000
SEED = "pact-e15-v1"


def perm_p(n, ka, kb, joint):
    """EXACT p for H0: each juror's error COUNT is fixed and which items it misses
    is independent of the other juror. Under that null the joint-error count is
    hypergeometric(N=n, K=ka, draws=kb), so the one-sided tail is closed-form and."""
    denom = comb(n, kb)
    tail = sum(comb(ka, x) * comb(n - ka, kb - x)
               for x in range(joint, min(ka, kb) + 1) if n - ka >= kb - x)
    return tail / denom


def vendor(model):
    return model.split("/")[0]


def load(verdicts_path):
    truth = {t["id"]: t for t in json.load(open(os.path.join(HERE, "jury_sample.json")))}
    blob = json.load(open(verdicts_path))
    jurors = blob["jurors"]
    incomplete = [j["juror"] for j in jurors if not j.get("complete", True)]
    if incomplete:
        print(f"!! EXCLUDING incomplete jurors: {incomplete}\n"
              f"   (re-run run_jurors.py --resume to fill them)")
    jurors = [j for j in jurors if j.get("complete", True)]
    calls = {j["juror"]: {v["id"]: (1 if v["verdict"] == "VIOLATION" else 0)
                          for v in j["verdicts"] if v["id"] in truth} for j in jurors}
    ids = sorted(set.intersection(*(set(m) for m in calls.values())))
    return truth, calls, ids, blob.get("provenance", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", default="jury_verdicts_xvendor.json")
    ap.add_argument("--exclude-ids", default="",
                    help="comma-separated item ids to drop (see label_audit.py), or "
                         "'audit' to take them from label_audit directly")
    args = ap.parse_args()
    path = args.verdicts if os.path.isabs(args.verdicts) else os.path.join(HERE, args.verdicts)
    if not os.path.exists(path):
        raise SystemExit(f"no verdict file at {path}; run run_jurors.py first")

    truth, calls, ids, prov = load(path)
    dropped = []
    if args.exclude_ids:
        if args.exclude_ids.strip() == "audit":
            import label_audit
            _items, conf, _stands, exctx = label_audit.audit()
            drop = {it["id"] for it, *_ in conf} | {it["id"] for it, *_ in exctx}
        else:
            drop = {int(x) for x in args.exclude_ids.split(",") if x.strip()}
        dropped = sorted(i for i in ids if i in drop)
        ids = [i for i in ids if i not in drop]
        print(f"\nEXCLUDING {len(dropped)} items flagged by the label audit: {dropped}")
        print("   (clause-grounded and computed blind of verdicts; see label_audit.py)")
    names = list(calls)
    n = len(ids)
    rng = random.Random(SEED)
    vendors = sorted({vendor(nm) for nm in names})

    print(f"\nE15 — lineage or judgment? ({len(names)} jurors, {len(vendors)} vendors, "
          f"{n} items, {B} replicates)")
    print(f"prompt {prov.get('prompt_version','?')} sha256 "
          f"{str(prov.get('prompt_sha256',''))[:16]}  temp {prov.get('temperature','?')}  "
          f"run {prov.get('run_utc','?')}")
    print(f"vendors: {', '.join(vendors)}\n")

    err = {nm: [1 if calls[nm][i] != truth[i]["label"] else 0 for i in ids] for nm in names}
    lab = [truth[i]["label"] for i in ids]

    # ---- A. quality ------------------------------------------------------
    print("A. Detection quality per juror, under one shared prompt")
    print(f"   {'juror':<44} {'P':>6} {'R':>6} {'F1':>6} {'errors':>7}")
    qual = {}
    for nm in sorted(names, key=lambda x: (vendor(x), x)):
        pred = [calls[nm][i] for i in ids]
        tp = sum(1 for p, l in zip(pred, lab) if p == 1 and l == 1)
        fp = sum(1 for p, l in zip(pred, lab) if p == 1 and l == 0)
        fn = sum(1 for p, l in zip(pred, lab) if p == 0 and l == 1)
        pr = tp / (tp + fp) if tp + fp else 1.0
        rc = tp / (tp + fn) if tp + fn else 1.0
        qual[nm] = f1(pred, lab)
        print(f"   {nm:<44} {pr:>6.3f} {rc:>6.3f} {qual[nm]:>6.3f} {sum(err[nm]):>7}")
    best = max(qual, key=qual.get)
    print(f"   best single juror: {best} at F1 {qual[best]:.3f}")

    # ---- B. pairwise ratios, tagged ---------------------------------------
    def ratio(ea, eb, idx=None):
        idx = range(len(ea)) if idx is None else idx
        a = [ea[j] for j in idx]
        b = [eb[j] for j in idx]
        m = len(a)
        ka, kb = sum(a), sum(b)
        if not ka or not kb:
            return None
        joint = sum(1 for x, y in zip(a, b) if x and y)
        return (joint / m) / ((ka / m) * (kb / m))

    print("\nB. Pairwise joint-error ratio (observed / independence-expected)")
    print(f"   {'kind':<6} {'pair':<58} {'ratio':>7} {'joint':>6} {'perm p':>8}")
    rows = []
    for a, b in combinations(names, 2):
        r = ratio(err[a], err[b])
        if r is None:
            continue
        kind = "WITHIN" if vendor(a) == vendor(b) else "cross"
        ka, kb = sum(err[a]), sum(err[b])
        joint = sum(1 for x, y in zip(err[a], err[b]) if x and y)
        p = perm_p(n, ka, kb, joint)
        rows.append((kind, a, b, r, joint, p))
    for kind, a, b, r, joint, p in sorted(rows, key=lambda x: (x[0] != "WITHIN", -x[3])):
        star = "" if p >= 0.05 else ("  **" if p < 0.01 else "  *")
        print(f"   {kind:<6} {a + ' / ' + b:<58} {r:>6.1f}x {joint:>6} {p:>8.2e}{star}")

    within = [r for r in rows if r[0] == "WITHIN"]
    cross = [r for r in rows if r[0] == "cross"]
    if not within:
        raise SystemExit("\nno within-vendor pair in this file — add a second model from "
                         "one vendor, or the lineage question cannot be asked.")

    mw = sum(r[3] for r in within) / len(within)
    mc = sum(r[3] for r in cross) / len(cross)

    # ---- C. the comparison, bootstrapped over items -----------------------
    print(f"\nC. The comparison ({len(within)} within-vendor pairs, {len(cross)} cross-vendor)")
    dw, dc, dd = [], [], []
    wpairs = [(r[1], r[2]) for r in within]
    cpairs = [(r[1], r[2]) for r in cross]
    for _ in range(B // 20):                 # item bootstrap; 1000 reps, 95% CI is stable
        idx = [rng.randrange(n) for _ in range(n)]
        rw = [x for x in (ratio(err[a], err[b], idx) for a, b in wpairs) if x is not None]
        rc = [x for x in (ratio(err[a], err[b], idx) for a, b in cpairs) if x is not None]
        if rw and rc:
            dw.append(sum(rw) / len(rw))
            dc.append(sum(rc) / len(rc))
            dd.append(dw[-1] - dc[-1])
    wlo, whi = ci(dw)
    clo, chi = ci(dc)
    dlo, dhi = ci(dd)
    print(f"   mean WITHIN-vendor ratio  {mw:>6.1f}x   95% CI [{wlo:.1f}, {whi:.1f}]")
    print(f"   mean cross-vendor  ratio  {mc:>6.1f}x   95% CI [{clo:.1f}, {chi:.1f}]")
    print(f"   difference (within - cross) {mw - mc:>5.1f}x   95% CI [{dlo:.1f}, {dhi:.1f}]")
    overlap = dlo <= 0.0 <= dhi
    print(f"   does that interval contain 0? {'YES' if overlap else 'NO'}")
    frac_cross_gt1 = sum(1 for x in dc if x > 1.0) / len(dc)
    print(f"   bootstrap replicates with cross-vendor mean > 1.0: {frac_cross_gt1:.4f}")

    # ---- D. what defeats everyone ----------------------------------------
    uni = [i for k, i in enumerate(ids) if all(err[nm][k] for nm in names)]
    print(f"\nD. Items that defeat ALL {len(names)} jurors across {len(vendors)} vendors: "
          f"{len(uni)} of {n}")
    for i in uni:
        t = truth[i]
        print(f"   id{i:>3} [{t['bucket']}, labelled {t['label']}] {t['text'][:74]}")
    if uni:
        print("   LABEL AUDIT, not a victory lap: an item that every unrelated vendor calls")
        print("   the same way, against our label, is as plausibly a LABELLING ERROR as a")
        print("   hard case. Each line above needs adjudicating before it is cited as")
        print("   evidence of correlated failure.")

    # ---- E. does the jury rule still lose? --------------------------------
    print(f"\nE. The voting rule, on real cross-vendor jurors (the E14 question, re-asked)")
    for thresh, label in ((2 / 3, "2/3 supermajority"), (0.5, "simple majority"),
                          (1e-9, "any-one-juror (lone-detector rule)")):
        pred = []
        for k, i in enumerate(ids):
            votes = sum(calls[nm][i] for nm in names)
            pred.append(1 if votes / len(names) > thresh - 1e-12 else 0)
        jf = f1(pred, lab)
        print(f"   {label:<34} F1 {jf:.3f}   vs best single {qual[best]:.3f}  "
              f"({'WORSE' if jf < qual[best] else 'better or equal'})")

    # ---- F. verdict -------------------------------------------------------
    print("\nF. What this does to the paper's claim")
    if overlap:
        print(f"""   The within/cross difference interval contains 0. On this corpus the
   correlation does NOT look like shared lineage: jurors from unrelated vendors
   fail together about as much as two tiers of one vendor do. That REMOVES the
   paper's "4.7x is an upper bound" hedge, which assumed lineage was inflating
   the number. The finding gets stronger and the framing has to change: the
   correlation is a property of the items and of how models read them, not of
   a shared trainer. Report the cross-vendor mean as the headline and retire
   the upper-bound sentence.""")
    elif mw > mc:
        print(f"""   WITHIN-vendor pairs are measurably more correlated than cross-vendor pairs
   ({mw:.1f}x vs {mc:.1f}x, difference CI [{dlo:.1f}, {dhi:.1f}]). Lineage explains part of
   the original number, which VINDICATES the paper's upper-bound reading. The
   honest restatement: same-vendor panels are the worst case, a cross-vendor
   panel buys real but partial independence, and the diversity constraint should
   be stated in vendor terms rather than "model family" terms.""")
    else:
        print(f"""   Cross-vendor pairs are MORE correlated than within-vendor ones
   ({mc:.1f}x vs {mw:.1f}x). That is the unexpected direction and wants a reason
   before it is reported: check whether one erratic juror dominates the cross
   pairings, and whether section D is really a labelling problem.""")
    if frac_cross_gt1 > 0.95:
        print(f"\n   Independence is rejected for cross-vendor panels too: {frac_cross_gt1:.1%} of")
        print("   bootstrap replicates put the cross-vendor mean above 1.0x.")
    print("\n   Scope: one corpus of 70 items, one prompt framing, one verdict per item at")
    print("   temperature 0. No interval here covers variation from prompt or clause.")


if __name__ == "__main__":
    main()
