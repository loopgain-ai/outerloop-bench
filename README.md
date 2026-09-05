# outerloop-bench

A reproducible benchmark for running [LoopGain](https://github.com/loopgain-ai/loopgain)
on **outer loops** — "fix until green" agent loops where a single iteration is an
entire headless agent session, not one model call.

LoopGain is a framework- and model-agnostic convergence monitor for agent
verify-revise loops. This benchmark answers one question: does the convergence
math still hold when an "iteration" is a whole agent session spending real API
dollars? We ran **90 real fix-until-green loops** (271 worker sessions, $6.50
total), plus a matched 36-loop cross-model run, and measured it.

Every trial record, both workers, the analysis scripts, and the verdicts are in
this repo. Provenance for every number is `aggregate` — recomputed from the raw
trial records under `results/trials/`, not from a summary.

## The finding, in one paragraph

The band classifier is **coherent at session scale**: across all 90 loops it never
once labeled a monotonically-improving loop as `DIVERGING` or `OSCILLATING`, even
though each session does completely different work in different files. When sessions
have budget the governed stop is clean (well-budgeted cell: **30/30 converged, zero
false stops**). The honest limit is the stop rule: on a deliberately budget-tight
cell it false-stopped **13 of 30** loops, **9** of them one session before the fix
would have landed — a hardcoded 2-consecutive-`STALLING` terminal count that is too
impatient when session-boundary progress is bursty. Raising that count from 2 to 5
halves false stops (14 → 7) while catching every genuine non-converging grind. The
savings a governed stop buys depend entirely on the baseline: ~78% against a bare
Ralph loop with no completion check, but only ~19% against a loop that already stops
on success.

## Experiment design

Each trial is a generated scratch repo with seeded bugs and a pytest suite that acts
as the spec (27–51 tests, 7–21 failing at the start). One loop runs like this:

1. **Spawn a real headless agent session.** A minimal raw-API worker
   (`claude_min_worker.py` / `oai_worker.py`) gets two tools — `bash` and
   `write_file` — and a bounded turn budget, with one instruction: run the tests,
   fix the code, never touch the tests.
2. **The harness computes the error signal, not the worker.** When the session ends,
   the harness restores the test files from git and runs pytest itself. The failing
   count is the error signal. The worker never grades its own work.
3. **`LoopGain.observe(failing_count)`** reads the count; every iteration is a git
   commit, so "roll back to the best iteration" is a real SHA.
4. **Repeat to a cap of 10 sessions** — the outer-loop cap an uninstrumented loop
   would hit — so a governed stop can be compared against the full run's real cost.

Three cells, run on purpose:

| cell | n | session budget | design intent |
|---|---|---|---|
| convergent | 30 | 10 turns | budget comfortably exceeds the work — baseline behavior |
| plateau | 30 | 8 turns | base bugs plus a genuinely hard module (recur / calcexpr) |
| regression | 30 | 6 turns | budget-tight coupled repos — a fix often can't finish in one session |

### The driver rule, and why it matters

A benchmark has to hold the driver constant at the simplest, most transparent layer.
The worker here runs on the **raw API, one inference per turn** — not inside a
production agent CLI. The reason is that "a turn" has to mean the same amount of work
from one run to the next. A production CLI spends turns on orientation and tool
planning, so its "turn" is not one inference, and turn-budget comparisons across
different drivers are not comparing equivalent units.

We learned this the expensive way. The **first** run of this study used the Claude
Code CLI (`claude -p`) as the worker, and the budget-tight cell looked dramatic:
**24 of 30 false stops**. It was an artifact. At a 6-turn budget the CLI was starving
the worker — **262 of 267** of that cell's sessions hit the turn cap without finishing
— which manufactured exactly the long flat trajectories that trip the stall rule. Re-run
on the raw API at the identical cells, seeds, and budgets, the same cell mostly
**converged** and false stops dropped to 13/30. The 24/30 measured `claude -p`'s turn
semantics, not anything about loops. Production-harness behavior is a real and useful
question — it is just a *different*, separately-labeled question. See
[`results/RAW-API-MAINRUN-VERDICT.md`](results/RAW-API-MAINRUN-VERDICT.md).

## Results

### Main study — raw-API, Haiku 4.5 worker (`cliraw-*`, 90 loops, $6.50)

- **Coherence: 0 violations in 90 loops.** The central claim, and it holds.
- **Well-budgeted cell (10 turns): 30/30 converged, 0 false stops.**
- **Budget-tight cell (6 turns): 13/30 false stops, 9 recoverable.** 54% of that
  cell's sessions left the failing count unchanged — session-boundary progress is a
  coarse, decimated sample of the real fix trajectory, so a single flat reading is
  weak evidence.
- **Stall-count sweep (K = 2→5):** false stops fall 14 → 7; true catches stay flat
  at 5. Patience trades false stops for nothing on genuine grinds.

#### Savings depend on the baseline

Recomputed over the `cliraw` cohort with two baselines
([`analyze_savings_table.py`](analyze_savings_table.py)). Every quantity is the
trial's mean per-session cost times a session count, so the table reflects the stop
rule, not run-to-run price noise.

| stop rule | vs a bare cap-10 loop (no completion check) | vs an until-green loop (stops on success) |
|---|---|---|
| shipped behavior (K = 2) | saves **78.3%** | saves **19.4%** |
| patient variant (K = 5) | saves **75.4%** | saves **8.5%** |

The first column is the real Ralph loop a lot of people run — grinding to a fixed cap
with no success check. The honest column is the second: against a loop that already
quits on success, a governed stop's marginal value is just the spend on loops that
were never going to converge. Real, worth having, not the headline.

### Cross-model — matched raw-API harness (`cmin-*` Haiku + `gptm-*` gpt-5-mini, 36 loops, $1.58)

Same minimal driver, same two tools, identical budgets, same repos and bugs, two
models. The findings replicate: **0 coherence violations in all 36 loops**, a clean
**12-for-12** in the well-budgeted cells, and the same near-breakthrough false stops.
What differs is capability, not budget — Haiku converged 14 of 18 loops to
gpt-5-mini's 10 — but at a 6-turn budget both models reached a file edit on every
fresh session, and late no-edit sessions appeared at the same rate (~69% each). The
matched cells cost $1.26 (Haiku) vs $0.32 (gpt-5-mini) for identical work. See
[`results/MATCHED-HARNESS-VERDICT.md`](results/MATCHED-HARNESS-VERDICT.md).

## Cohort map

`results/trials/` holds every record. Identify a cohort by its id prefix:

| prefix | cohort | role |
|---|---|---|
| `cliraw-` | 90 raw-API Haiku loops | **the main study** |
| `cmin-` / `gptm-` | 36 matched raw-API loops (Haiku / gpt-5-mini) | cross-model |
| *(no prefix)* | 89 `claude -p` CLI loops | the superseded first run — kept as the cautionary contrast, never a headline |
| `gpt-` | 18 early unmatched gpt loops | retained for provenance; not used in any reported result |

## Mandatory containment for new runs

Generated shell commands and candidate grading now require a trusted, locally
prepared Docker image containing Python, a POSIX shell, and pytest. The default
is `loopgain-python-pytest:local`; select an already installed trusted image with
`OUTERLOOP_SANDBOX_IMAGE`. Runtime execution never pulls, builds, or installs.
Preflight runs before reading worker credentials and before each model turn.
Native `claude` CLI mode (including the historical default) fails closed; select
`--worker claude-min`, `--worker openai`, or the existing `--cliraw` explicitly.
These remain different drivers, with their existing cohort labels.

Only declared task files enter a disposable nonroot, networkless container.
There is no writable host mount. Task state is bounded text reconstructed on a
16 MiB noexec tmpfs for each tool call. `./run_tests.sh` points to a trusted
read-only runner outside that tmpfs; grading invokes pytest directly. Host keys,
`.env`, Git metadata/config/hooks, home, and Docker socket are excluded. Only
existing declared implementation files are exported back as regular text files;
tests and runner remain under harness control. New helpers, renamed files,
symlinks, binaries, and scratch files do not persist. Direct worker invocations
must provide `--task-files` and `--editable-files` manifests. This is a fixed-file
benchmark tool, not a general-purpose repository agent.

Containers use read-only root/input, no capabilities, no-new-privileges, 128 MiB
memory without extra swap, one CPU, 32 PIDs, and bounded CPU, descriptors,
source, output and wall time. Source is limited to 1 MiB; command output to
64 KiB; JSON envelopes to 2 MiB. Tool and grading deadlines are 90 and 180 seconds.
Every operation forcibly removes its container and descendants. Infrastructure,
unsafe export, timeout, or cleanup failure aborts further turns; failed workers
are not automatically retried. The harness cancels active siblings and unscheduled
trials and owns cleanup even when a worker dies. Standalone SIGKILL or host loss
cannot run cleanup: inspect/remove `outerloop.session`-labelled containers before
resuming. Container isolation depends on patched Docker, its host kernel and a
trusted image; it is not a separate VM boundary.

Only synthetic checks are authorized by this remediation:

```sh
OUTERLOOP_SANDBOX_INTEGRATION=1 python -m pytest tests/test_sandbox.py -q
```

These tests use cached images and mocked providers, never benchmark runs. No
historical results are recomputed. Before a new study, record the image ID and
review the changed runtime/protocol; do not combine sandboxed runs with historical
host runs as equivalent measurements. New trial records include `sandbox_image`.

## Reproduce

The `loopgain` library is pure-Python with zero runtime dependencies.

```bash
pip install loopgain pytest          # into the interpreter you'll run with
export ANTHROPIC_API_KEY=...         # and/or OPENAI_API_KEY for the gpt worker
                                     # (or put them in a local .env)

# regenerate the analyses from the committed trial records (no API spend):
python3 analyze_driver_swap.py       # main-study driver-swap aggregates
python3 analyze_matched.py           # cross-model aggregates
python3 analyze_savings_table.py     # the savings table
python3 sweep_kill_rule.py           # the K = 2..5 stall-count sweep

# re-run the loops from scratch (spends real API dollars):
python3 validate_families.py         # pre-flight: prove the bug catalogs
python3 run_fulltest.py --worker claude-min --parallel 5
```

Set `LOOPGAIN_PY` to point pytest and the worker subprocesses at a specific
interpreter if you are not running everything from one environment.

## Honest limits

- These are **scratch repos with seeded bugs**, sized so hundreds of real agent
  sessions stay affordable — not production codebases.
- The workers are **mini-tier** models. Absolute dollars are small by design; the
  percentages are the point.
- The savings number that matters is the modest one (~19% against a loop that already
  stops on success). The big one is against a baseline that barely tries.
- The plateau cell stalled less than intended — the workers beat the "hard" modules
  more often than expected.
- A convergence monitor inherits its verifier's blind spots: a loop that converges on
  the *wrong* tests stops confidently on a wrong answer. We measure that
  wrong-fixed-point rate at ~4.5% in related work.

The way to know what your loop wastes is to measure your loop. This benchmark is how
we measure ours.

## License

[Apache-2.0](LICENSE).
