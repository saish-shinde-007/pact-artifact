#!/usr/bin/env python3
"""Serving shim: wraps a completion call so every response is logged as a covered
action and returns a receipt with its log position.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pactlog import Store

DB = os.environ.get("PACT_DB", "pact.db")
AGENT = "did:pact:demo/helper-1"
UPSTREAM = os.environ.get("PACT_UPSTREAM")  # e.g. https://api.example.com/v1/chat/completions

store = Store(DB)
store.keygen(AGENT)


def model_reply(messages) -> str:
    user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    if UPSTREAM:
        req = urllib.request.Request(
            UPSTREAM, data=json.dumps({"messages": messages}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read())
        return body["choices"][0]["message"]["content"]
    return f"echo: {user}"  # ponytail: mock model; set PACT_UPSTREAM for a real one


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = body.get("messages", [])
        prompt = json.dumps(messages)
        output = model_reply(messages)
        rec = store.append(AGENT, prompt, output)
        receipt = f"{AGENT}#{rec['seq']}@{rec['entry_hash'][:16]}"
        resp = {
            "choices": [{"message": {"role": "assistant", "content": output}}],
            "pact_receipt": receipt,
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-PACT-Receipt", receipt)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"PACT shim on :8787  db={DB}  upstream={'mock' if not UPSTREAM else UPSTREAM}")
    ThreadingHTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
