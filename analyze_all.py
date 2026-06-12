#!/usr/bin/env python3
"""Final merged analysis over ALL valid trial records (post-reruns).

Produces results/final-summary.json: per-cell stats + the K-rule trade-off
table + the session-budget finding, all recomputed from the raw trial JSONs.
"""

import json
import pathlib

from loopgain import LoopGain

ROOT = pathlib.Path(__file__).parent
CAP = 10
KS = [2, 3, 4, 5]


def load():
    valid, dead, aborted = [], [], []
    for f in sorted((ROOT / "results" / "trials").glob("*.json")):
        d = json.loads(f.read_text())
        if d.get("aborted"):
            aborted.append(d["id"])
            continue
        sess = [r for r in d["iterations"] if r["iter"] >= 1]
        if sess and not any(r.get("cost_usd", 0) > 0 for r in sess):
            dead.append(d["id"])
            continue
        if d.get("worker", "claude") != "claude":
            continue  # cross-model cohort is analyzed/pinned separately
        valid.append(d)
    return valid, dead, aborted


def bands(d):
    lg = LoopGain(target_error=0.0, max_iterations=50, assumed_fixed_cap=CAP)
    return [lg.observe(float(r["error"]), output=r["sha"]) for r in d["iterations"]]


def stop_under_k(states, k):
    run = 0
    for i, s in enumerate(states):
        if s == "TARGET_MET":
            return i, "converged"
        if s in ("OSCILLATING", "DIVERGING"):
            return i, s.lower()
        run = run + 1 if s == "STALLING" else 0
        if run >= k:
            return i, "stalled"
    return len(states) - 1, "max_iterations"


def main():
    valid, dead, aborted = load()
    out = {"date": "2026-06-11", "n_valid": len(valid), "dead_excluded": len(dead),
           "aborted": aborted, "cells": {}, "k_sweep": [],
           "total_real_cost_usd": round(sum(
               sum(r.get("cost_usd", 0.0) for r in d["iterations"]) for d in valid), 2)}

    # per-cell at shipped behavior (K=2)
    for cell in sorted(set(d["cell"] for d in valid)):
        rs = [d for d in valid if d["cell"] == cell]
        stats = {"n": len(rs), "max_turns": rs[0]["max_turns"], "outcomes": {},
                 "coherence_violations": 0, "false_stops": 0, "fs_recoverable": 0,
                 "true_catches": 0, "sessions_saved_on_catches": 0,
                 "ended_worse_than_best": 0, "rollback_value_iters": 0,
                 "cost_usd": round(sum(sum(r.get("cost_usd", 0.0) for r in d["iterations"]) for d in rs), 2)}
        for d in rs:
            errs = [r["error"] for r in d["iterations"]]
            st = bands(d)
            idx, outcome = stop_under_k(st, 2)
            stats["outcomes"][outcome] = stats["outcomes"].get(outcome, 0) + 1
            mono = all(b <= a for a, b in zip(errs, errs[1:]))
            if mono and ({"DIVERGING", "OSCILLATING"} & set(st)):
                stats["coherence_violations"] += 1
            later = errs[idx + 1:]
            if later and min(later) < errs[idx]:
                stats["false_stops"] += 1
                if min(later) == 0:
                    stats["fs_recoverable"] += 1
            if outcome == "stalled" and min(errs) > 0:
                stats["true_catches"] += 1
                stats["sessions_saved_on_catches"] += CAP - d["iterations"][idx]["iter"]
            if errs[-1] > min(errs):
                stats["ended_worse_than_best"] += 1
                stats["rollback_value_iters"] += errs[-1] - min(errs)
        out["cells"][cell] = stats

    # K sweep over everything
    for k in KS:
        row = {"k": k, "false_stops": 0, "fs_recoverable": 0, "true_catches": 0,
               "sessions_saved": 0, "burn_avoided_usd": 0.0}
        for d in valid:
            errs = [r["error"] for r in d["iterations"]]
            costs = {r["iter"]: r.get("cost_usd", 0.0) for r in d["iterations"]}
            st = bands(d)
            idx, outcome = stop_under_k(st, k)
            later = errs[idx + 1:]
            if later and min(later) < errs[idx]:
                row["false_stops"] += 1
                if min(later) == 0:
                    row["fs_recoverable"] += 1
            if outcome == "stalled" and min(errs) > 0:
                row["true_catches"] += 1
                stop_iter = d["iterations"][idx]["iter"]
                row["sessions_saved"] += CAP - stop_iter
                mean_cost = (sum(c for i, c in costs.items() if i > 0)
                             / max(1, len([i for i in costs if i > 0])))
                row["burn_avoided_usd"] += (CAP - stop_iter) * mean_cost
        row["burn_avoided_usd"] = round(row["burn_avoided_usd"], 2)
        out["k_sweep"].append(row)

    (ROOT / "results" / "final-summary.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
