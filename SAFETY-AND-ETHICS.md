# Research safety and ethics statement

This repository contains a reference implementation and evaluation harness for an
**AI accountability protocol** — machinery for logging, challenging, and adjudicating
the conduct of deployed AI systems. It is defensive safety research.

## The evaluation domain

Every experiment in this repository runs on a single, entirely benign domain:
**repository secret handling** (policy clause `pol:v2#c1`). Items are one-line
fragments of ordinary engineering content — a credential assigned in source, a
credential read from an environment variable, a test fixture, a Kubernetes manifest,
a commit message. The classifier's job is to tell a real credential exposure from a
placeholder, a variable merely *named* like a secret, or a documented example.

There is no weapons content, no exploit content, and no attack content anywhere in
this project.

### On credential-shaped strings

A corpus about credential handling necessarily contains strings that look like
credentials. None of them are. Every such string was passed through
`m0/scan_corpus.py` and **neutralized**: the prefix a shape-based detector keys on is
preserved (`AKIA`, `ghp_`, `xoxb-`, `-----BEGIN`) while the body is replaced with an
explicit `SYNTHETIC` marker. Nothing in this repository matches a live credential
format for any provider, and `scan_corpus.py` runs in the test suite so that cannot
regress.

## How the corpus was built

The methodology matters, because it was wrong earlier in this project and was fixed.

1. The five detector families (`m0/neutral_detectors.py`) were written from the
   policy clause alone and **committed before any data item existed**.
2. Six separate language-model agents then wrote the 70 items from that policy clause
   only. They never saw the detector code, never saw each other's output, and were
   instructed not to reverse-engineer any matching rule. They are related models rather
   than independent human authors; the paper discloses this as a confound.

Neither side could tune to the other. Earlier experiments had the same person write
both the detectors and the data, which made the detectors' "blind spots" an artifact
of authorship and inflated the results.

## A corpus that was removed

An earlier version of this work evaluated the same protocol on a corpus of
weapons-related *request strings* — one-line questions, of the kind used in public
safety benchmarks, containing no procedures, quantities, precursors, or answers.

**That corpus has been deleted from this project**, along with its experiment
records. The reason is scientific as much as prudential: experiment E14 showed the
protocol findings reproduce on the neutral domain, and reproduce *more strongly*
there (the jury trails its best member by 0.321 F1, against 0.003 on the earlier
corpus). The sensitive material was carrying nothing the benign material does not
carry better, so it had no claim to remain.

## What we do not do

- **We do not attempt to elicit harmful content from models.** No experiment asks a
  model to answer a harmful request. Models are asked only to *classify*.
- **We do not engineer around safety refusals.** In experiment E13, two of three
  evaluator models declined a classification task, reporting safeguard categories
  `general_harms` and `bio`. We recorded the refusals as a finding and stopped,
  rather than rephrasing to get past the safeguards. That refusal became a
  substantive result — juror availability is anti-correlated with case severity —
  which changed the protocol: abstention is now a first-class verdict that is never
  penalized.
- **We do not publish capability.** No output of this research increases anyone's
  ability to cause harm.

## Human subjects

None. No human subjects, no personal data, no user data.

## Dual-use assessment

Not dual-use research of concern. DURC frameworks address research that could
*generate* dangerous capability. A classification benchmark for credential handling
generates none. The protocol is oversight infrastructure, whose failure mode is that
bad conduct goes unrecorded — not that new harm becomes possible.

## Handling

- The repository is published deliberately, under Apache-2.0 (code) and CC BY 4.0
  (corpus and prose), so that the results can be replicated and challenged. Everything
  in it passed `m0/scan_corpus.py` before release, and that gate runs in the test suite
  so the property cannot regress.
- Ship this file at the repository root, and carry an ethics statement in the paper
  (required by FAccT and AIES, increasingly expected elsewhere).
