# CP Roadmap

This document defines the intended architecture and acceptance policy for the custom `CP-style` backend in this repo.

It is the implementation roadmap for [rcpsp/cp](rcpsp/cp), not a benchmark dump. Use [ITERATION_NOTES.md](ITERATION_NOTES.md) for experiment history and measured runs.

## Purpose

The `cp` backend exists because it has the highest ceiling of the in-repo backends under the assignment constraint of `no external optimization library in the final solver`.

The goal is:

- keep `hybrid` as the strong practical baseline
- use `cp` as the backend with the best chance of closing harder `RCPSP/max` cases
- improve `cp` through stronger propagation, better explanations, and better branching

The goal is **not** to clone all of OR-Tools or build a general-purpose CP-SAT engine.

## What This Backend Is

Today, [rcpsp/cp](rcpsp/cp) is a self-contained branch-and-propagate solver with:

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
2. Shared code may come from backend-neutral modules under [rcpsp/core](rcpsp/core) and other shared infra.
3. No dataset-name branching in solver logic.
4. Solver decisions may depend on structural features such as:
   - `n_jobs`
   - `n_resources`
   - time budget
   - window widths
   - overload/conflict structure
5. Do not add broad expensive propagators unless they clearly beat the acceptance matrix.

## Acceptance Matrix

Every meaningful `cp` change should be screened against the same stack.

### Tier 1: Main Short-Budget Screen

- `sm_j10 @ 0.1s`
- `sm_j20 @ 0.1s`
- `sm_j30 @ 0.1s`
- `testset_ubo50 @ 0.1s`
- `sm_j10 @ 1.0s`
- `sm_j20 @ 1.0s`

The harness preset for this screen is `submission_quick`.

### Tier 2: Anti-Overfitting Cases

- `testset_ubo10 @ 0.1s`
- `testset_ubo100 @ 0.1s`
- `testset_ubo200 @ 0.1s`

The harness preset for this screen is `broad_generalization`.

### Tier 3: Public 30s Matrix

- `sm_j10 @ 30s`
- `sm_j20 @ 30s`
- `sm_j30 @ 30s`
- `testset_ubo20 @ 30s`
- `testset_ubo50 @ 30s`

The harness preset for this matrix is `cp_acceptance`.

### Tier 4: Submission Gate

- `cp_acceptance`
- plus held-out `ubo10/100/200 @ 0.1s`

The harness preset for this final gate is `submission`.

### Current Main Targets

The `cp` roadmap is currently optimizing for:

1. keep `sm_j10 @ 1.0s` perfect
2. improve `sm_j20 @ 1.0s` exact closure
3. reduce `unknown` and `over_budget` on `sm_j30 @ 0.1s`
4. reduce `unknown` and `over_budget` on `testset_ubo50 @ 0.1s`
5. improve `30s` residue behavior without damaging the short-budget path
6. avoid fake gains that collapse on `ubo10/100/200`

## Optimization Policy

The backend is close enough to its current architectural ceiling that each change must declare what it is trying to optimize.

Do not treat `cp` as having one scalar objective called "faster". Track three separate objectives:

1. `tight-budget quality`
   - `0.1s` behavior
   - early incumbent quality
   - reducing `unknown`
   - avoiding constructor and warm-start regressions
2. `moderate-budget quality`
   - `1.0s` to `30s` behavior
   - better exact closure after propagation and DFS have time to work
3. `kernel throughput`
   - lower cost per propagation, conflict-selection, and projection step
   - lower node overhead
   - lower proof and seed overhead

Every non-trivial `cp` change should declare one primary target category before implementation:

- `constructor-first`
- `propagation-throughput`
- `search-quality`
- `proof-quality`
- `architecture`

The primary target decides how the change is judged:

- `constructor-first`
  - focus on `sm_j30 @ 0.1s`, `testset_ubo20 @ 0.1s`, `testset_ubo50 @ 0.1s`
- `propagation-throughput`
  - focus on profiles plus `sm_j10 @ 1.0s` and `sm_j20 @ 1.0s`
- `search-quality`
  - focus on exact closure at `1.0s` and `30s`
- `proof-quality`
  - focus on exact closure and proof-side `unknown` reduction
- `architecture`
  - accept neutral or modestly negative local results only if the change unlocks a stronger future propagator or search mode

For now, reject changes that only look better in a profiler but do not survive the acceptance matrix.

## Experiment Discipline

Record every meaningful `cp` change in [ITERATION_NOTES.md](ITERATION_NOTES.md) with:

- change id or short label
- hypothesis
- primary target
- files touched
- focused validation
- `submission_quick` result
- `broad_generalization` result
- keep / revert / revisit decision

Use these acceptance gates:

1. must pass focused `pytest`
2. must not introduce crashes or correctness regressions
3. must pass `submission_quick`
4. must pass `broad_generalization`
5. if the change targets `0.1s`, it should improve at least one short-budget row without materially hurting `1.0s`
6. if the change targets `1.0s` to `30s`, it should improve exact closure there without materially hurting `0.1s`

This is the default process until the backend gets another architectural step forward.

## Current Gaps

What `cp` is missing is now fairly specific:

### 1. Early incumbent quality on hard cases

The local seed in [rcpsp/cp/guided_seed.py](rcpsp/cp/guided_seed.py) is valid, but still fairly generic. On many hard feasible instances, CP gets only one real incumbent update before time expires.

### 2. Stronger cumulative inference

Current propagation in [rcpsp/cp/propagation.py](rcpsp/cp/propagation.py) has:

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

This remains the most likely source of the next real step-function improvement. Recent work showed that local kernel optimizations can recover or preserve benchmark rows, but they do not materially raise the architecture ceiling.

### 4. Better explanation reuse

The failure cache in [rcpsp/cp/search.py](rcpsp/cp/search.py) is useful, but still too coarse. It stores failed pair sets, not smaller reusable overload cores.

### 5. Better branch selection

`cp` still branches reasonably, not decisively. It needs better conflict ranking and child ordering based on explanation tightness and current slack.

### 6. Better budget modes

Some reasoning is good at `1.0s` and harmful at `0.1s`. The backend needs explicit `fast-budget` versus `deep-budget` behavior, instead of one universal propagation profile.

This is now a stronger priority than it looked initially. Recent reverted experiments repeatedly showed:

- some ideas are acceptable or promising at `1.0s` to `30s`
- the same ideas are harmful at `0.1s`, especially on held-out `ubo100/200`

So future deeper-budget experiments should be written as explicitly gated deep-budget behavior, not as new universal defaults.

## Near-Term Direction

The roadmap is now split into two lanes.

### Lane A: Stabilize The Current CP Solver

Goal:

- keep guardrails green
- only accept narrowly scoped, reversible improvements
- stop mixing correctness fixes, throughput tweaks, and search-quality experiments in one patch

Allowed work:

- correctness fixes
- cache-safety fixes
- bounded throughput improvements with guardrail wins
- targeted branch or constructor adjustments with an explicit budget target

### Lane B: Make The CP Solver Fuller

Goal:

- break through the current architecture ceiling rather than shaving a few more percent off hot paths

Priority items:

- incremental propagation and watched-state reruns
- explicit `fast` versus `deep` propagation modes
- better failure-core reuse and explanation shrinking
- stronger cumulative reasoning such as `not-first / not-last`
- better no-incumbent constructor and seed behavior on hard feasible cases

This lane is where future bigger gains should come from. Treat it as roadmap work, not opportunistic micro-optimization.

## Phased Plan

## Phase 0: Lock The Process

Goal: stop drift and benchmark chasing.

Implement:

- [x] this roadmap
- [x] the guardrail presets in the harness
- [x] use the same short-budget, held-out, and `30s` screens before accepting `cp` changes

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

- [x] cleaner propagation/search boundaries in [rcpsp/cp/propagation.py](rcpsp/cp/propagation.py) and [rcpsp/cp/search.py](rcpsp/cp/search.py)
- [x] no accepted regression on the required guardrail stack

Current accepted outcomes from Phase 1 work:

- propagation round/call instrumentation is live in `cp` metadata
- conflict counters are live in `cp` metadata
- conflict selection is materially stronger than the earlier baseline
- `sm_j20 @ 1.0s` improved to `155/158` exact while keeping `sm_j10 @ 1.0s` perfect

## Phase 2: Stronger Cheap Propagation

Goal: get more pruning per node without blowing the short budget.

Implement in [rcpsp/cp/propagation.py](rcpsp/cp/propagation.py):

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

Implement in [rcpsp/cp/search.py](rcpsp/cp/search.py):

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

- [ ] make [rcpsp/cp/guided_seed.py](rcpsp/cp/guided_seed.py) explicitly budget-aware by instance size and time limit
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
2. keep `submission_quick` and `broad_generalization` green before trusting a `30s` win
3. harden the solver kernel and make propagation modes more explicit
4. implement a cheap `not-first / not-last` pass driven by overload explanations
5. improve explanation-aware branching and failure reuse
6. only then spend more effort on `guided_seed`

This is the route to follow unless new benchmark evidence clearly contradicts it.
