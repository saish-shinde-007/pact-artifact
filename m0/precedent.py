"""PACT M2 — the precedent graph.

Adjudicated cases become citable ledger objects. A new challenge is matched
against them; a close enough match on the SAME policy clause yields an
auto-verdict citing its precedent chain, with no jury convened. Conflicting
precedents above threshold force escalation instead of a coin-flip, and any
node can be superseded by a full-jury or human ruling so early errors do not
fossilize (paper §VII-B).

Similarity here is cosine over hashed character n-grams — a lightweight stand-in
for the learned embedding a deployment would use. It is deliberately crude: the
risk it exposes (surface-similar but oppositely-labeled text matching) is the
real failure mode of precedent matching, and E7 measures it rather than hiding it.
"""
import math
from collections import defaultdict

from pactlog import H

DIM = 4096


def vec(text: str, n: int = 4) -> dict:
    """L2-normalized hashed character n-gram counts."""
    t = "".join(c if c.isalnum() else " " for c in text.lower())
    counts = defaultdict(float)
    for i in range(max(0, len(t) - n + 1)):
        idx = int.from_bytes(H(t[i:i + n].encode())[:4], "big") % DIM
        counts[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
    return {k: v / norm for k, v in counts.items()}


def cosine(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class PrecedentGraph:
    def __init__(self):
        self.nodes = []  # {id, clause, verdict, rationale, vec, source, superseded_by}

    def add(self, text: str, clause: str, verdict: str, rationale: str,
            source: str = "jury") -> int:
        nid = len(self.nodes)
        self.nodes.append({"id": nid, "clause": clause, "verdict": verdict,
                           "rationale": rationale, "vec": vec(text),
                           "source": source, "superseded_by": None})
        return nid

    def supersede(self, node_id: int, text: str, verdict: str, rationale: str,
                  by: str = "human") -> int:
        """A higher authority overrules a precedent; the old node stays on the
        ledger marked superseded, so the correction is itself auditable."""
        new_id = self.add(text, self.nodes[node_id]["clause"], verdict, rationale, by)
        self.nodes[node_id]["superseded_by"] = new_id
        return new_id

    def active(self, clause: str):
        return [n for n in self.nodes
                if n["superseded_by"] is None and n["clause"] == clause]

    def match(self, text: str, clause: str, tau: float):
        """Returns (status, node, similarity). status is 'hit', 'conflict', or 'miss'.
        Conflict = two active precedents above tau that disagree -> escalate."""
        q = vec(text)
        hits = []
        for n in self.active(clause):
            s = cosine(q, n["vec"])
            if s >= tau:
                hits.append((s, n))
        if not hits:
            return "miss", None, 0.0
        hits.sort(key=lambda h: -h[0])
        verdicts = {n["verdict"] for _, n in hits}
        if len(verdicts) > 1:
            return "conflict", hits[0][1], hits[0][0]
        return "hit", hits[0][1], hits[0][0]

    def chain(self, node_id: int) -> list:
        """Citation chain for a verdict: the node plus anything it superseded."""
        out, seen = [], set()
        for n in self.nodes:
            if n["superseded_by"] == node_id and n["id"] not in seen:
                out.append(n["id"]); seen.add(n["id"])
        return [node_id] + out
