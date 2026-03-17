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

## Current limitations

- infeasibility screening is still only pairwise, so it is incomplete
- `sm_j20` still has `15` unknown instances at `0.1s`
- `sm_j20` still has `6` unknown instances at `1.0s`
- branch ordering is heuristic and can likely be improved
- conflict-set extraction is simple and may not be the best branching object
- there is no dedicated local search after exact search finishes

## Next steps

### Highest-value next improvement

Target the remaining `6` hard `J20` unknown instances at `1s`:

- add stronger disjunctive propagation inside exact search
- derive more forced pair orderings from conflict sets and incumbent bounds
- improve feasibility-first behavior on the persistent unknown cases such as [sm_j20/PSP127.SCH](sm_j20/PSP127.SCH) and [sm_j20/PSP14.SCH](sm_j20/PSP14.SCH)

### Secondary improvements

- add local improvement on feasible incumbents
- test multiple branching heuristics
- run longer budgets such as `1s`, `5s`, and eventually closer to the assignment `30s`
- verify whether all currently labeled `infeasible` cases are truly infeasible under the correct instance semantics

## Candidate report framing

If we write this up as algorithm iterations:

1. Baseline temporal propagation and validation
2. Fast incumbent via conflict-repair heuristic
3. Pairwise infeasibility screening
4. Conflict-set branch-and-bound for feasibility and quality improvement
5. Future work: stronger propagation and branching heuristics

## External references consulted

- [Solving RCPSP/max by lazy clause generation](https://link.springer.com/article/10.1007/s10951-012-0285-x)
- [Why cumulative decomposition is not as bad as it sounds](https://people.eng.unimelb.edu.au/pstuckey/papers/cp09-cu.pdf)
