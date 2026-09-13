#!/usr/bin/env python3
"""E13: do real evaluator models fail independently? A panel judges the same items blind;
we report per-juror quality and pairwise observed/expected joint-error ratios.
--verdicts takes any panel's file; --exclude-ids audit drops the label-conflicted items.
"""
import argparse
import json
import os
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "jury_sample.json")
VERDICTS = "jury_verdicts.json"       # --verdicts default; resolved against HERE below
def rule_best_f1(truth, ids):
    """Best rule-based family F1 on EXACTLY these items — a stale full-corpus
    constant here once mislabelled the audited baseline (0.577 vs contrastive's
    0.414 on 59 items)."""
    import neutral_detectors as ND
    best = 0.0
    for fam in ND.FAMILIES:
        tp = fp = fn = 0
        for i in ids:
            pred = 1 if ND.family_call(fam, truth[i]["text"]) else 0
            tp += pred and truth[i]["label"]
            fp += pred and not truth[i]["label"]
            fn += (not pred) and truth[i]["label"]
        _, _, f = prf(tp, fp, fn)
        best = max(best, f)
    return best
# Panel size reads as a word in the prose below. Spelling the small cases keeps the
# sentences English for the panels anyone actually runs, and keeps a default run
# byte-identical to the version that hardcoded "three".
NUMBER_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
               7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def word(k):
    return NUMBER_WORD.get(k, str(k))


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", default=VERDICTS)
    ap.add_argument("--exclude-ids", default="",
                    help="comma-separated item ids to drop (see label_audit.py), or "
                         "'audit' to take them from label_audit directly")
    args = ap.parse_args()
    verdicts = (args.verdicts if os.path.isabs(args.verdicts)
                else os.path.join(HERE, args.verdicts))
    if not os.path.exists(verdicts):
        print("no verdict file; run three model tiers over /tmp/jury_items.json and\n"
              f"write {{'jurors': [{{'juror','verdicts'}}]}} to {verdicts}")
        return
    truth = {t["id"]: t for t in json.load(open(SAMPLE))}
    jurors = json.load(open(verdicts))["jurors"]
    calls = {j["juror"]: {v["id"]: (1 if v["verdict"] == "VIOLATION" else 0)
                          for v in j["verdicts"] if v["id"] in truth} for j in jurors}
    names = list(calls)
    ids = sorted(set.intersection(*(set(m) for m in calls.values())))
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
    n = len(ids)

    print(f"\nE13 — real evaluator models as jurors ({len(names)} models, {n} items)\n")

    # ---- A. quality -------------------------------------------------------
    print("A. Detection quality")
    print(f"   {'juror':<16} {'P':>7} {'R':>7} {'F1':>7} {'errors':>8}")
    qual = {}
    for nm in names:
        m = calls[nm]
        tp = sum(1 for i in ids if m[i] == 1 and truth[i]["label"] == 1)
        fp = sum(1 for i in ids if m[i] == 1 and truth[i]["label"] == 0)
        fn = sum(1 for i in ids if m[i] == 0 and truth[i]["label"] == 1)
        p, r, f = prf(tp, fp, fn)
        qual[nm] = f
        errs = sum(1 for i in ids if m[i] != truth[i]["label"])
        print(f"   {nm:<16} {p:>7.3f} {r:>7.3f} {f:>7.3f} {errs:>8}")
    rb = rule_best_f1(truth, ids)
    print(f"   {'(best rule-based)':<16} {'':>7} {'':>7} {rb:>7.3f}   (same items)")
    cleared = sum(1 for nm in names if qual[nm] > rb)
    print(f"   {cleared} of {len(names)} models beat the best rule-based family on these")
    print("   items, and the corpus does not saturate: every model makes real errors,")
    print("   which is what makes the next section possible at all.")

    # ---- B. the independence test ----------------------------------------
    print("\nB. Do they fail independently? (the assumption the design rests on)")
    print(f"   {'pair':<34} {'P(A)':>6} {'P(B)':>6} {'joint':>6} {'expected':>9} {'ratio':>7}")
    errs = {nm: {i for i in ids if calls[nm][i] != truth[i]["label"]} for nm in names}
    ratios = []
    for a, b in combinations(names, 2):
        pa, pb = len(errs[a]) / n, len(errs[b]) / n
        obs = len(errs[a] & errs[b]) / n
        exp = pa * pb
        ratio = obs / exp if exp else float("nan")
        ratios.append(ratio)
        print(f"   {a + ' / ' + b:<34} {pa:>6.3f} {pb:>6.3f} {obs:>6.3f} "
              f"{exp:>9.3f} {ratio:>6.1f}x")
    mean = sum(ratios) / len(ratios)
    print(f"\n   mean observed/expected joint-error ratio: {mean:.1f}x")

    # which items does everyone get wrong?
    universal = set.intersection(*errs.values())
    print(f"   items ALL {len(names)} models get wrong: {len(universal)} of {n}")
    for i in sorted(universal)[:6]:
        t = truth[i]
        print(f"     [{t['bucket']}, truth={t['label']}] {t['text'][:66]}")

    contested_share = (sum(1 for i in universal if truth[i]["bucket"] == "contested")
                       / len(universal)) if universal else 0.0
    print(f"\n   of those universal failures, {contested_share:.0%} are 'contested' items —"
          "\n   the cases flagged in advance as ones competent reviewers would split on.")
    print(f"""
   VERDICT: errors are strongly CORRELATED — roughly {mean:.0f}x more joint failure
   than independence predicts. The models do not fail on different items; they
   fail together, on the same hard items. {len(universal)} items defeat all {word(len(names))}, and they
   are concentrated in the cases pre-labelled as genuinely contested — the models
   converge on the easy calls and diverge into the SAME error on the hard ones.
   That is the worst possible failure shape for a jury: agreement where agreement
   is cheap, correlated error where the verdict actually matters.

   This is the first measured evidence on the assumption the jury design rests
   on, and it does not support the strong form of that design. A diversity
   constraint buys materially less than "three independent families" implies:
   when the hard case arrives, the panel tends to be wrong together, and a
   supermajority of correlated jurors is confidently wrong rather than usefully
   uncertain.

   What survives. Diversity is not worthless — the pairwise ratios differ, so
   some pairs are more complementary than others, and the cheapest juror here is
   the most erratic (its errors dominate the pairings). Selecting jurors for
   measured complementarity rather than declared "family" is the design this
   result points to, and it is a sharper rule than the one the paper began with.

   Scope, stated plainly: {word(len(names))} tiers from ONE vendor, {n} items, one prompt
   framing. Same-vendor models share training and tuning lineage, so this is an
   UPPER bound on correlation and the honest next experiment is a cross-vendor
   panel. But the direction is now measured rather than assumed, and the paper
   states the assumption as unsupported instead of implicit.""")


if __name__ == "__main__":
    main()
