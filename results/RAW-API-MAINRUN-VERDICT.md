# Raw-API Main-Run Verdict — driver swap of the outer-loop MAIN study — 2026-06-11

**Question.** The outer-loop MAIN study (89 valid loops, `results/trials/{convergent,plateau,regression}-*`,
no prefix) drove each Ralph-style session with `claude -p` — the full Claude Code CLI. Its headline
"Where it failed" result was the regression cell: at `max_turns=6`, **24/30 false stops**, 28/30 stalled,
only 2/30 converged — read as a *budget-starved* cohort the monitor kept cutting. But a `claude -p` **turn
is not one inference** — the CLI spends turns on orientation/tool-planning — so "6 turns" under the CLI is
not the same unit of work as 6 raw-API inferences. Every *other* LoopGain benchmark (Bench 1; the matched
cross-model run) uses the controlled raw-API driver (one inference per iteration). This re-run holds
everything constant **except the worker**: same cells, same seeds, same families, same bug-sets, same turn
budgets — `claude -p` swapped for `claude_min_worker.py` (raw HTTPS Messages API, two tools `bash`+`write_file`,
one inference/turn, cost = usage × published Haiku 4.5 prices).

**Design.** 3 cells × n=30 = **90 raw-API loops**, `cliraw-` prefix, worker `claude-min`
(`claude-haiku-4-5-20251001`). Budgets: convergent=10, plateau=8, regression=6 — identical to the claude-cli
cohort. Seeds verified identical (`cliraw-convergent-00` seed 1000, bugs `[0,1,2,3,5,6,7,8,9]` — same repo as
`convergent-00`). Total real spend: **$6.50**. Data: `results/trials/cliraw-*.json`; aggregates in
`results/summary-rawapi-mainrun.json`; recompute via `analyze_driver_swap.py` (same band + shipped K=2 stall
path as `analyze_all.py`, so both cohorts are scored apples-to-apples).

## Verdict: the "budget-starved 24/30" was a `claude -p` DRIVER ARTIFACT — coherence and the false-stop failure mode survive

The headline regression result **does not reproduce** on the controlled driver:

| regression cell (mt=6) | claude-cli (89) | raw-API (90) |
|---|---|---|
| **false stops** | **24/30** | **13/30** |
| &nbsp;&nbsp;of which recoverable (later reached 0) | 8 | **9** |
| converged | 2/30 | **16/30** |
| stalled | 28/30 | 14/30 |
| true stall-catches (never reached 0) | 20 | 5 |
| sessions where failing-count **moves** | **28.8%** | **46.5%** |
| sessions that hit max_turns | 262/267 | 142/142 |
| baseline cost | $15.23 | $2.64 |

At identical `max_turns=6`, the raw-API driver makes real progress on **1.6× more sessions** per the same
budget and **16/30 trials converge** (vs 2/30 under the CLI). The claude-cli cohort was genuinely *starved* —
262/267 sessions hit the turn cap without finishing — so it stalled almost everywhere, and the monitor's
stall-kills were mostly cutting **budget-starved grinds, not unsolvable loops**. That starvation was the
CLI's turn semantics (a CLI turn ≠ an inference), not a property of agent loops. **The 24/30 measured
`claude -p`, not LoopGain.**

## What SURVIVES the driver swap

- **Coherence violations: 0/89 claude-cli and 0/90 raw-API.** The core monitor claim — it never flags a
  monotonically-improving trajectory as OSCILLATING/DIVERGING — is **driver-independent** in every cell, both
  cohorts, 179 loops total. This is the central product claim and it holds cleanly.
- **The false-stop failure mode of the hardcoded `2×STALLING` kill rule is real on a clean driver too** —
  and arguably *sharper*: raw-API regression still false-stops **13/30**, and **9 of those 13 were
  recoverable** (the killed run would have reached zero — more than the claude-cli cohort's 8). On a
  non-starved driver the rule is cutting genuinely-solvable runs one session before the breakthrough, not
  starved grinds. plateau also retains 1/30 (recoverable). The "naive consecutive-stall kill misfires near
  breakthroughs" critique stands.
- **The K-sweep lever survives** (raise the consecutive-STALLING threshold to trade false stops for catches):

  | K | raw-API false_stops | fs_recoverable | true_catches | sessions_saved |
  |---|---|---|---|---|
  | 2 (shipped) | 14 | 10 | 5 | 37 |
  | 3 | 11 | 7 | 5 | 32 |
  | 4 | 10 | 6 | 5 | 27 |
  | 5 | 7 | 4 | 5 | 22 |

  Same qualitative shape as claude-cli (K=2 FS=36 → K=5 FS=25, true_catches flat at 26): higher K roughly
  halves false stops while keeping every true catch. Confirms a scale-aware kill rule is the right fix.
- **Convergent cell is clean on both** (claude-cli 1/30 FS all-converge; raw-API 0/30 FS, 30/30 converge).

## What was a claude-CLI ARTIFACT

- **The "budget-starved 24/30" headline** and the framing of the regression cell as a cohort the monitor
  rescues from starvation. On a clean driver the cell mostly *converges*.
- **The magnitude of "true catches / sessions saved" in the hard cells.** claude-cli reported 20 true catches
  and 73.1% / $11.13 savings in regression; raw-API shows 5 true catches and 43.2% / $1.14. The big claude-cli
  numbers were inflated by (a) starved grinds being counted as catches and (b) CLI overhead — claude-cli
  sessions cost ~6× more ($15.23 vs $2.64 baseline for the same 30 trials). The raw-API savings are **real but
  much smaller**, and they come mostly from cutting genuine plateaus, not starvation.
- **Trajectory flatness in the hard cells was driver-amplified.** Session-boundary flatness (failing-count
  unchanged): regression 71.2% claude-cli vs 53.5% raw-API; plateau 47.3% vs 13.2%. The CLI's starvation made
  trajectories far burstier/flatter, which is exactly what fed the consecutive-STALLING kills.

## The "why": session-scale error is a coarse, decimated signal — and the CLI made it worse

A failing-count read only at *session boundaries* is a decimated sample of the underlying fix trajectory:
each session already squeezes out what it can, so on hard remainders consecutive sessions read the same
count → flat → STALLING. That coarseness is intrinsic to the session abstraction (it shows on both drivers).
But `claude -p` at mt=6 *compounded* it: by starving sessions it drove frac-moved down to 28.8% (vs 46.5%
raw-API), manufacturing the long flat runs that produced 24/30. Remove the starvation and the same monitor
sees a normal mix — most runs converge, and the residual false stops are the genuine near-breakthrough kills
the K-sweep addresses.

## Bottom line for the post

Outcome (b): **the "Where it failed" section should be rebuilt on the raw-API numbers.** The honest finding
is *not* "the monitor cut 24/30 starved sessions" — it's:

1. **Coherence is 0 on a clean driver (0/90).** This is the claim to lead with; it's driver-independent.
2. **The `2×STALLING` kill rule false-stops 13/30 hard-cell runs near breakthroughs (9 recoverable)** — a real,
   honest limitation, present even when the driver isn't starving the worker. Raising K halves it.
3. **The original 24/30 was a production-CLI observation**, not a loop property: `claude -p` starves at
   `max_turns=6` because a CLI turn bundles orientation overhead and is not one inference. Keep it as a
   labeled "what the production CLI did differently" note — it's a true and useful adapter caveat, not a
   benchmark result.

## Provenance & scope

Internal verification cohort (`aggregate` over `results/trials/cliraw-*` raw records; recompute via
`analyze_driver_swap.py`). No public surface uses these numbers yet — the blog post
(`we-instrumented-89-agent-loops.md`) and `loopgain-verify` checks are owned by the main session and
reconcile against this file. Existing cohorts (claude-cli 89, gpt-old 18, matched cmin/gptm 36) untouched.
Reproduce: `run_fulltest.py --cliraw --parallel 5`.
