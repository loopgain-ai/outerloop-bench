#!/usr/bin/env python3
"""Outer-loop FULL TEST: 3 cells x n trajectories of real Ralph-style loops.

Cells (all cap=10, real headless haiku sessions, harness-computed error):
  convergent  n=30  families textstats/pipeline/orders, 10-turn sessions
  plateau     n=30  base family + a genuinely-hard module (recur/calcexpr), 8-turn sessions
  regression  n=30  coupled families, tight 6-turn sessions (natural regression pressure)

Per trajectory: live loop runs the fixed-cap baseline regime to cap or zero;
replay recomputes LoopGain's governed stop (target_error=0, max_iterations=cap);
the governed-run aggregate is posted to Dave's live tenant via send_telemetry
(workload_id = outerloop-<cell>) so results appear on dashboard.loopgain.ai.

Run (token sourced from ~/.zshrc by the launcher):
    python3 run_fulltest.py [--smoke] [--parallel 5]
"""

import argparse
import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import threading
import time

from loopgain import LoopGain

ROOT = pathlib.Path(__file__).parent
FAM = ROOT / "families"
HARD = ROOT / "hard"
TRIALS = ROOT / "trials"
RESULTS = ROOT / "results"
# Interpreter for pytest + worker subprocesses. Defaults to the interpreter
# running this script; override with LOOPGAIN_PY to point at a venv that has
# `loopgain` + pytest installed.
VENV_PY = os.environ.get("LOOPGAIN_PY", sys.executable)
MODEL = "claude-haiku-4-5-20251001"
OAI_MODEL = "gpt-5-mini"
CAP = 10
COST_ABORT_USD = 150.0

ENDPOINT = os.environ.get("LOOPGAIN_TELEMETRY_ENDPOINT", "https://telemetry.loopgain.ai/v1/aggregate")
TOKEN = os.environ.get("LOOPGAIN_TELEMETRY_TOKEN")

FAMILIES = {
    "textstats": {"files": ["textstats.py"], "test": "test_textstats.py"},
    "pipeline": {"files": ["money.py", "dates.py", "parsing.py", "report.py"], "test": "test_pipeline.py"},
    "orders": {"files": ["inventory.py", "orders.py"], "test": "test_orders.py"},
}
HARD_MODULES = {
    "recur": {"files": ["recur.py"], "test": "test_recur.py"},
    "calcexpr": {"files": ["calcexpr.py"], "test": "test_calcexpr.py"},
}

CELLS = {
    "convergent": {"n": 30, "families": ["textstats", "pipeline", "orders"],
                   "hard": None, "max_turns": 10, "kmin": 6, "kmax": 9},
    "plateau": {"n": 30, "families": ["orders", "textstats"],
                "hard": ["recur", "calcexpr"], "max_turns": 8, "kmin": 4, "kmax": 6},
    "regression": {"n": 30, "families": ["pipeline", "orders"],
                   "hard": None, "max_turns": 6, "kmin": 6, "kmax": 9},
}

WORKER_PROMPT = """You are one iteration of an automated fix loop on this repo.
Run ./run_tests.sh to see which tests fail. Fix implementation bugs in the source modules so tests pass.
Rules: NEVER modify the test files — the tests are the spec; all fixes go in the implementation modules.
Work within your turn budget; partial progress is fine. When you run out of obvious fixes or budget, stop. Do not ask questions."""

_cost_lock = threading.Lock()
_total_cost = 0.0
_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


def add_cost(c):
    global _total_cost
    with _cost_lock:
        _total_cost += c
        return _total_cost


def materialize(trial):
    """Build the trial repo: family files + seeded bug subset (+ hard module)."""
    d = TRIALS / trial["id"]
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    fam = FAMILIES[trial["family"]]
    for f in fam["files"] + [fam["test"]]:
        shutil.copy(FAM / trial["family"] / f, d / f)

    import runpy
    catalog = list(runpy.run_path(str(FAM / trial["family"] / "bugs.py"))["BUGS"])

    rng = random.Random(trial["seed"])
    k = rng.randint(trial["kmin"], min(trial["kmax"], len(catalog)))
    chosen = rng.sample(range(len(catalog)), k)
    applied = []
    for idx in sorted(chosen):
        fname, clean, buggy = catalog[idx]
        path = d / fname
        src = path.read_text()
        if src.count(clean) != 1:
            raise RuntimeError(f"{trial['id']}: snippet not unique in {fname} (bug {idx})")
        path.write_text(src.replace(clean, buggy))
        applied.append(idx)
    trial["bugs_applied"] = applied

    if trial["hard"]:
        hm = HARD_MODULES[trial["hard"]]
        for f in hm["files"] + [hm["test"]]:
            shutil.copy(HARD / f, d / f)

    (d / "run_tests.sh").write_text(
        "#!/bin/sh\nexec %s -m pytest --tb=short -q \"$@\"\n" % VENV_PY)
    (d / "run_tests.sh").chmod(0o755)
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "baseline"]):
        subprocess.run(cmd, cwd=d, check=True, capture_output=True)
    return d


def evaluate(d, total_tests):
    # NB: spec files are restored by restore_specs() BEFORE this runs; the
    # worker's source edits must survive evaluation.
    p = subprocess.run(["./run_tests.sh", "--tb=no"], cwd=d, capture_output=True, text=True, timeout=180)
    out = p.stdout + p.stderr
    m_fail = re.search(r"(\d+) failed", out)
    m_pass = re.search(r"(\d+) passed", out)
    m_err = re.search(r"(\d+) error", out)
    failed = int(m_fail.group(1)) if m_fail else 0
    passed = int(m_pass.group(1)) if m_pass else 0
    errors = int(m_err.group(1)) if m_err else 0
    if not m_fail and not m_pass:
        failed, passed = (total_tests or 999), 0
    return failed + errors, passed


def restore_specs(d, test_files):
    subprocess.run(["git", "checkout", "--"] + test_files + ["run_tests.sh"],
                   cwd=d, check=False, capture_output=True)


def run_worker(d, max_turns, worker="claude"):
    if worker == "openai":
        cmd = [VENV_PY, str(ROOT / "oai_worker.py"), "--model", OAI_MODEL,
               "--max-turns", str(max_turns), "--prompt", WORKER_PROMPT]
    elif worker == "claude-min":
        cmd = [VENV_PY, str(ROOT / "claude_min_worker.py"), "--model", MODEL,
               "--max-turns", str(max_turns), "--prompt", WORKER_PROMPT]
    else:
        cmd = ["claude", "--model", MODEL, "-p", WORKER_PROMPT,
               "--max-turns", str(max_turns),
               "--allowedTools", "Bash,Read,Edit,Write,Grep,Glob",
               "--output-format", "json"]
    for attempt in (1, 2):
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=1200)
            j = json.loads(p.stdout)
            dead = (j.get("total_cost_usd", 0) == 0 and (j.get("num_turns") or 0) <= 1)
            if dead:
                # 0-cost 1-turn session = the worker never actually ran (e.g. a
                # billing/limit blip). Never record it as a real iteration.
                if attempt == 1:
                    time.sleep(60)
                    continue
                return {"cost_usd": 0.0, "turns": j.get("num_turns"), "wall_s": round(time.time() - t0, 1),
                        "ok": False, "error": "dead worker (0-cost, <=1 turn): " + (j.get("result") or "")[:200]}
            return {"cost_usd": j.get("total_cost_usd", 0.0), "turns": j.get("num_turns"),
                    "subtype": j.get("subtype"), "wall_s": round(time.time() - t0, 1), "ok": True}
        except Exception as e:
            if attempt == 2:
                return {"cost_usd": 0.0, "turns": None, "wall_s": round(time.time() - t0, 1),
                        "ok": False, "error": str(e)[:200]}
            time.sleep(15)


def commit(d, i):
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", f"iter {i}", "--allow-empty"], cwd=d,
                   check=True, capture_output=True)
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=d,
                          capture_output=True, text=True).stdout.strip()


def run_trial(trial, stagger_s):
    time.sleep(stagger_s)
    if _total_cost > COST_ABORT_USD:
        log(f"SKIP {trial['id']}: cost guard tripped (${_total_cost:.2f})")
        return None
    d = materialize(trial)
    fam = FAMILIES[trial["family"]]
    test_files = [fam["test"]] + ([HARD_MODULES[trial["hard"]]["test"]] if trial["hard"] else [])

    iters = []
    failed, passed = evaluate(d, None)
    total_tests = failed + passed
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=d,
                         capture_output=True, text=True).stdout.strip()
    iters.append({"iter": 0, "error": failed, "passed": passed, "sha": sha,
                  "cost_usd": 0.0, "turns": 0, "wall_s": 0.0})

    aborted = None
    for i in range(1, CAP + 1):
        if failed == 0:
            break
        w = run_worker(d, trial["max_turns"], trial.get("worker", "claude"))
        if not w["ok"]:
            aborted = w.get("error", "worker failed")
            break
        restore_specs(d, test_files)
        failed, passed = evaluate(d, total_tests)
        sha = commit(d, i)
        iters.append({"iter": i, "error": failed, "passed": passed, "sha": sha, **w})
        add_cost(w["cost_usd"])

    # replay: the governed run (what a LoopGain user would have experienced)
    lg = LoopGain(target_error=0.0, max_iterations=CAP, assumed_fixed_cap=CAP)
    states, stop_after = [], iters[-1]["iter"]
    for r in iters:
        if not lg.should_continue():
            stop_after = r["iter"] - 1
            break
        states.append(lg.observe(float(r["error"]), output=r["sha"]))
    res = lg.result

    telemetry_sent = None
    if TOKEN and not aborted:
        try:
            tag = ("-cliraw" if trial.get("cliraw") else
                   {"openai": ("-gptm" if trial.get("matched") else "-gpt"),
                    "claude-min": "-cmin"}.get(trial.get("worker"), ""))
            wl = f"outerloop-{trial['cell']}{tag}"
            telemetry_sent = lg.send_telemetry(endpoint=ENDPOINT, token=TOKEN, workload_id=wl)
        except Exception as e:
            telemetry_sent = f"error: {e}"

    errs = [r["error"] for r in iters]
    rec = {
        **{k: trial[k] for k in ("id", "cell", "family", "hard", "seed", "max_turns", "bugs_applied")},
        "matched": trial.get("matched", False),
        "cliraw": trial.get("cliraw", False),
        "worker": trial.get("worker", "claude"),
        "worker_model": OAI_MODEL if trial.get("worker") == "openai" else MODEL,
        "total_tests": total_tests, "cap": CAP, "aborted": aborted,
        "iterations": iters, "errors": errs, "bands": states,
        "replay": {"stop_after": stop_after, "outcome": str(res.outcome),
                   "best_error": res.best_error, "best_output": res.best_output,
                   "iterations_used": res.iterations_used,
                   "savings_vs_fixed_cap": res.savings_vs_fixed_cap},
        "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in iters), 4),
        "cost_after_stop_usd": round(sum(r.get("cost_usd", 0.0) for r in iters
                                         if r["iter"] > stop_after), 4),
        "telemetry_sent": telemetry_sent,
    }
    (RESULTS / "trials").mkdir(parents=True, exist_ok=True)
    (RESULTS / "trials" / f"{trial['id']}.json").write_text(json.dumps(rec, indent=1))
    log(f"TRIAL {trial['id']} done: errors {errs} stop={stop_after} "
        f"outcome={res.outcome} cost=${rec['cost_usd']:.2f} tel={telemetry_sent} "
        f"(cum ${_total_cost:.2f})")
    return rec


def build_matrix(smoke=False, worker="claude", n_override=None, matched=False, cliraw=False):
    trials = []
    if cliraw:
        # Driver-swap cohort: the claude-cli MAIN STUDY re-run on the controlled
        # raw-API worker (claude-min). SAME cells, SAME seeds, SAME turn budgets,
        # SAME families as the original claude-cli 89 — only the worker changes.
        # Distinct `cliraw-` prefix keeps it separable from every other cohort
        # (claude-cli 89, gpt-old 18, matched cmin/gptm 36).
        prefix = "cliraw-"
    elif matched:
        # Matched-harness cohorts: both workers through the SAME minimal driver
        # at IDENTICAL turn budgets. Distinct prefixes keep them separable from
        # the earlier (non-comparable) cohorts.
        prefix = {"claude-min": "cmin-", "openai": "gptm-"}.get(worker, "")
    else:
        prefix = {"openai": "gpt-", "claude-min": "cmin-"}.get(worker, "")
    for cell, cfg in CELLS.items():
        n = 1 if smoke else (n_override or cfg["n"])
        for i in range(n):
            fam = cfg["families"][i % len(cfg["families"])]
            hard = cfg["hard"][i % len(cfg["hard"])] if cfg["hard"] else None
            mt = cfg["max_turns"]
            if worker == "openai" and cell == "regression" and not matched:
                # gpt-5-mini's orientation overhead is ~6 single-call turns; at 6 it
                # never reaches an edit (measured 2026-06-11). The starved condition
                # for this model starts at 8 — labeled in the trial record.
                # (Matched runs deliberately keep 6: the starvation behavior at
                # identical budgets is the thing under test.)
                mt = 8
            trials.append({
                "id": f"{prefix}{cell}-{i:02d}-{fam}" + (f"+{hard}" if hard else ""),
                "cell": cell, "family": fam, "hard": hard, "worker": worker,
                "matched": matched, "cliraw": cliraw,
                "seed": (sorted(CELLS).index(cell) + 1) * 1000 + i,
                "max_turns": mt, "kmin": cfg["kmin"], "kmax": cfg["kmax"],
            })
    return trials


def analyze(recs):
    out = {}
    for cell in CELLS:
        rs = [r for r in recs if r and r["cell"] == cell and not r["aborted"]]
        if not rs:
            out[cell] = {"n": 0}
            continue
        coher_viol = 0
        false_stops = []
        for r in rs:
            errs, stop = r["errors"], r["replay"]["stop_after"]
            mono = all(b <= a for a, b in zip(errs, errs[1:]))
            if mono and ({"DIVERGING", "OSCILLATING"} & set(r["bands"])):
                coher_viol += 1
            post = [e for rr, e in zip(r["iterations"], errs) if rr["iter"] > stop]
            stop_err = next(e for rr, e in zip(r["iterations"], errs) if rr["iter"] == stop)
            if post and min(post) < stop_err:
                false_stops.append({"id": r["id"], "stop_err": stop_err, "later_best": min(post)})
        stalls = [r for r in rs if r["replay"]["outcome"] == "stalled"]
        conv = [r for r in rs if r["replay"]["outcome"] == "converged"]
        ended_worse = [r for r in rs if r["errors"][-1] > min(r["errors"])]
        out[cell] = {
            "n": len(rs),
            "outcomes": {o: sum(1 for r in rs if r["replay"]["outcome"] == o)
                         for o in set(r["replay"]["outcome"] for r in rs)},
            "coherence_violations": coher_viol,
            "false_stops": false_stops,
            "stall_catches": len(stalls),
            "sessions_saved_on_stalls": sum(CAP - r["replay"]["stop_after"] for r in stalls),
            "converged_clean": len(conv),
            "ended_worse_than_best": len(ended_worse),
            "total_cost_usd": round(sum(r["cost_usd"] for r in rs), 2),
            "cost_after_stop_usd": round(sum(r["cost_after_stop_usd"] for r in rs), 2),
            "telemetry_ok": sum(1 for r in rs if r["telemetry_sent"] is True),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--parallel", type=int, default=5)
    ap.add_argument("--cells", type=str, default=None, help="comma-separated cell subset")
    ap.add_argument("--match", type=str, default=None, help="regex filter on trial id")
    ap.add_argument("--worker", type=str, default="claude", choices=["claude", "openai", "claude-min"])
    ap.add_argument("--n", type=int, default=None, help="override per-cell n")
    ap.add_argument("--matched", action="store_true",
                    help="matched-harness cohort: identical turn budgets, cmin-/gptm- prefixes")
    ap.add_argument("--cliraw", action="store_true",
                    help="driver-swap MAIN-STUDY re-run: claude-min worker, same seeds/budgets as "
                         "the claude-cli 89, cliraw- prefix")
    args = ap.parse_args()

    if not TOKEN:
        log("WARN: LOOPGAIN_TELEMETRY_TOKEN not set — dashboard posting disabled")
    worker = "claude-min" if args.cliraw else args.worker
    trials = build_matrix(args.smoke, worker, args.n, args.matched, cliraw=args.cliraw)
    if args.cells:
        keep = set(args.cells.split(","))
        trials = [t for t in trials if t["cell"] in keep]
    if args.match:
        trials = [t for t in trials if re.search(args.match, t["id"])]
    log(f"matrix: {len(trials)} trials, parallel={args.parallel}, cap={CAP}, "
        f"cost guard ${COST_ABORT_USD:.0f}")

    from concurrent.futures import ThreadPoolExecutor
    recs = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = [ex.submit(run_trial, t, (i % args.parallel) * 3) for i, t in enumerate(trials)]
        for f in futs:
            try:
                recs.append(f.result())
            except Exception as e:
                log(f"TRIAL ERROR: {e}")
                recs.append(None)

    summary = {
        "date": "2026-06-11",
        "smoke": args.smoke,
        "n_trials": len([r for r in recs if r]),
        "aborted": [r["id"] for r in recs if r and r["aborted"]],
        "total_cost_usd": round(_total_cost, 2),
        "cells": analyze(recs),
    }
    wtag = ("-cliraw" if args.cliraw else
            {"openai": ("-gptm" if args.matched else "-gpt"),
             "claude-min": "-cmin"}.get(worker, ""))
    suffix = (args.cells or "") + (("-" + re.sub(r"[^a-zA-Z0-9]+", "_", args.match)) if args.match else "") + wtag
    name = "summary-smoke.json" if args.smoke else (
        f"summary-{suffix}.json" if suffix else "summary.json")
    (RESULTS / name).write_text(json.dumps(summary, indent=2))
    log("\n" + json.dumps(summary["cells"], indent=2))
    log(f"\nTOTAL REAL COST: ${_total_cost:.2f}")
    log(f"wrote {RESULTS / name}")


if __name__ == "__main__":
    main()
