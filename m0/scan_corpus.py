#!/usr/bin/env python3
"""Safety gate for generated corpora.

The neutral-domain corpus is ABOUT credential handling, so its items necessarily
look like credentials. This scanner exists to guarantee that none of them ARE
credentials — neither a real secret that leaked in from the host, nor a
generated string that happens to match a live key format.

Nothing enters the corpus until this passes. Run it on any generated data before
committing it, and keep it in the test suite so it cannot be skipped later.
"""
import re
import sys

# live-credential shapes. A match is a hard stop, not a warning.
LIVE_PATTERNS = {
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "AWS secret": r"(?i)aws_secret_access_key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}",
    "GitHub PAT": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "Slack token": r"xox[abpsr]-[0-9A-Za-z-]{20,}",
    "OpenAI key": r"sk-[A-Za-z0-9]{32,}",
    "Google API key": r"AIza[0-9A-Za-z\-_]{35}",
    "Stripe key": r"(?:sk|pk)_live_[0-9a-zA-Z]{20,}",
    "private key block": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]{40,}",
    "JWT with payload": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "high-entropy hex64": r"\b[0-9a-f]{64}\b",
}

# host paths a generator should never have read from
HOST_LEAKS = [r"/Users/[A-Za-z0-9._-]+/", r"\.aws/credentials", r"\.ssh/id_",
              r"(?:^|[\s\"'])[~./][^\s\"']*/\.env\b",   # a real .env PATH, not process.env
              r"/Library/Keychains", r"/private/tmp/claude"]


def scan(items) -> list:
    """items: iterable of dicts with a 'text' key (or plain strings)."""
    findings = []
    for i, it in enumerate(items):
        text = it["text"] if isinstance(it, dict) else str(it)
        for name, pat in LIVE_PATTERNS.items():
            if re.search(pat, text):
                findings.append((i, "LIVE-CREDENTIAL-SHAPE", name, text[:90]))
        for pat in HOST_LEAKS:
            if re.search(pat, text, re.I):
                findings.append((i, "HOST-PATH-LEAK", pat, text[:90]))
        if len(text) > 400:
            findings.append((i, "OVERLONG", "item far longer than a code line", text[:90]))
    return findings


def assert_clean(items, label="corpus"):
    f = scan(items)
    if f:
        print(f"REJECTED: {label} has {len(f)} finding(s)", file=sys.stderr)
        for i, kind, what, snippet in f[:20]:
            print(f"  item {i}: {kind} [{what}] {snippet!r}", file=sys.stderr)
        raise SystemExit(1)
    return True


if __name__ == "__main__":
    import json
    if len(sys.argv) > 1:                       # scan an arbitrary generated file
        path = sys.argv[1]
        data = json.load(open(path))
        items = data if isinstance(data, list) else [
            it for c in data.get("categories", []) for it in c.get("items", [])]
        assert_clean(items, path)
        print(f"CLEAN: {len(items)} items, no live-credential shapes, no host paths")
    else:                                       # default: everything this repo ships
        import os
        import neutral_corpus
        here = os.path.dirname(os.path.abspath(__file__))
        total = 0
        for label, items in [("neutral_corpus.build()", neutral_corpus.build()),
                             ("jury_sample.json",
                              json.load(open(os.path.join(here, "jury_sample.json"))))]:
            assert_clean(items, label)
            total += len(items)
            print(f"CLEAN: {label} — {len(items)} items")
        print(f"CLEAN: {total} shipped items, no live-credential shapes, no host paths")
