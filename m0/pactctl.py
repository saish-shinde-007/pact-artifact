#!/usr/bin/env python3
"""PACT M0 CLI — demo, verify, prove, sample, challenge, erase, tamper."""
import argparse
import json
import statistics
import time

from pactlog import Store

WITNESSES = ["w1", "w2", "w3"]
AGENT = "did:pact:demo/helper-1"


def init(store: Store):
    store.keygen(AGENT)
    for w in WITNESSES:
        store.keygen(w)


def cmd_demo(store: Store, n: int):
    init(store)
    pre = store.status(AGENT)
    if pre["entries"]:
        print(f"NOTE: db already holds {pre['entries']} entries (possibly tampered from earlier "
              f"runs) — appending on top. For clean benchmark numbers: rm pact.db and rerun.")
    lat, sizes = [], []
    t0 = time.perf_counter()
    ck_bytes = 0
    ck_count = 0
    for i in range(n):
        r = store.append(AGENT, f"user question #{i}", f"echo: user question #{i}",
                         sample={"seed": i, "temp": 0.0})
        lat.append(r["append_us"])
        sizes.append(r["entry_bytes"])
        if (i + 1) % 50 == 0:
            ck = store.checkpoint(AGENT, WITNESSES)
            ck_bytes += ck["checkpoint_bytes"]
            ck_count += 1
            if ck["flags"]:
                print("witness flags:", ck["flags"])
    wall = time.perf_counter() - t0
    v = store.verify(AGENT, WITNESSES)
    print(f"appended {n} entries in {wall:.2f}s  ({n / wall:,.0f} entries/s single-thread)")
    print(f"append latency  p50 {statistics.median(lat):.0f} us   "
          f"p95 {sorted(lat)[int(0.95 * len(lat))]:.0f} us")
    print(f"entry size      avg {statistics.mean(sizes):.0f} B (local log, operator-side)")
    print(f"checkpoints     {ck_count} x ~{ck_bytes // max(ck_count, 1)} B cosigned "
          f"= {ck_bytes} B shared-ledger cost for {n} queries")
    print(f"per-query shared-ledger cost ≈ {ck_bytes / n:.2f} B")
    print(f"chain verify    {'OK' if v['ok'] else v['errors']}  ({v['entries']} entries)")
    print("status:", store.status(AGENT))


def cmd_bench(n: int):
    """M1: batched vs per-entry commit — the append-latency fix."""
    import os
    import tempfile

    modes = [("naive (no WAL, no key cache, per-entry commit)", False, False, False),
             ("+ WAL journaling", True, False, False),
             ("+ key-object cache", True, True, False),
             ("+ batched commit", True, True, True)]
    out = {}
    for mode, wal, kc, batched in modes:
        s = Store(os.path.join(tempfile.mkdtemp(), "b.db"), wal=wal, key_cache=kc)
        s.keygen(AGENT)
        lat = []
        t0 = time.perf_counter()
        ctx = s.batch() if batched else None
        if ctx:
            with ctx:
                for i in range(n):
                    lat.append(s.append(AGENT, f"q{i}", f"a{i}")["append_us"])
        else:
            for i in range(n):
                lat.append(s.append(AGENT, f"q{i}", f"a{i}")["append_us"])
        wall = time.perf_counter() - t0
        out[mode] = (statistics.median(lat), sorted(lat)[int(0.95 * len(lat))], n / wall)
    print(f"append benchmark, {n} entries per configuration\n")
    prev = None
    for mode, (p50, p95, tput) in out.items():
        gain = "" if prev is None else f"  ({prev / p50:.1f}x)"
        print(f"  {mode:<46} p50 {p50:7.1f} us   p95 {p95:7.1f} us   "
              f"{tput:>8,.0f}/s{gain}")
        prev = p50
    first = list(out.values())[0][0]
    last = list(out.values())[-1][0]
    print(f"\n  end to end: {first:.0f} us -> {last:.0f} us ({first / last:.1f}x)")


def cmd_jury(store: Store, seq: int):
    """M1: one challenge end-to-end through the ledger, with recursion."""
    from jury import adjudicate

    d = store.disclose(AGENT, seq)
    if d is None:
        raise SystemExit(f"seq {seq} has no payload (erased?) — pick another")
    if not d["commits_match"]:
        raise SystemExit(f"seq {seq}: disclosed payload does not match its on-ledger "
                         f"commitment — refusing to adjudicate substituted evidence")
    cid = store.challenge(AGENT, seq, seq, "pol:v1#c1")
    # seal a checkpoint AFTER filing so the jury seed is a value that did not
    # exist when the challenge id was assigned (no grinding)
    store.checkpoint(AGENT, WITNESSES)
    anchor = store.jury_anchor(cid)
    if anchor is None:
        raise SystemExit("no post-challenge checkpoint yet; cannot draw an unbiased jury")
    before = store.status(AGENT)
    res = adjudicate(store, cid, AGENT, d["prompt"], log_recursion=True, anchor=anchor)
    print(f"challenge #{cid} on seq {seq}  (anchor {anchor.hex()[:12]}…)")
    print(f"  jury          k={res['k']}  families={res['diversity']['families']}  "
          f"operators={res['diversity']['operators']}  "
          f"constraints_ok={res['diversity']['constraints_ok']}")
    print(f"  commit-reveal verified: {res['commit_reveal_ok']}")
    print(f"  tally         {res['violation_votes']}/{res['k']} violation -> {res['decision']}")
    print(f"  recursion     {res['k']} juror verdicts logged as covered actions")
    after = store.status(AGENT)
    print(f"  consequence   reputation {before['reputation']} -> {after['reputation']}, "
          f"stake {before['stake']} -> {after['stake']}, registry {after['registry']}")
    print(f"  backing       {store.verify_verdict(cid)}")
    print(f"  gate          {store.gate_check(AGENT)}")


def main():
    p = argparse.ArgumentParser(prog="pactctl")
    p.add_argument("--db", default="pact.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo"); d.add_argument("-n", type=int, default=200)
    b = sub.add_parser("bench"); b.add_argument("-n", type=int, default=2000)
    ju = sub.add_parser("jury"); ju.add_argument("seq", type=int)
    sub.add_parser("verify")
    pr = sub.add_parser("prove"); pr.add_argument("seq", type=int)
    sa = sub.add_parser("sample"); sa.add_argument("-k", type=int, default=5)
    di = sub.add_parser("disclose"); di.add_argument("seq", type=int)
    er = sub.add_parser("erase"); er.add_argument("seq", type=int)
    ta = sub.add_parser("tamper"); ta.add_argument("seq", type=int)
    ch = sub.add_parser("challenge")
    ch.add_argument("seq_from", type=int); ch.add_argument("seq_to", type=int)
    ch.add_argument("clause")
    ve = sub.add_parser("verdict")
    ve.add_argument("id", type=int); ve.add_argument("verdict", choices=["VIOLATION", "CLEARED", "FRIVOLOUS"])
    ve.add_argument("rationale")
    sub.add_parser("status")
    a = p.parse_args()
    store = Store(a.db)
    init(store)
    if a.cmd == "demo":
        cmd_demo(store, a.n)
    elif a.cmd == "bench":
        cmd_bench(a.n)
    elif a.cmd == "jury":
        cmd_jury(store, a.seq)
    elif a.cmd == "verify":
        print(json.dumps(store.verify(AGENT, WITNESSES), indent=2))
    elif a.cmd == "prove":
        r = store.prove(AGENT, a.seq)
        print(json.dumps(r, indent=2))
    elif a.cmd == "sample":
        picks = store.rla_sample(AGENT, a.k)
        print("RLA draw (seeded by latest witnessed root):", picks)
    elif a.cmd == "disclose":
        print(json.dumps(store.disclose(AGENT, a.seq), indent=2))
    elif a.cmd == "erase":
        store.erase(AGENT, a.seq)
        print(f"payload+salts for seq {a.seq} erased; commitment remains, now unlinkable")
    elif a.cmd == "tamper":
        store.tamper(AGENT, a.seq)
        print(f"seq {a.seq} silently edited — run `verify` to catch it")
    elif a.cmd == "challenge":
        cid = store.challenge(AGENT, a.seq_from, a.seq_to, a.clause)
        print(f"challenge #{cid} OPEN against {AGENT} [{a.seq_from}..{a.seq_to}] clause {a.clause}")
    elif a.cmd == "verdict":
        store.verdict(a.id, a.verdict, a.rationale)
        print(f"challenge #{a.id} closed: {a.verdict}; status:", store.status(AGENT))
    elif a.cmd == "status":
        print(json.dumps(store.status(AGENT), indent=2))


if __name__ == "__main__":
    main()
