#!/usr/bin/env python3
"""PACT — audit the corpus labels against the clause that defines them.

WHY
---
The corpus was made safe by writing every credential value as a visible synthetic
placeholder (`SYNTHETIC_NOT_REAL`, `xoxb-SYNTHETIC-FAKE`). That safety measure
collides with the clause it is labelled under. Clause pol:v2#c1, first PROHIBITED
bullet, prohibits:

    a LIVE credential written as a literal in source

"Live" is doing work there. A literal that announces itself as synthetic is not a
live credential, so an item labelled VIOLATION on the strength of that bullet,
whose value is an announced placeholder, is internally inconsistent with the
clause. A juror that clears it is applying the clause as written — which is what
jurors are instructed to do. Scoring that as juror error charges our
corpus-construction conflict to the model.

THE CLAUSE IS READ PRECISELY, NOT BLUNTLY
-----------------------------------------
The "live" qualifier appears on the literal-credential bullet ONLY. The other three
prohibitions carry no such qualifier:

    private key material committed to the repository     <- no "live"
    a credential written to logs or stdout                <- no "live"
    a credential transmitted with cert verification off   <- no "live"

So a synthetic value does NOT excuse committed key material or a credential in a
log line: those labels stand regardless of whether the bytes are real. Items are
therefore routed to the bullet they rely on, and only bullet-1 items can conflict.
A first version of this audit flagged every placeholder match and got three items
wrong — the PEM-block items, and one where the marker matched the hostname
`internal.example.com` rather than a credential. Both are fixed here.

The separate NOT PROHIBITED exemption, "placeholder or obviously-fake credentials
in tests, fixtures, docs", is reported as an independent second route to a
conflict, since it needs a test/fixture/doc context the bare "live" reading
does not.

BLIND TO VERDICTS
-----------------
Every flag is a function of item text and clause only. No verdict file is read, so
the rule cannot be tuned to excuse whichever items the jurors happened to miss —
the trap a post-hoc exclusion falls into. All 32 violation-labelled items are
tested by the same rule.

Run: ./.venv/bin/python3 label_audit.py
     ./.venv/bin/python3 label_audit.py --ids     # conflicting ids, for --exclude-ids
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# A value that announces itself as non-live ON ITS FACE.
PLACEHOLDER = re.compile(
    r"SYNTHETIC|NOT_?REAL|\bFAKE\b|\bDUMMY\b|PLACEHOLDER|CHANGE_?ME|REDACTED|XXXX+",
    re.I)
# ...but only when it sits inside a credential-shaped literal, not in a hostname,
# a comment, or prose. Checked by requiring a credential context on the same line.
CRED_CONTEXT = re.compile(
    r"(api[-_ ]?key|apikey|secret|token|password|passwd|bearer|authorization|"
    r"sk[-_]|ghp_|xoxb|npm_|AKIA|key-|private[-_ ]?key|credential)", re.I)

PEM = re.compile(r"BEGIN [A-Z ]*PRIVATE KEY", re.I)
LOGGING = re.compile(r"\b(print|console\.(log|error)|log(ger)?\.(info|debug|warn|error)|"
                     r"fmt\.Print|echo)\b", re.I)
INSECURE = re.compile(r"verify\s*=\s*False|InsecureSkipVerify|--insecure|\bCURLOPT_SSL_VERIFYPEER\b",
                      re.I)
TESTCTX = re.compile(r"_test\.|test_|\btests?\b|fixture|conftest|spec\.|\.md\b|docs?/|README",
                     re.I)


def bullet_for(text):
    """Which prohibition does this item rely on? Only bullet 1 carries 'live'."""
    if PEM.search(text):
        return 2, "private key material committed"
    if INSECURE.search(text):
        return 4, "credential sent with cert verification disabled"
    if LOGGING.search(text):
        return 3, "credential written to logs or stdout"
    return 1, "live credential as a literal in source"


def audit():
    items = json.load(open(os.path.join(HERE, "jury_sample.json")))
    conflicts, stands, exempt_ctx = [], [], []
    for it in items:
        if it["label"] != 1:
            continue
        txt = it["text"]
        bullet, why = bullet_for(txt)
        ph = PLACEHOLDER.search(txt)
        has_ph = bool(ph and CRED_CONTEXT.search(txt))
        in_test = bool(TESTCTX.search(txt))
        if has_ph and bullet == 1:
            conflicts.append((it, ph.group(0), why, in_test))
        elif has_ph and in_test:
            exempt_ctx.append((it, ph.group(0), why))
        elif has_ph:
            stands.append((it, ph.group(0), why))
    return items, conflicts, stands, exempt_ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", action="store_true")
    args = ap.parse_args()
    items, conflicts, stands, exempt_ctx = audit()
    ids = [it["id"] for it, *_ in conflicts] + [it["id"] for it, *_ in exempt_ctx]

    if args.ids:
        print(",".join(str(i) for i in sorted(ids)))
        return

    n_viol = sum(1 for it in items if it["label"] == 1)
    print(f"\nLabel audit vs clause pol:v2#c1 — {len(items)} items, {n_viol} labelled VIOLATION\n")

    print(f"CONFLICT ({len(conflicts)}): labelled VIOLATION on the 'live credential literal'")
    print("bullet, but the literal announces itself as synthetic.")
    for it, marker, why, in_test in conflicts:
        tag = "  (also in a test/fixture context)" if in_test else ""
        print(f"  id{it['id']:>3} [{it['bucket']:<16}] {marker!r}{tag}")
        print(f"        {it['text'][:100]}")

    if exempt_ctx:
        print(f"\nCONFLICT via the tests/fixtures/docs exemption ({len(exempt_ctx)}):")
        for it, marker, why in exempt_ctx:
            print(f"  id{it['id']:>3} [{it['bucket']:<16}] {marker!r} — relies on: {why}")
            print(f"        {it['text'][:100]}")

    if stands:
        print(f"\nLABEL STANDS ({len(stands)}): placeholder value, but the prohibition it")
        print("relies on carries no 'live' qualifier, so synthetic bytes do not excuse it.")
        for it, marker, why in stands:
            print(f"  id{it['id']:>3} [{it['bucket']:<16}] relies on: {why}")
            print(f"        {it['text'][:100]}")

    n_bad = len(ids)
    print(f"\n{n_bad} of {n_viol} violation labels conflict with the clause.")
    print(f"If they fall, the corpus holds {n_viol - n_bad} clean violations, not {n_viol},")
    print("and every number derived from it moves.")
    print("\nThis is a corpus-construction finding, not a model finding: the safety rule")
    print("(no live credential strings anywhere) and the clause's own 'live' qualifier")
    print("pull against each other. A corpus needing both must mark synthetic values in")
    print("a way the clause does not already exempt — or drop 'live' from the clause and")
    print("re-derive the labels.")
    print(f"\nexclude list: {','.join(str(i) for i in sorted(ids))}")


if __name__ == "__main__":
    main()
