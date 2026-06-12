# Matched-Harness Cross-Model Verdict — 2026-06-11

**Question.** The 2026-06-11 cross-model cell claimed a *model-dependent orientation-starvation
floor*: gpt-5-mini at 6 turns "never reaches an edit" while claude (via the `claude -p` CLI)
worked fine at 6. But the drivers were different — a claude CLI turn is not one raw-API
inference — so "turns" were not comparable units. This re-run holds the driver constant:
**both** models through the same minimal single-inference-per-turn worker
(`oai_worker.py` / `claude_min_worker.py`: raw HTTPS, two tools — `bash` + `write_file`,
parallel tool use, cost = usage × published prices), at **identical** turn budgets.

**Design.** 3 cells × n=6 per worker = 36 trials. convergent (max_turns=10), plateau (8),
regression (6). Models: `claude-haiku-4-5-20251001` (`cmin-` prefix) vs `gpt-5-mini`
(`gptm-` prefix). Same families, same seeds, same harness-computed error signal.
Total real spend: **$1.58** ($1.26 haiku, $0.32 gpt-5-mini). Data:
`results/trials/{cmin,gptm}-*.json`, aggregates in `results/summary-matched-harness.json`.

## Verdict: the starvation floor was a DRIVER ARTIFACT, not a model property

The starvation finding **does not replicate** under the matched harness:

- **First-session edit rate at max_turns=6 is 6/6 for BOTH models.** Every fresh-repo
  regression session — gpt-5-mini included — reached at least one file edit within 6
  single-inference turns. The original "gpt-5-mini never reaches an edit at 6 turns"
  observation came from the unmatched comparison and is refuted.
- **Zero-edit sessions exist, but only on LATE iterations** (after the trial's progress
  plateaus on remaining hard bugs), and at near-identical rates for both models in the
  regression cell: **69.4%** of haiku sessions (25/36) vs **69.2%** of gpt-5-mini sessions
  (27/39). The per-iteration decay profiles are likewise nearly identical
  (iter 2: 3/6 edit for both; iters 5–8: 0 edits for both).
- Conclusion: under identical drivers the budget floor behaves the same for both models.
  **Never tell users that different models need different turn budgets** — turn-budget
  guidance is only meaningful relative to a stated driver. The `mt=6→8` override the old
  gpt cohort ran with (still in `build_matrix` for non-matched runs) was compensating for
  the driver, not the model.

## Residual model differences (capability, not budget)

Real differences remain at identical budgets, but they are throughput/persistence, not floors:

- **Convergence:** haiku 14/18 trials converged (6/6 convergent, 5/6 plateau, 3/6 regression)
  vs gpt-5-mini 10/18 (6/6, 3/6, 1/6).
- **Persistence on hard modules (plateau, mt=8):** haiku kept editing in 15/16 sessions;
  gpt-5-mini edited in only 11/34 sessions after the easy bugs were gone.
- **Progress:** 0 haiku trials never reduced error; 5 gpt-5-mini trials never did
  (2 plateau, 3 regression).

## LoopGain behavior on the matched cohorts (n=36)

- **Coherence violations: 0/36** (0 in every cell, both models) — replicates the main result.
- **False stops:** haiku 2/18 (`cmin-plateau-00-orders+recur` stop@7→later 0;
  `cmin-regression-04-pipeline` stop@20→later 13); gpt-5-mini 3/18
  (`gptm-plateau-02-orders+recur` 16→0; `gptm-regression-01-orders` and
  `gptm-regression-03-orders`, both 8→0). Same failure shape on both models: the
  hardcoded 2×STALLING kill rule fires just before a breakthrough session.
- **True stall catches:** haiku 4 (16+7 sessions saved), gpt-5-mini 8 (24+40 sessions saved).

## Provenance & scope

Internal verification cohort (`aggregate` over results/trials raw records; recompute via
`analyze_matched.py`). No public surface uses these numbers yet — the blog post and
loopgain-verify checks are owned by another session and reconcile against this file.
Reproduce: `run_fulltest.py --worker claude-min --matched --n 6` and
`--worker openai --matched --n 6`.
