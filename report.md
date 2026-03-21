# Autoresearch Setup Report

## Summary

I set up an RCPSP-specific adaptation of Karpathy's `autoresearch` workflow in this repo instead of trying to use the upstream code unchanged.

Completed setup:

- cloned the upstream repo to `references/autoresearch-upstream` for local reference
- added a repo-local `program.md` that defines the RCPSP research loop
- added `scripts/run_autoresearch_eval.py` and `scripts/autoresearch_lib.py`
- added `scripts/fetch_reference_csvs.py`
- added `research_quick` and `research` presets to the guardrail runner
- changed `rcpsp/reference.py` to prefer local `benchmarks/data/<dataset>/optimum/optimum.csv`
- cached the missing public exact-reference files for `sm_j10` and `sm_j20` under `benchmarks/data`
- added `tests/test_autoresearch_lib.py`

Verification:

- `uv run python -m pytest -q tests/test_autoresearch_lib.py`
  - result: `2 passed`

## Why The Upstream Repo Needed Adapting

The upstream `autoresearch` repo is built around:

- a single editable file
- a fixed 5-minute training run
- one scalar metric, `val_bpb`

This RCPSP project is different:

- the editable surface spans multiple solver modules
- evaluation is over benchmark suites, not one training script
- the true objective is hidden-instance makespan quality under a hard validity and time-budget constraint
- the internal proxies are exact-match rate, ratio to reference, unknown counts, and false infeasible counts

So the right adaptation was to keep the RCPSP solver intact and build an autoresearch-style evaluation harness around the existing `benchmark` and `compare` commands.

## Current Clean Baseline Against The Metrics

These numbers come from the repo's saved `*_current_clean_*.json` benchmark artifacts, re-compared locally using the now-cached reference CSVs.

| Dataset / Budget | Exact Match Rate | Avg Exact Ratio | Unknowns | False Infeasible | Target Status |
| --- | ---: | ---: | ---: | ---: | --- |
| `sm_j10 @ 1.0s` | `187/187 = 100.0%` | `1.0000` | `0` | `0` | meets target |
| `sm_j20 @ 1.0s` | `120/158 = 75.9%` | `1.0210` | `7` | `0` | misses target |
| `sm_j30 @ 0.1s` | `66/120 = 55.0%` | `1.0305` | `21` | `0` | misses target |
| `testset_ubo20 @ 0.1s` | `45/66 = 68.2%` | `1.0154` | `1` | `0` | narrowly misses target |
| `testset_ubo50 @ 0.1s` | `13/33 = 39.4%` | `1.0209` | `25` | `0` | misses target |

Main takeaway:

- the repo is already very strong on `sm_j10`
- the main remaining gap is still `sm_j20 @ 1.0s`
- the broader guardrails, especially `sm_j30` and `testset_ubo50`, are still below the optimistic targets from `METRICS.md`
- correctness is good: every measured baseline had `false_infeasible = 0`

## Fresh Experiments

I ran fresh end-to-end experiments using the new autoresearch harness.

### 1. `hybrid` quick baseline

Command:

```bash
python scripts/run_autoresearch_eval.py --backend hybrid --preset research_quick --output-dir tmp/guardrails/autoresearch-quick-baseline
```

Result highlights:

- `sm_j10 @ 0.1s`: exact-match `94.7%`
- `sm_j20 @ 0.1s`: exact-match `57.0%`
- `sm_j30 @ 0.1s`: exact-match `51.7%`, unknown `66`
- `testset_ubo20 @ 0.1s`: exact-match `71.2%`, unknown `4`
- `testset_ubo50 @ 0.1s`: exact-match `9.1%`, unknown `67`
- score: `-173.97`

Finding:

- this fresh short-budget run is materially worse than the saved `current_clean` artifacts, especially on `sm_j20`, `sm_j30`, and `testset_ubo50`
- short-budget RCPSP results are highly sensitive to wall-clock behavior and should not be judged from a single run

### 2. `hybrid` medium baseline

Command:

```bash
python scripts/run_autoresearch_eval.py --backend hybrid --preset medium --output-dir tmp/guardrails/autoresearch-medium-hybrid
```

Result highlights:

- `sm_j10 @ 1.0s`: exact-match `186/187 = 99.5%`
- `sm_j20 @ 1.0s`: exact-match `113/158 = 71.5%`
- `sm_j20 @ 1.0s`: avg exact ratio `1.0299`
- `sm_j20 @ 1.0s`: unknown `12`
- score: `70.50`

Finding:

- this run is directionally strong but still below the `METRICS.md` target on all three key `sm_j20 @ 1.0s` dimensions:
  - exact-match rate
  - average exact ratio
  - unknown count

### 3. `cp` medium baseline

Command:

```bash
python scripts/run_autoresearch_eval.py --backend cp --preset medium --output-dir tmp/guardrails/autoresearch-medium-cp
```

Result highlights:

- `sm_j10 @ 1.0s`: exact-match `185/187 = 98.9%`
- `sm_j20 @ 1.0s`: exact-match `116/158 = 73.4%`
- `sm_j20 @ 1.0s`: avg exact ratio `1.0225`
- `sm_j20 @ 1.0s`: unknown `22`
- score: `-15.12`

Finding:

- `cp` produced slightly better `sm_j20` quality than `hybrid` on:
  - exact-match rate
  - average exact ratio
- but it paid for that with much worse coverage:
  - `unknown 22` vs `12` for `hybrid`
- under the current scoring logic, `hybrid` is still the better default backend because the unknown-count penalty dominates

## Continued Experiments: Focused `sm_j20 @ 1.0s` Seed Sweep

Because `sm_j20 @ 1.0s` is still the decisive bottleneck, I ran a narrower follow-up sweep there instead of spending more time on the already-solved `sm_j10` side.

| Backend / Seed | Exact Match Rate | Avg Exact Ratio | Unknowns | Avg Runtime | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `hybrid seed=0` | `112/158 = 70.9%` | `1.0280` | `12` | `0.646s` | focused rerun |
| `hybrid seed=1` | `112/158 = 70.9%` | `1.0279` | `12` | `4.185s` | runtime instability |
| `cp seed=0` | `116/158 = 73.4%` | `1.0225` | `22` | `0.505s` | from medium baseline |
| `cp seed=1` | `115/158 = 72.8%` | `1.0215` | `23` | `0.514s` | focused rerun |

### What changed relative to the earlier report

- the nominally identical `hybrid` medium configuration is not fully reproducible:
  - earlier full-medium run: `113/158` exact on `sm_j20`
  - focused rerun with the same backend and budget: `112/158` exact
- `cp` remains more consistent on quality:
  - `seed=0`: `73.4%` exact, `1.0225` average exact ratio
  - `seed=1`: `72.8%` exact, `1.0215` average exact ratio
- neither backend is close to the optimistic `sm_j20 @ 1.0s` target in `METRICS.md`

### New runtime finding: `hybrid` has a compliance risk

The `hybrid seed=1` benchmark finished with almost the same `sm_j20` quality as `seed=0`, but its runtime profile was much worse:

- average runtime rose from `0.646s` to `4.185s`
- `166/270` instances recorded runtime above `1.0s`
- one instance, `PSP48`, reported `955.584s`

That outlier is especially important because it did **not** buy a meaningful quality gain:

- `PSP48` at `seed=0`: feasible, makespan `53`, runtime about `1.00s`
- `PSP48` at `seed=1`: feasible, makespan `55`, runtime about `955.58s`

Interpretation:

- the solver or timing logic has a real wall-clock stability problem under some stochastic paths
- this matters directly for the project, because the brief treats the time budget as a hard scoring constraint
- quality alone is not enough; runtime-compliance needs to become an explicit guardrail

## Cross-Experiment Findings

### 1. The setup is now usable

The repo can now be used in an autoresearch-style loop with:

- local references for all benchmark families in scope
- a repeatable evaluator
- a program file that tells an agent what to optimize

### 2. `sm_j20 @ 1.0s` remains the main bottleneck

The optimistic target was:

- exact-match rate `>= 85%`
- avg exact ratio `<= 1.015`
- unknown count `<= 2`

The current clean baseline is still short on all three:

- `75.9%`
- `1.0210`
- `7 unknown`

Fresh medium runs were worse than the saved baseline.

The continuation experiments add one more important refinement:

- the quality gap is real, but so is a reproducibility and runtime-stability gap
- for `hybrid`, repeated runs can shift exact-match count slightly and can also produce pathological runtime outliers
- for `cp`, quality is steadier but unknown counts remain too high

### 3. `cp` has useful ideas but is not yet the submission default

Observed pattern:

- `cp` tends to improve `sm_j20` solution quality among the cases it solves
- `hybrid` still wins on the more important coverage profile

That suggests the next useful research direction is:

- borrow or port quality-improving ideas from `cp`
- but keep the `hybrid` backend as the default until unknown counts come down

### 4. Short-budget results are noisy

The saved `current_clean` quick artifacts were noticeably stronger than the fresh quick rerun. This is likely due to anytime behavior under tight wall-clock budgets.

Practical consequence:

- autoresearch should not keep or discard ideas based on one quick run alone
- quick runs should be treated as screens, not final truth
- medium runs on `sm_j10` and `sm_j20` should be the main keep/discard gate

The follow-up `sm_j20` seed sweep shows that some of this instability is not limited to `0.1s` runs:

- even at `1.0s`, repeated `hybrid` runs are not perfectly stable
- runtime compliance needs to be monitored separately from quality

## Recommended Next Experiments

1. Keep `hybrid` as the default optimization target.
2. Use `research_quick` only as a fast reject screen.
3. Use `medium` as the main acceptance gate for changes.
4. Target `sm_j20 @ 1.0s` unknown reduction first, because the `cp` experiments show quality gains are not enough if coverage regresses.
5. Add an explicit runtime guardrail, at minimum:
   - no instance should exceed the intended wall-clock budget by a large factor
   - investigate `hybrid` long-tail runtime behavior around cases like `PSP48`
6. Focus on `cp` ideas that improve incumbent quality without deepening search too much.
7. Re-run promising wins at least twice before keeping them, even at `1.0s`, because the medium-budget runs also showed drift.

## Follow-Up Experiment: Targeted Adaptive LNS

I implemented a bounded adaptive-LNS variant in the improvement phase instead of applying more blind weight tuning.

Design:

- keep the existing small-instance improvement path unchanged in spirit
- add adaptive destroy/repair operator weighting only for larger instances (`n_jobs >= 30`)
- use bandit-style weighted selection with reward updates based on:
  - finding any valid repaired candidate
  - improving the chosen base solution
  - improving the current global best solution
- preserve the old fast path for smaller instances because tight `1s` budgets are sensitive to even small inner-loop overheads

Regression tests added:

- reward scoring prefers global improvements over neutral or failed repairs
- adaptive operator selection shifts toward historically successful operators
- bottleneck-pair repair plans retain operator identity

Validation:

```bash
uv run python -m pytest -q tests/test_improve.py tests/test_runtime_limits.py tests/test_lag_tightening.py tests/test_cp_search.py tests/test_sgs_backend.py tests/test_autoresearch_lib.py
```

- result: `18 passed`

### Measured results against the current recorded baseline

| Dataset / Budget | Recorded Baseline | Adaptive-LNS Variant | Interpretation |
| --- | --- | --- | --- |
| `sm_j20 @ 1s` | `125/158`, ratio `1.0193`, unknown `0` | `122/158`, ratio `1.0198`, unknown `0` | worse at tight budget |
| `sm_j20 @ 5s` | `128/158`, ratio `1.0147`, unknown `0` | `130/158`, ratio `1.0133`, unknown `0` | better practical-budget quality |
| `sm_j30 @ 1s` | `85/120`, ratio `1.0187`, unknown `9`, over-budget `1` | `88/120`, ratio `1.0187`, unknown `6`, over-budget `0` | better larger-instance anytime behavior |
| `sm_j30 @ 5s` | `93/120`, ratio `1.0142`, unknown `3` | `93/120`, ratio `1.0147`, unknown `3` | neutral on exact match |
| `testset_ubo50 @ 1s` | `26/33`, ratio `1.0091`, unknown `5` | `26/33`, ratio `1.0083`, unknown `5` | neutral exact, slightly better ratio |
| `testset_ubo50 @ 5s` | `27/33`, ratio `1.0141`, unknown `3` | `27/33`, ratio `1.0115`, unknown `2` | same exact, better quality/coverage |

### Decision

This change should be kept, but with a narrow claim:

- it is **not** a clear improvement for the `1s` `sm_j20` speed/accuracy point
- it **is** a credible improvement for the more practical `5s` budget and for larger-instance behavior
- it reduces over-budget behavior on `sm_j30 @ 1s`
- it improves or holds quality on `sm_j30` and `testset_ubo50` without using any external optimization library

So the project recommendation remains:

- keep `1s` as the best pure speed/accuracy operating point from the older recorded sweep
- use `5s` as the practical report recommendation
- keep the new targeted adaptive-LNS branch because it is more aligned with the project's larger-instance generalization needs than another round of static parameter tuning

## Rejected Experiment: Elite Path Relinking

I also implemented an elite path-relinking variant inside the large-instance improvement loop. The design used the current elite pool to choose a guide schedule, then removed activities with large order displacement and tried to repair them toward the guide order.

That version was **rejected** and reverted.

Measured results versus the kept adaptive-LNS baseline:

| Dataset / Budget | Kept Adaptive-LNS Baseline | Path-Relinking Variant | Interpretation |
| --- | --- | --- | --- |
| `sm_j30 @ 1s` | `88/120`, ratio `1.0187`, unknown `6`, over-budget `0` | `85/120`, ratio `1.0197`, unknown `8`, over-budget `1` | worse |
| `sm_j30 @ 5s` | `93/120`, ratio `1.0147`, unknown `3` | `93/120`, ratio `1.0150`, unknown `3` | flat exact, slightly worse quality |
| `testset_ubo50 @ 1s` | `26/33`, ratio `1.0083`, unknown `5` | `26/33`, ratio `1.0109`, unknown `5` | same exact, worse quality |
| `testset_ubo50 @ 5s` | `27/33`, ratio `1.0115`, unknown `2` | `27/33`, ratio `1.0118`, unknown `2` | same exact, slightly worse quality |

Finding:

- the relinking implementation added complexity but did not improve the practical metrics
- on `sm_j30 @ 1s` it regressed exact match, unknown count, and deadline compliance
- on `5s` runs it was mostly neutral on exact match and slightly worse on quality ratio

Conclusion:

- keep the simpler targeted adaptive-LNS version
- do not include this relinking variant in the main solver story
- if path relinking is revisited later, it likely needs a stronger activity-list representation rather than the current schedule-repair approximation

## Rejected Experiment: Restricted Exact Neighborhoods

I also implemented a restricted exact-neighborhood phase between improvement and the existing global exact cleanup. The idea was:

- pick a bottleneck-focused neighborhood from the incumbent schedule
- freeze incumbent resource-order edges outside that neighborhood
- spend a bounded time slice on branch-and-bound over the reopened local neighborhood

That version was also **rejected** and reverted.

Measured results versus the kept adaptive-LNS baseline:

| Dataset / Budget | Kept Adaptive-LNS Baseline | Exact-Neighborhood Variant | Interpretation |
| --- | --- | --- | --- |
| `sm_j20 @ 1s` | `122/158`, ratio `1.0198`, unknown `0`, over-budget `0` | `118/158`, ratio `1.0230`, unknown `1`, over-budget `1` | clearly worse |
| `sm_j20 @ 5s` | `130/158`, ratio `1.0133`, unknown `0` | `128/158`, ratio `1.0128`, unknown `0` | worse exact match despite slightly better ratio |
| `sm_j30 @ 5s` | `93/120`, ratio `1.0147`, unknown `3` | `93/120`, ratio `1.0143`, unknown `3` | flat exact, tiny ratio improvement |
| `testset_ubo50 @ 5s` | `27/33`, ratio `1.0115`, unknown `2` | `27/33`, ratio `1.0106`, unknown `2` | flat exact, tiny ratio improvement |

Finding:

- the local exact-neighborhood idea did not pay off on the main `sm_j20` target
- it introduced deadline risk at `1s`
- on larger `5s` runs it only improved the average ratio slightly, without improving exact-match counts

Conclusion:

- do not keep this phase in the production solver
- the current global exact cleanup is already good enough relative to the extra complexity here
- if neighborhood exact search is revisited later, it should likely be tied to a stronger activity-list representation or a more selective neighborhood trigger

## Useful Outputs

Main evaluation files produced during this setup:

- `tmp/guardrails/autoresearch-quick-baseline/autoresearch_eval.json`
- `tmp/guardrails/autoresearch-medium-hybrid/autoresearch_eval.json`
- `tmp/guardrails/autoresearch-medium-cp/autoresearch_eval.json`
- `tmp/guardrails/seed-sweep-sm_j20/hybrid-seed0/autoresearch_eval.json`

Reference comparison outputs:

- `tmp/autoresearch-report/sm_j10_0p1_compare.json`
- `tmp/autoresearch-report/sm_j10_1p0_compare.json`
- `tmp/autoresearch-report/sm_j20_0p1_compare.json`
- `tmp/autoresearch-report/sm_j20_1p0_compare.json`
- `tmp/autoresearch-report/sm_j30_0p1_compare.json`
- `tmp/autoresearch-report/testset_ubo20_0p1_compare.json`
- `tmp/adaptive-alns-fastpath-j20/summary.json`
- `tmp/adaptive-alns-fastpath-j20-5s/summary.json`
- `tmp/adaptive-alns-fastpath-j30/summary.json`
- `tmp/adaptive-alns-fastpath-j30-5s/summary.json`
- `tmp/adaptive-alns-ubo50/summary.json`
- `tmp/path-relink-sm_j30/summary.json`
- `tmp/path-relink-ubo50/summary.json`
- `tmp/exact-neighborhood-sm_j20/summary.json`
- `tmp/exact-neighborhood-sm_j30/summary.json`
- `tmp/exact-neighborhood-ubo50/summary.json`
- `tmp/autoresearch-report/testset_ubo50_0p1_compare.json`
- `tmp/guardrails/seed-sweep-sm_j20/hybrid-seed1-compare.json`
- `tmp/guardrails/seed-sweep-sm_j20/cp-seed1-compare.json`

## Broad-Generalization Autoresearch Continuation

To reduce overfitting risk, I expanded the autoresearch objective beyond the course-facing sets and scored candidates against:

- `sm_j20 @ 1.0s` as the main course-quality target
- `testset_ubo10 @ 0.1s`
- `testset_ubo100 @ 0.1s`
- `testset_ubo200 @ 0.1s`

The search objective was updated to penalize:

- `unknown`
- `unknown_against_known_reference`
- `over_budget`
- average runtime blowups relative to the time budget

That means a configuration can no longer win purely by improving `sm_j20` if it collapses on broader public sets.

### Broader baseline before search

Current default `hybrid` behavior on the broader public sets is highly uneven:

| Dataset / Budget | Exact Match Rate | Unknowns | Over Budget | Avg Runtime |
| --- | ---: | ---: | ---: | ---: |
| `testset_ubo10 @ 0.1s` | `71/73 = 97.3%` | `0` | `0` | `0.035s` |
| `testset_ubo100 @ 0.1s` | `0/24 = 0.0%` | `81` | `54` | `0.127s` |
| `testset_ubo200 @ 0.1s` | `0/25 = 0.0%` | `90` | `90` | `0.962s` |

Interpretation:

- the solver is still strong on small public instances
- it does not currently scale to the larger public RCPSP/max families under the `0.1s` budget
- this is exactly the kind of failure mode that narrow benchmark tuning would hide

### Broad search run

Run:

```bash
python scripts/run_autoresearch_search.py --backend hybrid --trials 4 --seed 21 --main-preset medium --main-datasets sm_j20 --aux-preset broad_generalization --aux-datasets testset_ubo10 testset_ubo100 testset_ubo200 --output-dir tmp/autoresearch-search/run-20260321-broad
```

The original shell session disconnected before all trials were aggregated, so I resumed the missing trials manually with the same deterministic configurations. Final summary is now saved in:

- `tmp/autoresearch-search/run-20260321-broad/search_summary.json`

### Best broad-objective candidate

Best trial: `trial 03`

Config:

- `slack_weight=2.867`
- `tail_weight=1.228`
- `overload_weight=2.961`
- `resource_weight=0.308`
- `late_weight=0.516`
- `noise_weight=0.178`
- `max_restarts=4`

Main result on `sm_j20 @ 1.0s`:

- exact-match `125/158 = 79.1%`
- avg exact ratio `1.0179`
- unknown `0`
- over-budget `0`

This is meaningfully better than the recent safe default on `sm_j20`:

- exact-match improved from `73.4%` to `79.1%`
- avg exact ratio improved from `1.0238` to `1.0179`
- unknown stayed at `0`
- over-budget stayed at `0`

But it still fails the optimistic `METRICS.md` target:

- exact-match is still below `85%`
- avg exact ratio is still above `1.015`

### Why the candidate is still rejected

Even the best trial still fails the anti-overfitting objective badly:

| Dataset / Budget | Exact Match Rate | Unknowns | Over Budget |
| --- | ---: | ---: | ---: |
| `testset_ubo10 @ 0.1s` | `72/73 = 98.6%` | `0` | `0` |
| `testset_ubo100 @ 0.1s` | `0/24 = 0.0%` | `80` | `55` |
| `testset_ubo200 @ 0.1s` | `0/25 = 0.0%` | `90` | `90` |

So the search found a stronger `sm_j20` parameter setting, but not a configuration that generalizes across broader RCPSP/max families.

### Finding

The broader search answered an important question:

- parameter tuning still has headroom on `sm_j20`
- but parameter tuning alone is not enough to address broader-instance behavior

That means the next high-value work is structural, not another blind weight sweep.

### Updated acceptance policy

Going forward, a candidate should only be kept if it satisfies both:

1. improves or preserves the current `sm_j20 @ 1.0s` safe baseline
2. does not worsen `testset_ubo10`, `testset_ubo100`, or `testset_ubo200`

In practice that means:

- no new `over_budget` regressions on the course-facing sets
- no broad-set collapse hidden behind a better `sm_j20` score
- treat `broad_generalization` as a mandatory sidecar check, not an optional smoke test

### Recommended next move after this search

Do not spend the next loop on more heuristic-weight search.

The solver now needs a structural change that helps larger public RCPSP/max instances under tight budgets, likely one of:

- better early infeasibility / forced-order propagation before expensive search
- tighter bounded improvement loops for large-instance cases
- instance-size-aware fallback behavior so large public sets degrade gracefully instead of turning into mass `unknown`

Useful artifacts from this continuation:

- `tmp/guardrails/broad-generalization-baseline-current/summary.json`
- `tmp/autoresearch-search/run-20260321-broad/search_summary.json`
- `tmp/autoresearch-search/run-20260321-broad/trial_03/search_result.json`

## Budget Sweep And Speed/Accuracy Recommendation

I ran the current best `hybrid` configuration from the broad search across larger time budgets on `sm_j20`:

- `max_restarts=4`
- `slack_weight=2.867`
- `tail_weight=1.228`
- `overload_weight=2.961`
- `resource_weight=0.308`
- `late_weight=0.516`
- `noise_weight=0.178`

Completed budgets:

| Budget | Exact Match | Avg Exact Ratio | Unknown | Over Budget | Avg Runtime | Accuracy / Avg Runtime |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `1s` | `125/158 = 79.1%` | `1.0193` | `0` | `0` | `0.541s` | `1.4626` |
| `2s` | `126/158 = 79.7%` | `1.0194` | `0` | `0` | `1.086s` | `0.7344` |
| `5s` | `128/158 = 81.0%` | `1.0147` | `0` | `0` | `2.678s` | `0.3025` |
| `10s` | `133/158 = 84.2%` | `1.0146` | `0` | `0` | `5.250s` | `0.1603` |

### Interpretation

There are three different winners depending on what is being optimized:

- best **pure speed/accuracy ratio**: `1s`
- best **absolute completed quality**: `10s`
- best **practical trade-off**: `5s`

Why `5s` is the best practical trade-off:

- it improves exact-match quality over `1s` and `2s`
- it already reduces `avg_exact_ratio_to_reference` below the optimistic `1.015` target
- it keeps `unknown = 0` and `over_budget = 0`
- it is much cheaper than `10s` while only giving up `5` exact matches

For the report, I would present:

1. `1s` as the best **efficiency operating point**
2. `5s` as the recommended **submission-time operating point**
3. `10s` as the best **quality-focused completed budget**

### Extra experiments after the sweep

I continued with two additional experiments to see if the time/accuracy ratio could be improved further.

#### 1. Restart-count tuning at `1s`

I tested the same configuration with different restart caps:

| `max_restarts` | Exact Match | Unknown | Over Budget | Avg Runtime | Accuracy / Avg Runtime |
| --- | ---: | ---: | ---: | ---: | ---: |
| `2` | `118/157 = 74.7%` | `1` | `1` | `0.552s` | `1.3535` |
| `4` | `125/158 = 79.1%` | `0` | `0` | `0.541s` | `1.4626` |
| `8` | `121/157 = 76.6%` | `1` | `1` | `0.552s` | `1.3881` |

Finding:

- `max_restarts=4` remains the best choice
- both lower and higher restart caps were worse on the main speed/accuracy objective

#### 2. Double-justification structural experiment

I also implemented and tested a solver-native double-justification pass inspired by common RCPSP heuristic methods.

Result:

- it hurt `1s`
- it did not improve `2s`
- it was effectively neutral at `5s`

I reverted that change, so the codebase stays on the stronger baseline.

### Recommendation

If the report needs one sentence:

- **Best pure time/accuracy ratio:** `hybrid` at `1s`
- **Best practical budget to recommend:** `hybrid` at `5s`

Useful artifacts for this section:

- `tmp/time-sweep/speed_accuracy_summary.json`
- `tmp/time-sweep/sm_j20_10s_hybrid_compare.json`
- `tmp/time-ratio-tuning/r2/summary.json`
- `tmp/time-ratio-tuning/r8/summary.json`

## Other Datasets At `1s` And `5s`

I reran the tuned `hybrid` configuration on the remaining benchmark datasets under `benchmarks/data` so the report has one consistent set of measurements:

- `max_restarts=4`
- `slack_weight=2.867`
- `tail_weight=1.228`
- `overload_weight=2.961`
- `resource_weight=0.308`
- `late_weight=0.516`
- `noise_weight=0.178`

| Dataset | Budget | Exact Match | Avg Exact Ratio | Unknown | Over Budget | Avg Runtime |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `sm_j10` | `1s` | `186/187 = 99.5%` | `1.0005` | `0` | `0` | `0.482s` |
| `sm_j10` | `5s` | `187/187 = 100.0%` | `1.0000` | `0` | `0` | `2.397s` |
| `sm_j30` | `1s` | `85/116 = 70.8%` | `1.0187` | `9` | `1` | `0.537s` |
| `sm_j30` | `5s` | `93/120 = 77.5%` | `1.0142` | `3` | `0` | `2.624s` |
| `testset_ubo20` | `1s` | `59/66 = 89.4%` | `1.0086` | `0` | `0` | `0.530s` |
| `testset_ubo20` | `5s` | `62/66 = 93.9%` | `1.0060` | `0` | `0` | `2.599s` |
| `testset_ubo50` | `1s` | `26/32 = 78.8%` | `1.0091` | `5` | `0` | `0.674s` |
| `testset_ubo50` | `5s` | `27/32 = 81.8%` | `1.0141` | `3` | `0` | `3.284s` |

### What this means

The pattern is consistent with the `sm_j20` budget sweep:

- `1s` is the better pure efficiency point
- `5s` is the safer quality-oriented operating point

Dataset-specific takeaways:

- `sm_j10` is already solved well at `1s`; `5s` gives no practical benefit
- `sm_j30` benefits materially from `5s`, with better exact-match rate, lower unknowns, and no over-budget cases
- `testset_ubo20` is strong at both budgets; `5s` gives a modest quality lift
- `testset_ubo50` also benefits from `5s`, mainly by reducing unknowns

### Final recommendation after these runs

If the report needs one single operating point for the tuned `hybrid` solver:

- use **`5s`** as the practical recommendation

Reason:

- it is not the best pure accuracy-per-second point, but it is the best cross-dataset trade-off
- it meaningfully helps the harder datasets (`sm_j30`, `testset_ubo50`)
- it keeps `unknown` and `over_budget` under better control
- it is still comfortably below the project’s `30s` hard limit

Useful artifacts:

- `tmp/other-dataset-sweeps/combined_summary.json`
- `tmp/other-dataset-sweeps/sm_j10/summary.json`
- `tmp/other-dataset-sweeps/sm_j30/summary.json`
- `tmp/other-dataset-sweeps/testset_ubo20/summary.json`
- `tmp/other-dataset-sweeps/testset_ubo50/summary.json`
