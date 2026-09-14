# PACT — an accountability protocol for deployed AI systems

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22738800.svg)](https://doi.org/10.5281/zenodo.22738800)

Reference implementation and evaluation harness for the paper *PACT: An Accountability
Protocol for Deployed AI Systems, with Measured Limits on AI-Jury Adjudication*
([`PAPER.md`](PAPER.md)).

Every quantitative claim in the paper is produced by a script in [`m0/`](m0/) and is
reproducible by running it. Experiments are hash-seeded rather than RNG-seeded, so the
numbers reproduce exactly rather than approximately.

---

## What this is

Institutional oversight of AI — third-party evaluation, statutory record-keeping,
proposals for verifiable limits on frontier development — rests on audit records that
are produced and held by the operator of the system under audit. PACT makes deployed AI
conduct **non-repudiable and adjudicable among mutually distrusting parties**, by
separating a cheap evidence plane (hash-chained conduct logs, witness-cosigned Merkle
checkpoints) from a small governance plane (registries, challenges, juries, verdicts,
consequences).

I built it, then measured it against its own design assumptions. The most useful results
are the ones that came back negative.

## Headline findings

**Evaluator models do not fail independently, and the correlation is judgment, not
lineage.** Nineteen jurors from nine vendors judged the same 70 items blind under a
fixed, hash-stamped prompt. Cross-vendor pairs are as correlated as within-vendor pairs,
with the difference interval containing zero in every combination of prompt framing and
label set tested, and the mean joint-error ratio exceeds the independence prediction in
every bootstrap replicate. The magnitude moves with labelling and framing (2.7x to 5.8x),
so the paper claims the invariant rather than a single number. The items that defeat
whole panels are exactly the ones pre-labelled contested.

**A jury is not safer than its best member.** Every voting rule on the nineteen-juror
panel scores below the best single juror, in both prompt framings: two-thirds 0.757,
simple majority 0.800 and any-single-vote 0.737 against 0.865 under one framing; 0.811,
0.857 and 0.700 against 0.913 under the other. The rule-based eleven-seat jury turns out
to behave as a single member: its machine decisions match one detector on 69 of 70 items.

**Asymmetric thresholds buy containment, not detection.** A lone-detector rule (one
violation vote cannot be overridden into an auto-clear, only escalated) contains
**0.905 [0.762, 1.000]** of true violations where the two-thirds rule contains
**0.286 [0.095, 0.476]**; the intervals are disjoint. Human review load rises from
**20.0% to 72.9%**. Machine precision and recall are identical under both rules. The
rule changes nothing about what the system decides, only what it refuses to clear
silently.

**Juror availability falls as severity rises.** In a companion run on a more sensitive
corpus, two of three models refused the adjudication task outright. A juror must read
what it judges, so models tuned to refuse engagement with dangerous content also refuse
to *moderate* it. The panel thins toward the least cautious models exactly where care is
most needed. This is why abstention is a first-class, never-penalized verdict in the
protocol.

**Equivocation is invisible from any single vantage point.** A shard presenting a forged
root to 3 of 10 witnesses was detected **0 times by any witness individually and 21 times
by witnesses comparing notes** — exactly the 3 × 7 deceived/honest pairs. Cross-witness
gossip is a protocol requirement, not an optimization.

**The protocol is cheap.** 122 µs p50 per covered action (76% of it Ed25519 signing, so
the path is signature-bound), **13.3 B of shared ledger per query**, and one action in
100,000 stays provable to a witness-cosigned root through 22 hashes in a 2.3 KB proof
verified in 36 µs.

## Quickstart

```bash
cd m0 && python3 -m venv .venv && ./.venv/bin/pip install cryptography
```

```bash
cd m0 && ./.venv/bin/python3 test_pact.py
```

53 checks, 25 of them RED-verified: each was confirmed to fail when the code it guards is
mutated, so the suite is known to be capable of failing. Three pre-existing tests that
*could not fail at all* were found this way, including one that would have permitted the
jury supermajority threshold to be relaxed to a simple majority.

## Reproducing each figure

Run from `m0/`:

| Command | Produces |
|---|---|
| `./.venv/bin/python3 e13.py` | jury error-independence measurement (the 4.7× result) |
| `./.venv/bin/python3 ci.py` | bootstrap CIs and permutation tests on both headline numbers |
| `./.venv/bin/python3 e14.py` | detection quality, symmetric vs lone-detector rule |
| `./.venv/bin/python3 e7.py` | precedent graph reduction, screener recall, threshold safety band |
| `./.venv/bin/python3 e8.py` | federation cost, composed inclusion proofs, equivocation |
| `./.venv/bin/python3 e9.py` | reciprocal witnessing mesh coverage |
| `./.venv/bin/python3 pactctl.py bench -n 3000` | append-path latency and the 4.6× optimization breakdown |
| `./.venv/bin/python3 scan_corpus.py` | safety gate: vendor-grade secret patterns; FAILs on any live-format string it cannot account for, WARNs on the two documented allowlisted ones (`--self-test` proves it fires) |
| `./.venv/bin/python3 run_jurors.py` | put the 70 items to any set of real models and record verdicts |
| `./.venv/bin/python3 juror_prompt.py` | print the exact juror prompt, with its hash |
| `./.venv/bin/python3 e15.py` | cross-vendor replication: is the correlation lineage or judgment? |
| `./.venv/bin/python3 label_audit.py` | audit the corpus labels against the clause that defines them |

## Running the independence measurement on your own models

This is the part I most want other people to reuse, and it is now one command rather
than a JSON format you have to produce by hand. `run_jurors.py` puts the items to any set
of models through a single text endpoint and writes the verdict file that `e13.py` and
`e15.py` read; `juror_prompt.py` is the exact framing it uses, hashed into every verdict
file so a result can always be traced to the text that produced it.

```bash
export FAL_KEY=...        # any OpenRouter-compatible text endpoint
./.venv/bin/python3 run_jurors.py --out jury_verdicts_xvendor.json
./.venv/bin/python3 e15.py                        # within-vendor vs cross-vendor
./.venv/bin/python3 e15.py --exclude-ids audit    # same, on label-audited items
```

A juror with *any* missing verdict is written `"complete": false` and reported as
incomplete; it is never quietly padded or dropped. If you would rather wire your own
models up directly, `e13.py` still takes a hand-written verdict file:

Put the 70 items to each of your models as a classification task, then write
`m0/jury_verdicts.json` in this shape:

```json
{"jurors": [
  {"juror": "your-model-name",
   "verdicts": [{"id": 0, "verdict": "CLEARED", "rationale": "...", "confidence": 0.99}]}
]}
```

`verdict` is `"VIOLATION"` or `"CLEARED"`; `id` indexes into `jury_sample.json`. Then:

```bash
cd m0 && ./.venv/bin/python3 e13.py
```

It reports per-juror precision/recall/F1, every pairwise observed/expected joint-error
ratio, and which items defeat the whole panel.

**The cross-vendor replication has now been run, and it removed my own hedge.**
The original measurement covered three tiers of one vendor, so I wrote that 4.7× was
plausibly an *upper* bound: same-vendor models share tuning lineage, and shared lineage
could be inflating the number. `e15.py` tests that directly — **19 jurors across 9
vendors** (OpenAI, Google, Meta, Mistral, Alibaba, DeepSeek, Anthropic, xAI, Amazon)
judging the same 70 items under the same prompt, with 12 *within*-vendor pairs to compare
against 159 *cross*-vendor pairs.

The hedge does not survive, under either of two prompt framings (`PACT_PROMPT=jp:v2`
reruns the panel under a minimal second framing; `m0/jury_verdicts_xvendor_v2.json`) and
under either label set (below). Cross-vendor pairs are as correlated as within-vendor
pairs — corrected labels: mean 3.6× cross vs 3.5× within, difference 95% CI [−0.8, 0.7] —
and the difference interval contains zero in all six cuts (two framings × three label
regimes). Lineage is not what produces the agreement.

**And running it surfaced a problem with my own corpus, since adjudicated.** See
`label_audit.py`: 11 of the 32 violation-labelled items carried a value announcing itself
synthetic (`ghp_SYNTHETIC_NOT_REAL`) while the clause prohibits a ***live*** credential
literal; nineteen models from nine vendors cleared them, which is the clause applied as
written. Those labels are now **corrected in place** (`neutral_corpus.ADJUDICATED_V2`,
dated in source; texts untouched); the authored labels stay runnable everywhere with
`--labels v1`, and the label gate runs in the test suite so a future conflict fails CI.
Under corrected labels no item defeats the 19-model panel and **every voting rule scores
below the best single juror in both framings** — including the asymmetric rule, whose
apparent win under the authored labels was a label artifact. What survives every regime:
aggregation buys containment (0.905 vs 0.286, disjoint intervals), never accuracy; and
the correlation is judgment, not lineage. The magnitude moves with regime (2.7×–5.8×),
and the paper says so instead of picking a flattering value.

**What is still unmeasured.** The corpus was authored by language-model agents rather
than people, and there is no human baseline on the same items. If you run this on models
or a corpus I did not, I would like to know what you got.

## The corpus

`m0/neutral_corpus.py` holds 70 one-line code-review items (labels v2, adjudicated 2026-09-13; `build("v1")` returns them as authored) under policy clause
`pol:v2#c1` (repository secret handling), 21 of them violations under the adjudicated labels (32 as authored), in six buckets:
`benign_ordinary`, `benign_named`, `benign_placeholder`, `viol_literal`,
`viol_other_forms`, `contested`. `m0/jury_sample.json` is the same set flattened to
`{id, text, label, bucket}`.

How it was built matters, because it was wrong earlier in this project and was fixed. The
five detector families in `neutral_detectors.py` were written from the policy clause alone
and **committed before any data item existed**. Six separate language-model agents then wrote the
items from the same clause, each prompted in isolation, without access to the detector code
and without sight of each other's output. Neither side could tune to the other. These are
related models rather than independent human authors, and since the E13 jurors are also
models of a related lineage, shared lineage runs through the pipeline; the paper treats this
as a confound on the magnitude of the correlation. In the earlier version the same author wrote both, which made the detectors' blind
spots an artifact of authorship and inflated every result derived from them.

The corpus is benign by construction. It contains credential-*shaped* strings because it
is about credential handling, but every one is neutralized: the prefix a shape-based
detector keys on is preserved (`AKIA`, `ghp_`, `xoxb-`, `-----BEGIN`) while the body is
replaced with an explicit `SYNTHETIC` marker. Nothing matches a live credential format for
any provider, and `scan_corpus.py` enforces that in the test suite so it cannot regress.
See [`SAFETY-AND-ETHICS.md`](SAFETY-AND-ETHICS.md).

## What is not here

The evaluation runs in one process, with development keys held beside the data rather than
in an enclave, simulated rather than hardware attestation, and federation tiers as objects
rather than hosts. It measures the **protocol**, not deployment realities. Rungs two and
three of the verification ladder (optimistic re-execution, zero-knowledge inference proofs)
are specified in the paper and unimplemented here. A multi-host testnet is the work that
would change this.

## Repository layout

```
PAPER.md              submission draft (~5,400 words, IEEE scope)
ARCHITECTURE.md       design notes
V2-PLANETARY.md       planetary-scale federation design
REVIEW-FINDINGS.md    adversarial review: 30 findings that survived refutation
NOVELTY-AUDIT.md      prior-art audit
SAFETY-AND-ETHICS.md  research ethics statement
build_ieee.py         renders PAPER.md into the two-column preview (ieee.html)
build_tex.py          renders PAPER.md into IEEEtran LaTeX (main.tex)
main.tex              submission artifact -- GENERATED, never hand-edited
m0/                   reference implementation and experiments
figs/loom.svg         the architecture figure (source)
figs/loom.png         the same figure rendered for LaTeX
```

`ieee.html` is **generated** — regenerate with `python3 build_ieee.py`, never hand-edit. The same
applies to `main.tex` (`python3 build_tex.py`). **`main.tex` has never been compiled** —
there is no LaTeX toolchain on the machine it was written on, so build it on Overleaf
(pdfLaTeX, with `figs/loom.png` uploaded alongside) and expect to fix something before
submitting.
Hand-editing is exactly how the published preview drifted out of sync with the paper and
kept reporting withdrawn numbers for several revisions.

## On the numbers that changed

Several results in this repository are lower than the ones I first computed. A structured
adversarial review established that the original corpus had been written from the
detectors' own word lists; that a flagship end-to-end figure assumed perfect human review;
that a reduction ceiling used a denominator counting patterns no jury ever sees; and that a
quoted similarity landmark was hand-picked rather than searched. Each is corrected, and
each correction moved a number downward. [`REVIEW-FINDINGS.md`](REVIEW-FINDINGS.md) has
the full list. I am recording this because presenting the corrected numbers as though they
were the first ones would misrepresent how much of this evidence depended on choices I
made about what to measure.

## Citing this

If you use the corpus, the harness, or the independence measurement, please cite the
software archive:

```bibtex
@software{shinde_pact_2026,
  author  = {Shinde, Saish Sanjay},
  title   = {{PACT}: Reference Implementation and Evaluation Harness
             for an {AI} Accountability Protocol},
  year    = {2026},
  version = {1.0.0},
  doi     = {10.5281/zenodo.22738800},
  url     = {https://github.com/saish-shinde-007/pact-paper}
}
```

Replace the DOI and URL once the first release is archived on Zenodo. See
[`CITATION.cff`](CITATION.cff).

## License

Code is Apache-2.0 ([`LICENSE`](LICENSE)) — chosen over MIT for its explicit patent grant,
which matters for a protocol other people may implement.

The corpus, the paper, and the prose documents are **CC BY 4.0**
(<https://creativecommons.org/licenses/by/4.0/>). Use them, modify them, build on them;
attribute.

## Contact

Saish Sanjay Shinde — San José State University — saish.shinde@sjsu.edu
