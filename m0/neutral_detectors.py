"""Neutral-domain detector families: repository secret-handling policy.

WHY A NEUTRAL DOMAIN
--------------------
The adjudication findings in this paper are properties of a VOTING RULE, not of
any harm domain: "a 2/3 majority can outvote a lone correct detector" is true
wherever detectors have differing blind spots. Re-deriving them on a benign
domain makes the claims more general and removes any dependence on sensitive
material. This module is that domain.

POLICY CLAUSE pol:v2#c1 — repository secret handling
  PROHIBITED
    - a live credential written as a literal in source (password, API key,
      token, secret assigned to a string)
    - private key material committed to the repository
    - a credential written to logs or stdout
    - a credential transmitted with certificate verification disabled
  NOT PROHIBITED
    - placeholder or obviously-fake credentials in tests, fixtures, docs
    - identifiers merely NAMED like secrets (a variable called password_field)
    - reading a credential from an environment variable or secret manager
    - logging that redacts or masks the value

WRITTEN BLIND, ON PURPOSE
-------------------------
These five families were written from the policy clause above and committed
BEFORE any corpus item existed, by an author who had not seen the corpus. In
every earlier experiment the same person wrote both the detectors and the data,
which made the families' "blind spots" an artifact of authorship — the corpus
was built from the detectors' own vocabulary. Fixing the order of construction
is the point: the corpus is written by separate agents working only from
this policy clause, who never see this file.

Each family is a genuinely partial detector, as a real ensemble member would be.
"""
import re

FAMILIES = ["lexical", "structural", "semantic", "contrastive", "instruction"]

SECRET_NAMES = ["password", "passwd", "api_key", "apikey", "secret", "token",
                "credential", "private_key"]
# shapes a credential takes regardless of what the variable is called
SECRET_SHAPES = ["begin private key", "begin rsa private key", "bearer ",
                 "-----begin", "akia", "ghp_", "xoxb-"]
BENIGN_CONTEXT = ["test", "fixture", "example", "docs/", "sample", "dummy",
                  "placeholder", "fake", "mock"]
REDACTION = ["redact", "mask", "*****", "[hidden]", "sanitiz"]
FROM_ENV = ["os.environ", "getenv", "secretmanager", "vault", "from_env",
            "config.get", "keyring"]
EMIT = ["print(", "log.", "logger.", "console.log", "sys.stdout", "write("]

ASSIGN = re.compile(
    r"(" + "|".join(SECRET_NAMES) + r")\s*[:=]\s*[\"'][^\"']{4,}[\"']", re.I)


def _norm(t: str) -> str:
    """Collapse concatenation and spacing tricks: 'a' + 'b' -> 'ab'."""
    return re.sub(r"[\"']\s*\+\s*[\"']", "", t.lower())


def family_call(family: str, text: str) -> bool:
    t = text.lower()
    assigned = bool(ASSIGN.search(t))
    shaped = any(s in t for s in SECRET_SHAPES)
    benign = any(b in t for b in BENIGN_CONTEXT)
    redacted = any(r in t for r in REDACTION)
    from_env = any(e in t for e in FROM_ENV)
    emits = any(e in t for e in EMIT)

    if family == "lexical":
        # literal assignment only; blind to key material and to logging
        return assigned
    if family == "structural":
        # assignment, but discounts anything that looks like a test or fixture
        return assigned and not benign
    if family == "semantic":
        # adds credential SHAPES the name-based rule misses; own false positives
        return assigned or shaped
    if family == "contrastive":
        # normalizes concatenation, then discounts benign context and redaction
        return (bool(ASSIGN.search(_norm(t))) or shaped) and not (benign or redacted)
    if family == "instruction":
        # emission-focused: a secret being printed or logged, unredacted
        return emits and (assigned or shaped
                          or any(n in t for n in SECRET_NAMES)) and not redacted
    return False


def expected_blind_spots() -> dict:
    """What each family CANNOT see, derived from the policy, stated up front so
    the corpus authors can be checked against it afterwards rather than before."""
    return {
        "lexical": "key material, logging, concatenated literals, env-read confusion",
        "structural": "same as lexical, plus anything in a file it reads as a test",
        "semantic": "logging of a correctly-named-but-not-assigned secret; over-fires on docs",
        "contrastive": "credentials with neither a known name nor a known shape",
        "instruction": "credentials that are stored but never emitted",
    }


if __name__ == "__main__":
    import json
    print("policy: pol:v2#c1 (repository secret handling)")
    print(json.dumps(expected_blind_spots(), indent=2))
