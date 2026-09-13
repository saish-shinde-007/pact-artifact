"""PACT M0 — evidence-log core.

Hash-chained per-agent entries, Merkle checkpoints, witness cosigning,
inclusion proofs, RLA sampling, manual challenges, erasure.

M0 trust model: single node, dev keys in SQLite. NOT production —
keys live next to the data they sign; real deployments use enclave keys (paper §IV-A).
"""
import hashlib
import json
import secrets
import sqlite3
import threading
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def H(b: bytes) -> bytes:
    return hashlib.blake2b(b, digest_size=32).digest()


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def leaf_hash(b: bytes) -> bytes:
    return H(b"\x00" + b)


def node_hash(l: bytes, r: bytes) -> bytes:
    return H(b"\x01" + l + r)


def _next_level(level: list[bytes]) -> list[bytes]:
    """Pair up; PROMOTE an unpaired last node rather than duplicating it.
    Duplicating (the CVE-2012-2459 pattern) makes leaf count ambiguous from the
    root: merkle_root([a,b,c]) would equal merkle_root([a,b,c,c])."""
    nxt = [node_hash(level[j], level[j + 1]) for j in range(0, len(level) - 1, 2)]
    if len(level) % 2:
        nxt.append(level[-1])
    return nxt


def merkle_root(leaves: list[bytes]) -> bytes:
    if not leaves:
        return H(b"empty")
    level = [leaf_hash(x) for x in leaves]
    while len(level) > 1:
        level = _next_level(level)
    return level[0]


def merkle_proof(leaves: list[bytes], index: int) -> list[str]:
    """Audit path for leaves[index]: sibling hashes only, bottom-up.

    The side of each sibling is NOT stored. It is re-derived at verification
    time from (index, tree size), so a proof cannot be replayed at a position
    other than the one it was issued for."""
    path: list[str] = []
    level = [leaf_hash(x) for x in leaves]
    i = index
    while len(level) > 1:
        if i % 2:
            path.append(level[i - 1].hex())
        elif i + 1 < len(level):
            path.append(level[i + 1].hex())
        # else: unpaired last node, promoted with no sibling at this level
        level = _next_level(level)
        i //= 2
    return path


def verify_inclusion(leaf: bytes, index: int, path: list[str], root: bytes, n: int) -> bool:
    """Verify leaf sits at `index` of a tree of `n` leaves with the given root.

    `index` and `n` drive the walk: which side each sibling goes on, whether a
    level has a sibling at all, and how long the path must be. A proof issued
    for one position therefore fails at every other position."""
    if n <= 0 or not 0 <= index < n:
        return False
    h = leaf_hash(leaf)
    i, size, p = index, n, 0
    while size > 1:
        if i % 2:
            if p >= len(path):
                return False
            h = node_hash(bytes.fromhex(path[p]), h)
            p += 1
        elif i + 1 < size:
            if p >= len(path):
                return False
            h = node_hash(h, bytes.fromhex(path[p]))
            p += 1
        # else: promoted, nothing consumed
        i //= 2
        size = (size + 1) // 2
    return p == len(path) and h == root


SCHEMA = """
CREATE TABLE IF NOT EXISTS keys(name TEXT PRIMARY KEY, priv BLOB, pub BLOB);
CREATE TABLE IF NOT EXISTS entries(
  agent TEXT, seq INTEGER, ts TEXT, payload TEXT, entry_hash TEXT,
  prev_hash TEXT, sig TEXT, PRIMARY KEY(agent, seq));
CREATE TABLE IF NOT EXISTS payload_store(
  agent TEXT, seq INTEGER, prompt TEXT, output TEXT, salt_i TEXT, salt_o TEXT,
  PRIMARY KEY(agent, seq));
CREATE TABLE IF NOT EXISTS checkpoints(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, upto_seq INTEGER,
  root TEXT, ts TEXT, log_sig TEXT, witness_sigs TEXT);
CREATE TABLE IF NOT EXISTS witness_state(
  witness TEXT, agent TEXT, upto_seq INTEGER, root TEXT, PRIMARY KEY(witness, agent));
CREATE TABLE IF NOT EXISTS challenges(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, seq_from INTEGER, seq_to INTEGER,
  clause TEXT, bond REAL, status TEXT, verdict TEXT, rationale TEXT, ts TEXT,
  anchor_after INTEGER, evidence TEXT);
CREATE TABLE IF NOT EXISTS stakes(party TEXT PRIMARY KEY, stake REAL);
CREATE TABLE IF NOT EXISTS registry(agent TEXT PRIMARY KEY, status TEXT);
CREATE TABLE IF NOT EXISTS reputation(agent TEXT PRIMARY KEY, score REAL);
CREATE TABLE IF NOT EXISTS runtimes(agent TEXT, measurement TEXT,
  PRIMARY KEY(agent, measurement));
"""


class Store:
    def __init__(self, path: str, naive: bool = False,
                 wal: bool | None = None, key_cache: bool | None = None):
        # check_same_thread=False + _lock: the serving shim is threaded, and
        # append() is a read-modify-write on seq, so it must be serialized or
        # two concurrent appends collide on the primary key.
        #
        # naive=True disables the two append-path optimizations (WAL journaling
        # and the signing-key object cache) so the paper's "541 us naive"
        # baseline is reproducible by a shipped flag instead of by hand-editing.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        # each optimization is independently toggleable so the benchmark can
        # attribute the speedup instead of asserting an attribution
        self.naive = naive
        self.use_wal = (not naive) if wal is None else wal
        self.use_key_cache = (not naive) if key_cache is None else key_cache
        if self.use_wal:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.db.commit()
        self._batch = False
        self._privcache, self._pubcache = {}, {}

    def batch(self):
        """Context manager: buffer appends, one commit at exit.
        ponytail: trades a bounded durability window for ~10x append speed —
        the paper's async path; crash loses only the uncommitted tail."""
        store = self

        class _B:
            def __enter__(self):
                store._batch = True

            def __exit__(self, *a):
                store._batch = False
                store.db.commit()

        return _B()

    # -- keys --------------------------------------------------------------
    def keygen(self, name: str):
        if self.db.execute("SELECT 1 FROM keys WHERE name=?", (name,)).fetchone():
            return
        priv = Ed25519PrivateKey.generate()
        self.db.execute(
            "INSERT INTO keys VALUES(?,?,?)",
            (name, priv.private_bytes_raw(), priv.public_key().public_bytes_raw()),
        )
        self.db.commit()

    def _priv(self, name: str) -> Ed25519PrivateKey:
        # deserializing the key costs as much as signing; hold the object
        k = self._privcache.get(name) if self.use_key_cache else None
        if k is None:
            row = self.db.execute("SELECT priv FROM keys WHERE name=?", (name,)).fetchone()
            k = self._privcache[name] = Ed25519PrivateKey.from_private_bytes(row[0])
        return k

    def _pub(self, name: str) -> Ed25519PublicKey:
        k = self._pubcache.get(name)
        if k is None:
            row = self.db.execute("SELECT pub FROM keys WHERE name=?", (name,)).fetchone()
            k = self._pubcache[name] = Ed25519PublicKey.from_public_bytes(row[0])
        return k

    # -- append ------------------------------------------------------------
    def approve_runtime(self, agent: str, measurement: str):
        """Registry of runtime images this agent may serve from (L0). Simulated
        attestation: a real deployment gets `measurement` from a TEE quote rather
        than from the operator's own assertion."""
        self.db.execute("INSERT OR IGNORE INTO runtimes VALUES(?,?)", (agent, measurement))
        self.db.commit()

    def _approved(self, agent: str) -> set:
        return {r[0] for r in self.db.execute(
            "SELECT measurement FROM runtimes WHERE agent=?", (agent,)).fetchall()}

    def append(self, agent: str, prompt: str, output: str, policy: str = "pol:v1#c1",
               tool_calls=None, sample=None, runtime: str = "dev-runtime") -> dict:
        with self._lock:
            return self._append(agent, prompt, output, policy, tool_calls, sample, runtime)

    def _append(self, agent, prompt, output, policy, tool_calls, sample, runtime) -> dict:
        t0 = time.perf_counter()
        row = self.db.execute(
            "SELECT seq, entry_hash FROM entries WHERE agent=? ORDER BY seq DESC LIMIT 1",
            (agent,),
        ).fetchone()
        seq = (row[0] + 1) if row else 0
        prev = row[1] if row else "genesis"
        salt_i, salt_o = secrets.token_bytes(16), secrets.token_bytes(16)
        payload = {
            "seq": seq,
            "prev": prev,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": agent,
            "runtime": runtime,
            "input_commit": H(salt_i + prompt.encode()).hex(),
            "output_commit": H(salt_o + output.encode()).hex(),
            "tool_calls": tool_calls or [],
            "policy": policy,
            "sample": sample or {"seed": 0, "temp": 0.0},
        }
        blob = canon(payload)
        entry_hash = H(blob)
        sig = self._priv(agent).sign(entry_hash)
        self.db.execute(
            "INSERT INTO entries VALUES(?,?,?,?,?,?,?)",
            (agent, seq, payload["ts"], blob.decode(), entry_hash.hex(), prev, sig.hex()),
        )
        self.db.execute(
            "INSERT INTO payload_store VALUES(?,?,?,?,?,?)",
            (agent, seq, prompt, output, salt_i.hex(), salt_o.hex()),
        )
        if not self._batch:
            self.db.commit()
        return {
            "seq": seq,
            "entry_hash": entry_hash.hex(),
            "entry_bytes": len(blob),
            "append_us": (time.perf_counter() - t0) * 1e6,
        }

    def _leaves(self, agent: str, upto: int | None = None) -> list[bytes]:
        q = "SELECT payload FROM entries WHERE agent=? ORDER BY seq"
        rows = self.db.execute(q, (agent,)).fetchall()
        blobs = [r[0].encode() for r in rows]
        return blobs if upto is None else blobs[: upto + 1]

    # -- checkpoint + witnesses ---------------------------------------------
    def checkpoint(self, agent: str, witnesses: list[str]) -> dict:
        with self._lock:
            return self._checkpoint(agent, witnesses)

    def _checkpoint(self, agent: str, witnesses: list[str]) -> dict:
        leaves = self._leaves(agent)
        upto = len(leaves) - 1
        root = merkle_root(leaves)
        record = {"agent": agent, "upto_seq": upto, "root": root.hex(),
                  "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        log_sig = self._priv(agent).sign(canon(record)).hex()
        wsigs, flags = {}, []
        for w in witnesses:
            flag = self._witness_check(w, agent, upto, root, leaves)
            if flag:
                flags.append(flag)
                continue
            wsigs[w] = self._priv(w).sign(canon(record)).hex()
            self.db.execute(
                "INSERT OR REPLACE INTO witness_state VALUES(?,?,?,?)",
                (w, agent, upto, root.hex()),
            )
        self.db.execute(
            "INSERT INTO checkpoints(agent,upto_seq,root,ts,log_sig,witness_sigs) VALUES(?,?,?,?,?,?)",
            (agent, upto, root.hex(), record["ts"], log_sig, json.dumps(wsigs)),
        )
        self.db.commit()
        return {"upto_seq": upto, "root": root.hex(),
                "checkpoint_bytes": len(canon(record)) + len(log_sig) + sum(map(len, wsigs.values())),
                "witness_sigs": len(wsigs), "flags": flags}

    def _witness_check(self, w: str, agent: str, upto: int, root: bytes, leaves) -> str | None:
        """Honest witness: refuse log rewrites and shrinking views."""
        st = self.db.execute(
            "SELECT upto_seq, root FROM witness_state WHERE witness=? AND agent=?", (w, agent)
        ).fetchone()
        if st is None:
            return None
        old_upto, old_root = st
        if upto < old_upto:
            return f"{w}: SPLIT-VIEW (log shrank {old_upto}->{upto})"
        if merkle_root(leaves[: old_upto + 1]).hex() != old_root:
            return f"{w}: REWRITE (prefix root changed at upto={old_upto})"
        return None

    # -- verification --------------------------------------------------------
    def verify(self, agent: str, witnesses: list[str], strict: bool = False) -> dict:
        errors, warnings = [], []
        rows = self.db.execute(
            "SELECT seq, payload, entry_hash, prev_hash, sig FROM entries WHERE agent=? ORDER BY seq",
            (agent,),
        ).fetchall()
        prev = "genesis"
        pub = self._pub(agent)
        approved = self._approved(agent)
        if not approved:
            # never pass silently: an agent with no registered runtime is
            # UNATTESTED, not attested-ok. strict=True makes that fatal.
            msg = (f"agent {agent!r} has no registered runtime — attestation is "
                   f"NOT enforced for its {len(rows)} entries")
            (errors if strict else warnings).append(msg)
        for seq, payload, eh, ph, sig in rows:
            blob = payload.encode()
            if H(blob).hex() != eh:
                errors.append(f"seq {seq}: payload hash mismatch (TAMPERED)")
            if ph != prev:
                errors.append(f"seq {seq}: chain break (prev {ph} != {prev})")
            body = json.loads(payload)
            if body["seq"] != seq or body["prev"] != ph:
                errors.append(f"seq {seq}: payload/chain field mismatch")
            if approved and body.get("runtime") not in approved:
                errors.append(f"seq {seq}: unapproved runtime "
                              f"{body.get('runtime')!r} (ATTESTATION)")
            try:
                pub.verify(bytes.fromhex(sig), bytes.fromhex(eh))
            except Exception:
                errors.append(f"seq {seq}: bad signature")
            prev = eh
        leaves = [r[1].encode() for r in rows]
        for cid, upto, root, ts, log_sig, wsigs in self.db.execute(
            "SELECT id, upto_seq, root, ts, log_sig, witness_sigs FROM checkpoints WHERE agent=?",
            (agent,),
        ).fetchall():
            record = {"agent": agent, "upto_seq": upto, "root": root, "ts": ts}
            if merkle_root(leaves[: upto + 1]).hex() != root:
                errors.append(f"checkpoint {cid}: root mismatch vs current entries (TAMPERED)")
            try:
                pub.verify(bytes.fromhex(log_sig), canon(record))
            except Exception:
                errors.append(f"checkpoint {cid}: bad log signature")
            for w, s in json.loads(wsigs).items():
                try:
                    self._pub(w).verify(bytes.fromhex(s), canon(record))
                except Exception:
                    errors.append(f"checkpoint {cid}: bad witness sig from {w}")
        return {"entries": len(rows), "ok": not errors, "errors": errors,
                "warnings": warnings, "attested": bool(approved)}

    def prove(self, agent: str, seq: int) -> dict:
        ck = self.db.execute(
            "SELECT upto_seq, root FROM checkpoints WHERE agent=? AND upto_seq>=? ORDER BY upto_seq LIMIT 1",
            (agent, seq),
        ).fetchone()
        if not ck:
            raise SystemExit("no checkpoint covers this entry yet")
        upto, root = ck
        leaves = self._leaves(agent, upto)
        path = merkle_proof(leaves, seq)
        n = len(leaves)
        ok = verify_inclusion(leaves[seq], seq, path, bytes.fromhex(root), n)
        return {"seq": seq, "checkpoint_upto": upto, "root": root, "path": path,
                "n": n, "verified": ok}

    # -- audits, challenges, consequences ------------------------------------
    def rla_sample(self, agent: str, k: int) -> list[int]:
        """VRF-style deterministic draw seeded by the latest witnessed root."""
        ck = self.db.execute(
            "SELECT root, upto_seq FROM checkpoints WHERE agent=? ORDER BY id DESC LIMIT 1", (agent,)
        ).fetchone()
        if not ck:
            raise SystemExit("checkpoint first")
        root, n = bytes.fromhex(ck[0]), ck[1] + 1
        picks, i = [], 0
        while len(picks) < min(k, n):
            s = int.from_bytes(H(root + i.to_bytes(4, "big")), "big") % n
            if s not in picks:
                picks.append(s)
            i += 1
        return picks

    def disclose(self, agent: str, seq: int) -> dict | None:
        row = self.db.execute(
            "SELECT prompt, output, salt_i, salt_o FROM payload_store WHERE agent=? AND seq=?",
            (agent, seq),
        ).fetchone()
        if row is None:
            return None
        body = json.loads(self.db.execute(
            "SELECT payload FROM entries WHERE agent=? AND seq=?", (agent, seq)).fetchone()[0])
        ok_i = H(bytes.fromhex(row[2]) + row[0].encode()).hex() == body["input_commit"]
        ok_o = H(bytes.fromhex(row[3]) + row[1].encode()).hex() == body["output_commit"]
        return {"prompt": row[0], "output": row[1], "commits_match": ok_i and ok_o}

    def open_challenges_over(self, agent: str, seq: int) -> list[int]:
        return [r[0] for r in self.db.execute(
            "SELECT id FROM challenges WHERE agent=? AND status='OPEN' "
            "AND seq_from<=? AND seq_to>=?", (agent, seq, seq)).fetchall()]

    def erase(self, agent: str, seq: int, force: bool = False) -> dict:
        """GDPR path: drop payload + salts; the commitment stays but is unlinkable.

        Refuses while a challenge covering this entry is open — erasure would
        otherwise destroy the evidence under adjudication — and always records
        the erasure itself on the ledger, so a deletion can never be silent."""
        with self._lock:
            blocking = self.open_challenges_over(agent, seq)
            if blocking and not force:
                return {"erased": False, "blocked_by": blocking}
            self.db.execute("DELETE FROM payload_store WHERE agent=? AND seq=?", (agent, seq))
            self.db.commit()
            self._append(agent, f"erasure:seq={seq}", "payload and salts destroyed",
                         "pol:v1#erasure", None, None, "dev-runtime")
            return {"erased": True, "blocked_by": blocking, "logged": True}

    def tamper(self, agent: str, seq: int):
        """Adversary helper for tests/demos: silently edit a logged payload."""
        payload = self.db.execute(
            "SELECT payload FROM entries WHERE agent=? AND seq=?", (agent, seq)).fetchone()[0]
        body = json.loads(payload)
        body["output_commit"] = H(b"forged").hex()
        self.db.execute(
            "UPDATE entries SET payload=? WHERE agent=? AND seq=?",
            (canon(body).decode(), agent, seq),
        )
        self.db.commit()

    def challenge(self, agent: str, seq_from: int, seq_to: int, clause: str,
                  bond: float = 1.0) -> int:
        with self._lock:
            return self._challenge(agent, seq_from, seq_to, clause, bond)

    def _challenge(self, agent: str, seq_from: int, seq_to: int, clause: str,
                   bond: float = 1.0) -> int:
        # pin the checkpoint height at filing time; the jury seed comes from the
        # NEXT checkpoint, which does not yet exist and so cannot be ground for
        top = (self.db.execute("SELECT MAX(id) FROM checkpoints WHERE agent=?",
                               (agent,)).fetchone() or (0,))[0] or 0
        cur = self.db.execute(
            "INSERT INTO challenges(agent,seq_from,seq_to,clause,bond,status,ts,anchor_after)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (agent, seq_from, seq_to, clause, bond, "OPEN",
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), top),
        )
        self.db.commit()
        return cur.lastrowid

    def jury_anchor(self, challenge_id: int) -> bytes | None:
        """The unpredictable seed for this challenge's jury draw: the root of the
        first checkpoint sealed AFTER the challenge was filed.

        A challenger cannot grind for a favourable jury because the value did not
        exist when the challenge id was assigned. Returns None until such a
        checkpoint exists — adjudication must wait rather than fall back to a
        grindable seed."""
        row = self.db.execute(
            "SELECT agent, anchor_after FROM challenges WHERE id=?", (challenge_id,)).fetchone()
        if row is None:
            return None
        agent, after = row
        ck = self.db.execute(
            "SELECT root FROM checkpoints WHERE agent=? AND id>? ORDER BY id LIMIT 1",
            (agent, after or 0)).fetchone()
        return bytes.fromhex(ck[0]) if ck else None

    def verdict(self, challenge_id: int, verdict: str, rationale: str,
                severity: str = "S1", evidence: dict | None = None):
        with self._lock:
            return self._verdict(challenge_id, verdict, rationale, severity, evidence)

    def _verdict(self, challenge_id: int, verdict: str, rationale: str,
                 severity: str = "S1", evidence: dict | None = None):
        agent, bond = self.db.execute(
            "SELECT agent, bond FROM challenges WHERE id=?", (challenge_id,)).fetchone()
        self.db.execute(
            "UPDATE challenges SET status='CLOSED', verdict=?, rationale=?, evidence=? "
            "WHERE id=?",
            (verdict, rationale, json.dumps(evidence) if evidence else None, challenge_id),
        )
        score = (self.db.execute("SELECT score FROM reputation WHERE agent=?", (agent,)).fetchone()
                 or (1.0,))[0]
        stake = (self.db.execute("SELECT stake FROM stakes WHERE party=?", (agent,)).fetchone()
                 or (100.0,))[0]
        status = "active"
        if verdict == "VIOLATION":
            # the severity ladder, actually applied (P6)
            score *= 0.8
            stake *= {"S0": 1.0, "S1": 0.9, "S2": 0.75, "S3": 0.5}.get(severity, 0.9)
            status = {"S0": "active", "S1": "active",
                      "S2": "probation", "S3": "suspended"}.get(severity, "active")
            self.db.execute("INSERT OR REPLACE INTO stakes VALUES(?,?)", (agent, stake))
        elif verdict == "FRIVOLOUS":
            # the challenger forfeits its bond to the party it harassed
            ch_stake = (self.db.execute(
                "SELECT stake FROM stakes WHERE party=?", ("challenger",)).fetchone() or (100.0,))[0]
            self.db.execute("INSERT OR REPLACE INTO stakes VALUES(?,?)",
                            ("challenger", ch_stake - bond))
            self.db.execute("INSERT OR REPLACE INTO stakes VALUES(?,?)", (agent, stake + bond))
        self.db.execute("INSERT OR REPLACE INTO reputation VALUES(?,?)", (agent, score))
        if verdict == "VIOLATION":
            self.db.execute("INSERT OR REPLACE INTO registry VALUES(?,?)", (agent, status))
        self.db.commit()

    def verify_verdict(self, challenge_id: int) -> dict:
        """Is this verdict actually backed by a jury draw that reproduces?

        Re-derives the committee from the recorded anchor and checks the claimed
        jurors match. A verdict written directly to the store carries no evidence
        and is reported as unbacked rather than silently trusted (P5)."""
        from jury import sample_jury                       # local: avoids import cycle
        row = self.db.execute(
            "SELECT agent, verdict, evidence, seq_from, seq_to FROM challenges WHERE id=?",
            (challenge_id,)).fetchone()
        if row is None:
            return {"ok": False, "errors": ["no such challenge"]}
        agent, verdict, ev, s_from, s_to = row
        if not ev:
            return {"ok": False, "backed": False,
                    "errors": [f"verdict {verdict!r} has no jury evidence (self-issued)"]}
        ev = json.loads(ev)
        d = self.disclose(agent, s_from)
        if d is None:
            return {"ok": False, "backed": True, "errors": ["payload erased; cannot re-derive"]}
        seed = H(bytes.fromhex(ev.get("anchor") or "")
                 + f"challenge:{challenge_id}:{agent}:{d['prompt']}".encode())
        expected = [j["id"] for j in sample_jury(seed)[0]]
        errors = []
        if expected != ev.get("jurors"):
            errors.append("recorded jury does not match the draw for this anchor")
        if ev.get("k") != len(expected):
            errors.append("jury size mismatch")
        return {"ok": not errors, "backed": True, "errors": errors}

    def gate_check(self, agent: str) -> dict:
        """What a serving gate, marketplace or insurer reads before transacting.
        This is where consequences actually bite (P6)."""
        status = (self.db.execute("SELECT status FROM registry WHERE agent=?",
                                  (agent,)).fetchone() or ("active",))[0]
        return {"agent": agent, "status": status, "may_serve": status != "suspended",
                "reputation": self.status(agent)["reputation"]}

    def status(self, agent: str) -> dict:
        n = self.db.execute("SELECT COUNT(*) FROM entries WHERE agent=?", (agent,)).fetchone()[0]
        ck = self.db.execute("SELECT COUNT(*) FROM checkpoints WHERE agent=?", (agent,)).fetchone()[0]
        rep = (self.db.execute("SELECT score FROM reputation WHERE agent=?", (agent,)).fetchone()
               or (1.0,))[0]
        stake = (self.db.execute("SELECT stake FROM stakes WHERE party=?", (agent,)).fetchone()
                 or (100.0,))[0]
        reg = (self.db.execute("SELECT status FROM registry WHERE agent=?",
                               (agent,)).fetchone() or ("active",))[0]
        return {"entries": n, "checkpoints": ck, "reputation": round(rep, 3),
                "stake": round(stake, 2), "registry": reg}
