#!/usr/bin/env python3
"""Sweep the consecutive-STALLING kill rule (K) over recorded trajectories.

The shipped core terminates a trajectory-classified loop after 2 consecutive
STALLING readings (hardcoded, core.py v2-protocol rule). The classifier-level
stall_patience knob does NOT govern this. This recompute-only sweep replays
every valid trial's recorded band sequence and asks: at K consecutive STALLING
readings (K=2 is shipped behavior), what is the early-kill vs grind-catch
trade-off at session scale, in real dollars?

Bands are recomputed per-iteration from the error history via a non-terminating
LoopGain (max_iterations=50), matching how the live monitor recorded them.
"""

import json
import pathlib

from loopgain import LoopGain

ROOT = pathlib.Path(__file__).parent
KS = [2, 3, 4, 5]
CAP = 10


def load():
    out = []
    for f in sorted((ROOT / "results" / "trials").glob("*.json")):
        d = json.loads(f.read_text())
        if d.get("aborted"):
            continue
        sess = [r for r in d["iterations"] if r["iter"] >= 1]
        if sess and not any(r.get("cost_usd", 0) > 0 for r in sess):
            continue  # dead-worker artifact
        out.append(d)
    return out


def band_sequence(d):
    lg = LoopGain(target_error=0.0, max_iterations=50, assumed_fixed_cap=CAP)
    states = []
    for r in d["iterations"]:
        states.append(lg.observe(float(r["error"]), output=r["sha"]))
    return states


def stop_under_k(states, errors, k):
    """First index where the loop stops under: TARGET_MET, OSC/DIV terminal,
    or K consecutive STALLING readings. Returns index into the series."""
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
    trials = load()
    cells = sorted(set(t["cell"] for t in trials))
    counts = {c: sum(1 for t in trials if t["cell"] == c) for c in cells}
    print(f"valid trials: {len(trials)}  {counts}\n")

    header = (f"{'K':>2} | {'false_stops':>11} | {'fs_recoverable':>14} | {'true_catches':>12} | "
              f"{'sessions_saved':>14} | {'$burn_avoided':>13} | {'overrun_sessions':>16}")
    print(header)
    print("-" * len(header))
    for k in KS:
        fs = fs_recov = catches = saved = 0
        burn_avoided = 0.0
        overrun = 0
        for d in trials:
            errors = [r["error"] for r in d["iterations"]]
            costs = {r["iter"]: r.get("cost_usd", 0.0) for r in d["iterations"]}
            states = band_sequence(d)
            idx, outcome = stop_under_k(states, errors, k)
            stop_iter = d["iterations"][idx]["iter"]
            later = errors[idx + 1:]
            ever_zero = min(errors) == 0
            if later and min(later) < errors[idx]:
                fs += 1
                if min(later) == 0:
                    fs_recov += 1
            if outcome == "stalled" and not ever_zero:
                catches += 1
                saved += CAP - stop_iter
                mean_cost = (sum(c for i, c in costs.items() if i > 0)
                             / max(1, len([i for i in costs if i > 0])))
                burn_avoided += (CAP - stop_iter) * mean_cost
            if outcome in ("max_iterations",) and not ever_zero:
                overrun += CAP - stop_iter  # sessions a more aggressive rule would have cut
        print(f"{k:>2} | {fs:>11} | {fs_recov:>14} | {catches:>12} | "
              f"{saved:>14} | {burn_avoided:>13.2f} | {overrun:>16}")

    print("\nfalse_stops: stopped at error E, recorded continuation later went strictly below E")
    print("fs_recoverable: subset where the continuation actually reached 0 (the kill cost a SOLVED run)")
    print("true_catches: stopped early on runs that NEVER reached 0 (the grind LoopGain exists to kill)")
    print("$burn_avoided: real mean session cost x sessions cut on true catches")


if __name__ == "__main__":
    main()
