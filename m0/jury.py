"""PACT M1 — jury protocol. DOMAIN-AGNOSTIC.

VRF-style diversity-constrained sampling, commit-reveal voting, supermajority
tally with human escalation, abstention handling, and recursion (each juror
verdict is itself logged as a covered action).

This module holds NO domain vocabulary. Detection is injected: a detector is any
callable (family, text) -> bool, and the juror pool's families come from whatever
detector module is in use. The default domain is repository secret handling
(neutral_detectors.py).

That separation is deliberate. The findings this protocol produces — that a 2/3
majority can score below its own best member, that the per-operator cap rather
than the vote threshold is what bounds collusion, that the lone-detector rule
buys containment rather than detection — are properties of the VOTING RULE and
reproduce across domains (E14). Keeping the rule free of any domain's words is
what makes that testable rather than asserted.
"""
import math
import os
import secrets

import neutral_detectors as _default_domain
from pactlog import H, canon

# families come from the active detector domain, not from this module
FAMILIES = _default_domain.FAMILIES
POOL = [
    {"id": f"did:pact:org{ i }/juror", "operator": f"org{i}",
     "family": FAMILIES[i % len(FAMILIES)]}
    for i in range(15)
]


def sample_jury(seed: bytes, pool=POOL, k: int = 11, min_families: int = 3):
    """Deterministic constrained draw: <=1 juror/operator, >=min_families.
    Phase 1 seeds distinct families; phase 2 fills by VRF priority."""
    order = sorted(pool, key=lambda j: H(seed + j["id"].encode()).hex())
    picked, ops, fams = [], set(), set()
    for j in order:  # phase 1: guarantee family diversity
        if len(fams) >= min_families:
            break
        if j["family"] in fams or j["operator"] in ops:
            continue
        picked.append(j); ops.add(j["operator"]); fams.add(j["family"])
    for j in order:  # phase 2: fill remaining seats by priority
        if len(picked) >= k:
            break
        if j in picked or j["operator"] in ops:
            continue
        picked.append(j); ops.add(j["operator"]); fams.add(j["family"])
    diag = {
        "k": len(picked),
        "families": len({p["family"] for p in picked}),
        "operators": len({p["operator"] for p in picked}),
        "constraints_ok": len(picked) == min(k, len(pool))
        and len({p["family"] for p in picked}) >= min_families
        and len({p["operator"] for p in picked}) == len(picked),
    }
    return picked, diag


def juror_vote(juror: dict, text: str, detector=None) -> dict:
    """VIOLATION/CLEARED from the injected domain detector, plus a deterministic
    per-juror flip so that same-family jurors differ slightly — real models of a
    kind are correlated but not identical.

    `detector` is any callable (family, text) -> bool. It defaults to the active
    domain so callers need not pass one; passing a different one is how the same
    protocol gets evaluated on a different domain."""
    call = detector or _default_domain.family_call
    base = call(juror["family"], text)
    # deterministic ~8% idiosyncratic flip, seeded by juror+text
    noise = int.from_bytes(H(juror["id"].encode() + text.encode()), "big") % 100
    if noise < 8:
        base = not base
    return {"juror": juror["id"],
            "verdict": "VIOLATION" if base else "CLEARED",
            "rationale": f"{juror['family']} family assessment"}


def commit_phase(votes: list[dict], round_seed: bytes = b""):
    """Publish H(verdict || H(rationale) || nonce), where the nonce is 128 bits
    of juror-held randomness.

    The nonce MUST be secret and unpredictable. An earlier version derived it as
    H(juror_id || round_seed) from public inputs; because the verdict space is
    two values and the rationale is a short deterministic string, anyone could
    precompute both candidate commitments per juror and read every vote before
    the reveal — the hiding property was absent while the ceremony looked
    correct. `round_seed` is retained only to domain-separate rounds."""
    commits, nonces = [], []
    for v in votes:
        nonce = secrets.token_bytes(16) + H(round_seed)[:4]
        commits.append(H(v["verdict"].encode() + H(v["rationale"].encode()) + nonce).hex())
        nonces.append(nonce)
    return commits, nonces


def reveal_phase(commits, nonces, revealed: list[dict]):
    """Verify each revealed vote against its commitment. Returns (ok, offenders)
    — a juror who commits one verdict and reveals another is named here."""
    # Every reveal is checked, ABSTAIN included. An honest abstainer commits
    # ABSTAIN and verifies normally; a juror that commits a verdict and then
    # abstains at reveal has equivocated and is named. Exempting abstentions
    # from the check would hand jurors a costless way to withdraw a vote they
    # had already bound themselves to.
    bad = [v["juror"] for c, nonce, v in zip(commits, nonces, revealed)
           if H(v["verdict"].encode() + H(v["rationale"].encode()) + nonce).hex() != c]
    return not bad, bad


def commit_reveal(votes: list[dict], round_seed: bytes = b"round"):
    """Convenience wrapper: honest commit followed by honest reveal."""
    commits, nonces = commit_phase(votes, round_seed)
    ok, _ = reveal_phase(commits, nonces, votes)
    return commits, ok


W_ORDER = ["W0", "W1", "W2", "W3", "W4"]
# §V-D: severity gates on evidentiary weight. A serious consequence may not rest
# on hearsay — S1 and above need at least a co-signed record, S3 an attested one.
MIN_EVIDENCE = {"S0": "W0", "S1": "W2", "S2": "W2", "S3": "W3"}


def evidence_sufficient(severity: str, wclass: str) -> bool:
    need = MIN_EVIDENCE.get(severity, "W2")
    try:
        return W_ORDER.index(wclass) >= W_ORDER.index(need)
    except ValueError:
        return False


def tally(votes: list[dict], severity: str = "S1", asymmetric: bool = False,
          evidence_class: str = "W3", min_quorum: int = 7, min_families: int = 3,
          families: list | None = None):
    """2/3 supermajority decides; otherwise, or if severity>=S2, escalate.

    asymmetric=True adds the lone-detector rule: for catastrophic clauses a
    single VIOLATION vote blocks auto-clearing and escalates to humans instead.
    Symmetric majority voting otherwise silently suppresses a lone correct
    detector — measured in E2, and the reason this option exists."""
    # ABSTAIN is a verdict, not a missing vote (E13). A juror that declines to
    # engage — as safety-tuned evaluator models do on exactly the severe content
    # that most needs judging — must neither be counted toward either side nor
    # punished as a process fault. If abstentions thin the panel below quorum or
    # below its family floor, the case escalates rather than proceeding on
    # whichever jurors happened to be least cautious.
    seated = len(votes)
    votes = [v for v in votes if v["verdict"] in ("VIOLATION", "CLEARED")]
    k = len(votes)
    if k < min_quorum:
        return "ESCALATE", None
    if families is not None:
        live = {f for f, v in zip(families, votes)}
        if len(live) < min_families:
            return "ESCALATE", None
    viol = sum(1 for v in votes if v["verdict"] == "VIOLATION")
    need = math.ceil(2 / 3 * k)
    if severity in ("S2", "S3"):
        return "ESCALATE", viol
    if viol >= need:
        # a conviction may not be issued on evidence too weak for its severity
        if not evidence_sufficient(severity, evidence_class):
            return "ESCALATE", viol
        return "VIOLATION", viol
    if asymmetric and viol > 0:
        return "ESCALATE", viol
    if (k - viol) >= need:
        return "CLEARED", viol
    return "ESCALATE", viol


def adjudicate(store, challenge_id: int, agent: str, entry_text: str,
               clause: str = "pol:v1#c1", severity: str = "S1",
               colluders: set | None = None, log_recursion: bool = True,
               asymmetric: bool = False, anchor: bytes | None = None,
               evidence_class: str = "W3") -> dict:
    """Full path: sample -> commit-reveal -> tally -> (recursion) -> consequence.

    `anchor` is the unpredictable value the jury draw is seeded from — in a
    deployment a finalized block hash, here the root of a witnessed checkpoint
    sealed AFTER the challenge was filed (Store.jury_anchor). Without it the
    seed is a function of attacker-known inputs and a challenger can grind
    challenge ids until a favourable jury is drawn.

    colluders: juror ids that vote CLEARED regardless of truth (for E5)."""
    seed = H((anchor or b"") + f"challenge:{challenge_id}:{agent}:{entry_text}".encode())
    jury, diag = sample_jury(seed)
    colluders = colluders or set()
    votes = []
    for j in jury:
        v = juror_vote(j, entry_text)
        if j["id"] in colluders:
            v = {"juror": j["id"], "verdict": "CLEARED", "rationale": "colluding"}
        votes.append(v)
    commits, nonces = commit_phase(votes, seed)
    cr_ok, offenders = reveal_phase(commits, nonces, votes)
    if not cr_ok:
        # a juror whose reveal contradicts its commitment is a process fault:
        # no verdict is issued, the case escalates, and the offenders are named.
        return {"decision": "ESCALATE", "violation_votes": None, "k": len(jury),
                "commit_reveal_ok": False, "offenders": offenders, "diversity": diag,
                "seated_colluders": sum(1 for j in jury if j["id"] in colluders)}
    decision, viol = tally(votes, severity, asymmetric, evidence_class)

    seated_colluders = sum(1 for j in jury if j["id"] in colluders)
    if log_recursion and store is not None:
        # recursion: each juror verdict is itself a covered action
        for j, v in zip(jury, votes):
            store.keygen(j["id"])
            store.append(j["id"], f"vote:challenge{challenge_id}:{agent}", v["verdict"],
                         policy=clause)
    if store is not None and decision in ("VIOLATION", "CLEARED"):
        store.verdict(challenge_id, decision, f"jury {viol}/{len(jury)} violation votes",
                      severity=severity,
                      evidence={"jurors": [j["id"] for j in jury], "votes": viol,
                                "k": len(jury), "anchor": (anchor or b"").hex(),
                                "commits": commits})
    return {
        "decision": decision, "violation_votes": viol, "k": len(jury),
        "commit_reveal_ok": cr_ok, "offenders": [], "diversity": diag,
        "seated_colluders": seated_colluders,
    }
