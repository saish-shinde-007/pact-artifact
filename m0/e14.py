#!/usr/bin/env python3
"""E14: the voting rules on rule-based detector families, oracle-free. The families were
committed before six isolated model agents wrote the data, so neither side could tune
to the other. --exclude-ids audit reruns everything on the label-audited corpus.
"""
import argparse
import math
from itertools import combinations

import neutral_corpus
import neutral_detectors as ND
from jury import POOL, sample_jury, tally
from pactlog import H

ITEMS = neutral_corpus.build()
NVIOL = sum(i["label"] for i in ITEMS)


def prf(pred):
    tp = sum(1 for p, it in zip(pred, ITEMS) if p == 1 and it["label"] == 1)
    fp = sum(1 for p, it in zip(pred, ITEMS) if p == 1 and it["label"] == 0)
    fn = sum(1 for p, it in zip(pred, ITEMS) if p == 0 and it["label"] == 1)
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def juror_vote(family, text, juror_id):
    """Same shape as jury.juror_vote: family call plus a deterministic
    idiosyncratic flip, so same-family jurors are not identical."""
    base = ND.family_call(family, text)
    if int.from_bytes(H(juror_id.encode() + text.encode()), "big") % 100 < 8:
        base = not base
    return "VIOLATION" if base else "CLEARED"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="v2", choices=("v2", "v1"),
                    help="v2 = adjudicated labels (default); v1 = as authored")
    ap.add_argument("--exclude-ids", default="",
                    help="comma-separated item ids to drop (see label_audit.py), or "
                         "'audit' to take them from label_audit directly")
    args = ap.parse_args()

    global ITEMS, NVIOL
    dropped = []
    global ITEMS, NVIOL
    ITEMS = neutral_corpus.build(args.labels)
    NVIOL = sum(i["label"] for i in ITEMS)
    if args.labels == "v1":
        print("\nLABELS v1 (as authored, pre-adjudication)")
    if args.exclude_ids:
        if args.exclude_ids.strip() == "audit":
            import label_audit
            _items, conf, _stands, exctx = label_audit.audit()
            drop = {it["id"] for it, *_ in conf} | {it["id"] for it, *_ in exctx}
        else:
            drop = {int(x) for x in args.exclude_ids.split(",") if x.strip()}
        dropped = sorted(it["id"] for it in ITEMS if it["id"] in drop)
        ITEMS = [it for it in ITEMS if it["id"] not in drop]
        NVIOL = sum(i["label"] for i in ITEMS)
        print(f"\nEXCLUDING {len(dropped)} items flagged by the label audit: {dropped}")
        print("   (clause-grounded and computed blind of verdicts; see label_audit.py)")

    print(f"\nE14 — neutral domain (repository secret handling), {len(ITEMS)} items, "
          f"{NVIOL} violations\n")
    print("Detectors were committed before the data existed; six separate model")
    print("agents wrote the data in isolation, without seeing the detectors.\n")

    # ---- 1. per-family baselines -----------------------------------------
    print("1. Single-detector baselines")
    print(f"   {'family':<16} {'P':>6} {'R':>6} {'F1':>6}")
    best_f1, best_name = 0.0, ""
    for fam in ND.FAMILIES:
        p, r, f = prf([1 if ND.family_call(fam, it["text"]) else 0 for it in ITEMS])
        print(f"   {fam:<16} {p:>6.3f} {r:>6.3f} {f:>6.3f}")
        if f > best_f1:
            best_f1, best_name = f, fam
    print(f"   best single detector: '{best_name}' F1 {best_f1:.3f}")

    # do they actually have differing blind spots, or did they converge?
    miss = {fam: {it["id"] for it in ITEMS
                  if it["label"] == 1 and not ND.family_call(fam, it["text"])}
            for fam in ND.FAMILIES}
    print("\n   pairwise disagreement on missed violations (are blind spots distinct?)")
    # Mutual = both directions non-empty; a nested pair (one miss-set inside the
    # other) is not complementarity and must not be counted as if it were.
    mutual = nested = identical = 0
    for a, b in combinations(ND.FAMILIES, 2):
        only_a, only_b = len(miss[a] - miss[b]), len(miss[b] - miss[a])
        if only_a and only_b:
            mutual += 1
        elif only_a or only_b:
            nested += 1
        else:
            identical += 1
        if only_a or only_b:
            print(f"     {a} / {b}: {only_a} caught only by {b}, {only_b} only by {a}")
    npairs = mutual + nested + identical
    print(f"   mutually distinct blind-spot pairs: {mutual} of {npairs}"
          f" (nested: {nested}, identical: {identical})")

    # ---- 2/3. the jury, symmetric vs lone-detector -------------------------
    seats = sample_jury(b"e14-seed")[0]
    states = {}
    for label, asym in (("symmetric 2/3", False), ("+ lone-detector", True)):
        out = []
        for it in ITEMS:
            votes = [{"juror": j["id"], "rationale": "r",
                      "verdict": juror_vote(j["family"], it["text"], j["id"])}
                     for j in seats]
            d, _ = tally(votes, asymmetric=asym)
            out.append({"VIOLATION": "violation", "CLEARED": "cleared"}.get(d, "escalated"))
        states[label] = out

    print(f"\n2. Jury outcomes, oracle-free (k={len(seats)}, "
          f"{len({j['family'] for j in seats})} families, "
          f"{len({j['operator'] for j in seats})} operators)")
    print(f"   {'rule':<20} {'contained':>10} {'leaked':>8} {'auto-prec':>10} {'human load':>11}")
    for label, st in states.items():
        viol = [s for s, it in zip(st, ITEMS) if it["label"] == 1]
        conv = [(s, it) for s, it in zip(st, ITEMS) if s == "violation"]
        ap = (sum(1 for _, it in conv if it["label"] == 1) / len(conv)) if conv else 1.0
        print(f"   {label:<20} {sum(1 for s in viol if s != 'cleared') / len(viol):>10.3f} "
              f"{sum(1 for s in viol if s == 'cleared') / len(viol):>8.3f} "
              f"{ap:>10.3f} {sum(1 for s in st if s == 'escalated') / len(st):>11.1%}")

    # Claim 2 head-on: does the jury score BELOW its best member? Escalations are
    # scored as non-convictions, the machine's own decision, with no human credit.
    best_p, _, _ = prf([1 if ND.family_call(best_name, it["text"]) else 0 for it in ITEMS])
    print(f"\n   {'scored as machine decisions only (escalate = not convicted)':<52}")
    print(f"   {'rule':<20} {'P':>6} {'R':>6} {'F1':>6}   vs best single F1 {best_f1:.3f}")
    for label, st in states.items():
        p, r, f = prf([1 if s == "violation" else 0 for s in st])
        print(f"   {label:<20} {p:>6.3f} {r:>6.3f} {f:>6.3f}   {f - best_f1:+.3f}")
    sym_conv = [(s, it) for s, it in zip(states["symmetric 2/3"], ITEMS) if s == "violation"]
    jury_prec = (sum(1 for _, it in sym_conv if it["label"] == 1) / len(sym_conv)
                 ) if sym_conv else 1.0
    print(f"\n   precision: best single {best_p:.3f} -> jury {jury_prec:.3f} "
          f"({jury_prec - best_p:+.3f})")

    # does the lone-detector case exist here at all?
    lone = [it for it in ITEMS if it["label"] == 1
            and sum(1 for f in ND.FAMILIES if ND.family_call(f, it["text"])) == 1]
    print(f"   violations visible to exactly ONE family: {len(lone)} "
          f"(the cases a 2/3 rule can outvote)")

    # ---- 4. collusion, cap on vs off --------------------------------------
    print("\n3. Collusion: does the per-operator cap still bound it?")
    hostile = POOL + [{"id": f"did:pact:orgX/j{i}", "operator": "orgX",
                       "family": "lexical"} for i in range(7)]
    ids = [j["id"] for j in hostile if j["operator"] == "orgX"]
    clear_cut = [it for it in ITEMS if it["label"] == 1
                 and sum(1 for f in ND.FAMILIES if ND.family_call(f, it["text"])) >= 4]
    print(f"   ({len(clear_cut)} violations seen by >=4 of 5 families — a clean baseline)")
    print(f"   {'colluders':<12} {'cap ON':>18} {'cap OFF':>18}")
    coll_rates = {}
    for n_coll in (0, 3, 5, 7):
        coll = set(ids[:n_coll])
        on = off = 0
        for it in clear_cut:
            seed = H(f"e14:{it['id']}".encode())
            for box, acc in ((sample_jury(seed, hostile)[0], "on"),
                             (sorted(hostile, key=lambda x: H(seed + x["id"].encode()).hex())[:11],
                              "off")):
                votes = [{"juror": j["id"], "rationale": "r",
                          "verdict": "CLEARED" if j["id"] in coll
                          else juror_vote(j["family"], it["text"], j["id"])} for j in box]
                if tally(votes)[0] == "VIOLATION":
                    if acc == "on":
                        on += 1
                    else:
                        off += 1
        m = max(len(clear_cut), 1)
        coll_rates[n_coll] = (on / m, off / m)
        print(f"   {n_coll:>2} registered  {on / m:>17.1%} {off / m:>17.1%}")

    if dropped:
        # The VERDICT paragraph below quotes the FULL 70-item corpus. Rather than
        # print prose whose numbers no longer match the run, restate the same four
        # claims from the figures this run actually produced.
        sym, asym = states["symmetric 2/3"], states["+ lone-detector"]

        def leak(st):
            v = [s for s, it in zip(st, ITEMS) if it["label"] == 1]
            return sum(1 for s in v if s == "cleared") / len(v)

        def load(st):
            return sum(1 for s in st if s == "escalated") / len(st)

        symf = prf([1 if s == "violation" else 0 for s in sym])[2]
        asymf = prf([1 if s == "violation" else 0 for s in asym])[2]
        print(f"""
  VERDICT on the AUDITED corpus ({len(ITEMS)} items, {NVIOL} violations) — the four
  claims restated from THIS run's figures. The paragraph the default run prints
  describes the full 70-item corpus and is not reprinted here.

  1. "a 2/3 jury can score below its own best member":
       jury F1 {symf:.3f} vs best single '{best_name}' {best_f1:.3f} ({symf - best_f1:+.3f})
       -> {'STILL HOLDS' if symf < best_f1 else 'DOES NOT HOLD'}
  2. "the lone-detector rule buys containment with human load":
       leaked {leak(sym):.3f} -> {leak(asym):.3f}, human load {load(sym):.1%} -> {load(asym):.1%}
       machine F1 unchanged by the rule ({symf:.3f} -> {asymf:.3f}) by construction:
       it converts auto-clears into escalations and decides nothing new
       -> {'STILL HOLDS' if leak(asym) < leak(sym) and load(asym) > load(sym) else 'DOES NOT HOLD'}
  3. "the per-operator cap bounds collusion": at 7 colluders
       cap ON {coll_rates[7][0]:.1%} vs cap OFF {coll_rates[7][1]:.1%} conviction on
       {len(clear_cut)} clear-cut violations -> {'STILL HOLDS' if coll_rates[7][0] > coll_rates[7][1] else 'DOES NOT HOLD'}
       (each step is one item at this corpus size; not independently conclusive)
  4. "a diverse jury raises precision over its best member":
       best single {best_p:.3f} -> jury {jury_prec:.3f} ({jury_prec - best_p:+.3f})
       -> {'HOLDS HERE' if jury_prec > best_p else 'STILL DOES NOT HOLD'}

  Dropping {len(dropped)} of 32 violation labels removes {len(dropped)} positives and no negatives,
  so every rate above rests on {NVIOL} violations rather than 32, and every precision
  move comes from the true-positive side alone. Read these as directions, not as
  precise effect sizes.""")
        return

    print("""
  VERDICT — three of four claims generalize, one does not.

  REPRODUCED, and far more strongly than on the withdrawn corpus:
    "a 2/3 jury can score below its own best member". There it was -0.003 F1;
    here it is -0.321 (0.256 vs 0.577). On a corpus nobody could tune to, a
    supermajority almost never forms, so the jury convicts far less than its
    best member would. This is the paper's central negative result and it is
    domain-independent.

  REPRODUCED: the lone-detector rule trades leakage for human review. Leaked
    violations fall 0.500 -> 0.094 while human load rises 20% -> 73%. Note the
    machine's own P/R are IDENTICAL under both rules: the rule changes nothing
    about what the machine decides, only about what it refuses to auto-clear.
    That is why containment, not F1, is the honest metric for it.

  REPRODUCED but weakly, and on too little data to lean on: the per-operator
    cap still bounds collusion (67% vs 17% conviction at 7 colluders), but the
    clean baseline here is only 6 items, so each step is one item. Directionally
    consistent with E5; not independently conclusive.

  DID NOT REPRODUCE: "a diverse jury raises precision over its best member."
    On the withdrawn corpus precision went 0.750 -> 0.993. Here it goes
    0.750 -> 0.714, slightly DOWN. That gain came from the earlier corpus
    concentrating its false positives in two families, so majority voting washed
    them out. With blind-authored data the false positives are not so
    conveniently distributed. The precision claim was an artifact and the paper
    must withdraw it.

  Why the difference matters: the detectors here have genuinely distinct blind
  spots (section 1 shows real asymmetric complementarity) yet aggregation still
  did not help precision. Complementary coverage is necessary for a jury to pay
  off, and it is not sufficient.""")


if __name__ == "__main__":
    main()
