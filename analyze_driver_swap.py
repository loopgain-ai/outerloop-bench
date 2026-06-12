#!/usr/bin/env python3
"""Driver-swap head-to-head: claude-cli MAIN STUDY (89) vs raw-API re-run (cliraw 90).

Both cohorts use IDENTICAL cells, seeds, families, bug-sets and turn budgets
(convergent=10, plateau=8, regression=6). The ONLY difference is the worker:
the original drove each session with `claude -p` (full Claude Code CLI, a "turn"
does many inferences); the cliraw cohort drives each session with the controlled
raw-API worker (claude_min_worker.py: one inference per turn, two tools).

Everything is recomputed from the raw trial JSONs with the SAME recompute path
analyze_all.py uses — non-terminating LoopGain bands + the shipped K=2 stall
kill rule — so the two cohorts are scored apples-to-apples.

Writes results/summary-rawapi-mainrun.json. Run:
    python3 analyze_driver_swap.py
"""

import json
import pathlib

from loopgain import LoopGain

ROOT = pathlib.Path(__file__).parent
TRIALS = ROOT / "results" / "trials"
CAP = 10
KS = [2, 3, 4, 5]
CELLS = ["convergent", "plateau", "regression"]
OTHER_PREFIXES = {"cmin", "gpt", "gptm", "cliraw"}


def is_dead(d):
    sess = [r for r in d["iterations"] if r["iter"] >= 1]
    return bool(sess) and not any(r.get("cost_usd", 0) > 0 for r in sess)


def load(which):
    """which='cli' -> the no-prefix claude-cli main study; which='cliraw' -> raw-API re-run."""
    recs = []
    for f in sorted(TRIALS.glob("*.json")):
        d = json.loads(f.read_text())
        pfx = d["id"].split("-")[0]
        if which == "cliraw":
            if pfx != "cliraw":
                continue
        else:  # cli
            if pfx in OTHER_PREFIXES:
                continue
        if d.get("aborted") or is_dead(d):
            continue
        recs.append(d)
    return recs


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


def cell_stats(recs, cell):
    rs = [d for d in recs if d["cell"] == cell]
    stats = {"n": len(rs), "max_turns": rs[0]["max_turns"] if rs else None,
             "outcomes": {}, "coherence_violations": 0,
             "false_stops": 0, "fs_recoverable": 0, "fs_ids": [],
             "true_catches": 0, "sessions_saved_on_catches": 0,
             "converged_clean": 0, "ended_worse_than_best": 0,
             # savings table: governed (K=2) vs run-to-(green-or-cap) baseline
             "baseline_cost_usd": 0.0, "governed_cost_usd": 0.0, "saved_usd": 0.0,
             "cost_usd": 0.0}
    for d in rs:
        errs = [r["error"] for r in d["iterations"]]
        costs = [r.get("cost_usd", 0.0) for r in d["iterations"]]
        st = bands(d)
        idx, outcome = stop_under_k(st, 2)
        stats["outcomes"][outcome] = stats["outcomes"].get(outcome, 0) + 1
        mono = all(b <= a for a, b in zip(errs, errs[1:]))
        if mono and ({"DIVERGING", "OSCILLATING"} & set(st)):
            stats["coherence_violations"] += 1
        later = errs[idx + 1:]
        if later and min(later) < errs[idx]:
            stats["false_stops"] += 1
            stats["fs_ids"].append(d["id"])
            if min(later) == 0:
                stats["fs_recoverable"] += 1
        if outcome == "converged":
            stats["converged_clean"] += 1
        if outcome == "stalled" and min(errs) > 0:
            stats["true_catches"] += 1
            stats["sessions_saved_on_catches"] += CAP - d["iterations"][idx]["iter"]
        if errs[-1] > min(errs):
            stats["ended_worse_than_best"] += 1
        # cost accounting
        full = sum(costs)
        governed = sum(c for r, c in zip(d["iterations"], costs) if r["iter"] <= d["iterations"][idx]["iter"])
        stats["baseline_cost_usd"] += full
        stats["governed_cost_usd"] += governed
        stats["saved_usd"] += full - governed
        stats["cost_usd"] += full
    for k in ("baseline_cost_usd", "governed_cost_usd", "saved_usd", "cost_usd"):
        stats[k] = round(stats[k], 2)
    stats["saved_pct"] = round(100 * stats["saved_usd"] / stats["baseline_cost_usd"], 1) if stats["baseline_cost_usd"] else 0.0
    return stats


def k_sweep(recs):
    rows = []
    for k in KS:
        row = {"k": k, "false_stops": 0, "fs_recoverable": 0, "true_catches": 0,
               "sessions_saved": 0, "burn_avoided_usd": 0.0}
        for d in recs:
            errs = [r["error"] for r in d["iterations"]]
            costs = {r["iter"]: r.get("cost_usd", 0.0) for r in d["iterations"]}
            st = bands(d)
            idx, outcome = stop_under_k(st, k)
            stop_iter = d["iterations"][idx]["iter"]
            later = errs[idx + 1:]
            ever_zero = min(errs) == 0
            if later and min(later) < errs[idx]:
                row["false_stops"] += 1
                if min(later) == 0:
                    row["fs_recoverable"] += 1
            if outcome == "stalled" and not ever_zero:
                row["true_catches"] += 1
                row["sessions_saved"] += CAP - stop_iter
                mean_cost = (sum(c for i, c in costs.items() if i > 0)
                             / max(1, len([i for i in costs if i > 0])))
                row["burn_avoided_usd"] += (CAP - stop_iter) * mean_cost
        row["burn_avoided_usd"] = round(row["burn_avoided_usd"], 2)
        rows.append(row)
    return rows


def burstiness(recs, cell):
    """Trajectory shape: across all worker-sessions (iter>=1), how often does the
    failing-test count actually MOVE vs the previous iteration? A 'bursty' driver
    leaves the count flat most sessions then jumps; a smoother driver moves it more
    often. Quantifies the 'why' behind any false-stop-rate difference."""
    rs = [d for d in recs if d["cell"] == cell]
    sessions = 0
    moved = 0
    moved_down = 0
    flat = 0
    mean_turns = []
    max_turn_hits = 0
    for d in rs:
        errs = [r["error"] for r in d["iterations"]]
        for prev, cur, r in zip(errs, errs[1:], d["iterations"][1:]):
            sessions += 1
            if cur != prev:
                moved += 1
                if cur < prev:
                    moved_down += 1
            else:
                flat += 1
            if r.get("turns"):
                mean_turns.append(r["turns"])
            if r.get("subtype") == "error_max_turns":
                max_turn_hits += 1
    return {
        "sessions": sessions,
        "moved": moved,
        "moved_down": moved_down,
        "flat": flat,
        "frac_moved": round(moved / sessions, 3) if sessions else None,
        "frac_flat": round(flat / sessions, 3) if sessions else None,
        "mean_turns": round(sum(mean_turns) / len(mean_turns), 2) if mean_turns else None,
        "hit_max_turns": max_turn_hits,
    }


def main():
    cli = load("cli")
    raw = load("cliraw")
    out = {
        "date": "2026-06-11",
        "design": "driver swap on identical seeds/budgets: claude-cli main study "
                  "(claude -p, many inferences/turn) vs raw-API re-run (claude_min_worker, "
                  "one inference/turn). Only the worker changes. Recompute path = analyze_all "
                  "(non-terminating bands + shipped K=2 stall kill).",
        "n": {"claude_cli": len(cli), "rawapi": len(raw)},
        "cells": {},
        "k_sweep": {"claude_cli": k_sweep(cli), "rawapi": k_sweep(raw)},
        "burstiness": {},
    }
    for cell in CELLS:
        out["cells"][cell] = {
            "claude_cli": cell_stats(cli, cell),
            "rawapi": cell_stats(raw, cell),
        }
        out["burstiness"][cell] = {
            "claude_cli": burstiness(cli, cell),
            "rawapi": burstiness(raw, cell),
        }
    # headline question
    rc = out["cells"]["regression"]
    out["key_question_regression_false_stops"] = {
        "claude_cli": f"{rc['claude_cli']['false_stops']}/{rc['claude_cli']['n']}",
        "rawapi": f"{rc['rawapi']['false_stops']}/{rc['rawapi']['n']}",
        "claude_cli_true_catches": rc["claude_cli"]["true_catches"],
        "rawapi_true_catches": rc["rawapi"]["true_catches"],
    }
    out["coherence_violations_total"] = {
        "claude_cli": sum(out["cells"][c]["claude_cli"]["coherence_violations"] for c in CELLS),
        "rawapi": sum(out["cells"][c]["rawapi"]["coherence_violations"] for c in CELLS),
    }
    (ROOT / "results" / "summary-rawapi-mainrun.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print(f"\nwrote {ROOT / 'results' / 'summary-rawapi-mainrun.json'}")


if __name__ == "__main__":
    main()
