# RCPSP/max Project Report

## Project Positioning

Our final solver is a scheduling-specific branch-and-propagate backend for `RCPSP/max`. The design target is the course requirement from [Project.pdf](Project.pdf): produce good valid schedules under a strict `30s` wall-clock budget per instance, without relying on external optimization libraries.

This is intentionally not a full industrial constraint-programming engine. We implemented a focused solver around lag closure, cumulative resource pruning, pair-order branching, and a lightweight warm-start phase for early incumbents. That scope fits the assignment better than trying to reproduce a full CP-SAT or CP Optimizer style stack.

## Why We Chose `cp`

`cp` is now the active submission backend.

Reasoning:

- it is self-contained and consistent with the assignment constraint of no external optimization library
- it has the strongest ceiling on the harder `30s` public cases
- it gives us a clean architecture for propagation, branching, and exact-style search
- it is easier to reason about scientifically than the older mixed `hybrid` path

The repo still contains `hybrid` and `sgs`, but they are now archival comparison baselines rather than the main development path.

## Solver Overview

The `cp` backend does not search directly over full schedules. Instead, it searches over extra pairwise resource-order decisions and keeps tightening time windows as search progresses.

High-level flow:

1. Parse the instance and compute lag closure.
2. Build the root CP node with temporal lower bounds and any forced resource orders.
3. Run `guided_seed` to try to find an early incumbent or early infeasibility.
4. If needed, run a short constructive warm-start attempt from the root.
5. Enter DFS over pair-order resource decisions.
6. At each node, propagate temporal and resource constraints to a fixpoint.
7. If a node is impossible, prune it.
8. If a node yields a valid schedule, compress it and compare it against the incumbent.
9. Otherwise branch on a conflict and continue until proof or timeout.

Main implementation files:

- [search.py](rcpsp/cp/search.py)
  - top-level control flow, branching, incumbent handling, budget gating
- [propagation.py](rcpsp/cp/propagation.py)
  - EST/LST tightening, timetable pruning, forced pair-order inference
- [construct.py](rcpsp/cp/construct.py)
  - CP-native constructive schedule generation
- [guided_seed.py](rcpsp/cp/guided_seed.py)
  - construct / improve / short proof warm-start orchestration
- [state.py](rcpsp/cp/state.py)
  - search-node and statistics state
- [exact.py](rcpsp/cp/exact.py)
  - bounded exact helper used inside the seed phase

## What The Solver Currently Does Well

The strongest evidence for the backend is the `30s` public acceptance matrix from [tmp/guardrails/cp-cp_acceptance-20260323-152344/summary.json](tmp/guardrails/cp-cp_acceptance-20260323-152344/summary.json).

| Dataset | Exact | Unknown | Over Budget |
| --- | ---: | ---: | ---: |
| `sm_j10 @ 30s` | `187 / 187` | `0` | `0` |
| `sm_j20 @ 30s` | `158 / 158` | `0` | `0` |
| `sm_j30 @ 30s` | `117 / 120` | `2` | `0` |
| `testset_ubo20 @ 30s` | `66 / 66` | `0` | `0` |
| `testset_ubo50 @ 30s` | `31 / 33` | `2` | `0` |

This means the backend is already strong on the main course-facing public matrix, especially for `sm_j20`.

## What Still Looks Weak

The short-budget guardrail screen is still much harder. Current quick-screen numbers come from [tmp/guardrails/cp-submission_quick-20260324-123953/summary.json](tmp/guardrails/cp-submission_quick-20260324-123953/summary.json).

| Dataset | Exact | Unknown | Over Budget |
| --- | ---: | ---: | ---: |
| `sm_j10 @ 1.0s` | `187 / 187` | `0` | `0` |
| `sm_j20 @ 1.0s` | `155 / 158` | `0` | `0` |
| `sm_j30 @ 0.1s` | `78 / 120` | `21` | `1` |
| `testset_ubo20 @ 0.1s` | `57 / 66` | `1` | `0` |
| `testset_ubo50 @ 0.1s` | `16 / 33` | `15` | `0` |

The held-out anti-overfitting screen is also still a scaling wall. Current numbers come from [tmp/guardrails/cp-broad_generalization-20260324-124159/summary.json](tmp/guardrails/cp-broad_generalization-20260324-124159/summary.json).

| Dataset | Exact | Feasible | Unknown | Over Budget |
| --- | ---: | ---: | ---: | ---: |
| `testset_ubo10 @ 0.1s` | `73 / 73` | `73` | `0` | `0` |
| `testset_ubo100 @ 0.1s` | `0 / 24` | `3` | `75` | `3` |
| `testset_ubo200 @ 0.1s` | `0 / 25` | `0` | `88` | `72` |

So the backend is already credible on the submission-facing `30s` matrix, but it is still weak on:

- very short budgets on larger instances
- first-incumbent generation on hard feasible cases
- larger held-out Kobe instances such as `ubo100` and `ubo200`

## Current Bottleneck

The clearest current weakness is first-incumbent generation on the hardest feasible cases.

Our residue loop:

```bash
uv run python scripts/run_cp_residue.py
```

currently still leaves two public `30s` residue cases unsolved:

- `testset_ubo50/psp4.sch`
- `testset_ubo50/psp9.sch`

The latest residue diagnostics show:

- `guided_seed` fails on all four hard residue cases
- DFS starts without an incumbent on all four
- the dominant construct failure reason is `deadline`, not invalid schedule generation

That means the next valuable solver work is not another broad refactor. It is improving the no-incumbent path in [construct.py](rcpsp/cp/construct.py) and [guided_seed.py](rcpsp/cp/guided_seed.py).

## Evaluation Workflow

The active validation workflow is now CP-first:

1. `uv run python scripts/run_cp_residue.py`
2. `uv run python scripts/run_guardrails.py --preset submission_quick`
3. `uv run python scripts/run_guardrails.py --preset broad_generalization`
4. `uv run python scripts/run_guardrails.py --preset cp_acceptance`
5. `uv run python scripts/run_guardrails.py --preset submission`

Interpretation:

- `submission_quick`
  - fast screen for regressions on the main public families
- `broad_generalization`
  - anti-overfitting check on held-out Kobe public sets
- `cp_acceptance`
  - public `30s` matrix for submission-facing quality
- `submission`
  - combined final readiness screen

## What We Are Not Claiming

This solver is not:

- a full lazy-clause-generation engine
- a full timetable-edge-finding implementation
- a general-purpose CP platform
- guaranteed to solve every hidden instance optimally

That is acceptable for the project. The brief asks for a thoughtful solver under tight runtime and tooling constraints, not a full external-solver replacement.

## Recommended Next Work

The next technical step should be narrow and CP-native:

- improve first-incumbent generation in [construct.py](rcpsp/cp/construct.py)
- improve seed-budget usage in [guided_seed.py](rcpsp/cp/guided_seed.py)
- keep heavy changes gated away from the `0.1s` fast path unless they clearly survive `submission_quick`

The most likely payoff is on the remaining `ubo50` residue cases and on reducing short-budget unknown counts, not on broad architecture changes.

## Final Read

For this project, the current `cp` backend is a reasonable and defensible final direction. It is small enough to explain clearly, strong enough to be competitive on the public `30s` matrix, and structured enough to improve further without turning into an unbounded solver-engine project.
