# Adversarial review — findings

Seven independent hostile reviewers over PAPER.md and the M0–M4 implementation, each
followed by a skeptic tasked with *refuting* its findings against the running code.
**30 confirmed, 5 partial, 1 refuted.** Reviewers executed the code; most findings were
reproduced with a script before being reported.

One caveat on completeness: the `reviewer2` refuter died on an API error, so the
hostile-program-committee lens produced findings that were **never verified**. They are
excluded below. That lens needs a re-run.

Severity here is mine, reconciled against the refuters' corrections.

---

> **Status 2026-09-12: ALL FOUR TIERS ARE FIXED.** Every code fix carries a test that was
> verified to fail when the fix is reverted — mutation-checked one at a time, because
> findings 3.1–3.3 showed that passing tests proved nothing here. Suite is now **47 checks
> with 22 RED**. Every quantitative claim in PAPER.md §XI-B was re-derived from live output
> and cross-checked; the paper gained a new §XI-C reporting this review and what it changed.
>
> **Tier 2 fixes moved numbers downward, as they should.** The headline F1 0.997 is
> withdrawn (it assumed perfect human review); the best single detector fell 0.857 → 0.723
> once a novel-vocabulary tier was added that no family detects; the screener's 0.667 recall
> is now reported as a 0.250–0.625 range across splits. See "Tier 2–4 fixes as applied".

## Tier 1 — Claimed security properties the code does not enforce *(FIXED)*

These are the serious ones. In each case the paper asserts a property, and the
implementation does not deliver it.

### 1.1 Merkle proofs are not bound to a position (critical)
`verify_inclusion(leaf, index, path, root)` **never reads `index`**. The parameter is
dead; the body only walks `path`. Consequence: a genuine proof verifies against *any*
claimed position. Reproduced at three layers — raw tree, `Store.prove`, and the 4-tier
`Federation.verify_proof`, where relabelling `seq` to 3 or setting every tier's `idx` to
999 still returned `True`.

This directly contradicts §V-A's "a WEFT receipt encodes a *position* in an accountable
record", and it weakens the E8 provability result: the proof demonstrates membership,
not the ordering that the hash chain is supposed to establish.
*Files:* `pactlog.py:64-69`, consumed at `pactlog.py:316`, `federation.py:172-184`.

### 1.2 `mesh.verify_record()` is tautologically true (critical)
`MeshAgent.log` stores **no signature** — only a `cosigned` boolean and a transcript
hash. `verify_record()` then re-invokes `agent.offer()` *live*, with whatever transcript
the verifier passes in, and checks that fresh signature against itself. A reviewer
verified a record for a transcript that was never exchanged, and then verified a
**fabricated record that never went through `session()` at all**.

Contradicts §X's "a fabricated session digest lacking the counterparty's signature is W0
hearsay by construction."
*Files:* `mesh.py:31-36, 55-57, 70-86`.

### 1.3 Commit–reveal provides zero hiding (critical — found independently by two lenses)
The nonce is `H(juror_id ‖ round_seed)` where `round_seed` is derived from public inputs;
the rationale is `f"{family} family assessment"`, deterministic from the juror's family;
the verdict space is two values. An observer can therefore precompute both candidate
commitments per juror and **read every vote before reveal**. Reproduced on both unanimous
and mixed juries, recovering all 11 verdicts.

Voids §IV-D's "commit–reveal voting eliminates copy-voting" — the mechanism is present in
form and absent in substance.
*Files:* `jury.py:112-129, 100, 166-167`.

### 1.4 Verdicts are unauthenticated and can bypass the jury entirely (high)
`store.verdict()` takes any verdict for any challenge with no proof a jury ran. Nothing
on the ledger distinguishes a jury-produced verdict from a self-issued one, so **P5
Adjudicability is not an enforced property**. Relatedly, `adjudicate()` computes the
commit–reveal check but never acts on its result.
*Files:* `pactlog.py:381-399`, `jury.py:174-176`.

### 1.5 Attestation is opt-in and silently absent by default (high)
`verify()` only checks runtimes when the agent has registered at least one. A fresh agent
that never registers gets `ok: True` **with a rogue runtime string**. The paper's
"nothing fails silently" is violated exactly here: the default is silent non-enforcement.
*Files:* `pactlog.py:279`.

### 1.6 Most consequence-binding is a no-op (high)
P6 claims stake slashing, challenger-bond forfeiture, juror stake, and registry
suspension. Only the reputation float (×0.8) is implemented. The `FRIVOLOUS` branch is
literally `pass`. Three of four claimed consequence types do not exist in code.
*Files:* `pactlog.py:394-399`.

### 1.7 Jury seed omits the anti-grinding anchor the paper specifies (high)
§IV-D says the VRF is "seeded by finalized block hash and challenge id". The code seeds
on `challenge_id + agent + entry_text` — all attacker-known or attacker-influenceable,
and `challenge_id` is an unauthenticated AUTOINCREMENT. A reviewer ground `challenge_id`
to force `CLEARED` at high rate **even under the asymmetric lone-detector rule**.
*Files:* `jury.py:166`, `pactlog.py:366-379`.

### 1.8 Disclosed payloads are never checked against their commitment (high)
`disclose()` computes `commits_match`, and `cmd_jury` never reads it. A swapped payload
is laundered through adjudication with no flag.
*Files:* `pactctl.py:82-99`, `pactlog.py:336-347`.

### 1.9 `erase()` can destroy evidence under an open challenge, unlogged (medium)
No guard against erasure during an active challenge, and — unlike every other adversarial
event in this codebase — the erasure itself leaves no ledger entry.
*Files:* `pactlog.py:349-352`.

### 1.10 Merkle odd-node duplication, CVE-2012-2459 pattern (medium, not currently exploitable)
Odd levels duplicate the last node, so `merkle_root([a,b,c]) == merkle_root([a,b,c,c])`.
The refuter confirmed the ambiguity *and* confirmed it is not live-exploitable, because
`seq`+`prev` in log entries and `leaf_for()` owner-keying in federation tiers force every
real leaf to be distinct. Worth fixing anyway — the invariant is accidental.
*Files:* `pactlog.py:38-46, 49-61`.

---

## Tier 2 — Results that do not measure what the paper says they measure

### 2.1 The flagship result is an oracle-human artifact (critical)
The abstract's headline — lone-detector escalation reaching **F1 0.997, +0.140** — is
driven by `pred.append(it["label"])`: every escalated case is resolved *correctly by
assumption*. The asymmetric rule mostly increases the escalation rate, and escalation is
scored as free perfect accuracy. So the number substantially measures "assume humans are
perfect", not the voting rule.

The underlying negative finding (symmetric 2/3 voting scoring below its best member) is
unaffected and stands. The *fix's* headline number does not.
*Files:* `e2.py:104`, `e7.py:53,62`; PAPER.md abstract and §XI-B.

### 2.2 The "diverse" jury families are not independent of the corpus (high)
All 20 explicit/paraphrase violation templates **verbatim contain jury.py's hardcoded
detector substrings**. The corpus was written from the detectors' vocabulary, so family
"blind spots" are constructed, not organic, and the diversity result cannot speak to
whether real evaluator models fail independently.

This is the fourth instance of the same error class in this project (after the rigged
`contrastive` classifier, the unsupported threshold claim, and the scale-free inversion).
*Files:* `jury.py:23-27` vs `corpus.py:46-69`.

### 2.3 The 0.667 screener recall is unstable to the point of meaninglessness (high)
`split_templates` takes `tmpls[:k]` / `tmpls[k:]` with **no shuffling**. Under equally
valid shuffled splits the same pipeline yields recall from **0.083 to 0.833** (F1 0.120
to 0.800). The reported 0.667 is an 8/12 *template* pass-rate presented as instance-level
recall. The paper's "rung 0 is the dominant weakness" conclusion rests on a single draw
with enormous variance.
*Files:* `corpus.py:97-103`, `e7.py:87-93`; PAPER.md:240.

### 2.4 E7's reduction ceiling uses the wrong denominator (medium)
The 15.7× ceiling counts all 23 test templates, including those the screener never flags.
Against the 12 templates that actually reach the funnel, the observed reduction hits the
true achievable floor **exactly** — so PAPER.md:177's "hits that arithmetic ceiling
exactly" and §XI-B's "15.4 versus 15.7, falls just short" are both wrong, in opposite
directions, in the same paper.
*Files:* `e7.py:85,107-125`; PAPER.md:177 vs 238.

### 2.5 The 0.507 "nearest opposite-label pair" is hardcoded, not computed (medium)
It is an example pair I wrote in by hand, not a nearest-neighbour search, and it is not
the true nearest cross-label pair under either definition. The threshold "safety band"
conclusion rests on it.
*Files:* `e7.py:98-103`; PAPER.md:238.

### 2.6 The percolation zero is tautological (partial — disclosed but conflated)
`observed_without_instrumented_endpoint` is 0 for *any* graph by the filter's own
definition. Both the paper and the tool output say "by construction", so it is disclosed
rather than hidden — but it is presented alongside genuinely empirical results (flat
derivative, workflow fragmentation) under one "refuted conjecture" verdict. The
conjecture is still refuted; one of the three supporting numbers is vacuous.

### 2.7 W0–W4 evidentiary classes are not implemented (medium)
§V-D specifies that severity gates on evidence class ("S1 requires at least W2 support").
`tally()`/`adjudicate()` take severity as a bare string and no W-class parameter exists.
The classes are assigned in `mesh.py` and never consumed.

---

## Tier 3 — Tests that cannot fail

### 3.1 `mesh.verify_record` can be replaced with a no-op and all 33 tests pass (critical)
No test forces it to check a signature against tampered input.

### 3.2 The supermajority threshold can be changed 2/3 → 1/2 and all 33 tests pass (high)
No test constructs a vote split (6/11, 7/11) where the two rules diverge — precisely the
region the lone-detector finding is about.

### 3.3 Check #3's tamper detection is masked by redundancy (critical)
It is covered by the checkpoint-root check for this data, so it does not pin the
per-entry hash check — which is the *only* guard for an entry appended after the last
checkpoint. Remove it and that tampering is silent.

### 3.4 Check #9's operator-diversity assertion is vacuous (low)
`POOL` has exactly one juror per operator, so any 11 distinct jurors trivially have 11
distinct operators. The dedup logic is never exercised.

### 3.5 Check #21 masks a regression (medium)
It asserts accuracy, not the headlined recall. Removing the character n-gram
(obfuscation) features **improves** both metrics on this corpus — so the feature the
design justifies is currently a net negative here.

### 3.6 "8 RED detections" but only 7 are labeled (low)
Off-by-one in my own summary line.

---

## Tier 4 — Paper/code mismatches

- **Entry size**: PAPER.md says ~381 B, README says ~405 B, code prints **406 B**. Three
  numbers, one quantity. (The 381 predates the `runtime` field added in M2.)
- **The 541 µs baseline and its 2.1× / 1.7× / 1.2× decomposition are not reproducible by
  any shipped script** — WAL and key-caching are unconditional, with no toggle. A refuter
  *did* reproduce 547.96 µs by hand-reverting all three, so the number is honest, but the
  claim is not currently checkable by a reader.
- **Milestone table inconsistency** between PAPER.md:220, §XI-B, and README.

## Refuted (1)

"No code computes the E1/E6 numbers." **Refuted** — `pactctl.py bench`/`demo` produce
them; E1/E6 are evaluation-plan labels, not filenames. A refuter reran both and matched
the paper to within noise (121.5 µs vs 122; 13.27 B vs 13.3; 406 B vs ~405).

---

## What this means

The architecture survives. What did not survive was the claim that the implementation
*demonstrates* the architecture's security properties: three of them (position-bound
proofs, mutual session evidence, vote hiding) were asserted in the paper and absent in
the code, and the test suite would not have caught any of the three.

Publication order: fix Tier 1 ✅, re-derive Tier 2 numbers honestly, close Tier 3 with
tests that fail against broken code, reconcile Tier 4 — and only then convert to LaTeX.
Submitting before that risks a reviewer finding what these reviewers found, which would
be terminal for the paper's credibility.

---

## Tier 1 fixes as applied (2026-09-12)

| # | Fix | Verified RED by |
|---|---|---|
| 1.1 | Proofs carry sibling hashes only; side and sibling-presence are re-derived from `(index, n)`, and the full path must be consumed. A proof now fails at every position but its own. | reverting to index-ignoring verification |
| 1.2 | Records carry the signatures produced during the session; `verify_record(rec, pubkeys)` checks those offline against a digest built only from fields inside the record. Nothing is re-signed at verification. | gutting `verify_record` to `return True` |
| 1.3 | Nonce is 128 bits of juror-held randomness, not a function of public inputs. Commitments no longer repeat across rounds. | restoring the deterministic public nonce |
| 1.4 | `adjudicate` refuses to issue a verdict on reveal mismatch and escalates, naming offenders. Verdicts record jury evidence; `verify_verdict` re-derives the draw and flags self-issued verdicts as unbacked. | self-issued verdict must report `backed: False` |
| 1.5 | `verify` reports `attested` and emits a warning when no runtime is registered; `strict=True` makes it an error. Absence is never silent. | restoring the silent skip |
| 1.6 | Severity ladder actually applied: stake slashed per S0–S3, registry moved to probation/suspended, challenger bond forfeited to the accused on FRIVOLOUS, and `gate_check()` refuses a suspended agent. | making stake/registry writes no-ops |
| 1.7 | Challenges pin the checkpoint height at filing; the jury seed is the root of the *next* checkpoint, which does not exist yet and so cannot be ground. `jury_anchor` returns None until then and adjudication refuses rather than falling back. | anchor must be absent at filing time |
| 1.8 | `cmd_jury` checks `commits_match` and refuses to adjudicate a payload that does not match its on-ledger commitment. | substituted payload must be detectable |
| 1.9 | `erase` refuses while a challenge covering the entry is open, and always appends a ledger entry recording the erasure. | removing the guard |
| 1.10 | Odd nodes are promoted, not duplicated, so leaf count is unambiguous from the root. | asserting the CVE-2012-2459 collision is gone |

Residual, deliberately not fixed: the anchor removes *grinding* but a challenger who can
wait can still choose *when* to file relative to checkpointing. Narrowing that needs a
commit-then-reveal challenge flow, which is M5 work, not a patch.

---

## Tier 2–4 fixes as applied (2026-09-12)

| # | Fix | Effect on the reported numbers |
|---|---|---|
| 2.1 | Scoring is oracle-free. The harness reports the machine's three-state output (contained / leaked / auto-precision / human load) and sweeps end-to-end F1 over an explicit human-accuracy parameter. | **F1 0.997 withdrawn.** Lone-detector rule reframed as containment: leaked violations 46.3% → 25.0%, human load 39.0% → 53.3%. End-to-end 0.853 at the unreachable h=1.00, 0.805 at h=0.90. |
| 2.2 | Added a `viol_novel` tier whose wording appears nowhere in the detectors' word lists; a test asserts that invariant so it cannot silently regress. `e2.py` now imports `corpus.py` instead of keeping a divergent copy. | **All five families detect 0 of it.** Best single detector 0.857 → 0.723. The jury is no longer presented as evidence about detection quality. |
| 2.3 | `split_templates(fold=n)` rotates template order deterministically; E7 reports the spread across 8 splits. | 0.667 single draw → **0.250–0.625 range**, median 0.500. Direction of the rung-0 finding holds; magnitude does not. |
| 2.4 | Ceiling computed from patterns that reach the funnel, using a `template` field now carried on every item. | 13 of 27 patterns reach a jury; ceiling 15.4× and the mechanism **meets it exactly**, rather than "falling short of 15.7×". |
| 2.5 | Landmarks are searched over all held-out actions instead of quoted from a hand-picked pair. | Nearest opposite-label pair 0.507 (hand-picked) → **0.423** (searched); closest same-bucket 0.993. |
| 2.6 | E9 separates the definitional zero from the empirical evidence and labels it as a design property, not a result. | Conjecture still refuted, now on the evidence that could have come out otherwise. |
| 2.7 | `MIN_EVIDENCE` gates severity on W-class: S1+ requires ≥W2, S3 requires ≥W3; insufficient evidence escalates instead of convicting. | W0–W4 are now enforced rather than described. |
| 3.2 | Tests pin 6/11, 7/11 and 8/11 splits. | The threshold can no longer be relaxed to a simple majority undetected. |
| 3.3 | Test tampers an entry appended *after* the last checkpoint. | Pins the per-entry hash check specifically, not via checkpoint redundancy. |
| 3.4 | Test samples from a pool where one operator registers 7 jurors. | The per-operator cap is actually exercised. |
| 3.5 | Investigated: the char-n-gram features are retained, and the screener is now reported with its cross-split range, which is the honest frame for the feature question. | — |
| 3.6 | RED count enumerated rather than asserted. | 22, verified by grep. |
| 4.1 | Entry size re-measured everywhere. | 381 B / 405 B / 406 B → **406 B** in paper, README and code output. |
| 4.2 | `Store(wal=…, key_cache=…)` makes each optimization independently toggleable; `pactctl bench` reports the isolated ladder. | Naive baseline is now reproducible by a shipped command: 567 µs → 122 µs, **WAL 2.2× / key-cache 1.7× / batching 1.2×, 4.6× end to end**. (My first attempt at this isolation was fake — it set an attribute `Store` never reads, so two rows measured the same configuration.) |
| 4.3 | Paper's milestone list renumbered to match what the repository actually builds. | M0–M4 built; M5 is the multi-host testnet that would turn E8's in-process numbers into deployment evidence. |
