#!/usr/bin/env python3
"""Offline stall-patience sweep over the recorded full-test trajectories.

Recompute-only ($0): replay every valid trial's error series through LoopGain
at stall_patience = 3 (default) .. 6 and tabulate the early-kill vs grind-catch
trade-off using the trials' REAL per-session dollar costs.

A trial is valid if its worker sessions actually ran (any iteration cost > 0).
"""

import json
import pathlib

from loopgain import LoopGain, TrajectoryThresholds

ROOT = pathlib.Path(__file__).parent
TRIALS = sorted((ROOT / "results" / "trials").glob("*.json"))
PATIENCE = [3, 4, 5, 6]
CAP = 10


def load():
    out = []
    for f in TRIALS:
        d = json.loads(f.read_text())
        if d.get("aborted"):
            continue
        if not any(r.get("cost_usd", 0) > 0 for r in d["iterations"]):
            continue  # dead-worker artifact cell
        out.append(d)
    return out


def replay(d, patience):
    tt = TrajectoryThresholds(stall_patience=patience)
    lg = LoopGain(target_error=0.0, max_iterations=d["cap"],
                  trajectory_thresholds=tt, assumed_fixed_cap=d["cap"])
    stop_after = d["iterations"][-1]["iter"]
    for r in d["iterations"]:
        if not lg.should_continue():
            stop_after = r["iter"] - 1
            break
        lg.observe(float(r["error"]), output=r["sha"])
    return stop_after, lg.result


def main():
    trials = load()
    print(f"valid trials: {len(trials)}  "
          f"({', '.join(sorted(set(t['cell'] for t in trials)))})\n")
    header = (f"{'patience':>8} | {'false_stops':>11} | {'quality_forgone':>15} | "
              f"{'stall_catches':>13} | {'sessions_saved':>14} | {'$saved':>7} | {'$burned_past_stop':>17}")
    print(header)
    print("-" * len(header))
    rows = {}
    for pat in PATIENCE:
        fs, fs_mag, catches, saved_sessions, saved_usd, burned = 0, [], 0, 0, 0.0, 0.0
        for d in trials:
            stop, res = replay(d, pat)
            errs = {r["iter"]: r["error"] for r in d["iterations"]}
            costs = {r["iter"]: r.get("cost_usd", 0.0) for r in d["iterations"]}
            last = d["iterations"][-1]["iter"]
            stop_err = errs[stop]
            later = [errs[i] for i in errs if i > stop]
            mean_late_cost = (sum(costs[i] for i in costs if i > 0) /
                              max(1, len([i for i in costs if i > 0])))
            if later and min(later) < stop_err:
                fs += 1
                fs_mag.append(stop_err - min(later))
            if str(res.outcome) == "stalled" and min(errs.values()) > 0:
                catches += 1  # true stall: target never reached, loop killed early
                saved_sessions += CAP - stop
                saved_usd += (CAP - stop) * mean_late_cost
            burned += sum(costs[i] for i in costs if i > stop)
        rows[pat] = fs
        qf = (f"{sum(fs_mag)/len(fs_mag):.1f} tests avg" if fs_mag else "—")
        print(f"{pat:>8} | {fs:>11} | {qf:>15} | {catches:>13} | "
              f"{saved_sessions:>14} | {saved_usd:>7.2f} | {burned:>17.2f}")
    print("\nfalse_stops = replay stopped at error E but the recorded continuation later got strictly below E")
    print("$saved extrapolates each trial's mean real session cost over the sessions a bare cap-10 loop would still run on true stalls")
    print("$burned_past_stop = real dollars the UNgoverned baseline spent after LoopGain's stop point (what governance avoids)")


if __name__ == "__main__":
    main()
