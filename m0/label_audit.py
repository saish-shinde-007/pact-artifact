#!/usr/bin/env python3
"""Audit corpus labels against clause pol:v2#c1, blind of all verdicts: a VIOLATION label
resting on the 'live credential literal' bullet conflicts when its value announces itself
synthetic. The private-key/log/TLS bullets carry no 'live' qualifier, so those labels stand.
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
