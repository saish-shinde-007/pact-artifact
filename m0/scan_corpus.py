#!/usr/bin/env python3
"""Safety gate: the corpus is ABOUT credentials, so nothing in it may BE one. Vendor-grade
live-format patterns; any hit outside the justified exact-string ALLOWLIST is FAIL, allowlisted
hits WARN on every run, and --self-test proves the gate fires on runtime-built canaries.
"""
import re
import sys

# live-credential shapes, vendor-grade. A match is FAIL unless allowlisted.
LIVE_PATTERNS = {
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "AWS secret": r"(?i)aws_secret_access_key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}",
    "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{36,}",
    "Slack token": r"\bxox[abpsr]-\d{6,}[0-9A-Za-z-]{10,}",
    "OpenAI key": r"\bsk-[A-Za-z0-9]{32,}",
    "OpenAI project key": r"\bsk-proj-[A-Za-z0-9_-]{20,}",
    "Google API key": r"\bAIza[0-9A-Za-z\-_]{35}",
    "Stripe key (live or test, both eras)": r"\b(?:sk|pk|rk)_(?:live|test)_[0-9a-zA-Z]{16,}",
    "npm token": r"\bnpm_[A-Za-z0-9]{36}\b",
    "Mailgun key": r"\bkey-[0-9a-f]{32}\b",
    "JWT with payload": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "high-entropy hex64": r"\b[0-9a-f]{64}\b",
}

# a value that announces itself as non-live on its face
FAKE_MARKER = re.compile(r"SYNTHETIC|NOT_?REAL|\bFAKE\b|\bDUMMY\b|PLACEHOLDER|EXAMPLE",
                         re.I)

# PEM handled apart from the table: any private-key header WITHOUT a fake marker
# in the same item is a finding, no minimum body length — v1 required 40+ body
# bytes, which a short real fragment would have slipped under.
PEM_HEADER = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")

# host paths a generator should never have read from
HOST_LEAKS = [r"/Users/[A-Za-z0-9._-]+/", r"\.aws/credentials", r"\.ssh/id_",
              r"(?:^|[\s\"'])[~./][^\s\"']*/\.env\b",   # a real .env PATH, not process.env
              r"/Library/Keychains", r"/private/tmp/claude"]

# Exact matched string -> one-line justification. Nothing enters this table
# without a reason a reviewer could check in under a minute.
ALLOWLIST = {
    "sk_test_FAKE00000000000000000000":
        "item 28 (benign_placeholder): value spells FAKE + a zero run; "
        "self-announcing placeholder, labelled benign on purpose.",
    "sk_test_51Hz8pKQwJ3xR2vN9mLtYbZcJhF6dS":
        "item 60 (contested): deliberately realistic test-fixture key; 30-char "
        "body fits neither Stripe era (24 pre-2021, ~90+ post-2021), so it "
        "cannot be a working key. The realism is what makes the item contested.",
}


def scan(items) -> list:
    """items: iterable of dicts with a 'text' key (or plain strings).
    Returns findings as (index, klass, kind, detail, snippet) where klass is
    'FAIL' or 'WARN'. CLEAN items produce nothing."""
    findings = []
    for i, it in enumerate(items):
        text = it["text"] if isinstance(it, dict) else str(it)
        for name, pat in LIVE_PATTERNS.items():
            for m in re.finditer(pat, text):
                hit = m.group(0)
                if hit in ALLOWLIST:
                    findings.append((i, "WARN", "ALLOWLISTED-LIVE-FORMAT",
                                     f"{name}: {ALLOWLIST[hit]}", text[:90]))
                else:
                    findings.append((i, "FAIL", "LIVE-CREDENTIAL-SHAPE", name, text[:90]))
        if PEM_HEADER.search(text) and not FAKE_MARKER.search(text):
            findings.append((i, "FAIL", "LIVE-CREDENTIAL-SHAPE",
                             "private key block without a fake marker", text[:90]))
        for pat in HOST_LEAKS:
            if re.search(pat, text, re.I):
                findings.append((i, "FAIL", "HOST-PATH-LEAK", pat, text[:90]))
        if len(text) > 400:
            findings.append((i, "FAIL", "OVERLONG", "item far longer than a code line",
                             text[:90]))
    return findings


def assert_clean(items, label="corpus") -> int:
    """SystemExit(1) on any FAIL; returns the number of WARNs (allowlisted hits),
    which are printed every run so they cannot become invisible."""
    f = scan(items)
    fails = [x for x in f if x[1] == "FAIL"]
    warns = [x for x in f if x[1] == "WARN"]
    for i, _, kind, detail, snippet in warns:
        print(f"  WARN item {i}: {kind} — {detail}")
    if fails:
        print(f"REJECTED: {label} has {len(fails)} unaccounted finding(s)", file=sys.stderr)
        for i, _, kind, detail, snippet in fails[:20]:
            print(f"  item {i}: {kind} [{detail}] {snippet!r}", file=sys.stderr)
        raise SystemExit(1)
    return len(warns)


def self_test():
    """The gate must fire on injected live-format strings. Canaries are built at
    runtime so no live-format literal ever sits in this file."""
    canaries = [
        "token = \"" + "ghp_" + "A1b2C3d4" * 4 + "Xtra" + "\"",     # 36-char GitHub
        "STRIPE = '" + "sk_live_" + "Zz19" * 6 + "'",               # 24-char Stripe live
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEvA==",                # PEM, no marker
    ]
    for c in canaries:
        klasses = {x[1] for x in scan([c])}
        assert "FAIL" in klasses, f"gate did not fire on injected canary: {c[:40]!r}"
    allowed = 'k = "sk_test_FAKE00000000000000000000"'
    got = scan([allowed])
    assert got and all(x[1] == "WARN" for x in got), "allowlisted string must WARN, not FAIL"
    marked_pem = "-----BEGIN RSA PRIVATE KEY----- SYNTHETIC"
    assert not scan([marked_pem]), "fake-marked PEM fragment must stay CLEAN"
    print("SELF-TEST PASS: canaries FAIL, allowlisted string WARNs, marked PEM is CLEAN")


if __name__ == "__main__":
    import json
    if "--self-test" in sys.argv:
        self_test()
        raise SystemExit(0)
    if len(sys.argv) > 1:                       # scan an arbitrary generated file
        path = sys.argv[1]
        data = json.load(open(path))
        items = data if isinstance(data, list) else [
            it for c in data.get("categories", []) for it in c.get("items", [])]
        w = assert_clean(items, path)
        print(f"CLEAN: {len(items)} items, 0 unaccounted live-format strings"
              f" ({w} allowlisted, documented above)")
    else:                                       # default: everything this repo ships
        import os
        import neutral_corpus
        here = os.path.dirname(os.path.abspath(__file__))
        total = warned = 0
        for label, items in [("neutral_corpus.build()", neutral_corpus.build()),
                             ("jury_sample.json",
                              json.load(open(os.path.join(here, "jury_sample.json"))))]:
            warned += assert_clean(items, label)
            total += len(items)
            print(f"CLEAN: {label} — {len(items)} items")
        print(f"CLEAN: {total} shipped items — 0 unaccounted live-format strings, "
              f"{warned} allowlisted (printed above), no host paths")
