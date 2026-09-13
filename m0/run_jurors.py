#!/usr/bin/env python3
"""Put the corpus to any set of juror models over one text endpoint and write the verdict
file e13/e15 read. One request per item, no history; a juror with missing verdicts is marked
incomplete, never padded; endpoint, temperature, prompt hash and UTC time are stamped in.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import juror_prompt

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "jury_sample.json")
ENDPOINT = "https://fal.run/openrouter/router"
TEMPERATURE = 0.0
HARNESS_VERSION = "rj:v1"

# Nine vendors, ten jurors. Two Anthropic tiers are deliberate: they give a
# WITHIN-vendor pair measured under the same prompt as the cross-vendor pairs,
# which is what separates shared lineage from shared judgment.
DEFAULT_MODELS = [
    "openai/gpt-4o-mini",                       # OpenAI
    "google/gemini-2.5-flash",                  # Google
    "meta-llama/llama-3.3-70b-instruct",        # Meta
    "mistralai/mistral-small-3.2-24b-instruct", # Mistral
    "qwen/qwen3-32b",                           # Alibaba
    "deepseek/deepseek-chat-v3.1",              # DeepSeek
    "anthropic/claude-haiku-4.5",               # Anthropic
    "anthropic/claude-sonnet-4.5",              # Anthropic (same vendor, on purpose)
    "x-ai/grok-4.3",                            # xAI
    "amazon/nova-lite-v1",                      # Amazon
]

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


def load_key(env_file):
    if os.environ.get("FAL_KEY"):
        return os.environ["FAL_KEY"]
    if env_file and os.path.exists(env_file):
        for line in open(env_file):
            if line.strip().startswith("FAL_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("no FAL_KEY: export FAL_KEY=... or pass --env-file")


def extract_json(txt):
    """First JSON object in the reply. Models fence it, prefix it, or narrate."""
    if not txt:
        return None
    t = txt.strip()
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) > 1:
            t = parts[1]
            t = t[4:] if t.lower().startswith("json") else t
    m = re.search(r"\{.*?\}", t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def one_verdict(key, model, item, attempts=4):
    """A single juror's verdict on a single item, or None after real effort."""
    system, user = juror_prompt.build(item["text"])
    body = json.dumps({"model": model, "prompt": user, "system_prompt": system,
                       "temperature": TEMPERATURE}).encode()
    last = ""
    for a in range(attempts):
        try:
            req = urllib.request.Request(
                ENDPOINT, data=body,
                headers={"Authorization": f"Key {key}", "Content-Type": "application/json"})
            resp = json.load(urllib.request.urlopen(req, timeout=180))
            obj = extract_json(resp.get("output") or "")
            if obj and str(obj.get("verdict", "")).upper() in ("VIOLATION", "CLEARED"):
                conf = obj.get("confidence")
                try:
                    conf = round(float(conf), 3)
                except (TypeError, ValueError):
                    conf = None
                return {"id": item["id"],
                        "verdict": str(obj["verdict"]).upper(),
                        "rationale": str(obj.get("rationale", ""))[:300],
                        "confidence": conf}
            last = f"unparseable reply: {repr((resp.get('output') or '')[:120])}"
        except urllib.error.HTTPError as e:
            detail = e.read()[:160].decode(errors="replace")
            last = f"HTTP {e.code}: {detail}"
            if e.code not in (408, 409, 429, 500, 502, 503, 504):
                break
        except Exception as e:                       # noqa: BLE001 - transport variety
            last = f"{type(e).__name__}: {e}"
        time.sleep(2 * (a + 1))
    log(f"    ! {model} item {item['id']}: {last}")
    return None


def run_model(key, model, items, existing, workers):
    """All items for one juror. `existing` seeds a --resume run."""
    have = {v["id"]: v for v in existing}
    todo = [it for it in items if it["id"] not in have]
    t0 = time.time()
    if todo:
        with cf.ThreadPoolExecutor(workers) as ex:
            for v in ex.map(lambda it: one_verdict(key, model, it), todo):
                if v:
                    have[v["id"]] = v
    verdicts = [have[i["id"]] for i in items if i["id"] in have]
    missing = [i["id"] for i in items if i["id"] not in have]
    dur = time.time() - t0
    status = "complete" if not missing else f"INCOMPLETE, missing {missing}"
    log(f"  {model:<42} {len(verdicts):>3}/{len(items)} verdicts  {dur:>5.1f}s  {status}")
    return {"juror": model, "complete": not missing, "missing_ids": missing,
            "verdicts": verdicts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--out", default="jury_verdicts_xvendor.json")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--workers", type=int, default=8, help="parallel items per juror")
    ap.add_argument("--resume", action="store_true",
                    help="keep verdicts already in --out, request only the gaps")
    args = ap.parse_args()

    key = load_key(args.env_file)
    items = json.load(open(SAMPLE))
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    out_path = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)

    prior = {}
    if args.resume and os.path.exists(out_path):
        for j in json.load(open(out_path)).get("jurors", []):
            prior[j["juror"]] = j.get("verdicts", [])
        log(f"resuming: {sum(len(v) for v in prior.values())} verdicts already on disk")

    log(f"\nPACT juror run — {len(models)} jurors x {len(items)} items")
    log(f"prompt {juror_prompt.PROMPT_VERSION} sha256 {juror_prompt.prompt_hash()[:16]}  "
        f"temp {TEMPERATURE}  endpoint {ENDPOINT}\n")

    jurors = [run_model(key, m, items, prior.get(m, []), args.workers) for m in models]

    payload = {
        "provenance": {
            "harness": HARNESS_VERSION,
            "endpoint": ENDPOINT,
            "temperature": TEMPERATURE,
            "prompt_version": juror_prompt.PROMPT_VERSION,
            "prompt_sha256": juror_prompt.prompt_hash(),
            "run_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "n_items": len(items),
            "one_request_per_item": True,
        },
        "jurors": jurors,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, indent=1)

    done = [j for j in jurors if j["complete"]]
    bad = [j for j in jurors if not j["complete"]]
    log(f"\nwrote {out_path}")
    log(f"  complete jurors:   {len(done)}/{len(jurors)}")
    if bad:
        log("  INCOMPLETE (excluded from any analysis that needs full coverage):")
        for j in bad:
            log(f"    {j['juror']}  missing {len(j['missing_ids'])}: {j['missing_ids']}")
        log("  re-run with --resume to fill the gaps before reporting anything.")


if __name__ == "__main__":
    main()
