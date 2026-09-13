"""PACT M4 — the reciprocal witnessing mesh (WEFT §V-B).

Agent-to-agent sessions close with co-signed conduct digests: each endpoint signs
its commitment to the transcript, the peer's identity, and the policy context, and
files the result in its own log. Two cross-linked records per interaction.

Why it matters: an uninstrumented agent that transacts with an instrumented one
still leaves an attributable record of that interaction, and declining to co-sign
is itself a recorded, visible event rather than silence.

Evidence classes follow the paper's W-ladder: a mutually signed digest is W2, a
unilateral record (peer absent or refusing) is W0.
"""
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pactlog import H, canon


def digest(session: str, peers: list[str], transcript_commit: str, policy: str) -> bytes:
    """The signed statement. Built only from fields carried IN the record, so a
    verifier never needs — and never trusts — a transcript supplied alongside it."""
    return canon({"session": session, "peers": sorted(peers),
                  "transcript_commit": transcript_commit, "policy": policy})


class MeshAgent:
    def __init__(self, aid: str, instrumented: bool = True, cosigns: bool = True):
        self.aid = aid
        self.instrumented = instrumented          # keeps a conduct log at all
        self.cosigns = cosigns                    # willing to co-sign a digest
        self.key = Ed25519PrivateKey.generate()
        self.log: list[dict] = []

    @property
    def pub(self):
        return self.key.public_key()

    def offer(self, session: str, peer: str, transcript_commit: str, policy: str):
        """Countersign a peer's session digest, or decline."""
        if not self.cosigns:
            return None
        d = digest(session, [self.aid, peer], transcript_commit, policy)
        return {"by": self.aid, "sig": self.key.sign(d).hex()}


def session(a: MeshAgent, b: MeshAgent, transcript: bytes,
            policy: str = "pol:v1#c1") -> dict:
    """Run one interaction to close. The returned record CARRIES the signatures
    produced during the session; nothing is re-signed at verification time."""
    sid = H(a.aid.encode() + b.aid.encode() + transcript).hex()[:16]
    commit = H(transcript).hex()
    sigs, refusals = {}, []
    for me, peer in ((a, b), (b, a)):
        if not me.instrumented:
            continue
        for who in (me, peer):
            other = peer.aid if who is me else me.aid
            s = who.offer(sid, other, commit, policy)
            if s is None:
                if who is peer:
                    refusals.append(peer.aid)
            else:
                sigs[s["by"]] = s["sig"]
        me.log.append({"session": sid, "peer": peer.aid,
                       "cosigned": peer.aid in sigs,
                       "transcript_commit": commit,
                       "sigs": dict(sigs)})
    if len(sigs) >= 2:
        cls = "W2"      # mutually signed
    elif sigs:
        cls = "W0"      # unilateral record only
    else:
        cls = "none"    # neither side instrumented: nothing exists
    return {"session": sid, "peers": sorted([a.aid, b.aid]), "policy": policy,
            "transcript_commit": commit, "sigs": sigs, "class": cls,
            "signers": sorted(sigs), "refusals": sorted(set(refusals)),
            "observed": cls != "none"}


def verify_record(rec: dict, pubkeys: dict) -> bool:
    """Check the signatures the record actually carries against public keys.

    A W2 record must carry a valid signature from BOTH named peers over the
    exact statement in the record. Verification is offline and adversarial: it
    never asks an agent to sign anything now, so a fabricated record — or a
    record re-presented against a different transcript — cannot pass just
    because the named agents are still cooperative."""
    if rec.get("class") != "W2":
        return False
    peers = rec.get("peers") or []
    sigs = rec.get("sigs") or {}
    if len(peers) != 2 or not all(p in sigs for p in peers):
        return False
    d = digest(rec["session"], peers, rec["transcript_commit"], rec["policy"])
    for aid in peers:
        pub = pubkeys.get(aid)
        if pub is None:
            return False
        try:
            pub.verify(bytes.fromhex(sigs[aid]), d)
        except Exception:
            return False
    return True
