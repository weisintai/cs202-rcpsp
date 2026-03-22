# CP Roadmap

This document defines the intended architecture and acceptance policy for the custom `CP-style` backend in this repo.

It is the implementation roadmap for [rcpsp/cp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp), not a benchmark dump. Use [ITERATION_NOTES.md](/Users/weisintai/development/smu/modules/y2s2/cs202/project/ITERATION_NOTES.md) for experiment history and measured runs.

## Purpose

The `cp` backend exists because it has the highest ceiling of the in-repo backends under the assignment constraint of `no external optimization library in the final solver`.

The goal is:

- keep `hybrid` as the strong practical baseline
- use `cp` as the backend with the best chance of closing harder `RCPSP/max` cases
- improve `cp` through stronger propagation, better explanations, and better branching

The goal is **not** to clone all of OR-Tools or build a general-purpose CP-SAT engine.

## What This Backend Is

Today, [rcpsp/cp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp) is a self-contained branch-and-propagate solver with:

- explicit node state over pairwise resource-order decisions
- lag-closure-based temporal pruning
- incumbent-based latest-start bounds
- compulsory-part timetable checks
- limited forced pair-order inference
- a monotone failure cache over pair sets
- a local `guided_seed` path for early incumbent and easy infeasibility detection

This is the right architecture direction.

It is **not yet** a solver with:

- strong global cumulative reasoning
- explanation reuse on the level of a modern CP engine
- enough short-budget anytime strength on large `RCPSP/max` instances

## What The Benchmarks Taught Us

The current shape is clear:

- `hybrid` is the best practical backend at `0.1s`, especially on `sm_j30` and `testset_ubo50`
- `cp` is stronger at deeper search on the medium public sets, especially `sm_j20 @ 1.0s`
- held-out `testset_ubo100` and `testset_ubo200` expose a real scaling wall for both in-repo backends at `0.1s`
- PyJobShop on OR-Tools is much stronger on large feasible cases, but that is because it has much stronger propagation and search, not because we need the whole CP-SAT engine

This means:

- do not abandon `cp`
- do not expect micro-tweaks to close the gap
- do not keep treating `cp` as an imported heuristic wrapper
- stop expecting one small generic change to improve both `0.1s` and `30s` behavior at once

The route forward is `targeted RCPSP/max-specific CP ideas`, not `full solver-engine cloning`.

## Current Practical Read

The backend is now at a local maximum for broad “cheap generic improvement” experiments.

What the recent accepted and rejected work says:

- accepted:
  - conflict-selection improvements
  - lag-closure pruning already in search
  - guided-seed phase diagnostics
  - residue analysis tooling
- rejected:
  - several branch-order rewrites
  - failure-cache shrinking
  - broader pair-forcing propagation
  - generic stronger propagation that looked fine on one slice and failed the full acceptance matrix

So the roadmap needs to be followed more strictly now:

- preserve the accepted short-budget baseline
- treat `0.1s` and `30s` as different operating regimes
- do not keep landing changes that only win on one budget profile

## What Standard CP References Say

The external references line up on a few points:

- scheduling solvers are strongest when `propagation` and `search` are clearly separated
- the propagation process should be `local`, `incremental`, and driven to fixpoint
- search needs some state-restoration strategy, but that does not force one specific implementation
- high-value scheduling propagators are cumulative-specific, especially timetable and stronger order inference
- explanations matter because they make conflicts and pruning reusable

That matches:

- Claude Le Pape's scheduling tutorial
- Schulte and Carlsson's chapter on finite-domain CP systems
- Schutt et al. on `RCPSP/max` and explaining cumulative propagation

So the current roadmap direction is valid, but it was missing some foundational solver-engine work.

For this repo, the relevant interpretation is:

- keep the current lightweight `immutable node + recomputation / incremental reuse` style unless profiling shows it is the actual bottleneck
- do not jump straight to a full trailing-based CP engine

## Hard Constraints

The `cp` backend should keep these invariants:

1. No imports from `rcpsp.heuristic` or `rcpsp.sgs`.
2. Shared code may come from backend-neutral modules under [rcpsp/core](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/core) and other shared infra.
3. No dataset-name branching in solver logic.
4. Solver decisions may depend on structural features such as:
   - `n_jobs`
   - `n_resources`
   - time budget
   - window widths
   - overload/conflict structure
5. Do not add broad expensive propagators unless they clearly beat the acceptance matrix.

## Acceptance Matrix

Every meaningful `cp` change should be screened against the same matrix.

### Tier 1: Main Acceptance Cases

- `sm_j10 @ 0.1s`
- `sm_j20 @ 0.1s`
- `sm_j30 @ 0.1s`
- `testset_ubo50 @ 0.1s`
- `sm_j10 @ 1.0s`
- `sm_j20 @ 1.0s`

### Tier 2: Anti-Overfitting Cases

- `testset_ubo10 @ 0.1s`
- `testset_ubo100 @ 0.1s`
- `testset_ubo200 @ 0.1s`

### Current Main Targets

The `cp` roadmap is currently optimizing for:

1. keep `sm_j10 @ 1.0s` perfect
2. improve `sm_j20 @ 1.0s` exact closure
3. reduce `unknown` and `over_budget` on `sm_j30 @ 0.1s`
4. reduce `unknown` and `over_budget` on `testset_ubo50 @ 0.1s`
5. avoid fake gains that collapse on `ubo10/100/200`

The guardrail preset for this matrix is `cp_acceptance`.

## Current Gaps

What `cp` is missing is now fairly specific:

### 1. Early incumbent quality on hard cases

The local seed in [rcpsp/cp/guided_seed.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp/guided_seed.py) is valid, but still fairly generic. On many hard feasible instances, CP gets only one real incumbent update before time expires.

### 2. Stronger cumulative inference

Current propagation in [rcpsp/cp/propagation.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp/propagation.py) has:

- EST/LST tightening
- compulsory-part overload detection
- limited forced pair-order inference

It does not yet have enough of:

- `not-first / not-last` style inference
- stronger explanation shrinking
- richer conflict-derived pair forcing

### 3. Missing solver-engine infrastructure

The current backend has node propagation and DFS, but it still under-specifies the machinery that real CP solvers rely on:

- a clearer `propagation-to-fixpoint` contract
- better incremental reuse of node state across child nodes
- better organization of propagation responsibilities by constraint family
- a clean distinction between `cheap always-on` propagation and `budgeted heavier` propagation

This does **not** mean building full trailing, watched literals, or CP-SAT internals.

It does mean the roadmap should explicitly improve the CP kernel before chasing more surface heuristics.

### 4. Better explanation reuse

The failure cache in [rcpsp/cp/search.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp/search.py) is useful, but still too coarse. It stores failed pair sets, not smaller reusable overload cores.

### 5. Better branch selection

`cp` still branches reasonably, not decisively. It needs better conflict ranking and child ordering based on explanation tightness and current slack.

### 6. Better budget modes

Some reasoning is good at `1.0s` and harmful at `0.1s`. The backend needs explicit `fast-budget` versus `deep-budget` behavior, instead of one universal propagation profile.

This is now a stronger priority than it looked initially. Recent reverted experiments repeatedly showed:

- some ideas are acceptable or promising at `1.0s` to `30s`
- the same ideas are harmful at `0.1s`, especially on held-out `ubo100/200`

So future deeper-budget experiments should be written as explicitly gated deep-budget behavior, not as new universal defaults.

## Phased Plan

## Phase 0: Lock The Process

Goal: stop drift and benchmark chasing.

Implement:

- [x] this roadmap
- [x] the `cp_acceptance` guardrail preset
- [x] use the same public plus held-out matrix before accepting `cp` changes

Exit criteria:

- [x] `cp` changes are discussed against the same matrix every time
- [x] `cp` remains self-contained

## Phase 1: Solver Kernel Hardening

Goal: make the backend behave more like a real scheduling CP solver before adding more search sugar.

Implement:

- [x] make the propagation contract more explicit:
  - [x] temporal tightening
  - [x] cumulative tightening
  - [x] forced-order inference
  - [x] failure explanation
- [~] make fixpoint behavior explicit and cheap:
  - [x] expose propagation rounds and propagation call counts
  - [ ] only rerun propagators when their watched state actually changed
  - [ ] keep a small worklist-style structure, even if it stays simple
- [x] improve child-state reuse:
  - [x] reuse parent `lag_dist`
  - [x] avoid rebuilding more node state than necessary where already easy to do so
  - [x] make it obvious which node fields are derived and which are authoritative
- [x] make the restoration strategy explicit:
  - [x] current default is `copying / recomputation with incremental reuse`
  - [x] only pursue heavier restoration machinery if profiling justifies it
- [~] define propagation modes clearly:
  - [x] cheap always-on propagation is the current default
  - [ ] optional stronger propagation for deeper budgets

Do not:

- build generic SAT or CP engine machinery
- over-abstract the code before it earns its keep

Exit criteria:

- [x] cleaner propagation/search boundaries in [rcpsp/cp/propagation.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp/propagation.py) and [rcpsp/cp/search.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp/search.py)
- [x] no accepted regression on the `cp_acceptance` matrix

Current accepted outcomes from Phase 1 work:

- propagation round/call instrumentation is live in `cp` metadata
- conflict counters are live in `cp` metadata
- conflict selection is materially stronger than the earlier baseline
- `sm_j20 @ 1.0s` improved to `155/158` exact while keeping `sm_j10 @ 1.0s` perfect

## Phase 2: Stronger Cheap Propagation

Goal: get more pruning per node without blowing the short budget.

Implement in [rcpsp/cp/propagation.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp/propagation.py):

- [x] stronger fixpoint use of `lag_dist` during EST/LST tightening
- [ ] cheap `not-first / not-last` style inference around overload explanation sets
- [ ] smaller overload explanations from compulsory-part failures
- [~] better pair forcing when overload structure already nearly determines an order

Do not start with:

- broad energetic scans on every node
- expensive global cumulative reasoning on all budgets

Exit criteria:

- lower node counts or better exact closure on `sm_j20 @ 1.0s`
- fewer `unknown` or `over_budget` cases on `sm_j30` / `testset_ubo50 @ 0.1s`

Recent lesson:

- several propagation-side attempts were reverted because they damaged the `0.1s` acceptance sets, even when they looked reasonable on `1.0s` or on a small long-budget sample
- Phase 2 should therefore stay conservative until Phase 6 budget separation is real

## Phase 3: Explanation-Aware Search

Goal: branch on the most decisive conflicts and reuse failure information better.

Implement in [rcpsp/cp/search.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp/search.py):

- [~] rank conflicts by explanation tightness and incumbent pressure
- [ ] prefer pairs where one direction is already nearly impossible
- [ ] store smaller reusable failure cores derived from overload explanations
- [ ] order children by explanation tightness, not only by generic branch order

Exit criteria:

- the difficult `sm_j20` residue shrinks
- medium-budget exact closure improves without broad short-budget regressions

## Phase 4: Better Local Incumbents

Goal: improve anytime behavior, but keep this clearly secondary to the CP kernel.

Implement:

- [ ] make [rcpsp/cp/guided_seed.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/cp/guided_seed.py) explicitly budget-aware by instance size and time limit
- [ ] spend more seed effort on incumbent quality for `j20+` and less on generic proof when that proof rarely pays off
- [~] bias improvement around critical-chain and bottleneck-resource activities
- [x] keep seed metadata rich enough to tell whether the seed helped or just consumed budget

Do not:

- import `hybrid` or `sgs`
- let guided seed become a hidden duplicate backend

Exit criteria:

- improves `sm_j20 @ 1.0s` exact closure or exact-ratio quality
- does not clearly damage `sm_j30` or `testset_ubo50 @ 0.1s`

Current accepted diagnostic result:

- seed-phase metadata now shows where the incumbent came from
- on the remaining `sm_j20 @ 1.0s` residue:
  - `PSP153` is currently seed-improve limited
  - `PSP36` and `PSP45` are currently proof/search limited
- this means future Phase 4 work should be selective, not blanket seed-budget tuning

## Phase 5: Deep-Budget Mode

Goal: use `5s` to `30s` budgets better without harming the `0.1s` path.

Implement:

- explicit deep-budget propagation/search profile
- enable heavier reasoning only when the budget can pay for it
- add a residue harness for long-budget public misses and larger held-out samples

Focus:

- remaining `sm_j20` exact misses
- `sm_j30`
- `testset_ubo50`
- sampled `ubo100` / `ubo200`

Exit criteria:

- long-budget improvements are real, not just over-budget noise

## What To Borrow From Strong Solvers

Worth extracting and re-implementing:

- window tightening ideas
- compulsory-part overload explanations
- conflict ranking heuristics
- cumulative inference patterns like `not-first / not-last`
- lightweight timetable or `TTEF-lite` ideas when they are tightly scoped and benchmark-justified

Not worth cloning wholesale:

- SAT clause machinery
- watched literals
- generic integer propagators
- the full OR-Tools / CP-SAT runtime

## What A Complete CP Solver Would Also Need

If the goal ever became `build a general CP solver`, the roadmap would need much more:

- a generic propagation engine
- general variable/domain abstractions
- state restoration services such as trailing, copying, or recomputation
- generic explanation and nogood infrastructure
- a scheduler for propagator wakeups

That is intentionally out of scope here.

This roadmap is for a `strong scheduling-specific CP backend`, not a full CP platform.

## Immediate Next Work

The next actual code work after this roadmap reset should be:

1. keep using `cp_acceptance` as the required gate
2. harden the solver kernel and make propagation modes more explicit
3. implement a cheap `not-first / not-last` pass driven by overload explanations
4. improve explanation-aware branching and failure reuse
5. only then spend more effort on `guided_seed`

This is the route to follow unless new benchmark evidence clearly contradicts it.
