# PACT-2 — A Planetary Federation for AI Accountability

**v2 architecture: faster, smarter, and scoped to monitor most of the world's models — built as a technical answer to the standing public calls for verifiable AI oversight.**
Saish Shinde, 2026-09-12. Companion to `ARCHITECTURE.md` (v1). v1 stays the per-deployment protocol; v2 is the planetary federation wrapped around it.

---

## 0. What this is

Prominent industry calls for AI oversight converge on three asks, and all three are verification problems:

1. Third-party evaluators with employee-level access to verify safety and guarantee slowdown compliance.
2. AI companies in democracies setting common safety standards.
3. Democratic governments coordinating with authoritarian ones on AI — "verification here is critical."

All three are institutional commitments with no technical substrate. "Employee-level access" is a badge and an NDA; a common standard is a PDF; international verification is a diplomat's promise. Each one currently reduces to *trusting the audited party's own records*.

PACT-2 is the substrate: a three-tier planetary federation in which conduct evidence is captured at the serving edge, aggregated through jurisdictional shards, and pinned to a thin global root that mutually distrusting parties — rival labs, rival states — can all verify and none can rewrite. §6 maps each of these asks to a concrete subsystem.

**Design targets (the numbers the architecture must hit):**

| Target | Value |
|---|---|
| Covered actions | ~10¹⁰–10¹¹ per day planet-wide (order of all daily AI interactions) |
| Evidence finality (edge → globally pinned) | ≤ 60 s |
| Screening verdict on flagged conduct | seconds |
| Adjudicated verdict, routine case | minutes (precedent path) |
| Human-touched cases | ~10² per day globally — everything else machine-resolved with appeal rights |
| Marginal logging overhead at the edge | < 1% p50 latency |

---

## 1. Why v1 doesn't scale to "most models in the world"

Three bottlenecks, honestly named:

- **B1 — one consortium chain.** A single BFT validator set cannot absorb planetary checkpoint traffic, and no single consortium is politically acceptable to every jurisdiction.
- **B2 — jury latency.** Full k=11 juries with commit-reveal take minutes-to-hours per challenge. Fine for hundreds of challenges; dead at millions.
- **B3 — opt-in coverage.** v1 covers whoever installs the shim. "Most models in the world" never voluntarily install anything.

PACT-2 answers: B1 → hierarchical federation with no global consensus on evidence (§2). B2 → tiered adjudication funnel with a precedent graph (§3) and statistical auditing (§4). B3 → chokepoint instrumentation plus a passive observation layer (§5).

---

## 2. Federation topology — evidence needs no global consensus

The key structural observation: **per-agent logs are independent hash chains. They commute. Nothing about evidence requires a total global order.** Only governance actions (challenges, verdicts, stakes, registry changes) need consensus, and those are rare. So:

```
agent log  →  operator log  →  shard ledger (jurisdiction / sector)  →  planetary root
   (ms)          (seconds)          (seconds, DAG-BFT)                    (~1 min epoch)
```

- **Edge.** Serving runtimes emit signed hash-chain entries exactly as in v1. Nothing changes at the shim.
- **Operator aggregation.** Operators fold agent-log roots into an operator-level Merkle log continuously.
- **Shards.** ~10²–10³ shard ledgers, drawn on jurisdictional and sectoral lines (EU shard, US shard, healthcare shard, frontier-lab shard…). Each shard runs its own validator set under its own law — this is what makes the design *politically* deployable, not just technically. Shards run modern DAG-BFT: measured systems do 100k–400k tx/s at sub-second to ~1 s latency (Bullshark ~75–100k tps; Mysticeti 300–400k tps under 1 s with a 3-message-round lower bound; Shoal++ sub-second at 100k+ tps). Governance consensus is never the bottleneck — the arithmetic below shows shard load is orders of magnitude under these ceilings.
- **Planetary root.** Deliberately *not* a blockchain. A thin transparency log of shard roots, cosigned each epoch (~60 s) by a global **witness fabric**: hundreds of independent witnesses run by labs, universities, NGOs, and governments — including adversarial ones (§6.3). Witness cosigning at this scale is measured territory: CoSi aggregated 8,000 witness cosignatures across simulated 200 ms RTTs in ~2 s per round; tamper-evident hardware witnesses (Armored Witness) already exist as deployable boxes. The root holds ~10³ shard-root updates per minute — trivially small, absurdly replicated.

**Checkpoint arithmetic.** 10⁷ concurrent covered agents, one checkpoint per minute each = 1.7×10⁵ checkpoint writes/s planet-wide. Absorbed at operator + shard level (each shard sees only its slice; a big shard handles ~10²–10³ writes/s against a 10⁵/s ceiling). The planetary root sees ~17 writes/s. Every layer has 100–1000× headroom.

**Equivocation dies at the root.** A shard (or state) that shows different histories to different audiences is caught by any two honest witnesses comparing cosigned roots — split-view is the one attack the topology makes structurally loud.

---

## 3. The speed layer — an adjudication funnel with early exits

v1's jury is the *last* resort, not the first responder. Five rungs, each with a latency budget and an early exit; every rung's decision carries an appeal right upward.

```
Rung 0  Edge screeners        µs–ms     co-located small safety classifiers risk-score
                                        every entry into the log itself
Rung 1  Precedent matcher     ms–s      embedding lookup against the adjudicated case
                                        graph; ≥τ similarity ⇒ auto-verdict citing precedent
Rung 2  Screening jury k=3    seconds   SPRT early stopping: unanimous-fast cases close
                                        in one round
Rung 3  Full jury k=11        minutes   v1 protocol: VRF-sampled, operator-diverse,
                                        commit-reveal
Rung 4  Human board           hours+    severity ≥ S2, splits, novel precedent
```

**Funnel math at planetary load:** 10¹⁰ actions/day → screeners flag 0.1% → 10⁷ flagged → precedent matcher resolves 99% → 10⁵ to screening juries → 10% escalate → 10⁴ full juries → ~1% → **~10² human cases per day, globally.** Human attention becomes the scarce resource the architecture explicitly budgets — which is exactly the "scalable oversight" shape safety research keeps asking for.

**The precedent graph is the core v2 novelty on the speed axis.** Every adjudicated case (evidence commitments, clause, verdict, rationale) becomes a citable precedent node. Matching is by embedding similarity plus clause identity; auto-verdicts cite their precedent chain and are appealable to the rung above. Conflicting precedents force escalation — that's how doctrine evolves. This is common law, mechanized: the marginal cost of justice for a *repeated* violation class falls toward an embedding lookup, and jury capacity concentrates on genuinely novel conduct. Precedents themselves are covered artifacts — challengeable, revisable by a superseding full-jury or human ruling (stare decisis with an explicit override path, so early bad verdicts don't fossilize).

**Screening juries stop early.** Sequential probability ratio testing on juror votes: a 3-0 with high-confidence rationales closes immediately; anything contested escalates. Most flagged conduct is obviously-fine or obviously-bad; spend jury tokens only on the middle.

---

## 4. The smart layer — statistics instead of exhaustiveness

**Risk-limiting audits (RLA), imported from election auditing.** Don't verify everything; verify a random sample sized to a stated confidence. PACT-2's auditor claim has the form: *"with 99% confidence, this model's violation rate on covered traffic is below ε."* VRF-drawn sample (unpredictable, unriggable), Merkle-proven membership (operator can't cherry-pick), sample size independent of traffic volume for a fixed (ε, confidence). This converts "we can't check 10¹⁰ actions" from a defect into a non-problem.

**Adaptive sampling.** Per-model sampling rate ∝ capability tier × inverse reputation × recency of incidents. A frontier agentic model with tool access gets orders of magnitude more scrutiny per action than a sentiment classifier. Reputation earns back scrutiny relief — the incentive loop that makes operators *want* clean records. Sampling posture is public; the draw itself is unpredictable.

**Sealed evals — pre-registration for capability and safety tests.** Common-standard eval suites are committed as hashes *before* any lab runs them; prompts revealed only at execution, results logged as covered actions. Kills teaching-to-the-test and quiet benchmark gaming; gives plank 2 (§6.2) its teeth. Continuous conformance replaces the annual audit PDF.

**Federated anomaly exchange — epidemiological surveillance for AI.** Shards exchange differentially-private sketches of behavior distributions and signed *incident signatures* (jailbreak patterns, misuse motifs) — the MISP/threat-intel model applied to model conduct. A jailbreak burning through one shard's models becomes a planetary alert in minutes, without any raw prompt crossing a border. The system behaves like a CDC for AI: local cases, global situational awareness.

---

## 5. The coverage pyramid — "most models in the world" without asking each one

Nobody instruments 10⁸ models one by one. You instrument the funnel the world's inference already flows through, then observe the remainder from outside.

| Tier | Who | How covered | Order |
|---|---|---|---|
| A | Hyperscaler clouds + frontier API providers | Native PACT shim in serving stacks; TEE attestation | ~10 orgs ≈ majority of world inference FLOPs |
| B | Model hubs, inference platforms, app stores, API marketplaces | Gate: listing/serving requires registry status + provenance manifests | ~10² orgs |
| C | Accelerator vendors | On-chip/driver-level workload attestation; training-run declarations (compute accounting) | ~5 orgs — the long-run strongest lever |
| D | Self-hosted, open-weights, uncooperative | Passive observation layer (below) | everyone else |

Precedent says chokepoints work: Certificate Transparency covered effectively the entire web through ~6 browsers and ~60 CAs. Tier A+B is the same play — cover the funnel and you cover most models *without their individual consent*, because their distribution channel is covered.

**Tier D — the passive layer, coverage without cooperation.** Uncovered models with public endpoints are still observable:
- **Probe networks:** watchdog agents run standing mystery-shopper probes against public endpoints; probe transcripts are themselves covered actions, so findings arrive as well-formed challenges with evidence.
- **Provenance absence as signal:** as C2PA-style manifests become the norm on Tier A/B output, unprovenance'd AI content becomes machine-flaggable residue.
- **Incident federation:** AI-incident registries (AIID-style, EU AI Act Art. 73 serious-incident reports) feed the same shard ledgers, so uncooperative-model harms accumulate as a public, non-repudiable record even when attribution is behavioral rather than cryptographic.
- Honest caveat, stated in the paper: Tier D gives *detection and public record*, not attribution-grade proof. The pyramid narrows what "unmonitored" means; it does not abolish it.

**Adoption flywheel (what makes A/B sign up):** compliance-by-construction (Art. 12 logs and Art. 73 reports auto-generated from the ledger), insurance priced on registry status, procurement mandates, legal safe-harbor treatment of logged conduct as due-diligence evidence, and scrutiny relief via reputation (§4). Regulation supplies the push; cost relief supplies the pull.

---

## 6. Answering the three asks (the novel part)

### 6.1 Plank 1 — "third-party evaluators with employee-level access" → the Evaluator Access Plane

Badge-access is both too weak and too strong: too weak because an evaluator can't prove what they saw was the real system (a lab can stage a Potemkin view), too strong because labs rationally fear IP leakage, which caps how much access they'll ever grant. Cryptographic access dominates on both axes:

- **Verifiable views.** Evaluators read through Merkle-proven queries against the witnessed log — every view provably a slice of the *same* record everyone else is pinned to. Split-view against an evaluator = split-view against the world's witnesses = caught.
- **Standing tripwires.** Evaluators register standing queries compiled against L4 clauses ("alert on capability-eval X exceeding threshold Y", "alert on deployment of unregistered weights"). Monitoring becomes continuous, not visit-based — closer to *resident inspector* than annual auditor.
- **Bidirectional accountability.** Evaluator reads are themselves covered actions. Labs get leak deterrence and a non-repudiable record of exactly what left the building; evaluators get non-repudiable proof of what they were and were not shown. That symmetry is what makes deep access *grantable* — it de-risks the lab side of that commitment, turning "we'll give evaluators access" from a trust-us pledge into an auditable protocol any lab can adopt.
- **Slowdown compliance, specifically:** pause commitments compile to L4 clauses over registry state (no new frontier-scale training-run declarations above compute threshold C during window W; no deployment of models above capability gate G). Tier C attestation + training-run declarations make violations of a declared pause *evidenced*, not rumored.

### 6.2 Plank 2 — "common safety standards" → the Common Standards Registry

Standards become code-objects, not PDFs: a shared clause library on the planetary root that each lab's L4 policy imports and extends (a lab may exceed the floor, never silently fall below it). Conformance is continuous — sealed evals (§4) run as covered actions, results pinned, deltas public. Divergence between what a lab signed and what its deployments enforce is machine-detectable. "Common standards" stops meaning "we all published similar principles" and starts meaning "we import the same clauses and the same tests prove we enforce them."

### 6.3 Plank 3 — "coordinate with authoritarian governments; verification is critical" → the International Safeguards Tier

The hardest plank, and the one federated design exists for. Precedent: nuclear arms control worked not on trust but on *verification machinery* — declarations, safeguards, inspections, seals. PACT-2 is that machinery, cryptographic:

- **Sovereignty-compatible shards.** Each bloc runs its own shard under its own law. No raw data crosses borders — only shard roots, aggregate attestations, and treaty-relevant declarations. A state federates without exposing citizens' data or domestic-model internals: this is what makes joining *possible* for a government that will never accept a foreign-hosted database.
- **Cross-witnessing as the treaty instrument.** Each party witnesses the *other's* shard roots — tamper-evident witness hardware physically deployable in the other bloc's territory, the cryptographic equivalent of resident inspectors. Neither side can rewrite history without handing the other side proof of the rewrite. Mutual distrust becomes the security assumption instead of the failure mode.
- **Compute declarations at Tier C.** Accelerator-level attestation and training-run declarations (compute-accounting line of work) give treaty verification its physical anchor — large training runs are hard to hide from the layer that ships and meters the chips. Declared-vs-attested discrepancies are exactly the "evidence, not accusation" artifact arms-control regimes run on.
- **Graduated disclosure.** Blocs negotiate what crosses the root: existence proofs only, aggregate safety-eval attestations, or sampled conduct audits under RLA guarantees (§4) — a ratchet treaties can tighten stepwise, with each step verifiable before the next is granted.

One-line version for the paper: **What is being asked for is verification across mutually distrusting parties; mutual distrust is the exact threat model this ledger is built for. Those asks are the requirements document; PACT-2 is the reference implementation.**

---

## 7. Novelty claims for paper v2 (each must survive related-work check)

1. **N1 — Consensus-free planetary evidence plane:** per-agent chains → shard ledgers → witness-cosigned root; global consensus only over ~10³ shard roots/min, never over conduct data.
2. **N2 — Precedent-graph adjudication ("mechanized common law"):** adjudicated cases as citable, challengeable precedent nodes; auto-verdicts with appeal; an unverified 100×–1000× jury-load reduction target (v1 measured 6.0×, bounded by pattern count — see PAPER.md §VII-D).
3. **N3 — Risk-limiting audits for AI conduct:** election-audit statistics giving (ε, confidence) violation-rate guarantees under VRF sampling with Merkle-proven membership; adaptive scrutiny priced by capability × reputation.
4. **N4 — Evaluator Access Plane:** verifiable views + standing tripwires + bidirectionally logged access as the cryptographic replacement for (and enabler of) employee-level evaluator access.
5. **N5 — Cross-witnessed safeguards tier:** sovereignty-preserving shard federation with reciprocal witness deployment and compute declarations — an arms-control-shaped verification regime for AI treaties.
6. **N6 — Sealed evals:** pre-committed, post-revealed common eval suites logged as covered actions — anti-gaming conformance for common standards.

Positioning vs the closest commercial work (EQTY Lab's verifiable-governance products on Hedera + NVIDIA, 2025–26): that line proves demand and shares the attestation-to-ledger move, but is a single-vendor enterprise compliance product anchored to one chain — no adversarial adjudication loop, no jury protocol, no precedent system, no multi-bloc federation, no evaluator plane. PACT-2 is an open protocol for *mutually distrusting* parties, with the accountability loop closed end-to-end.

---

## 8. Feasibility — the measured numbers this design leans on

- **TEE attestation is deployable now:** NVIDIA cites 2–5% throughput overhead for H100 confidential computing on typical LLM serving; independent benchmarking shows worst cases of ~21–30% TTFT and ~18–21% token-throughput cost on small/mid models under fixed request rates, shrinking toward zero for 70B-class models; attestation itself is a 1–3 s one-time cost per instance. Rung-1 verification is affordable today, with published numbers to cite.
- **zkML is not ready to be load-bearing:** proof generation for a 7B model remains ~2.6×10³ seconds *per token* on general compilers; zkLLM's specialized CUDA pipeline buys ~50× but still lands at minutes-to-hours per inference, though verification is sublinear (seconds) and proofs are tens of KB. Exactly as v1's ladder assumed: zkML slots in for small judge models first. The design would be wrong if it depended on zkML; it doesn't.
- **Witness fabrics scale:** 8,000-witness cosigning rounds complete in ~2 s under WAN delays (CoSi); production witness specs (C2SP tlog-witness) and tamper-evident witness hardware (Armored Witness) exist. A planetary root cosigned by hundreds of witnesses per minute is comfortably inside measured territory.
- **Shard consensus has 100–1000× headroom:** DAG-BFT systems sustain 100k–400k tx/s at ≈ sub-second finality (Bullshark, Mysticeti, Shoal++). Even a pessimistic 10⁷ governance tx/day planet-wide is ~10² tx/s — noise for a single shard, let alone hundreds.
- **The funnel makes human oversight finite:** 10¹⁰ actions/day compresses to ~10² human cases/day (§3) — the first planetary-oversight design where the human layer has a stated, plausible budget.

---

## 9. Honest risks (paper's discussion section, v2 additions beyond v1 §9/§9.5)

1. **Screeners miss what they can't classify.** Rung-0 classifiers define the flag distribution; novel harms evade novel-harm-blind screeners. Mitigations: RLA sampling is screener-independent (random draws catch what classifiers don't), probe networks hunt actively, screener models are covered + challengeable. Residual risk stated plainly.
2. **Precedent lock-in.** Early bad verdicts could fossilize. Supersession path (full jury / human board overrides), precedent decay windows, conflicting-precedent forced escalation.
3. **Chokepoint politics.** Tier A/B coverage concentrates power in platforms; governance of the gatekeepers matters as much as of the models. Consortium seats + witness fabric include non-platform actors by construction.
4. **Authoritarian gaming.** A bloc can run a parallel unlogged stack; safeguards verify *declared* activity plus Tier-C physical signals. Same honest limit as arms control — verification narrows cheating space and raises its cost/evidence trail; it cannot abolish covert programs. Say so.
5. **Tier D is detection, not proof.** Never let the paper imply the passive layer gives attribution-grade coverage.
6. **DP sketches leak or lie.** Anomaly exchange uses differential privacy + signed provenance of sketches; poisoned sketches are challengeable like any covered artifact.

---

## 10. Build deltas (extends v1 milestones M0–M3)

- **M4 — Funnel:** rung-0 screener integration in the shim; precedent-graph store + matcher; SPRT screening juries. Measure: jury-load reduction vs v1 on replayed E14 traffic.
- **M5 — Federation:** two shards + planetary root + ≥10 independent witnesses (recruit via transparency-dev-style community); cross-shard verdict settlement. Measure: edge→root pin latency ≤ 60 s.
- **M6 — Planes:** Evaluator Access Plane MVP (verifiable views + one standing tripwire) and sealed-eval flow on a public benchmark. This is the demo that speaks directly to plank 1 and plank 2.

Paper strategy update: v1 = systems paper (protocol + measurements). v2 = the *vision/architecture* paper — "an accountability substrate for humanity's use of AI" — aimed at a venue that rewards scope (IEEE S&P/CCS SoK-adjacent, or a strong FAccT/AIES main-track slot), with v1's prototype as the existence proof. Two papers, one repo.
