# PACT M0–M4 — reference implementation

Runnable core of the PACT architecture (`../PAPER.md`).

**M0** — single-node evidence log: hash-chained entries, Merkle checkpoints cosigned
by three witnesses, inclusion proofs, RLA sampling, erasure, manual challenge →
verdict → reputation. Plus an OpenAI-style serving shim that logs every completion
and returns a receipt.

**M1** — the jury protocol: VRF-style diversity-constrained sampling (≤1 seat per
operator, ≥3 base-model families), two-phase commit–reveal voting, supermajority
tally with human escalation, recursion (each juror verdict is itself a covered
action), and the E2/E5 experiment harness.

**M2** — the precedent graph (clause-scoped matching, conflict escalation,
supersession), a rung-0 screener that is an actually-trained classifier evaluated
on held-out templates, registry-enforced runtime attestation, and the E7 funnel
experiment.

**M3** — the federation: agent → operator → shard → witness-cosigned planetary
root, composed four-tier inclusion proofs with owner binding, a witness fabric
with cross-witness gossip, and the E8 experiment.

**M4** — the WEFT reciprocal witnessing mesh: co-signed agent-to-agent session
digests with refusal-as-signal, and the E9 coverage simulation that refuted the
paper's percolation conjecture.

## Run it

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python3 test_pact.py     # 49 checks, 23 RED (each mutation-verified)
./.venv/bin/python3 e14.py           # E14 detection quality + lone-detector rule
./.venv/bin/python3 e7.py            # E7 precedent graph + threshold safety band
./.venv/bin/python3 e8.py            # E8 federation, provability, equivocation
./.venv/bin/python3 e9.py            # E9 mesh coverage + percolation test
./.venv/bin/python3 e13.py           # E13 real evaluator models as jurors
./.venv/bin/python3 pactctl.py bench -n 3000
```

Full loop:

```bash
rm -f pact.db && ./.venv/bin/python3 pactctl.py demo -n 1000
./.venv/bin/python3 pactctl.py prove 123      # Merkle inclusion proof
./.venv/bin/python3 pactctl.py sample -k 5    # RLA draw off the witnessed root
./.venv/bin/python3 pactctl.py jury 7         # full jury adjudication on the ledger
./.venv/bin/python3 pactctl.py erase 42       # GDPR path, chain stays valid
./.venv/bin/python3 pactctl.py tamper 500 && ./.venv/bin/python3 pactctl.py verify
```

Shim (mock model; set `PACT_UPSTREAM` for a real endpoint):

```bash
./.venv/bin/python3 shim.py
curl -s localhost:8787/v1/chat/completions -d '{"messages":[{"role":"user","content":"hi"}]}'
```

## Measured (M3 MacBook, single thread, 2026-09-12)

**Append path** (`pactctl.py bench` — each optimization independently toggleable, so
the attribution is measured, not asserted). 567 µs p50 naive → **122 µs p50 / 142 µs
p95**, 7,800 entries/s: write-ahead logging **2.2×**, caching the deserialized
signing key **1.7×**, batched commits **1.2×**, **4.6× end to end**. Profiling says
the remainder is **76% Ed25519 signing**, i.e. the path is signature-bound and the
signature is the guarantee; going further means batch-signing groups of entries, not
micro-optimization.

**Footprint.** Entry ~406 B operator-side; witness-cosigned checkpoint ~663 B;
shared-ledger cost **13.3 B/query** at 50-entry checkpoints, ~0.07 B/query at the
10⁴-entry batching the paper assumes.

**Integrity.** Tampering one entry breaks that entry and every checkpoint covering
it while earlier checkpoints stay valid — detection localizes the edit to one
checkpoint window. Witnesses refuse to cosign rewritten history. A juror who commits
one verdict and reveals another is named. All three are RED-proven tests.

**E2 detection (420 labeled actions, 4 violation tiers incl. novel vocabulary).**

Scored **oracle-free** — an earlier version credited every escalated case with the
true label, which assumed perfect human review and produced an F1 of 0.997 that
mostly measured that assumption.

| rule | contained | leaked | auto-precision | human load |
|---|---|---|---|---|
| symmetric 2/3 | 0.537 | 0.463 | 0.974 | 39.0% |
| + lone-detector | **0.750** | **0.250** | 0.974 | 53.3% |

End-to-end F1 *if* human review is right h of the time (assumption, swept):

| rule | h=1.00 | h=0.95 | h=0.90 | h=0.80 |
|---|---|---|---|---|
| symmetric 2/3 | 0.695 | 0.676 | 0.660 | 0.614 |
| + lone-detector | 0.853 | 0.827 | 0.805 | 0.751 |

Best single family: `contrastive`, F1 0.723. The lone-detector rule buys
**containment, not detection** — it converts silent auto-clears into escalations,
nearly halving unrecoverable leakage while the machine's own precision barely moves.

**The novel-vocabulary tier is the honest generalization test, and all five families
detect 0 of it.** The corpus was originally written from the detectors' own keyword
lists, which made their "blind spots" an artifact of authorship. E2 therefore
measures protocol behaviour given members that disagree — not detection quality.

**E5 collusion.** An operator registering 7 jurors seats ≤1 under the per-operator
cap and true violations still convict 100% at every colluder count. Remove the cap
and the same 7 take 3.5/11 seats and conviction collapses to 30%. The cap, not the
vote threshold, is what makes buying a verdict expensive.

**E7 precedent graph (420 held-out actions, 27 distinct patterns).** Jury
convocations fall **200 → 13** and human reviews **135 → 10**.

| τ | juries | reduction | precedent-resolved | prec. errors | F1 |
|---|---|---|---|---|---|
| 0.35 | 10 | 20.0× | 182 | **26** | 0.721 |
| 0.45–0.90 | 13 | 15.4× | 187 | 0 | 0.769 |
| 0.95 | 44 | 4.5× | 156 | 0 | 0.750 |

The binding ceiling is set by patterns that actually **reach** the funnel (13 of 27
survive the screener), not by all distinct patterns — so the ceiling is 15.4× and
the mechanism **meets it exactly**. The earlier "15.4× against a 15.7× ceiling,
falls just short" framing divided by patterns no jury ever sees.

Landmarks are now **searched**, not hand-picked: over all 420 actions the closest
same-bucket pair is **0.993** and the closest opposite-label pair **0.423**. Too
loose and benign text inherits a violation verdict; too tight and genuine repeats
stop matching. **The threshold is a safety parameter, not a tuning knob.**

Two honest limits:

1. **The reduction ceiling is pattern count, not the mechanism.** Any 100–1000×
   claim is a claim about *traffic repetitiveness*, not about PACT.
2. **Rung 0 is the dominant weakness — direction solid, magnitude not.** The trained
   screener recalls 0.625 on unseen phrasings in the headline split, but across 8
   equally valid template splits recall ranges **0.250–0.625** (median 0.500).
   Whatever it misses is auto-cleared and never reaches adjudication, which is the
   strongest argument in these results for risk-limiting audit sampling — it draws
   from all covered actions and is independent of screener error.

**Attestation (P1).** Entries carry a runtime measurement checked against the
agent's registry; an entry from an unapproved image fails verification, and an agent
with *no* registered runtime is reported `attested: False` with a warning rather than
passing silently (`strict=True` makes it an error). Simulated — the measurement is
asserted, not TEE-quoted.

**E13 — real evaluator models as jurors.** Three real Claude tiers (haiku, sonnet,
opus, as they behaved on 2026-09-12 — exact build versions were not pinned) were given
the same 70 labeled items under one policy clause, blind. Run `./.venv/bin/python3
e13.py` to reproduce.

- **Real models clear the rule-based stand-ins comfortably, and do not saturate.**
  F1 0.512 / 0.862 / 0.900 against the best stand-in's 0.577, with 21, 8 and 6 errors
  out of 70. Unlike the withdrawn corpus this one leaves real errors to correlate,
  which is what makes the next finding possible at all.
- **They do not fail independently.** Pairwise observed/expected joint-error ratios
  of **2.5×, 2.8× and 8.8×** — mean **4.7×** — where independence would give 1.0×.
  The highest ratio is between the two closest-lineage models.
- **Five items defeat all three, and 100% of them are `contested`.** The models
  converge on the easy calls and make the *same* error on the hard ones. That is the
  worst failure shape a jury can have: agreement where agreement is cheap, correlated
  error where the verdict matters.
- **Scope.** Three tiers from ONE vendor, 70 items, one prompt framing. Same-vendor
  models share tuning lineage, so 4.7× is plausibly an **upper bound** on what a
  cross-vendor panel would show. A cross-vendor replication is the obvious next
  experiment — see the top-level `README.md` for how to run this on your own models.

**Juror availability falls as severity rises.** In a companion run on the corpus since
withdrawn, two of three models refused the adjudication task outright, reporting
safeguard categories. A juror must read what it judges, so models tuned to refuse
engagement with sensitive content also refuse to *moderate* it: **juror availability is
anti-correlated with case severity**, and the panel thins toward the least cautious
models exactly where care is most needed. The refusals were recorded as a finding and
the run stopped there rather than being rephrased to get past the safeguards.

That last one changed the protocol. `ABSTAIN` is now a first-class verdict: it
counts toward neither side, is never slashed, and abstentions that drop a panel
below quorum or below its family floor force escalation instead of a verdict from
the remainder. Equivocation is still punished — including committing a verdict and
then abstaining at reveal, which a first draft of this fix accidentally permitted
(mutation testing caught it).

**Post-review hardening (see `../REVIEW-FINDINGS.md`).** An adversarial review found ten
Tier-1 defects where a property the paper claims was not enforced by the code. All are
fixed, and each fix carries a test verified to fail when the fix is reverted. The
load-bearing ones: Merkle proofs are now bound to their position (the old
`verify_inclusion` ignored `index` entirely, so any proof verified anywhere);
`mesh.verify_record` now checks the signatures a record *carries* instead of re-signing
live (the old one returned True for fabricated records); commit–reveal nonces are now
secret randomness (the old ones were derivable from public inputs, so every vote could
be read before reveal); verdicts carry jury evidence and `verify_verdict` flags
self-issued ones; and the severity ladder actually moves stake and registry status,
with `gate_check()` refusing a suspended agent.

**E8 federation.** Four tiers: agent → operator → shard → witness-cosigned root.

- **Ledger load is flat in traffic.** Root cost per epoch is a function of shard
  count alone (~9.7 KB for 10 shards, 10 witnesses) — no query rate moves it.
- **Aggregation fits the epoch budget 125× over.** Sealing 10,000 operators /
  100,000 agents costs **0.48 s**, 0.8% of a 60 s pin interval, because it hashes
  roots not payloads. Pin latency is the configured interval, not compute.
- **Bandwidth is batched; trust is not.** One action out of 100,000 stays provable
  to the planetary root in **22 hashes, 2.3 KB, verified in 36 µs** — 9 hops at 10
  entries, 15 at 10³, 22 at 10⁵. Proofs are owner-bound at each tier, so a valid
  subtree re-claimed under another identity is rejected (RED-tested).
- **Quorum degrades gracefully**, and the log records the shortfall rather than
  failing silently.

**E9 mesh coverage — the percolation conjecture is dead.** 2,000-agent random and
scale-free graphs.

| p | random graph | scale-free | predicted 1−(1−p)² |
|---|---|---|---|
| 0.10 | 0.195 | 0.178 | 0.190 |
| 0.50 | 0.766 | 0.739 | 0.750 |

- **Observation never propagates.** Interactions observed without an instrumented
  endpoint: **0 at every p**. An instrumented agent records its own interactions and
  nothing beyond. Coverage is strictly one-hop; the coverage derivative is flat, with
  no threshold or phase transition. Four-hop workflows: "all hops observed" 0.045 vs
  "≥1 hop" 0.338 at p=0.10 — workflows are seen in fragments.
- **Scale-free is harder, not easier.** Skewed degree (median 2, max 86) means random
  picks usually hit low-degree agents, so realistic topology *underperforms* the
  pairwise formula.
- **What replaces it: degree-weighted exposure**, 1−(1−p)^degree. At p=0.10,
  degree-16+ agents are exposed **0.86** vs **0.17** for degree-1–2 — a 5× gap
  favouring exactly the heavily-used services that matter.
- **Chokepoints quantified.** Instrumenting the top 1% by degree covers 22% of all
  interactions — what ~12% random instrumentation buys, a **12× efficiency multiple**.
  It does *not* beat 50% random (0.74); the claim is efficiency per agent, not reach.

**Equivocation: the zero is the finding.** A shard showed a forged root to 3 of 10
witnesses. Detected by any witness **alone: 0**. Detected by witnesses **comparing:
21** (= 3 deceived × 7 honest). Locally consistent deception is locally invisible —
so cross-witness gossip is *mandatory*, not an optimization: a fabric that cosigns
without comparing detects nothing at all, however large it is. The paper now
specifies it as such.

## Honest scope

Dev keys live beside the data (the paper wants enclave keys); one process;
attestation is simulated, not TEE-quoted; the federation's tiers are objects in
that process rather than separate hosts, so E8 measures aggregation arithmetic and
protocol logic and says **nothing** about network behaviour, real clock skew, or
Byzantine validators; jurors in E14 are deterministic heuristic detectors of five families,
not hosted models, so those numbers stay reproducible offline — E13 is the experiment
that uses real hosted models, and it reads their recorded verdicts from
`jury_verdicts.json` rather than calling an API at run time; the corpus is synthetic text from a
generator we wrote, which can separate detectors and expose protocol-level effects
but cannot stand in for real traffic; E9's graphs are synthetic topologies, not a
measured agent economy, so they bound the mechanism rather than predict deployed
coverage. No process proofs or receipt-robustness work yet.

This exists to make the paper's core loop runnable and falsifiable. So far it has
corrected four of the paper's own claims:

1. **M1** — majority voting is not safe for adjudication; a 2/3 jury can score below
   its own best member by voting down a lone correct detector.
2. **M2** — the precedent speedup is a property of traffic repetitiveness, not of the
   architecture; and the similarity threshold is a safety parameter.
3. **M3** — a witness fabric does *not* detect equivocation unless witnesses compare
   notes; gossip is mandatory, not an optimization.
4. **M4** — mesh coverage does not percolate. It is strictly one-hop and
   degree-weighted; the conjecture is withdrawn.
