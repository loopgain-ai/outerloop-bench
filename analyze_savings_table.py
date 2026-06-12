#!/usr/bin/env python3
"""Savings-table recompute for blog post #5 — the raw-API MAIN study (cliraw cohort).

The post's savings table compares a LoopGain-governed stop against TWO baselines.
Earlier drafts carried savings numbers with no reproducible source; this script is
that source. It recomputes everything from the raw cliraw-*.json trial records with
the SAME band/stop replay analyze_driver_swap.py uses (non-terminating LoopGain bands
+ K-consecutive-STALLING kill), so the table is pinned to real data.

Cost model (deliberately simple and worker-independent — every quantity is the
trial's mean per-session cost times a session COUNT, so the table reflects the
stop rule, not run-to-run price noise):

    mean(trial)      = mean cost_usd over the trial's worker-sessions (iter >= 1)
    bare-cap-10      = mean * 10                         (a Ralph loop with no completion check)
    until-green      = mean * (sessions-to-first-zero, else 10)   (stops on success only)
    governed(K)      = mean * (sessions-to-LoopGain-stop under K consecutive STALLING)

Savings vs a baseline = 1 - sum(governed) / sum(baseline), aggregated over the cohort.

Run:
    python3 analyze_savings_table.py
"""

import json
import pathlib

from loopgain import LoopGain

ROOT = pathlib.Path(__file__).parent
TRIALS = ROOT / "results" / "trials"
CAP = 10
KS = [2, 5]


def is_dead(d):
    sess = [r for r in d["iterations"] if r["iter"] >= 1]
    return bool(sess) and not any(r.get("cost_usd", 0) > 0 for r in sess)


def load_cliraw():
    recs = []
    for f in sorted(TRIALS.glob("cliraw-*.json")):
        d = json.loads(f.read_text())
        if d.get("aborted") or is_dead(d):
            continue
        recs.append(d)
    return recs


def bands(d):
    lg = LoopGain(target_error=0.0, max_iterations=50, assumed_fixed_cap=CAP)
    return [lg.observe(float(r["error"]), output=r["sha"]) for r in d["iterations"]]


def stop_iter_under_k(d, k):
    """Number of worker-sessions LoopGain would run before stopping under a
    K-consecutive-STALLING kill (TARGET_MET / OSCILLATING / DIVERGING also stop)."""
    run = 0
    for i, s in enumerate(bands(d)):
        if s == "TARGET_MET" or s in ("OSCILLATING", "DIVERGING"):
            return d["iterations"][i]["iter"]
        run = run + 1 if s == "STALLING" else 0
        if run >= k:
            return d["iterations"][i]["iter"]
    return d["iterations"][-1]["iter"]


def sessions_to_first_zero(d):
    for r in d["iterations"]:
        if r["iter"] >= 1 and r["error"] == 0:
            return r["iter"]
    return CAP


def main():
    recs = load_cliraw()
    rows = {}
    for k in KS:
        sum_bare = sum_ug = sum_gov = 0.0
        for d in recs:
            sess = [r.get("cost_usd", 0.0) for r in d["iterations"] if r["iter"] >= 1]
            mean = sum(sess) / max(1, len(sess))
            sum_bare += mean * CAP
            sum_ug += mean * min(sessions_to_first_zero(d), CAP)
            sum_gov += mean * min(stop_iter_under_k(d, k), CAP)
        vs_bare = round((1 - sum_gov / sum_bare) * 100, 1)
        vs_ug = round((1 - sum_gov / sum_ug) * 100, 1)
        rows[k] = {"vs_bare_pct": vs_bare, "vs_until_green_pct": vs_ug,
                   "sum_bare_usd": round(sum_bare, 4),
                   "sum_until_green_usd": round(sum_ug, 4),
                   "sum_governed_usd": round(sum_gov, 4)}
    out = {
        "cohort": "cliraw (raw-API MAIN study, 90 loops)",
        "n": len(recs),
        "cost_model": "mean per-session cost x session-count; baselines bare-cap-10 / "
                      "until-green / governed(K)",
        "rows": rows,
    }
    (ROOT / "results" / "summary-savings-table.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
