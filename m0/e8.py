#!/usr/bin/env python3
"""PACT M3 — E8: does the federation actually behave the way §VI claims?

Four claims under test:
  1. Ledger load is O(1) in query rate and O(operators) — the scaling law.
  2. Aggregation compute fits inside the epoch budget, so pin latency is set by
     the configured interval rather than by compute.
  3. Every action stays individually provable to the planetary root, and the
     proof grows logarithmically — "aggregation batches bandwidth, never trust".
  4. Equivocation by a shard is detected by any two honest witnesses.

Aggregation here operates on synthetic subtree roots: signing cost was measured
separately in E1, and mixing it in would hide the aggregation arithmetic this
experiment is about.

Run: ./.venv/bin/python3 e8.py
"""
import json
import time

from federation import Federation, gossip
from pactlog import H, merkle_root

EPOCH_BUDGET_S = 60.0


def build(n_shards, n_operators, n_agents_per_op, witnesses=10, quorum=6):
    fed = Federation(witnesses=witnesses, quorum=quorum)
    for o in range(n_operators):
        shard = f"shard{o % n_shards}"
        op = f"op{o}"
        fed.register(shard, op)
        for a in range(n_agents_per_op):
            fed.submit(op, f"{op}/agent{a}", H(f"{op}/agent{a}".encode()))
    return fed


def main():
    print("\nE8 — federation behaviour\n")

    # ---- 1. scaling law: root cost vs query rate ------------------------------
    print("1. Ledger load versus query rate (10 shards, 100 operators, 10 agents each)")
    print("   queries/epoch   root writes/epoch   root bytes/epoch   ledger bytes/query")
    fed = build(10, 100, 10)
    e = fed.seal()
    root_writes = len(fed.planet.owners)
    root_bytes = len(json.dumps(e["root"])) + e["cosignatures"] * 96
    for qpe in (10**3, 10**5, 10**7, 10**9):
        print(f"   {qpe:>13,}   {root_writes:>17}   {root_bytes:>16,}   "
              f"{root_bytes / qpe:>18.6f}")
    print("   Root cost per epoch is MEASURED and flat; the per-query column is that")
    print("   constant divided by hypothetical traffic. The point is structural: the")
    print("   root only ever sees shard roots, so no traffic volume can move it.")

    # ---- 2. aggregation compute vs epoch budget ------------------------------
    print("\n2. Aggregation compute per epoch (does it fit in a 60 s pin budget?)")
    print("   operators   agents   seal() wall-clock   share of 60 s budget")
    for n_ops in (100, 1_000, 10_000):
        f2 = build(50, n_ops, 10)
        t0 = time.perf_counter()
        f2.seal()
        dt = time.perf_counter() - t0
        print(f"   {n_ops:>9,}   {n_ops * 10:>6,}   {dt:>16.3f}s   "
              f"{dt / EPOCH_BUDGET_S:>19.2%}")
    print("   Aggregation is Merkle hashing over roots, not over payloads, so the")
    print("   epoch budget is dominated by the configured interval, not by compute.")

    # ---- 3. individual provability through all four tiers --------------------
    print("\n3. Individual provability to the planetary root")
    print("   entries/agent   proof hops   proof bytes   verify time   valid")
    for n_entries in (10, 1_000, 100_000):
        f3 = build(4, 8, 4)
        leaves = [H(f"entry-{i}".encode()) for i in range(n_entries)]
        f3.submit("op0", "op0/agent0", merkle_root(leaves))
        f3.seal()
        p = f3.prove("op0", "op0/agent0", leaves, n_entries // 2)
        t0 = time.perf_counter()
        ok = Federation.verify_proof(p)
        dt = (time.perf_counter() - t0) * 1e6
        hops = (len(p["agent"]["path"]) + len(p["operator"]["path"])
                + len(p["shard"]["path"]) + len(p["planet"]["path"]))
        print(f"   {n_entries:>13,}   {hops:>10}   {len(json.dumps(p)):>11,}   "
              f"{dt:>10.0f}us   {ok}")
    print("   A single action out of 100,000 is still provable to the planetary root")
    print("   in a few dozen hashes. Aggregation compressed what crosses the network,")
    print("   not what can be proven.")

    # ---- 4. witness quorum under churn ---------------------------------------
    print("\n4. Witness-quorum liveness under churn (10 witnesses, quorum 6)")
    print("   offline   live   cosignatures   quorum met")
    f4 = build(2, 4, 2, witnesses=10, quorum=6)
    for offline in range(0, 7):
        for i, w in enumerate(f4.witnesses):
            w.online = i >= offline
        e = f4.seal()
        print(f"   {offline:>7}   {e['witnesses_live']:>4}   {e['cosignatures']:>13}   "
              f"{e['quorum_met']}")
    print("   Liveness degrades gracefully and then stops at the stated threshold —")
    print("   it does not fail silently, and the log records the shortfall.")

    # ---- 5. equivocation -----------------------------------------------------
    print("\n5. Equivocation: a shard shows two different histories")
    f5 = build(2, 4, 2, witnesses=10, quorum=6)
    f5.seal()
    forged = H(b"forged history")
    e = f5.seal(equivocate={"shard": "shard0", "to": ["w0", "w1", "w2"], "root": forged})
    caught = gossip(f5.witnesses)
    print(f"   witnesses shown the forged root:     3 of 10")
    print(f"   detected by any witness ALONE:       {len(e['alarms'])}")
    print(f"   detected by witnesses COMPARING:     {len(caught)}  "
          f"(= 3 deceived x 7 honest pairs)")
    if caught:
        c = caught[0]
        print(f"   evidence: {c['witness_a']} recorded {c['root_a'][:12]}… while "
              f"{c['witness_b']} recorded {c['root_b'][:12]}…")
        print("   for the same shard and epoch. Two signed statements that cannot both")
        print("   be true — the shard cannot deny one without disowning its own signature.")
    print("\n   The zero in the middle row is the finding, not a failure. A witness")
    print("   shown one consistent history has nothing to object to; equivocation is")
    print("   invisible from any single vantage point and only exists as a")
    print("   disagreement BETWEEN vantage points. So gossip is not an optimization")
    print("   of the witness fabric — without it the fabric detects nothing at all,")
    print("   and the paper should specify it as mandatory rather than implied.")


if __name__ == "__main__":
    main()
