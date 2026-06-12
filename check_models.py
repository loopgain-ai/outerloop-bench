#!/usr/bin/env python3
"""List which mini-tier OpenAI models the bench key can access (no key printed)."""
import json
import os
import pathlib
import urllib.request

key = os.environ.get("OPENAI_API_KEY")
if not key:
    env = pathlib.Path(os.environ.get("LOOPGAIN_BENCH_ENV", ".env")).read_text()
    key = next(l.split("=", 1)[1].strip().strip('"') for l in env.splitlines()
               if l.startswith("OPENAI_API_KEY="))
req = urllib.request.Request("https://api.openai.com/v1/models",
                             headers={"Authorization": "Bearer " + key})
ids = [m["id"] for m in json.load(urllib.request.urlopen(req, timeout=30))["data"]]
for pref in ("gpt-5-mini", "gpt-4.1-mini", "gpt-5-nano", "gpt-4o-mini"):
    hits = sorted(i for i in ids if i == pref or i.startswith(pref + "-"))
    if hits:
        print(pref, "->", hits[:3])
