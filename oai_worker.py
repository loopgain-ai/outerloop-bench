#!/usr/bin/env python3
"""Minimal transparent OpenAI agent worker — one bounded session, Ralph-style.

A deliberate mirror of the headless `claude -p` worker: the model gets a bash
tool and a write_file tool, works in the current directory for up to
--max-turns assistant turns, and the script prints ONE json object to stdout
with the same shape the claude CLI reports:

    {"total_cost_usd": ..., "num_turns": ..., "subtype": "success"|"error_max_turns",
     "is_error": false, "result": "<final text>"}

Cost is computed from the API's reported token usage at published per-token
prices (cached input discounted). No SDK dependency — raw HTTPS via urllib.
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

# API key: read OPENAI_API_KEY from the environment, or from a local .env file
# (override the path with LOOPGAIN_BENCH_ENV). No key is ever committed.
ENV_PATH = pathlib.Path(os.environ.get("LOOPGAIN_BENCH_ENV", ".env"))

# $ per 1M tokens: (input, cached_input, output)
PRICES = {
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
}

TOOLS = [
    {"type": "function", "function": {
        "name": "bash",
        "description": "Run a shell command in the repo directory and get stdout+stderr.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Overwrite a file (relative path) with the given full content.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
]


def api_key():
    v = os.environ.get("OPENAI_API_KEY")
    if v:
        return v
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OPENAI_API_KEY not found in environment or .env")


def call_api(key, payload):
    body = json.dumps(payload).encode()
    for attempt in range(4):
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=body,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
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
    ap.add_argument("--model", default="gpt-5-mini")
    ap.add_argument("--max-turns", type=int, default=10)
    ap.add_argument("--prompt", required=True)
    args = ap.parse_args()
    key = api_key()
    p_in, p_cached, p_out = PRICES[args.model]

    cwd = pathlib.Path.cwd()
    messages = [
        {"role": "system",
         "content": "You are an automated coding agent working in a git repo. "
                    "Use the bash and write_file tools to inspect and fix code. "
                    "Keep going until done or told otherwise; do not ask questions."},
        {"role": "user", "content": args.prompt},
    ]
    cost = 0.0
    turns = 0
    final_text = ""
    subtype = "success"
    while True:
        if turns >= args.max_turns:
            subtype = "error_max_turns"
            break
        resp = call_api(key, {"model": args.model, "messages": messages,
                              "tools": TOOLS, "parallel_tool_calls": True})
        turns += 1
        u = resp.get("usage", {})
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        cost += ((u.get("prompt_tokens", 0) - cached) * p_in
                 + cached * p_cached
                 + u.get("completion_tokens", 0) * p_out) / 1e6
        msg = resp["choices"][0]["message"]
        messages.append(msg)
        calls = msg.get("tool_calls")
        if not calls:
            final_text = msg.get("content") or ""
            break
        for tc in calls:
            try:
                targs = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                result = "tool arguments were not valid JSON"
            else:
                result = run_tool(tc["function"]["name"], targs, cwd)
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": result})

    print(json.dumps({"total_cost_usd": round(cost, 6), "num_turns": turns,
                      "subtype": subtype, "is_error": False,
                      "result": final_text[:500]}))


if __name__ == "__main__":
    main()
