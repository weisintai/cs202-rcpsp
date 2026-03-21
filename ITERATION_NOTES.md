# RCPSP/max Iteration Notes

Last updated: 2026-03-21

## 2026-03-21 SGS direction update

Recent reference checks clarified the solver boundary more than the code did.

### What we learned from cloned references

- The strongest reusable no-library SGS references we found are mostly `plain RCPSP`, not `RCPSP/max`.
- The strongest public references that *do* handle our `.SCH` benchmark family cleanly are optimization-backed, especially PyJobShop on OR-Tools / CP.
- So there is no obvious maintained no-library RCPSP/max solver we can just copy.

### What changed in our plan

- `sgs` should be treated as an `upper-bound engine` first.
- Its job is to return good feasible schedules quickly and improve them over time.
- The next major gains should come from cheap RCPSP/max propagation, not from endlessly tuning bootstrap heuristics.

### What actually worked

The best recent improvement was adding a very small warm-start budget before the SGS/ALNS loop:

- get a feasible schedule with the existing conflict-repair constructor
- feed that incumbent into `sgs`
- let the activity-list search improve it instead of starting from nothing

This improved short-budget feasibility coverage substantially across `sm_j10`, `sm_j20`, `sm_j30`, and `testset_ubo50`.

### What the next propagation experiment taught us

We also tried the first lightweight `latest-start` window pass inside `sgs`:

- derive latest starts from the current incumbent makespan
- feed that signal into priority scoring and eligible-activity choice

That experiment was useful, but the result was not strong enough to keep on the hot path.

- the helper itself is valid and is now kept as tested infrastructure in `rcpsp/sgs/time_windows.py`
- but using it aggressively inside the live ALNS / decoder loop mostly traded solution quality for small coverage gains
- the current mainline therefore keeps the warm-start improvement, but does **not** let latest-start scoring dominate the decoder yet

So the next SGS step is narrower than before:

- keep latest-start and time-window code as Phase 3 scaffolding
- do not let it override activity-list order until we also have stronger fixpoint propagation
- focus next on operator quality and cheap propagated rejections, not blanket latest-start ranking

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
- [rcpsp/heuristic/solver.py](rcpsp/heuristic/solver.py)
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

- [rcpsp/heuristic/solver.py](rcpsp/heuristic/solver.py)

### 5. Pairwise infeasibility screening

Implemented a lightweight infeasibility screen:

- computes all-pairs longest lag implications
- detects cases where two activities are forced to overlap
- if their combined resource demand exceeds a capacity, marks the instance as infeasible

Relevant code:

- [rcpsp/heuristic/solver.py](rcpsp/heuristic/solver.py)

### 6. Conflict-set branch-and-bound

Replaced the weak fallback search with a stronger exact-style search:

- find the earliest overloaded resource conflict
- shrink it to a minimal conflict set
- branch by forcing one activity to be last in that set
- propagate those disjunctive decisions as extra temporal edges
- prune with the current incumbent makespan

Relevant code:

- [rcpsp/heuristic/solver.py](rcpsp/heuristic/solver.py)

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

- [rcpsp/heuristic/solver.py](rcpsp/heuristic/solver.py)

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

- [rcpsp/heuristic/solver.py](rcpsp/heuristic/solver.py)

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
- `light energetic window pruning inside exact search`:
  - idea: add incumbent-aware resource-window pruning on the currently overloaded resource, but only near the incumbent where the bound should be tightest
  - result: `sm_j20 @ 1.0s` dropped to `110/158` exact matches (`69.6%`) and average exact ratio worsened from `1.0172` to `1.0216`
  - verdict: rejected because the extra bound cost more search time than it saved in this implementation

What we learned:

- the `pair / bottleneck` neighborhood itself is not obviously bad, but it is not strong enough yet to justify taking probability mass or budget away from the accepted ALNS mix
- future experiments should avoid broad operator-mix changes unless they clearly help `sm_j20`, because that set is the most sensitive quality guardrail right now
- CP-style pruning needs to be either much cheaper or much stronger; the first lightweight energetic-window attempt was neither

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

## CP-style backend scaffold

Started a separate experimental `cp` backend instead of continuing to force CP-style ideas into the accepted hybrid solver.

### References cloned locally

- `references/kobe-scheduling`
  - RCPSP/max MiniZinc cumulative model and benchmark references
- `references/minicp`
  - compact CP engine structure, cumulative propagator, DFS search
- `references/chuffed`
  - lazy clause generation / nogood-learning reference

See [references/README.md](references/README.md) for the curated list of relevant files.

### Implementation shape

Added:

- [rcpsp/cp/solver.py](rcpsp/cp/solver.py)
  - separate CP-style backend
  - pair-disjunction search state
  - temporal propagation by recomputing earliest feasible starts under added order edges
  - incumbent-based latest-start bounds
  - compulsory-part overload check
  - pairwise disjunctive branching on resource conflicts
  - small primal heuristic using the existing constructive scheduler under the current branch
- [main.py](main.py)
  - `--backend hybrid|cp` for `solve` and `benchmark`

The accepted `hybrid` solver remains the default. The `cp` backend is experimental and currently weaker.

### Preview result

Quick preview on `sm_j10 @ 0.05s`:

- feasible: `161`
- infeasible: `77`
- unknown: `32`
- exact matches: `59/187` (`31.6%`)
- average ratio to exact reference: `1.0976`

This confirms the backend is alive and can be iterated on, but it is still far behind the accepted hybrid solver.

### CP backend iteration: conflict-set branching and fixed search budget

The first follow-up CP iteration exposed a real architecture bug: the warm-start phase was allowed to consume the entire time budget on very short runs, so the `cp` backend often never reached branch-and-propagate search at all. That made the earlier preview look weaker than it really was.

Implemented in [rcpsp/cp/solver.py](rcpsp/cp/solver.py):

- switched from pair-only branching to conflict-set branching
  - each child can add several `other -> selected` disjunctive edges at once, similar to the stronger hybrid exact search
- threaded lag-distance state through the CP node so pairwise lag-based pruning can be reused when no incumbent exists
- reduced the warm-start budget to a small fixed share of the wall-clock limit so CP search still gets most of the time

Updated preview at `0.05s`:

- `sm_j10`
  - feasible: `161 -> 185`
  - infeasible: `77 -> 80`
  - unknown: `32 -> 5`
  - exact matches: `59/187 -> 113/187` (`31.6% -> 60.4%`)
  - average ratio to exact reference: `1.0976 -> 1.0325`
- `sm_j20`
  - feasible: `161 -> 169`
  - infeasible: `67 -> 70`
  - unknown: `42 -> 31`
  - exact matches: `51/158 -> 56/158` (`32.3% -> 35.4%`)
  - average ratio to exact reference: `1.1001 -> 1.0661`

Interpretation:

- the CP backend is still behind the accepted `hybrid` solver by a wide margin
- but it is no longer just a proof-of-life scaffold
- `sm_j10` now shows that the separate CP architecture can classify most instances quickly if the budget split is sane
- the next bottleneck is stronger propagation on harder `j20+` instances, not more warm-start tuning

### CP backend iteration: EST/LST timetable pruning

Added a first real `time-window + compulsory-part` propagator in [rcpsp/cp/solver.py](rcpsp/cp/solver.py).

What changed:

- maintain explicit `EST` and `LST` bounds inside `_propagate_cp_node`
- tighten `LST` backward through the difference constraints and added disjunctive edges
- build compulsory-part resource profiles from the current `EST/LST` windows
- fail on mandatory overloads
- prune activity `EST/LST` against the resource profile using `profile minus own mandatory part`
- rerun temporal propagation to a fixpoint after timetable pushes

This is still a lightweight implementation, but it is the first version where the CP backend has genuine timetable-style resource propagation instead of only conflict detection.

Updated preview at `0.05s`:

- `sm_j10`
  - feasible: `185 -> 186`
  - infeasible: `80 -> 80`
  - unknown: `5 -> 4`
  - exact matches: `113/187 -> 141/187` (`60.4% -> 75.4%`)
  - average ratio to exact reference: `1.0325 -> 1.0201`
- `sm_j20`
  - feasible: `169 -> 169`
  - infeasible: `70 -> 70`
  - unknown: `31 -> 31`
  - exact matches: `56/158 -> 70/158` (`35.4% -> 44.3%`)
  - average ratio to exact reference: `1.0661 -> 1.0558`

Interpretation:

- this is a clear improvement to the `cp` backend, not just noise
- `sm_j10/PSP1` now reaches the temporal lower bound (`26`) at `0.05s`, where the earlier CP backend stalled at `28`
- `sm_j20` quality improved materially even without reducing the overall unknown count yet
- the next likely gain is stronger explanation / conflict extraction from the timetable overloads, not another warm-start tweak

### Rejected CP follow-ups after timetable propagation

- `forced pair-order extraction from EST/LST windows`
  - idea: if two activities cannot overlap on some resource and only one relative order is still feasible under the current `EST/LST` windows, add that order edge immediately
  - result at `0.05s`: `sm_j20` exact matches improved only marginally (`70 -> 71`), but `sm_j10` quality slipped (`141 -> 140` exact matches) and overall `j20` coverage did not improve
  - verdict: rejected for now; the inference is plausible, but this implementation did not produce a clean net win
- `branch guidance toward flexible non-mandatory activities at conflict times`
  - idea: when branching on a resource conflict, prioritize delaying activities that are not compulsory at the hotspot and still have larger `EST/LST` windows
  - result at `0.05s`: essentially neutral on `sm_j20`, but `sm_j10` regressed from `186 feasible / 4 unknown` to `185 / 5`
  - verdict: rejected; not strong enough to justify changing the accepted timetable-propagation baseline

### CP backend iteration: explicit timetable-overload explanations

Implemented the next blueprint step in [rcpsp/cp/solver.py](rcpsp/cp/solver.py):

- introduce explicit `OverloadExplanation` objects for timetable failures
- return propagation outcomes as `(node, overload explanation)` instead of anonymous failure
- track explanation statistics in solver metadata:
  - `timetable_failures`
  - `max_timetable_explanation`

This is mainly infrastructure for the next blueprint steps:

- failure caching keyed by explained conflicts
- explanation-driven branching

Short-budget preview impact at `0.05s`:

- `sm_j10`
  - feasible: `186 -> 185`
  - infeasible: `80 -> 80`
  - unknown: `4 -> 5`
  - exact matches: stayed at `141/187`
  - average ratio to exact reference: `1.0201 -> 1.0206`
- `sm_j20`
  - feasible/infeasible/unknown: unchanged at `169 / 70 / 31`
  - exact matches: `70/158 -> 71/158`
  - average ratio to exact reference: `1.0558 -> 1.0594`

Interpretation:

- this is not a clean benchmark win by itself
- but it is the correct architectural step: timetable failures are no longer opaque `None` returns
- the backend now exposes the exact failure object needed for the next logical implementation, namely explanation-based failure caching

### Rejected explanation-based search follow-ups

- `exact-state failure cache`
  - idea: cache failed CP states keyed by the exact order set and store the associated timetable-overload explanation
  - result: no cache hits on the public `0.05s` preview and no evidence of benefit on the checked harder `1.0s` `j20` instances
  - verdict: rejected for now; too weak at the current state granularity
- `explanation-guided branch ordering`
  - idea: use timetable-overload explanation frequency as a VSIDS-like activity score for future conflict-set branching
  - result at `0.05s`: regressed both main preview sets relative to the accepted timetable baseline
    - `sm_j10` exact matches: `141 -> 139`
    - `sm_j20` exact matches: `70 -> 69`
  - verdict: rejected; the explanation signal is too sparse/weak in the current backend

### Rejected CP follow-up: energetic window overload detection

- `window-level overload explanations`
  - idea: extend timetable failure detection from point-time compulsory overloads to energetic overloads on whole time windows `[a, b)` using minimum unavoidable overlap under the current `EST/LST` bounds
  - result at `0.05s`: severe regression relative to the accepted explanation baseline
    - `sm_j10`: exact matches `141 -> 104`, unsat matches `83 -> 80`, unknown known-reference cases `0 -> 1`
    - `sm_j20`: exact matches `71 -> 50`, matched unsat `70 -> 70`, unknown known-reference cases `15 -> 15`, average exact ratio to reference worsened to `1.1049`
  - interpretation: the concept is valid, but this implementation was far too expensive for the pruning it delivered in the current CP architecture
  - verdict: rejected; if energetic reasoning comes back later, it needs to be either much cheaper or much tighter than this full window scan

### CP backend iteration: hybrid-guided incumbent warm start

Implemented in [rcpsp/cp/solver.py](rcpsp/cp/solver.py):

- keep the accepted timetable/explanation CP backend intact
- on larger budgets, spend a short slice of time in the accepted `hybrid` backend first
- use the resulting incumbent to tighten the CP backend's `LST` bounds before branch-and-propagate search
- keep the cheap randomized constructor loop afterward so tiny budgets still behave like the earlier CP baseline

This is the first recent CP change that clearly pays off on full `1.0s` public benchmarks instead of only on micro-budget previews.

Accepted benchmark impact:

- `sm_j10 @ 1.0s`
  - feasible/infeasible/unknown: `187 / 83 / 0`
  - exact matches: `166/187` (`88.8%`)
  - average exact ratio to reference: `1.0074`
- `sm_j20 @ 1.0s`
  - feasible/infeasible/unknown: `181 / 72 / 17`
  - exact matches: `106/158` (`67.1%`)
  - average exact ratio to reference: `1.0216`
  - bounded feasible cases: `24/26`
  - average ratio to best-known upper bound on bounded cases: `1.0552`

Interpretation:

- the CP backend is still behind the accepted `hybrid` backend on `sm_j20`, but the gap is now materially smaller
- the key gain came from a better incumbent bound, not a new pruning rule
- this is a strong sign that incumbent quality is a primary bottleneck for the current CP architecture

### Rejected warm-start over-tuning

- `larger warm-start slice for budgets >= 1.0s`
  - idea: give the hybrid-guided warm-start phase an even larger share of the time budget once `time_limit >= 1.0`
  - result on `sm_j20 @ 1.0s`: slightly better average exact ratio to reference (`1.0216 -> 1.0198`), but worse exact matches (`106 -> 104`) and fewer matches to the best-known bounded upper bound (`7 -> 6`)
  - verdict: rejected; keep the simpler warm-start budget because it wins on the more important count metrics

### Individual tests of the next three CP ideas

Tested the next three ideas individually against the accepted CP warm-start baseline, using `sm_j20 @ 1.0s` as the decisive comparison.

Accepted CP warm-start baseline:

- `sm_j20 @ 1.0s`
  - exact matches: `106/158` (`67.1%`)
  - avg exact ratio to reference: `1.0216`
  - bounded feasible cases: `24/26`
  - matched best-known bounded upper bounds: `7`

1. `overload-based nogoods only`
- idea: cache timetable-overload explanations as small nogoods keyed by the explained activity set and local order pattern
- result:
  - exact matches: `104/158`
  - avg exact ratio to reference: `1.0209`
  - bounded feasible cases: `24/26`
  - matched best-known bounded upper bounds: `9`
- interpretation:
  - slightly better average quality and bounded-case matching
  - but worse on the primary count metric `exact matches`
- verdict: rejected for now; promising signal, but not enough to displace the accepted baseline

2. `incumbent-triggered search resets only`
- idea: when CP finds a better incumbent, clear the duplicate-state filter and restart search under the tighter makespan bound
- result:
  - exact matches: `104/158`
  - avg exact ratio to reference: `1.0207`
  - bounded feasible cases: `24/26`
  - matched best-known bounded upper bounds: `5`
- interpretation:
  - again slightly better average ratio
  - but exact matches still fell, and bounded-case matching worsened
- verdict: rejected

3. `explanation-driven overload branching only`
- idea: when timetable propagation returns a small overload explanation, branch immediately on that explained resource conflict instead of only treating it as failure
- result:
  - exact matches: `102/158`
  - avg exact ratio to reference: `1.0224`
  - bounded feasible cases: `24/26`
  - matched best-known bounded upper bounds: `6`
- interpretation:
  - this was the weakest of the three single-idea variants
- verdict: rejected

Overall conclusion:

- none of the three individual ideas beat the accepted CP warm-start baseline on the main public `sm_j20 @ 1.0s` benchmark
- `nogoods only` was the most interesting of the three because it improved bounded-case matching, but it still lost on exact-match count
- this reinforces the current read: the next meaningful CP step is likely stronger cumulative propagation rather than more search bookkeeping

### Accepted fix: weaker pairwise exact branching

The review findings about the exact branch shape were correct.

What was wrong:

- both the heuristic exact layer and the CP backend were branching by selecting one activity from a conflict set and forcing **every** other conflicting activity before it
- that is stronger than the actual cumulative disjunction, so it can cut off valid improving schedules
- the CP backend also kept children that timetable propagation had already marked with an overload explanation, which wasted search effort

Accepted code changes:

- `rcpsp/heuristic/solver.py`
  - changed the exact brancher from `all others before selected` to `one pairwise order edge per child`
  - changed the small-instance repair path to try weaker single-blocker moves in both directions instead of greedily accumulating blocker-before-selected edges
- `rcpsp/cp/solver.py`
  - changed CP branching to the same weaker pairwise resource-order children
  - dropped children immediately when `_propagate_cp_node()` returns an overload explanation
- `tests/test_branching_regressions.py`
  - added regression tests for the two 4-job counterexamples that exposed the issue

Regression tests now locked in:

- exact branching toy:
  - heuristic solve returns makespan `5`
  - CP solve returns makespan `5`
- small-instance repair toy:
  - `construct_schedule()` now returns makespan `7`

Public benchmark impact:

- `sm_j10 @ 0.1s` `hybrid`
  - feasible/infeasible/unknown: `187 / 83 / 0`
  - exact matches: `185/187`
  - exact match rate: `98.9%`
  - average exact ratio to reference: `1.0008`
- `sm_j20 @ 0.1s` `hybrid`
  - feasible/infeasible/unknown: `180 / 73 / 17`
  - exact matches: `103/158`
  - exact match rate: `65.2%`
  - average exact ratio to reference: `1.0348`
  - note: this is a mixed short-budget result; coverage slipped slightly even though the brancher is more correct

- `sm_j10 @ 1.0s` `hybrid`
  - feasible/infeasible/unknown: `187 / 83 / 0`
  - exact matches: `187/187`
  - exact match rate: `100%`
  - average exact ratio to reference: `1.0000`
- `sm_j20 @ 1.0s` `hybrid`
  - feasible/infeasible/unknown: `184 / 79 / 7`
  - exact matches: `120/158`
  - exact match rate: `75.9%`
  - average exact ratio to reference: `1.0210`
  - matched best-known bounded upper bounds: `8`

- `sm_j10 @ 1.0s` `cp`
  - feasible/infeasible/unknown: `187 / 83 / 0`
  - exact matches: `187/187`
  - exact match rate: `100%`
  - average exact ratio to reference: `1.0000`
- `sm_j20 @ 1.0s` `cp`
  - feasible/infeasible/unknown: `181 / 69 / 20`
  - exact matches: `127/158`
  - exact match rate: `80.4%`
  - average exact ratio to reference: `1.0159`
  - matched best-known bounded upper bounds: `6`
  - improved one bounded case beyond the published best-known upper bound: `PSP150`

Interpretation:

- this is a real accepted fix, not only a toy-case cleanup
- the weaker pairwise branch shape improves exact-search quality substantially at `1.0s`
- `hybrid` remains the stronger submission backend because its coverage is better on `sm_j20`
- `cp` now has the better `sm_j20` quality profile among the cases it solves, but it still leaves too many unknowns to replace `hybrid` as the default

### Accepted test-runner wiring

Test execution is now wired cleanly through `uv`:

- added `pytest` as a dev dependency in `pyproject.toml`
- added `tests/conftest.py` so imports resolve from the repo root
- `uv run pytest` now passes on the current regression suite

### Rejected CP overload-nogood pass

Tried a small explanation-based overload cache in the CP backend:

- cache key was based on the overload explanation plus local windows/order pattern
- goal was to reuse repeated timetable failures instead of only relying on the current `seen` filter

Result on `sm_j20 @ 1.0s`:

- exact matches: `126/158`
- exact match rate: `79.7%`
- avg exact ratio to reference: `1.0183`

Comparison against the current accepted CP baseline:

- baseline exact matches: `127/158`
- baseline avg exact ratio to reference: `1.0159`

Verdict:

- rejected
- the idea still looks directionally right, but this lightweight local cache was not strong enough to beat the accepted CP baseline

### Accepted CP propagation step: scoped forced pair-order inference

Implemented a stronger cumulative propagation step in [rcpsp/cp/solver.py](rcpsp/cp/solver.py):

- after timetable propagation updates `EST/LST`, inspect pairs of activities that cannot overlap on some resource
- if the current windows make only one relative order feasible, add that resource order immediately as a propagated edge
- scope this propagation to `n_jobs >= 20` so it strengthens the harder sets without perturbing the already-solved `J10` regime

This is effectively a small disjunctive propagation layer sitting inside the CP fixpoint, rather than waiting to discover the same forced order by branching later.

Accepted benchmark impact:

- `sm_j10 @ 1.0s` `cp`
  - feasible/infeasible/unknown: `187 / 83 / 0`
  - exact matches: `187/187`
  - exact match rate: `100%`
  - average exact ratio to reference: `1.0000`
- `sm_j20 @ 1.0s` `cp`
  - feasible/infeasible/unknown: `181 / 69 / 20`
  - exact matches: `128/158`
  - exact match rate: `81.0%`
  - average exact ratio to reference: `1.0178`
  - matched best-known bounded upper bounds: `7`
  - better-than-best-known bounded cases: `PSP150`

Comparison against the previous accepted CP baseline:

- `sm_j10 @ 1.0s`
  - exact matches: `187 -> 187`
  - no regression after scoping the propagator to `n_jobs >= 20`
- `sm_j20 @ 1.0s`
  - exact matches: `127 -> 128`
  - average exact ratio to reference: `1.0159 -> 1.0178`
  - matched best-known bounded upper bounds: `6 -> 7`

Verdict:

- accepted
- the gain is modest but real on the main `sm_j20` count metric
- scoping it away from `J10` kept the easy-set frontier intact
- this is a better next-step cumulative propagator than the earlier rejected full energetic-window scan

### Rejected CP follow-up: localized energetic overload around hotspot windows

Tried a cheaper energetic variant inside the CP fixpoint:

- use the current `lower` schedule to find the hotspot resource/time
- build candidate windows around that hotspot from nearby `EST/LST` boundaries
- compute minimum unavoidable energy in those windows
- fail early when required energy exceeds window capacity

This was meant to be a cheaper replacement for the previously rejected full energetic-window scan.

Results:

- `sm_j20 @ 1.0s`
  - exact matches improved `128 -> 129`
  - average exact ratio to reference improved `1.0178 -> 1.0159`
- but broader guardrails regressed:
  - `sm_j30 @ 0.1s` exact matches dropped `68 -> 57`
  - `testset_ubo50 @ 0.1s` exact matches stayed flat at `12`

Verdict:

- rejected
- this version helped the main `J20` target slightly, but it damaged `sm_j30` too much to keep
- if energetic reasoning comes back again, it needs a more stable explanation/boundary strategy than this hotspot-local version

### Accepted CP search step: gated monotone failure cache over pair orders

Used delegated CP search work to add a safer failure cache in [rcpsp/cp/search.py](rcpsp/cp/search.py) and [rcpsp/cp/state.py](rcpsp/cp/state.py):

- cache only monotone `node.pairs` order sets, never the full `(pairs, lower)` state
- prune a child or node if its pair set is a superset of a known failed pair set
- avoid caching the empty pair set
- enable the cache only for `time_limit >= 0.5` so short-budget guardrails do not pay unnecessary bookkeeping cost
- expose `failure_cache_hits`, `failure_cache_inserts`, and `failure_cache_size` in CP metadata

Added a focused search-level regression in [tests/test_cp_search.py](tests/test_cp_search.py) to keep the failure cache minimal and monotone.

Accepted benchmark impact:

- `sm_j10 @ 1.0s` `cp`
  - feasible/infeasible/unknown: `187 / 83 / 0`
  - exact matches: `187/187`
  - exact match rate: `100%`
  - average exact ratio to reference: `1.0000`
- `sm_j20 @ 1.0s` `cp`
  - feasible/infeasible/unknown: `181 / 69 / 20`
  - exact matches: `130/158`
  - exact match rate: `82.3%`
  - average exact ratio to reference: `1.0162`
  - better-than-best-known bounded cases: `PSP150`
- `sm_j30 @ 0.1s` `cp`
  - feasible/infeasible/unknown: `154 / 78 / 38`
  - exact matches: `66/120`
  - exact match rate: `55.0%`
  - average exact ratio to reference: `1.0311`
- `testset_ubo50 @ 0.1s` `cp`
  - feasible/infeasible/unknown: `53 / 14 / 23`
  - exact matches: `12/33`
  - exact match rate: `36.4%`
  - average exact ratio to reference: `1.0375`

Comparison against the previous accepted CP baseline:

- `sm_j10 @ 1.0s`
  - exact matches: `187 -> 187`
  - no regression on the already-solved easy set
- `sm_j20 @ 1.0s`
  - exact matches: `128 -> 130`
  - average exact ratio to reference: `1.0178 -> 1.0162`
- `sm_j30 @ 0.1s`
  - exact matches: `68 -> 66`
  - but feasible coverage improved `153 -> 154`, unsat matches improved `77 -> 78`, and known-reference unknowns dropped `32 -> 31`
- `testset_ubo50 @ 0.1s`
  - exact matches: `12 -> 12`
  - average exact ratio to reference improved slightly `1.0407 -> 1.0375`

Verdict:

- accepted
- this is the first search-side CP change in a while that improves the main `sm_j20 @ 1.0s` target without clearly damaging the broader guardrails
- the cache still needs stronger explanations before it becomes real nogood learning, but it is now a useful medium-budget pruning layer
