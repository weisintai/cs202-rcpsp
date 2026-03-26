# RCPSP Iteration Program

This repo now uses a direct solver-iteration workflow. The target is the RCPSP/max solver in this repo, and the north star is [METRICS.md](METRICS.md).

## Mission

Improve hidden-instance RCPSP performance by:

- always returning valid schedules
- staying safely within the assignment wall-clock budget
- minimizing makespan
- avoiding overfitting to only `sm_j10` and `sm_j20`

The real objective is lower makespan on harder unseen instances, with validity and deadline compliance as hard constraints.

## Files That Matter

- `METRICS.md`
  - explicit optimization targets and guardrails
- `README.md`
  - CLI usage and benchmark workflow
- `ITERATION_NOTES.md`
  - what has already helped, failed, or regressed
- `rcpsp/heuristic/*`
  - legacy heuristic baseline
- `rcpsp/cp/*`
  - current submission-candidate backend
- `rcpsp/core/*`
  - branching, compression, conflict, lag, and metric helpers
- `scripts/run_guardrails.py`
  - preset benchmark screens
- `scripts/run_cp_residue.py`
  - fastest loop on the hardest public misses

## Setup

1. Cache the public exact-reference CSVs locally if they are missing:

```bash
uv run python scripts/fetch_reference_csvs.py --datasets sm_j10 sm_j20
```

2. Establish a baseline run:

```bash
uv run python scripts/run_guardrails.py --backend cp --preset submission_quick --output-dir tmp/guardrails/baseline-submission-quick
```

3. Read:

- `METRICS.md`
- `README.md`
- `ITERATION_NOTES.md`

## Research Loop

1. Form one concrete hypothesis.
2. Make one focused code change.
3. Run the smallest relevant tests first.
4. Run the residue set if the change touches incumbent generation, branching, or propagation:

```bash
uv run python scripts/run_cp_residue.py --time-limit 5.0
```

5. Run the fast screen:

```bash
uv run python scripts/run_guardrails.py --backend cp --preset submission_quick --output-dir tmp/guardrails/submission-quick
```

6. Only if the fast screen is clean, run the broader guardrails:

```bash
uv run python scripts/run_guardrails.py --backend cp --preset broad_generalization --output-dir tmp/guardrails/broad-generalization
uv run python scripts/run_guardrails.py --backend cp --preset cp_acceptance --output-dir tmp/guardrails/cp-acceptance
```

7. Keep the change only if the target set improves and the broader guardrails stay clean.

## Acceptance Rules

Never accept a change that:

- introduces false infeasible classifications
- breaks `sm_j10 @ 1.0s` exact-match coverage
- clearly worsens `sm_j20 @ 1.0s` without a stronger offsetting gain
- introduces `over_budget > 0` on any submission-facing run
- improves `sm_j10` or `sm_j20` while obviously damaging `sm_j30`, `testset_ubo20`, or `testset_ubo50`

Prefer small, reviewable diffs. Do not touch benchmark data, public reference baselines, or the project PDF unless there is a concrete reason.
