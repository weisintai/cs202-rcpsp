# RCPSP/max Iteration Notes

Last updated: 2026-03-17

## Project goal

Build a solver for the scheduling instances in this folder that:

- reads one `.SCH` instance
- respects all temporal lag constraints
- respects renewable resource capacities
- returns a valid schedule quickly
- minimizes project makespan as much as possible within the time budget

The provided instances behave like `RCPSP/max`, not only plain DAG precedence scheduling, because the `.SCH` files include positive and negative lags.

## Current code structure

- [main.py](main.py)
  - CLI for `solve` and `benchmark`
- [rcpsp/parser.py](rcpsp/parser.py)
  - parses ProGenMax `.SCH` files
- [rcpsp/temporal.py](rcpsp/temporal.py)
  - longest-path style propagation for lag constraints
- [rcpsp/validate.py](rcpsp/validate.py)
  - validates temporal and resource feasibility
- [rcpsp/solver.py](rcpsp/solver.py)
  - incumbent heuristic
  - pairwise infeasibility screening
  - conflict-set branch-and-bound

## What has been implemented

### 1. Parser and model

Implemented a parser for the benchmark `.SCH` format:

- header with number of jobs and resources
- successor and lag rows
- duration and resource-demand rows
- resource capacities

This is now handled in [rcpsp/parser.py](rcpsp/parser.py).

### 2. Temporal propagation

Implemented lag-based feasibility propagation using longest-path relaxation:

- computes earliest feasible start times under temporal constraints alone
- gives a temporal lower bound on the sink start time
- detects temporal inconsistency if lag cycles are impossible

This is in [rcpsp/temporal.py](rcpsp/temporal.py).

### 3. Validator

Implemented schedule validation:

- checks `S_j >= S_i + lag` for every edge
- builds a time-indexed resource profile
- verifies renewable capacity feasibility at every time unit

This is in [rcpsp/validate.py](rcpsp/validate.py).

### 4. Heuristic constructor

Implemented a fast incumbent builder:

- starts from temporal earliest starts
- repairs resource conflicts by adding disjunctive ordering constraints
- left-shifts the final schedule to compress idle time
- now uses a size-adaptive repair policy:
  - smaller instances keep the original broad first-conflict incremental repair
  - larger instances use a tighter minimal-conflict repair and test both order directions

Relevant code:

- [rcpsp/solver.py](rcpsp/solver.py)

### 5. Pairwise infeasibility screening

Implemented a lightweight infeasibility screen:

- computes all-pairs longest lag implications
- detects cases where two activities are forced to overlap
- if their combined resource demand exceeds a capacity, marks the instance as infeasible

Relevant code:

- [rcpsp/solver.py](rcpsp/solver.py)

### 6. Conflict-set branch-and-bound

Replaced the weak fallback search with a stronger exact-style search:

- find the earliest overloaded resource conflict
- shrink it to a minimal conflict set
- branch by forcing one activity to be last in that set
- propagate those disjunctive decisions as extra temporal edges
- prune with the current incumbent makespan

Relevant code:

- [rcpsp/solver.py](rcpsp/solver.py)

### 7. uv project setup

Added a minimal `uv`-based project setup:

- [pyproject.toml](pyproject.toml)
- usage examples in [README.md](README.md)

## Benchmark commands used

Solve one instance:

```bash
uv run main.py solve sm_j10/PSP1.SCH --time-limit 0.2 --json
```

Benchmark a whole folder:

```bash
uv run main.py benchmark sm_j10 --time-limit 0.1 --output sm_j10_results_bnb_0p1.json
uv run main.py benchmark sm_j20 --time-limit 0.1 --output sm_j20_results_bnb_0p1.json
```

## Kept benchmark files

The repo now keeps only the current clean reference outputs. Intermediate experiment dumps are generated as needed and ignored by git.

Current clean reference outputs:

- [sm_j10_results_current_clean_0p1.json](sm_j10_results_current_clean_0p1.json)
- [sm_j20_results_current_clean_0p1.json](sm_j20_results_current_clean_0p1.json)
- [sm_j10_results_current_clean_1p0.json](sm_j10_results_current_clean_1p0.json)
- [sm_j20_results_current_clean_1p0.json](sm_j20_results_current_clean_1p0.json)

## Findings so far

### Dataset reality

- The project brief is simpler than the actual data.
- The data appears to be `RCPSP/max` with general lag constraints.
- Some instances appear to be infeasible under the current lag interpretation.

Example:

- [sm_j20/PSP1.SCH](sm_j20/PSP1.SCH) is classified as infeasible because activities `2` and `17` are forced to overlap and exceed one resource capacity together.

### Baseline before conflict-set branch-and-bound

At `0.1s` per instance:

- `sm_j10`
  - feasible: `145`
  - infeasible: `77`
  - unknown: `48`
  - avg ratio: `1.3772`
- `sm_j20`
  - feasible: `127`
  - infeasible: `67`
  - unknown: `76`
  - avg ratio: `1.3241`

### After conflict-set branch-and-bound

At `0.1s` per instance:

- `sm_j10`
  - feasible: `186`
  - infeasible: `77`
  - unknown: `7`
  - avg ratio: `1.3370`
- `sm_j20`
  - feasible: `177`
  - infeasible: `67`
  - unknown: `26`
  - avg ratio: `1.2998`

### Net improvement

- `sm_j10`
  - newly feasible: `41`
  - unknown reduced by `41`
  - average ratio improved
- `sm_j20`
  - newly feasible: `50`
  - unknown reduced by `50`
  - average ratio improved

### Example recovered instance

- [sm_j10/PSP102.SCH](sm_j10/PSP102.SCH)
  - previously `unknown`
  - now `feasible`
  - makespan `52`
  - temporal lower bound `35`

### Follow-up iteration: conditional pairwise pruning plus exact exhaustion classification

Added one more targeted change after inspecting representative unknown instances:

- if exact search finishes without timeout and still finds no feasible schedule, classify the instance as `infeasible`
- run the pairwise forced-overlap prune inside branch-and-bound only while there is no incumbent yet

Motivation:

- `sm_j10/PSP125.SCH` exhausted exact search in a small number of nodes, so it should not stay `unknown`
- `sm_j20/PSP127.SCH` timed out in the exact search, but node-level pairwise pruning reduced explored nodes substantially

Representative measurements:

- `sm_j10/PSP125.SCH`
  - before: `unknown`, `57` exact-search nodes
  - after: `infeasible`, `21` exact-search nodes
- `sm_j20/PSP127.SCH`
  - before: `11,294` nodes at `1s`
  - after: `3,934` nodes at `1s`

At `0.1s` per instance after this conditional prune:

- `sm_j10`
  - feasible: `186`
  - infeasible: `84`
  - unknown: `0`
  - avg ratio: `1.3370`
- `sm_j20`
  - feasible: `178`
  - infeasible: `77`
  - unknown: `15`
  - avg ratio: `1.3048`

Net effect relative to the previous branch-and-bound version:

- `sm_j10`
  - all `7` remaining unknowns moved to `infeasible`
  - no regression on existing feasible instances
- `sm_j20`
  - `11` status changes total
  - `10` unknown instances resolved
  - `1` unknown instance became feasible
  - no regression on existing feasible-instance ratios

### Follow-up iteration: size-adaptive conflict repair

Inspected the remaining hard `J20` cases and tried a branch-guided completion heuristic inside exact search, but it reduced node throughput too much under the `0.1s` budget, so it was not kept.

The accepted change was instead in the incumbent constructor:

- smaller instances keep the original first-conflict incremental repair
- larger instances switch to minimal-conflict repair
- for those larger instances, the constructor tries both `selected after blockers` and `selected before blockers`

At `0.1s` per instance with this size-adaptive repair:

- `sm_j10`
  - feasible: `186`
  - infeasible: `84`
  - unknown: `0`
  - avg ratio: `1.3370`
- `sm_j20`
  - feasible: `180`
  - infeasible: `75`
  - unknown: `15`
  - avg ratio: `1.3007`

Net effect relative to the current conditional-prune version:

- `sm_j10`
  - no change in counts or average ratio
- `sm_j20`
  - `2` more feasible instances
  - `2` fewer instances marked infeasible
  - average ratio improved from `1.3048` to `1.3007`
  - intersection-only average ratio improved from `1.3048` to `1.3006`

Recovered examples:

- [sm_j20/PSP264.SCH](sm_j20/PSP264.SCH)
  - previously `infeasible` at `0.1s`
  - now `feasible`
  - at `1s`, feasible with makespan `99`
- [sm_j20/PSP269.SCH](sm_j20/PSP269.SCH)
  - previously `infeasible` at `0.1s`
  - now `feasible`
  - at `1s`, feasible with makespan `136`

### Follow-up iteration: incumbent-guided child ordering in exact search

The next accepted change was inside branch-and-bound:

- while no incumbent exists, keep the old feasibility-first DFS branching
- once an incumbent exists, evaluate children cheaply with temporal propagation
- sort those children by their sink lower bound before exploring them

This keeps the short-budget feasibility behavior while improving improvement search quality.

At `0.1s` per instance with this change:

- `sm_j10`
  - feasible: `186`
  - infeasible: `84`
  - unknown: `0`
  - avg ratio: `1.3362`
- `sm_j20`
  - feasible: `180`
  - infeasible: `75`
  - unknown: `15`
  - avg ratio: `1.2964`

Net effect relative to the previous size-adaptive version:

- `sm_j10`
  - same status counts
  - one feasible instance improved: [sm_j10/PSP65.SCH](sm_j10/PSP65.SCH)
  - average ratio improved from `1.3370` to `1.3362`
- `sm_j20`
  - same status counts
  - `11` feasible-instance ratio changes
  - `10` improved and `1` worsened
  - average ratio improved from `1.3007` to `1.2964`

At `1.0s` per instance with the current best solver:

- `sm_j10`
  - feasible: `186`
  - infeasible: `84`
  - unknown: `0`
  - avg ratio: `1.3355`
- `sm_j20`
  - feasible: `184`
  - infeasible: `78`
  - unknown: `8`
  - avg ratio: `1.2966`

From `0.1s` to `1.0s` on `sm_j20`:

- `4` more instances become feasible
- `3` more instances are classified infeasible
- the persistent unknown set drops from `15` to `8`

Remaining unknown `J20` instances at `1.0s`:

- [sm_j20/PSP127.SCH](sm_j20/PSP127.SCH)
- [sm_j20/PSP14.SCH](sm_j20/PSP14.SCH)
- [sm_j20/PSP211.SCH](sm_j20/PSP211.SCH)
- [sm_j20/PSP243.SCH](sm_j20/PSP243.SCH)
- [sm_j20/PSP247.SCH](sm_j20/PSP247.SCH)
- [sm_j20/PSP249.SCH](sm_j20/PSP249.SCH)
- [sm_j20/PSP39.SCH](sm_j20/PSP39.SCH)
- [sm_j20/PSP99.SCH](sm_j20/PSP99.SCH)

### Follow-up iteration: adaptive incremental pairwise propagation

The next accepted change was a search-speed improvement for no-incumbent exact search:

- keep the pairwise infeasibility screen
- replace repeated full all-pairs lag recomputation with incremental lag-closure updates along the DFS
- enable this only for larger time budgets, because the payoff is mainly deeper classification rather than short-budget solution quality

This improves the hard `J20` cases that spend most of their time in no-incumbent exact search.

Current clean benchmark results:

At `0.1s` per instance:

- `sm_j10`
  - feasible: `186`
  - infeasible: `84`
  - unknown: `0`
  - avg ratio: `1.3362`
- `sm_j20`
  - feasible: `180`
  - infeasible: `75`
  - unknown: `15`
  - avg ratio: `1.2989`

At `1.0s` per instance:

- `sm_j10`
  - feasible: `186`
  - infeasible: `84`
  - unknown: `0`
  - avg ratio: `1.3355`
- `sm_j20`
  - feasible: `184`
  - infeasible: `80`
  - unknown: `6`
  - avg ratio: `1.2969`

Net effect relative to the previous incumbent-guided exact-search version at `1.0s` on `sm_j20`:

- same feasible count: `184`
- unknown reduced from `8` to `6`
- two hard instances moved from `unknown` to `infeasible`
  - [sm_j20/PSP247.SCH](sm_j20/PSP247.SCH)
  - [sm_j20/PSP99.SCH](sm_j20/PSP99.SCH)

Remaining unknown `J20` instances at `1.0s` with the current solver:

- [sm_j20/PSP127.SCH](sm_j20/PSP127.SCH)
- [sm_j20/PSP14.SCH](sm_j20/PSP14.SCH)
- [sm_j20/PSP211.SCH](sm_j20/PSP211.SCH)
- [sm_j20/PSP243.SCH](sm_j20/PSP243.SCH)
- [sm_j20/PSP249.SCH](sm_j20/PSP249.SCH)
- [sm_j20/PSP39.SCH](sm_j20/PSP39.SCH)

## Research notes

### What seems strongest for this problem family

The strongest ideas found for `RCPSP/max` are in:

- constraint programming
- lazy clause generation
- conflict-driven branching on resource overloads
- strong propagation with disjunctive decisions

This motivated the current conflict-set branch-and-bound implementation.

## Iteration: Repair + Compress

### What changed

Added a post-processing step for heuristic and exact-search schedules:

1. keep the existing conflict-repair heuristic
2. if the resulting schedule is still invalid, run a repair `left-shift` without the internal disjunctive edge set
3. once a valid schedule exists, derive the implied `resource order` from that schedule
4. recompute the earliest schedule that preserves that resource order

Relevant code is in:

- [rcpsp/solver.py](rcpsp/solver.py)

### Why this was needed

While testing [sm_j10/PSP223.SCH](sm_j10/PSP223.SCH), the old solver labeled the instance `infeasible`, but the repair path produced a valid schedule. That exposed an important limitation:

- the current exact search is a strong feasibility/quality intensifier
- but it is **not** a formal proof procedure for infeasibility
- resource conflicts can also be resolved by `voluntary delay`, not only by the disjunctive branching pattern currently explored

So this iteration improves robustness in exactly the cases where the previous solver could miss a feasible schedule.

### Benchmark summary

Relative to the previous clean baseline:

At `0.1s` per instance:

- `sm_j10`
  - feasible: `186 -> 187`
  - infeasible: `84 -> 83`
  - unknown: `0 -> 0`
  - avg ratio over all feasible: `1.3362 -> 1.3397`
  - avg ratio on common feasible instances only: `1.3362 -> 1.3351`
- `sm_j20`
  - feasible: `180 -> 181`
  - infeasible: `75 -> 75`
  - unknown: `15 -> 14`
  - avg ratio over all feasible: `1.2989 -> 1.2973`
  - avg ratio on common feasible instances only: `1.2989 -> 1.2954`

At `1.0s` per instance:

- `sm_j10`
  - feasible: `186 -> 187`
  - infeasible: `84 -> 83`
  - unknown: `0 -> 0`
  - avg ratio over all feasible: `1.3355 -> 1.3391`
  - avg ratio on common feasible instances only: `1.3355 -> 1.3345`
- `sm_j20`
  - feasible: `184 -> 184`
  - infeasible: `80 -> 80`
  - unknown: `6 -> 6`
  - avg ratio over all feasible: `1.2969 -> 1.2949`
  - avg ratio on common feasible instances only: `1.2969 -> 1.2949`

Concrete instance-level effects:

- [sm_j10/PSP223.SCH](sm_j10/PSP223.SCH) moved from `infeasible` to `feasible` with makespan `92`
- [sm_j10/PSP88.SCH](sm_j10/PSP88.SCH) improved from `48 -> 43`
- [sm_j20/PSP79.SCH](sm_j20/PSP79.SCH) moved from `unknown` to `feasible` with makespan `105`
- [sm_j20/PSP139.SCH](sm_j20/PSP139.SCH) improved from `144 -> 117`

### Longer targeted checks

For the previously unresolved `J20` cases:

- by `5s`, only [sm_j20/PSP127.SCH](sm_j20/PSP127.SCH) and [sm_j20/PSP39.SCH](sm_j20/PSP39.SCH) remained `unknown`
- at `30s`, [sm_j20/PSP127.SCH](sm_j20/PSP127.SCH) became `infeasible`
- at `30s`, [sm_j20/PSP39.SCH](sm_j20/PSP39.SCH) still remained `unknown`

## Reference-driven target

We added a `compare` command against the public `sm_j10` / `sm_j20` reference values.

Current reference comparison at `1.0s` per instance:

- `sm_j10`
  - exact-reference cases: `187`
  - exact matches: `152`
  - exact match rate: `81.3%`
  - average ratio to exact reference: `1.0175`
- `sm_j20`
  - exact-reference cases: `158`
  - exact matches: `91`
  - exact match rate: `57.6%`
  - average ratio to exact reference: `1.0322`
  - bounded cases solved: `26/26`
  - average ratio to best-known upper bound on bounded cases: `1.0697`

Important observation:

- on `sm_j10`, `27/35` misses are only `+1` to `+3`
- on `sm_j20`, `35/67` misses are only `+1` to `+3`

This means the next major gain should come from `incumbent improvement`, not only from stronger classification.

## Iteration: ALNS-style incumbent polishing

### What changed

Added a lightweight incumbent-improvement layer on top of the current solver:

1. start from the best feasible incumbent found by the existing heuristic phase
2. derive the incumbent's induced resource-order graph
3. destroy part of that order using small activity-removal neighborhoods
4. rebuild with the existing repair heuristic
5. keep the best repaired schedule in a small elite pool

Implemented neighborhoods:

- mobility-based removal
- non-peak removal
- segment removal
- random removal

Relevant code is in:

- [rcpsp/solver.py](rcpsp/solver.py)

### Why this helped

The reference comparison already showed that many misses were small:

- on `sm_j10`, most misses were `+1` to `+3`
- on `sm_j20`, many misses were also `+1` to `+3`

This is exactly the regime where local schedule perturbation is more valuable than deeper exact-search plumbing.

### Benchmark summary

Relative to the previous accepted `repair + compress` solver:

At `0.1s` per instance:

- `sm_j10`
  - feasible: `187 -> 187`
  - infeasible: `83 -> 83`
  - unknown: `0 -> 0`
  - avg ratio: `1.3397 -> 1.3343`
- `sm_j20`
  - feasible: `181 -> 181`
  - infeasible: `75 -> 75`
  - unknown: `14 -> 14`
  - avg ratio: `1.2973 -> 1.2873`

At `1.0s` per instance:

- `sm_j10`
  - feasible: `187 -> 187`
  - infeasible: `83 -> 83`
  - unknown: `0 -> 0`
  - avg ratio: `1.3391 -> 1.3310`
- `sm_j20`
  - feasible: `184 -> 184`
  - infeasible: `80 -> 80`
  - unknown: `6 -> 6`
  - avg ratio: `1.2949 -> 1.2832`

### Reference comparison improvement at `1.0s`

- `sm_j10`
  - exact matches: `152 -> 162`
  - exact match rate: `81.3% -> 86.6%`
  - average ratio to exact reference: `1.0175 -> 1.0107`
- `sm_j20`
  - exact matches: `91 -> 107`
  - exact match rate: `57.6% -> 67.7%`
  - average ratio to exact reference: `1.0322 -> 1.0195`

This is the first iteration that moved us materially closer to the public best-known values instead of only improving internal ratios.

### Concrete wins

New exact matches on `sm_j10` included:

- [sm_j10/PSP56.SCH](sm_j10/PSP56.SCH): `42 -> 34`
- [sm_j10/PSP161.SCH](sm_j10/PSP161.SCH): `35 -> 29`
- [sm_j10/PSP236.SCH](sm_j10/PSP236.SCH): `40 -> 36`

New exact matches on `sm_j20` included:

- [sm_j20/PSP112.SCH](sm_j20/PSP112.SCH): `97 -> 90`
- [sm_j20/PSP146.SCH](sm_j20/PSP146.SCH): `66 -> 59`
- [sm_j20/PSP173.SCH](sm_j20/PSP173.SCH): `91 -> 81`
- [sm_j20/PSP208.SCH](sm_j20/PSP208.SCH): `95 -> 85`

Large quality improvements without full exact matching included:

- [sm_j20/PSP264.SCH](sm_j20/PSP264.SCH): `99 -> 81`
- [sm_j20/PSP79.SCH](sm_j20/PSP79.SCH): `101 -> 92`
- [sm_j20/PSP269.SCH](sm_j20/PSP269.SCH): `136 -> 130`

## Added benchmark families

To check that the solver is not just drifting toward the public `sm_j10` and `sm_j20` sets, we added three more public benchmark families from the same RCPSP/max collection:

- [sm_j30](sm_j30)
- [testset_ubo20](testset_ubo20)
- [testset_ubo50](testset_ubo50)

We also extended the CLI so that:

- `benchmark` discovers both uppercase `PSP*.SCH` and lowercase `psp*.sch`
- `compare` supports `sm_j30`, `testset_ubo20`, and `testset_ubo50`
- reference matching is case-insensitive, so `PSP1` and `psp1` compare correctly

New benchmark files:

- [sm_j30_results_current_clean_0p1.json](sm_j30_results_current_clean_0p1.json)
- [testset_ubo20_results_current_clean_0p1.json](testset_ubo20_results_current_clean_0p1.json)
- [testset_ubo50_results_current_clean_0p1.json](testset_ubo50_results_current_clean_0p1.json)

### Generalization snapshot at `0.1s`

- `sm_j30`
  - feasible: `172`
  - infeasible: `79`
  - unknown: `19`
  - avg ratio: `1.2773`
  - exact match rate on exact-reference cases: `55.8%`
  - average ratio to exact reference: `1.0300`
- `testset_ubo20`
  - feasible: `70`
  - infeasible: `19`
  - unknown: `1`
  - avg ratio: `1.2604`
  - exact match rate on exact-reference cases: `65.2%`
  - average ratio to exact reference: `1.0164`
- `testset_ubo50`
  - feasible: `49`
  - infeasible: `14`
  - unknown: `27`
  - avg ratio: `1.1012`
  - exact match rate on exact-reference cases: `39.4%`
  - average ratio to exact reference: `1.0193`
  - one bounded case beat the current published upper bound: `psp57`

This is a good sign overall:

- the solver still looks competitive on `sm_j30` without any dataset-specific changes
- `testset_ubo20` generalizes reasonably well
- `testset_ubo50` is the clearest stress case, with many more `unknown` instances at the short `0.1s` budget

The main takeaway is that we are not obviously overfitting to `sm_j10` and `sm_j20`, but larger and harder sets still need stronger anytime improvement and better classification depth.

## Accepted iteration: post-exact polishing

The accepted change from this round is narrower than the first experiments:

- keep the existing accepted ALNS-style heuristic layer
- keep the exact-search layer
- add one more incumbent-polishing pass after exact search returns a feasible schedule, but only for `time_limit >= 0.5`

Why this was accepted:

- it improves `sm_j10` and `sm_j20` at `1.0s`
- it does not change feasibility coverage on those two sets
- it uses the remaining wall-clock budget better on instances where exact search finds a decent incumbent early
- the broader experiments with double justification and adaptive operator weighting were not kept because they hurt some short-budget generalization runs

### Accepted benchmark summary at `1.0s`

- `sm_j10`
  - feasible: `187`
  - infeasible: `83`
  - unknown: `0`
  - avg ratio: `1.3310 -> 1.3278`
  - exact match rate: `86.6% -> 89.8%`
  - average ratio to exact reference: `1.0107 -> 1.0082`
- `sm_j20`
  - feasible: `184`
  - infeasible: `80`
  - unknown: `6`
  - avg ratio: `1.2832 -> 1.2786`
  - exact match rate: `67.7% -> 71.5%`
  - average ratio to exact reference: `1.0195 -> 1.0172`

### Accepted short-budget guardrails at `0.1s`

- `sm_j30`
  - feasible: `170`
  - infeasible: `79`
  - unknown: `21`
  - exact match rate on exact-reference cases: `55.0%`
- `testset_ubo20`
  - feasible: `70`
  - infeasible: `19`
  - unknown: `1`
  - exact match rate on exact-reference cases: `66.7%`
- `testset_ubo50`
  - feasible: `51`
  - infeasible: `14`
  - unknown: `25`
  - exact match rate on exact-reference cases: `39.4%`

### Concrete win

The post-exact polishing pass directly fixed one of the worst visible `sm_j10` outliers:

- [sm_j10/PSP223.SCH](sm_j10/PSP223.SCH): the earlier solver was at `92`; the accepted post-exact pass found `68` within the same `1.0s` budget during targeted testing

### Current clean benchmark files

- [sm_j10_results_current_clean_1p0.json](sm_j10_results_current_clean_1p0.json)
- [sm_j20_results_current_clean_1p0.json](sm_j20_results_current_clean_1p0.json)
- [sm_j30_results_current_clean_0p1.json](sm_j30_results_current_clean_0p1.json)
- [testset_ubo20_results_current_clean_0p1.json](testset_ubo20_results_current_clean_0p1.json)
- [testset_ubo50_results_current_clean_0p1.json](testset_ubo50_results_current_clean_0p1.json)

## Current limitations

- infeasibility screening is still only pairwise, so it is incomplete
- the conflict-set exact search is not a formal infeasibility proof procedure
- `sm_j20` still has `14` unknown instances at `0.1s`
- `sm_j20` still has `6` unknown instances at `1.0s`
- branch ordering is heuristic and can likely be improved
- conflict-set extraction is simple and may not be the best branching object
- the new local search is still lightweight and not yet critical-chain-aware
- `sm_j10` is still short of the `90%` exact-match target
- `sm_j20` is still short of the `70%` exact-match target
- the main remaining `sm_j20` quality outliers are [sm_j20/PSP123.SCH](sm_j20/PSP123.SCH), [sm_j20/PSP153.SCH](sm_j20/PSP153.SCH), [sm_j20/PSP82.SCH](sm_j20/PSP82.SCH), [sm_j20/PSP57.SCH](sm_j20/PSP57.SCH), and [sm_j20/PSP269.SCH](sm_j20/PSP269.SCH)
- `sm_j30` still has `19` unknown instances at `0.1s`
- `testset_ubo50` still has `27` unknown instances at `0.1s`

## Next steps

### Highest-value next improvement

Keep the reference-driven direction, but make the destroy/repair neighborhoods sharper.

The concrete next step is:

1. bias removal toward the current critical chain and high-load periods
2. add pair reinsertion / swap moves around bottleneck activities
3. intensify around elite incumbents instead of sampling only one repaired neighborhood at a time

Planned operators:

- critical-chain removal
- peak-focused removal
- pair reinsertion / swap around bottleneck activities
- repeated `repair + compress`
- stronger elite-pool intensification

Evaluation rule for every iteration:

- run `benchmark`
- run `compare`
- track exact-match rate and average ratio to the public references

Target for a strong final solver:

- `sm_j10`: push exact-match rate above `90%`
- `sm_j20`: push exact-match rate above `70%`
- reduce the average exact-reference gap on `sm_j20` from `1.95%` toward `1.5%` or below

### Rejected follow-up experiments

- `focused bottleneck-pair post-polishing`:
  - idea: reserve a small tail budget after the main post-exact ALNS pass and spend it on repairing only `2-3` tightly coupled activities around the current highest-load region
  - result: `sm_j10 @ 1.0s` improved to `171/187` exact matches (`91.4%`), but `sm_j20 @ 1.0s` fell to `107/158` exact matches (`67.7%`)
  - verdict: rejected because the budget split hurt `sm_j20`
- `focused bottleneck-pair operator inside the ALNS loop`:
  - idea: keep the original time allocation, but add the same small pair neighborhood as an occasional destroy operator instead of a separate post-pass
  - result: `sm_j20 @ 1.0s` recovered slightly to `108/158` exact matches (`68.4%`), still below the accepted baseline `113/158` (`71.5%`)
  - verdict: rejected because it still weakened the main quality target

What we learned:

- the `pair / bottleneck` neighborhood itself is not obviously bad, but it is not strong enough yet to justify taking probability mass or budget away from the accepted ALNS mix
- future experiments should avoid broad operator-mix changes unless they clearly help `sm_j20`, because that set is the most sensitive quality guardrail right now

### Secondary improvements

- keep improving the persistent `J20` unknown cases, but only after the incumbent-improvement layer exists
- add stronger disjunctive propagation inside exact search
- derive more forced pair orderings from conflict sets and incumbent bounds
- add local improvement on feasible incumbents
- reconsider whether exact-search exhaustion should return `unknown` rather than `infeasible`
- test multiple branching heuristics
- run longer budgets such as `1s`, `5s`, and eventually closer to the assignment `30s`
- verify whether all currently labeled `infeasible` cases are truly infeasible under the correct instance semantics

## Candidate report framing

If we write this up as algorithm iterations:

1. Baseline temporal propagation and validation
2. Fast incumbent via conflict-repair heuristic
3. Pairwise infeasibility screening
4. Conflict-set branch-and-bound for feasibility and quality improvement
5. Repair + compress using induced resource order
6. ALNS-style incumbent polishing toward public best-known values

## External references consulted

- [Solving RCPSP/max by lazy clause generation](https://link.springer.com/article/10.1007/s10951-012-0285-x)
- [Why cumulative decomposition is not as bad as it sounds](https://people.eng.unimelb.edu.au/pstuckey/papers/cp09-cu.pdf)
- [ALNS RCPSP example](https://alns.readthedocs.io/en/stable/examples/resource_constrained_project_scheduling_problem.html)
- [ptal/kobe-scheduling](https://github.com/ptal/kobe-scheduling)
