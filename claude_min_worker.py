#!/usr/bin/env python3
"""Minimal transparent Anthropic agent worker — one bounded session, Ralph-style.

An EXACT mirror of oai_worker.py for the Anthropic Messages API: the model gets
a bash tool and a write_file tool, works in the current directory for up to
--max-turns assistant turns (one inference per turn, parallel tool use
allowed), and the script prints ONE json object to stdout with the same shape
the claude CLI reports:

    {"total_cost_usd": ..., "num_turns": ..., "subtype": "success"|"error_max_turns",
     "is_error": false, "result": "<final text>"}

Cost is computed from the API's reported token usage at published per-token
prices (Haiku 4.5: $1.00/M input, $5.00/M output; cache read $0.10/M, cache
write $1.25/M — verified against the platform pricing docs 2026-06-11).
Top-level cache_control mirrors OpenAI's automatic prefix caching so the
cached-input discount applies on both sides. No SDK dependency — raw HTTPS
via urllib. No claude CLI, no OAuth.
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

# API key: read ANTHROPIC_API_KEY from the environment, or from a local .env file
# (override the path with LOOPGAIN_BENCH_ENV). No key is ever committed.
ENV_PATH = pathlib.Path(os.environ.get("LOOPGAIN_BENCH_ENV", ".env"))

# $ per 1M tokens: (input, cache_write, cache_read, output)
PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 1.25, 0.10, 5.00),
}

TOOLS = [
    {"name": "bash",
     "description": "Run a shell command in the repo directory and get stdout+stderr.",
     "input_schema": {"type": "object", "properties": {
         "command": {"type": "string"}}, "required": ["command"]}},
    {"name": "write_file",
     "description": "Overwrite a file (relative path) with the given full content.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["path", "content"]}},
]


def api_key():
    v = os.environ.get("ANTHROPIC_API_KEY")
    if v:
        return v
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                v = line.split("=", 1)[1].strip().strip('"')
                if v:
                    return v
    raise SystemExit("ANTHROPIC_API_KEY not found in environment or .env")


def call_api(key, payload):
    body = json.dumps(payload).encode()
    for attempt in range(4):
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": key,
                     "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def run_tool(name, args, cwd):
    if name == "bash":
        try:
            p = subprocess.run(["/bin/sh", "-c", args["command"]], cwd=cwd,
                               capture_output=True, text=True, timeout=90)
            out = (p.stdout + p.stderr).strip()
        except subprocess.TimeoutExpired:
            out = "(command timed out after 90s)"
        return out[-6000:] if out else "(no output)"
    if name == "write_file":
        target = (pathlib.Path(cwd) / args["path"]).resolve()
        if pathlib.Path(cwd).resolve() not in target.parents and target != pathlib.Path(cwd).resolve():
            return "refused: path escapes the repo directory"
        target.write_text(args["content"])
        return f"wrote {args['path']} ({len(args['content'])} chars)"
    return f"unknown tool {name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--max-turns", type=int, default=10)
    ap.add_argument("--prompt", required=True)
    args = ap.parse_args()
    key = api_key()
    p_in, p_write, p_read, p_out = PRICES[args.model]

    cwd = pathlib.Path.cwd()
    system = ("You are an automated coding agent working in a git repo. "
              "Use the bash and write_file tools to inspect and fix code. "
              "Keep going until done or told otherwise; do not ask questions.")
    messages = [{"role": "user", "content": args.prompt}]
    cost = 0.0
    turns = 0
    final_text = ""
    subtype = "success"
    while True:
        if turns >= args.max_turns:
            subtype = "error_max_turns"
            break
        resp = call_api(key, {"model": args.model, "max_tokens": 8192,
                              "system": system, "messages": messages,
                              "tools": TOOLS,
                              "cache_control": {"type": "ephemeral"}})
        turns += 1
        u = resp.get("usage", {})
        cost += (u.get("input_tokens", 0) * p_in
                 + u.get("cache_creation_input_tokens", 0) * p_write
                 + u.get("cache_read_input_tokens", 0) * p_read
                 + u.get("output_tokens", 0) * p_out) / 1e6
        content = resp.get("content", [])
        calls = [b for b in content if b.get("type") == "tool_use"]
        if not calls:
            final_text = "".join(b.get("text", "") for b in content
                                 if b.get("type") == "text")
            break
        messages.append({"role": "assistant", "content": content})
        results = []
        for tc in calls:
            result = run_tool(tc["name"], tc.get("input") or {}, cwd)
            results.append({"type": "tool_result", "tool_use_id": tc["id"],
                            "content": result})
        messages.append({"role": "user", "content": results})

    print(json.dumps({"total_cost_usd": round(cost, 6), "num_turns": turns,
                      "subtype": subtype, "is_error": False,
                      "result": final_text[:500]}))


if __name__ == "__main__":
    main()
