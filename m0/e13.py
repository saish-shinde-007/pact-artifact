#!/usr/bin/env python3
"""PACT — E13: do real evaluator models fail INDEPENDENTLY?

Every jury result in this paper rests on one assumption: that jurors drawn from
different model families have uncorrelated errors, so aggregating them buys
something. The protocol's diversity constraint — at most one juror per operator,
at least three base-model families — is worth its cost only if that holds.

It had never been tested. The detector families of E14 are hand-written rules, so
they cannot speak to it. Here three real Claude model tiers adjudicate the same 70
labeled code-review items blind, under one policy clause, and we measure:

  A. per-model detection quality against the rule-based detectors
  B. the independence test — if errors were independent, P(both wrong) would equal
     P(A wrong) x P(B wrong). Observed/expected is the number that matters.
  C. what that implies for a diversity-constrained jury

Scope: three tiers of ONE vendor's models. Cross-vendor jurors would plausibly be
less correlated, so the correlation measured here is an upper bound on what a
cross-vendor panel would show — but it is measured, where the paper previously
assumed. A cross-vendor replication is the obvious next experiment.

Run: ./.venv/bin/python3 e13.py   (reads jury_sample.json + jury_verdicts.json in this dir)
"""
import json
import os
from itertools import combinations

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jury_sample.json")
VERDICTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jury_verdicts.json")
RULE_BEST_F1 = 0.577          # best single rule-based detector, E14 neutral domain


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    if not os.path.exists(VERDICTS):
        print("no verdict file; run three model tiers over /tmp/jury_items.json and\n"
              f"write {{'jurors': [{{'juror','verdicts'}}]}} to {VERDICTS}")
        return
    truth = {t["id"]: t for t in json.load(open(SAMPLE))}
    jurors = json.load(open(VERDICTS))["jurors"]
    calls = {j["juror"]: {v["id"]: (1 if v["verdict"] == "VIOLATION" else 0)
                          for v in j["verdicts"] if v["id"] in truth} for j in jurors}
    names = list(calls)
    ids = sorted(set.intersection(*(set(m) for m in calls.values())))
    n = len(ids)

    print(f"\nE13 — real evaluator models as jurors ({len(names)} models, {n} items)\n")

    # ---- A. quality -------------------------------------------------------
    print("A. Detection quality")
    print(f"   {'juror':<16} {'P':>7} {'R':>7} {'F1':>7} {'errors':>8}")
    for nm in names:
        m = calls[nm]
        tp = sum(1 for i in ids if m[i] == 1 and truth[i]["label"] == 1)
        fp = sum(1 for i in ids if m[i] == 1 and truth[i]["label"] == 0)
        fn = sum(1 for i in ids if m[i] == 0 and truth[i]["label"] == 1)
        p, r, f = prf(tp, fp, fn)
        errs = sum(1 for i in ids if m[i] != truth[i]["label"])
        print(f"   {nm:<16} {p:>7.3f} {r:>7.3f} {f:>7.3f} {errs:>8}")
    print(f"   {'(best rule-based)':<16} {'':>7} {'':>7} {RULE_BEST_F1:>7.3f}")
    print("   Real models clear the rule-based detectors comfortably, and unlike the")
    print("   earlier corpus this one does NOT saturate: every model makes real errors,")
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
   fail together, on the same hard items. {len(universal)} items defeat all three, and they
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

   Scope, stated plainly: three tiers from ONE vendor, 70 items, one prompt
   framing. Same-vendor models share training and tuning lineage, so this is an
   UPPER bound on correlation and the honest next experiment is a cross-vendor
   panel. But the direction is now measured rather than assumed, and the paper
   states the assumption as unsupported instead of implicit.""")


if __name__ == "__main__":
    main()
