"""PACT M3 — the federation tiers.

agent log -> operator root -> shard root -> witness-cosigned planetary root.

Two claims live here and both are testable rather than asserted:

1. Aggregation batches BANDWIDTH, never TRUST. Every individual action stays
   provable by a composed O(log n) inclusion path up all four tiers. Each hop's
   root must reappear, bound to its owner's identity, as the next hop's leaf —
   otherwise proofs could be spliced between tiers.
2. Equivocation dies at the root. A shard showing different histories to
   different audiences is caught the moment any two honest witnesses compare
   cosigned checkpoints, and the two signatures are the proof.

The planetary root is deliberately NOT a blockchain: it is a thin transparency
log of shard roots with witness cosignatures (paper §VI).
"""
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pactlog import H, canon, merkle_proof, merkle_root, verify_inclusion


def leaf_for(kind: str, owner: str, root: bytes, epoch: int | None = None) -> bytes:
    """Bind a subtree root to its owner so proofs cannot be spliced across tiers."""
    d = {"kind": kind, "owner": owner, "root": root.hex()}
    if epoch is not None:
        d["epoch"] = epoch
    return canon(d)


class Tier:
    """One aggregation level: an ordered set of (owner -> subtree root) entries."""

    def __init__(self, kind: str):
        self.kind = kind
        self.owners: list[str] = []
        self.roots: dict[str, bytes] = {}

    def set(self, owner: str, root: bytes):
        if owner not in self.roots:
            self.owners.append(owner)
        self.roots[owner] = root

    def leaves(self, epoch: int | None = None) -> list[bytes]:
        return [leaf_for(self.kind, o, self.roots[o], epoch) for o in self.owners]

    def root(self, epoch: int | None = None) -> bytes:
        return merkle_root(self.leaves(epoch))

    def proof(self, owner: str, epoch: int | None = None):
        leaves = self.leaves(epoch)
        idx = self.owners.index(owner)
        return idx, merkle_proof(leaves, idx), len(leaves)


class Witness:
    """Independent cosigner. Remembers the last checkpoint it signed per shard and
    refuses to endorse a history that contradicts it."""

    def __init__(self, name: str):
        self.name = name
        self.key = Ed25519PrivateKey.generate()
        self.seen: dict[str, tuple[int, str]] = {}  # shard -> (epoch, root hex)
        self.online = True

    def cosign(self, shard: str, epoch: int, root: bytes):
        if not self.online:
            return None
        prev = self.seen.get(shard)
        if prev and prev[0] == epoch and prev[1] != root.hex():
            return {"error": "EQUIVOCATION", "shard": shard, "epoch": epoch,
                    "witness": self.name, "seen": prev[1], "now": root.hex()}
        self.seen[shard] = (epoch, root.hex())
        stmt = canon({"shard": shard, "epoch": epoch, "root": root.hex()})
        return {"witness": self.name, "shard": shard, "epoch": epoch,
                "root": root.hex(), "sig": self.key.sign(stmt).hex()}


def gossip(witnesses: list[Witness]) -> list[dict]:
    """Any two honest witnesses comparing notes expose a split view. Returns the
    disagreements, each carrying both witnesses' recorded roots as evidence."""
    found = []
    for i, a in enumerate(witnesses):
        for b in witnesses[i + 1:]:
            for shard, (epoch, root) in a.seen.items():
                other = b.seen.get(shard)
                if other and other[0] == epoch and other[1] != root:
                    found.append({"shard": shard, "epoch": epoch,
                                  "witness_a": a.name, "root_a": root,
                                  "witness_b": b.name, "root_b": other[1]})
    return found


class Federation:
    def __init__(self, witnesses: int = 10, quorum: int = 6):
        self.operators: dict[str, Tier] = {}      # operator -> agents tier
        self.shards: dict[str, Tier] = {}         # shard -> operators tier
        self.shard_of: dict[str, str] = {}        # operator -> shard
        self.planet = Tier("shard")
        self.witnesses = [Witness(f"w{i}") for i in range(witnesses)]
        self.quorum = quorum
        self.epoch = 0
        self.log: list[dict] = []                 # planetary transparency log

    def register(self, shard: str, operator: str):
        self.shards.setdefault(shard, Tier("operator"))
        self.operators.setdefault(operator, Tier("agent"))
        self.shard_of[operator] = shard

    def submit(self, operator: str, agent: str, agent_root: bytes):
        """An operator folds one agent's checkpoint into its own root."""
        self.operators[operator].set(agent, agent_root)

    def seal(self, equivocate: dict | None = None) -> dict:
        """One planetary epoch: roll operators into shards, shards into the root,
        collect witness cosignatures.

        equivocate={'shard': s, 'to': [witness names], 'root': bytes} presents a
        different shard root to those witnesses — the attack of paper §VI.
        """
        self.epoch += 1
        for operator, tier in self.operators.items():
            self.shards[self.shard_of[operator]].set(operator, tier.root())
        for shard, tier in self.shards.items():
            self.planet.set(shard, tier.root())

        sigs, alarms = [], []
        for shard in self.planet.owners:
            true_root = self.planet.roots[shard]
            for w in self.witnesses:
                shown = true_root
                if equivocate and equivocate["shard"] == shard and w.name in equivocate["to"]:
                    shown = equivocate["root"]
                r = w.cosign(shard, self.epoch, shown)
                if r is None:
                    continue
                (alarms if r.get("error") else sigs).append(r)

        root = self.planet.root(self.epoch)
        live = sum(1 for w in self.witnesses if w.online)
        entry = {"epoch": self.epoch, "root": root.hex(), "cosignatures": len(sigs),
                 "witnesses_live": live, "quorum_met": live >= self.quorum,
                 "alarms": alarms}
        self.log.append(entry)
        return entry

    # ---- composed inclusion proof: entry -> agent -> operator -> shard -> root
    def prove(self, operator: str, agent: str, agent_leaves: list[bytes], seq: int) -> dict:
        shard = self.shard_of[operator]
        a_root = merkle_root(agent_leaves)
        op_idx, op_path, op_n = self.operators[operator].proof(agent)
        sh_idx, sh_path, sh_n = self.shards[shard].proof(operator)
        pl_idx, pl_path, pl_n = self.planet.proof(shard, self.epoch)
        return {
            "entry": agent_leaves[seq].hex(), "seq": seq, "n": len(agent_leaves),
            "agent": {"path": merkle_proof(agent_leaves, seq), "root": a_root.hex()},
            "operator": {"owner": agent, "idx": op_idx, "path": op_path, "n": op_n,
                         "root": self.operators[operator].root().hex(), "name": operator},
            "shard": {"owner": operator, "idx": sh_idx, "path": sh_path, "n": sh_n,
                      "root": self.shards[shard].root().hex(), "name": shard},
            "planet": {"owner": shard, "idx": pl_idx, "path": pl_path, "n": pl_n,
                       "root": self.planet.root(self.epoch).hex(), "epoch": self.epoch},
        }

    @staticmethod
    def verify_proof(p: dict) -> bool:
        """Each hop verifies, AND each hop's root reappears bound to its owner as
        the next hop's leaf. Without that second check, proofs splice."""
        entry = bytes.fromhex(p["entry"])
        a_root = bytes.fromhex(p["agent"]["root"])
        if not verify_inclusion(entry, p["seq"], p["agent"]["path"], a_root, p["n"]):
            return False
        op_leaf = leaf_for("agent", p["operator"]["owner"], a_root)
        op_root = bytes.fromhex(p["operator"]["root"])
        if not verify_inclusion(op_leaf, p["operator"]["idx"], p["operator"]["path"],
                                op_root, p["operator"]["n"]):
            return False
        sh_leaf = leaf_for("operator", p["shard"]["owner"], op_root)
        sh_root = bytes.fromhex(p["shard"]["root"])
        if not verify_inclusion(sh_leaf, p["shard"]["idx"], p["shard"]["path"],
                                sh_root, p["shard"]["n"]):
            return False
        pl_leaf = leaf_for("shard", p["planet"]["owner"], sh_root, p["planet"]["epoch"])
        pl_root = bytes.fromhex(p["planet"]["root"])
        return verify_inclusion(pl_leaf, p["planet"]["idx"], p["planet"]["path"],
                                pl_root, p["planet"]["n"])
