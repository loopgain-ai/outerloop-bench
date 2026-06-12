#!/usr/bin/env python3
"""Matched-harness cross-model analysis.

Compares the cmin-* cohort (claude-haiku-4-5 via claude_min_worker.py) against
the gptm-* cohort (gpt-5-mini via oai_worker.py) — both run through the SAME
minimal single-inference-per-turn driver at IDENTICAL turn budgets
(convergent=10, plateau=8, regression=6). Answers: is the orientation-starvation
floor a driver property (same for both models) or a model property?

Edits are recovered from the per-iteration git commits in trials/<id>/:
an iteration whose commit diff vs the previous sha is empty made NO file edits.

Writes results/summary-matched-harness.json. Run:
    python3 analyze_matched.py
"""

import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).parent
RESULTS = ROOT / "results"
TRIALS_DIR = ROOT / "trials"
CELLS = ["convergent", "plateau", "regression"]
COHORTS = {"cmin": "claude-haiku-4-5-20251001 (minimal driver)",
           "gptm": "gpt-5-mini (minimal driver)"}


def load(prefix):
    recs = []
    for f in sorted((RESULTS / "trials").glob(f"{prefix}-*.json")):
        recs.append(json.loads(f.read_text()))
    return recs


def iteration_edits(rec):
    """Per worker-iteration: did the session change any file? (git diff between
    consecutive iteration commits; commits use --allow-empty so an empty diff
    means the worker never edited.)"""
    d = TRIALS_DIR / rec["id"]
    shas = [i["sha"] for i in rec["iterations"]]
    edits = []
    for prev, cur in zip(shas, shas[1:]):
        try:
            p = subprocess.run(["git", "diff", "--name-only", prev, cur],
                               cwd=d, capture_output=True, text=True, timeout=30)
            edits.append(bool(p.stdout.strip()))
        except Exception:
            edits.append(None)
    return edits


def analyze_cell(recs, cell):
    rs = [r for r in recs if r["cell"] == cell and not r["aborted"]]
    if not rs:
        return {"n": 0}
    coher_viol = 0
    false_stops = []
    sessions_total = 0
    sessions_max_turns = 0
    sessions_zero_edit = 0
    sessions_edit_unknown = 0
    trials_never_edited = 0
    trials_never_reduced = 0
    turns_used = []
    for r in rs:
        errs, stop = r["errors"], r["replay"]["stop_after"]
        mono = all(b <= a for a, b in zip(errs, errs[1:]))
        if mono and ({"DIVERGING", "OSCILLATING"} & set(r["bands"])):
            coher_viol += 1
        post = [e for rr, e in zip(r["iterations"], errs) if rr["iter"] > stop]
        stop_err = next(e for rr, e in zip(r["iterations"], errs) if rr["iter"] == stop)
        if post and min(post) < stop_err:
            false_stops.append({"id": r["id"], "stop_err": stop_err, "later_best": min(post)})
        worker_iters = r["iterations"][1:]
        edits = iteration_edits(r)
        sessions_total += len(worker_iters)
        sessions_max_turns += sum(1 for i in worker_iters if i.get("subtype") == "error_max_turns")
        sessions_zero_edit += sum(1 for e in edits if e is False)
        sessions_edit_unknown += sum(1 for e in edits if e is None)
        turns_used += [i.get("turns") for i in worker_iters if i.get("turns")]
        if worker_iters and not any(e for e in edits if e):
            trials_never_edited += 1
        if min(errs) >= errs[0]:
            trials_never_reduced += 1
    stalls = [r for r in rs if r["replay"]["outcome"] == "stalled"]
    cap = rs[0]["cap"]
    per_iter = {}
    iter1_edits = 0
    iter1_n = 0
    for r in rs:
        for idx, e in enumerate(iteration_edits(r), 1):
            per_iter.setdefault(idx, []).append(e)
        ed = iteration_edits(r)
        if ed:
            iter1_n += 1
            iter1_edits += 1 if ed[0] else 0
    return {
        "n": len(rs),
        "max_turns": rs[0]["max_turns"],
        "outcomes": {o: sum(1 for r in rs if r["replay"]["outcome"] == o)
                     for o in sorted(set(r["replay"]["outcome"] for r in rs))},
        "coherence_violations": coher_viol,
        "false_stops": false_stops,
        "stall_catches": len(stalls),
        "sessions_saved_on_stalls": sum(cap - r["replay"]["stop_after"] for r in stalls),
        "ended_worse_than_best": sum(1 for r in rs if r["errors"][-1] > min(r["errors"])),
        "sessions": {
            "total": sessions_total,
            "hit_max_turns": sessions_max_turns,
            "zero_edit": sessions_zero_edit,
            "edit_unknown": sessions_edit_unknown,
            "zero_edit_rate": round(sessions_zero_edit / sessions_total, 3) if sessions_total else None,
            "mean_turns": round(sum(turns_used) / len(turns_used), 2) if turns_used else None,
            "iter1_edit_rate": f"{iter1_edits}/{iter1_n}",
            "edit_rate_by_iteration": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(per_iter.items())},
        },
        "trials_never_edited": trials_never_edited,
        "trials_never_reduced_error": trials_never_reduced,
        "total_cost_usd": round(sum(r["cost_usd"] for r in rs), 4),
        "aborted_ids": [r["id"] for r in recs if r["cell"] == cell and r["aborted"]],
    }


def main():
    out = {"date": "2026-06-11",
           "design": "matched harness: both workers via minimal single-inference-per-turn "
                     "driver, identical budgets (convergent=10, plateau=8, regression=6), n=6/cell",
           "verdict": {
               "question": "Under identical drivers, is the orientation-starvation floor at 6 "
                           "single-inference turns a driver property or a model property?",
               "answer": "DRIVER ARTIFACT. The starvation finding does not replicate under the "
                         "matched harness: at max_turns=6 both models reach a file edit on every "
                         "first (fresh-repo) session — iter-1 edit rate 6/6 for both. Zero-edit "
                         "sessions occur only on LATE iterations after progress plateaus, at "
                         "near-identical rates for both models (regression cell: 69.4% haiku vs "
                         "69.2% gpt-5-mini). The original 'model-dependent starvation floor' "
                         "claim was driver asymmetry (claude CLI turn != one raw-API inference). "
                         "Do NOT tell users different models need different turn budgets.",
               "residual_model_differences": "Capability, not budget: at identical budgets haiku "
                         "converged 14/18 trials vs gpt-5-mini 10/18, and on plateau (hard-module) "
                         "trials haiku keeps attempting edits in late sessions (15/16 sessions "
                         "edited) while gpt-5-mini stops editing (11/34). These are model "
                         "properties of persistence/throughput, not turn-budget floors.",
           },
           "cohorts": {}}
    for prefix, label in COHORTS.items():
        recs = load(prefix)
        out["cohorts"][prefix] = {
            "label": label,
            "n_trials": len(recs),
            "cells": {c: analyze_cell(recs, c) for c in CELLS},
        }
    (RESULTS / "summary-matched-harness.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print(f"\nwrote {RESULTS / 'summary-matched-harness.json'}")


if __name__ == "__main__":
    main()
