# SGS Roadmap

This document defines the intended `SGS-first` architecture for the custom `RCPSP/RCPSP-max` backend in this repo.

It is the implementation roadmap for [rcpsp/sgs](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs), not a benchmark log. Use [ITERATION_NOTES.md](/Users/weisintai/development/smu/modules/y2s2/cs202/project/ITERATION_NOTES.md) for experiments and measured results.

## Why SGS First

For this project, the safest path is:

- build a fast constructive solver that always returns a schedule
- improve it with activity-list metaheuristics
- add propagation and exact search only after the decoder is strong

This is the right bias for our constraints:

- no external optimization engines in the final solver
- tight runtime budget
- public benchmark targets are mostly small and medium instances
- the current data is `RCPSP/max`, so generalized lags matter from day one

This does **not** mean ignoring CP research. It means borrowing the strongest ideas from CP and exact RCPSP/max papers, but wrapping them around an `SGS-centered` solver instead of trying to build a full solver engine first.

## Core Decision

The `sgs` backend should be organized around one central primitive:

- a priority-list decoder that maps an activity ordering to a feasible schedule

Everything else should orbit that decoder:

- initial construction
- forward-backward improvement
- ALNS or random-key GA
- lower bounds
- propagation
- branch-and-bound

If a new idea does not strengthen one of those layers, it is probably a distraction.

## Research Basis

The roadmap below is based on these source families:

- parsing and instance representation:
  - [PyJobShop project scheduling example](https://pyjobshop.org/stable/examples/project_scheduling.html)
  - [PyJobShop repository](https://github.com/PyJobShop/PyJobShop)
- SGS and activity-list metaheuristics:
  - [ALNS RCPSP example notebook](https://raw.githubusercontent.com/N-Wouda/ALNS/master/examples/resource_constrained_project_scheduling_problem.ipynb)
  - [Fleszar and Hindi 2004](https://www.sciencedirect.com/science/article/abs/pii/S0377221702008846)
  - [Valls, Ballestin, Quintanilla 2005](https://ftp.iaorifors.com/paper/51049)
- RCPSP/max propagation and exact reasoning:
  - [Schutt et al. 2013, Solving RCPSP/max by lazy clause generation](https://link.springer.com/article/10.1007/s10951-012-0285-x)
  - [Constructive branch-and-bound with general temporal constraints](https://link.springer.com/article/10.1007/s10951-022-00735-9)
- benchmark data and reference models:
  - [PSPLIB](http://www.om-db.wi.tum.de/psplib/)
  - [MiniZinc RCPSP benchmarks](https://github.com/MiniZinc/minizinc-benchmarks/tree/master/rcpsp)

## Scope Boundary

The `sgs` backend is the experimental rewrite track for a clean, phased solver.

The accepted `hybrid` backend and the `cp` backend should remain stable while `sgs` evolves.

The end goal is:

- `sgs` becomes the main constructive and metaheuristic solver
- `sgs` eventually absorbs the most useful lower-bound and exact-search ideas
- `cp` remains a separate research track, not the default implementation path

## Current State

What already exists in [rcpsp/sgs](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs):

- split positive lags into `min-lag` arcs and negative lags into `max-lag` constraints
- build a precedence DAG from nonnegative arcs
- generate deterministic and sampled activity-list priorities
- decode an activity list with a serial window-based decoder
- run a light forward/backward re-decoding pass
- evaluate restart batches through a dedicated Phase 1 restart module
- expose a backend-local guardrail benchmark runner

This is only a `Phase 0 / early Phase 1 scaffold`.

What is still missing:

- a true production-quality serial SGS
- an optional parallel SGS
- a real benchmark harness dedicated to `sgs`
- metaheuristics built on the decoder
- lower bounds and propagation inside the `sgs` track
- exact search over activity lists or time windows

Before this backend is taken seriously, it must cover the public guardrail sets that matter most for the course:

- `sm_j10`
- `sm_j20`
- `sm_j30`
- `testset_ubo50`

If `sgs` cannot run `j10` and `j20` reliably, it is not ready for Phase 2.

## Development Rules

These rules apply to all `sgs` work:

1. Keep the decoder central.
2. Measure every accepted change on `sm_j10`, `sm_j20`, `sm_j30`, and `testset_ubo50`.
3. Do not keep random tweaks unless they clearly fit a phase below.
4. Do not add heavy exact-search machinery before the Phase 1 decoder is trustworthy.
5. For `RCPSP/max`, keep `min-lag` and `max-lag` logic explicit in every layer.

## Target Structure

The current package can evolve toward this structure inside `rcpsp/sgs/`:

```text
rcpsp/sgs/
├── model.py                 # Activity, lag arcs, instance
├── adapter.py               # current parser-to-sgs bridge
├── graph.py                 # precedence graph and activity-list utilities
├── heuristics/
│   ├── serial.py            # main serial SGS decoder
│   ├── parallel.py          # optional parallel SGS
│   ├── fbi.py               # forward-backward or double justification
│   └── priorities.py        # dispatch rules and activity-list generation
├── meta/
│   ├── alns.py              # recommended first metaheuristic
│   └── rkga.py              # optional random-key GA
├── bounds/
│   ├── cpm.py               # ES/LS and critical path
│   └── resource_lb.py       # simple resource lower bounds
├── propagation/
│   ├── time_windows.py      # RCPSP/max window tightening
│   └── cumulative.py        # not-first/not-last, optional edge-finding
├── search/
│   └── branch_and_bound.py  # exact search around SGS + bounds
├── benchmark.py             # backend-specific benchmark helpers
└── solver.py                # orchestration
```

The current files do not need to match this immediately. The point is to keep phase work isolated.

## Phase 0: Foundations and Data

### Goal

Represent the problem correctly and make the `sgs` track self-consistent.

### Deliverables

- `Activity`-level representation with:
  - duration
  - renewable demands
  - min-lag predecessors and successors
  - max-lag predecessors and successors
- precedence DAG built from the min-lag arcs that are safe for activity-list generation
- topological order utilities
- adapter from [rcpsp/parser.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/parser.py) into the `sgs` model
- benchmark smoke tests that load the public datasets without crashing

### In this repo

This phase is `partially done` in:

- [rcpsp/sgs/models.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/models.py)
- [rcpsp/sgs/adapter.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/adapter.py)
- [rcpsp/sgs/graph.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/graph.py)

### Exit Criteria

- all `sm_j10` instances load through the `sgs` adapter
- all `sm_j10`, `sm_j20`, `sm_j30`, and `testset_ubo50` instances parse without model errors
- one dummy activity-list decode runs end-to-end on `sm_j10`

## Phase 1: Basic Feasible Solver

### Goal

Always produce a valid schedule quickly.

This is the foundation of the whole backend. If this phase is weak, all later metaheuristics are weak.

### Deliverables

- a true `serial SGS` that:
  - consumes an activity list
  - schedules activities in precedence-feasible order
  - searches the earliest feasible start that satisfies:
    - renewable capacities
    - min-lag constraints
    - max-lag constraints already fixed by earlier decisions
- optional `parallel SGS`
- `FBI` or double-justification improvement pass
- deterministic priority rules:
  - topological
  - earliest start
  - latest finish or slack-based
  - random topological
- a batch runner that evaluates many random activity lists and keeps the best schedule

### Important design note for RCPSP/max

For plain RCPSP, the activity list lives on a DAG and the serial SGS simply inserts the next precedence-feasible job.

For `RCPSP/max`, negative lags create upper bounds on relative start times. That means:

- the activity list should still be generated from the safe min-lag precedence DAG
- the decoder must maintain dynamic lower and upper windows while scheduling
- a candidate insertion that breaks a max-lag bound must be rejected immediately

This is the key difference from a plain PSPLIB RCPSP decoder.

### In this repo

This phase is `started but not complete` in:

- [rcpsp/sgs/serial.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/serial.py)
- [rcpsp/sgs/priorities.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/priorities.py)
- [rcpsp/sgs/fbi.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/fbi.py)
- [rcpsp/sgs/restarts.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/restarts.py)
- [rcpsp/sgs/solver.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/solver.py)
- [rcpsp/sgs/benchmark.py](/Users/weisintai/development/smu/modules/y2s2/cs202/project/rcpsp/sgs/benchmark.py)

The immediate next step is to keep improving the serial decoder and priority rules until `sm_j10` and `sm_j20` stop being the main bottleneck.

### Exit Criteria

- `sm_j10`: `100%` feasible at short budgets
- `sm_j20`: high feasibility and stable quality at short budgets
- `1000` random priority lists per selected instance can be decoded inside the time budget
- benchmark output records the best upper bound per instance

`sm_j10` and `sm_j20` are the minimum credibility gate for this backend. `testset_ubo50` matters, but it does not replace those easier public sets.

### Practical benchmark target

Use:

- `python main.py benchmark sm_j10 --backend sgs --time-limit 0.1`
- `python main.py benchmark sm_j20 --backend sgs --time-limit 0.1`
- `python main.py benchmark sm_j30 --backend sgs --time-limit 0.1`
- `python main.py benchmark testset_ubo50 --backend sgs --time-limit 0.1`

Do not move on until `sgs` stops failing basic feasibility too often.

## Phase 2: Metaheuristics for Upper Bounds

### Goal

Turn the decoder into a strong anytime heuristic.

### Recommended order

1. `ALNS`
2. `Random-key GA` only if ALNS is not enough

ALNS is the better first step here because:

- it is easier to tune incrementally
- it reuses the activity-list representation cleanly
- the ALNS RCPSP example already matches the design style we want

### Deliverables

- state representation as a precedence-feasible activity list
- destroy operators:
  - mobility removal
  - non-peak removal
  - segment removal
- repair by reinserting tasks and re-decoding with SGS
- FBI or double justification after repair
- optional random-key GA with:
  - permutation decoding
  - precedence repair
  - SGS fitness evaluation

### Research guidance

Copy the architecture idea, not the code, from:

- [ALNS RCPSP example notebook](https://raw.githubusercontent.com/N-Wouda/ALNS/master/examples/resource_constrained_project_scheduling_problem.ipynb)
- [Fleszar and Hindi 2004](https://www.sciencedirect.com/science/article/abs/pii/S0377221702008846)
- [Valls, Ballestin, Quintanilla 2005](https://ftp.iaorifors.com/paper/51049)

### Exit Criteria

- `sm_j30`: strong anytime upper bounds at `0.1s`, `1.0s`, and `5.0s`
- `testset_ubo50`: clear improvement over Phase 1 schedules
- the metaheuristic improves over plain random priority-list sampling on the same budget

## Phase 3: Lower Bounds and Propagation

### Goal

Add pruning power around the SGS core.

This phase is where the solver stops being only a heuristic sampler and starts behaving like a serious `RCPSP/max` engine.

### Deliverables

- `CPM` forward and backward passes:
  - earliest starts
  - latest starts under incumbent bound
- simple resource lower bounds
- time-window propagation for min-lags and max-lags
- basic cumulative reasoning:
  - compulsory parts
  - not-first / not-last
  - optional edge-finding

### Key design point

Do not build a separate CP node state inside `sgs`.

Instead:

- compute bounds and windows
- use them to tighten the candidate insertion space of the decoder
- reuse them inside ALNS repair and later B&B

### Research guidance

Use these sources as the model:

- [Schutt et al. 2013](https://link.springer.com/article/10.1007/s10951-012-0285-x)
- [PyJobShop project scheduling example](https://pyjobshop.org/stable/examples/project_scheduling.html)

The implementation should stay lightweight and explicit, not solver-framework-like.

### Exit Criteria

- lower bound reported for every instance
- measurable pruning of candidate start windows during decode
- `sm_j30`: lower bounds close enough to upper bounds that many cases are nearly closed without exact search

## Phase 4: Exact Search Around SGS

### Goal

Prove optimality on the smaller public sets and close the remaining gaps on harder ones.

### Recommended search style

Prefer one of:

- activity-list branch-and-bound
- time-window branch-and-bound

At each node:

- propagate time windows
- compute a lower bound
- generate or improve an incumbent with SGS + FBI
- prune when `LB >= UB`

### Branching guidance

Start simple:

- smallest start-time window first
- or branch on the activity with the strongest resource/critical-path pressure

Do not start with conflict-driven learning or deep CP-style search.

### Research guidance

Use these only as design references:

- [Constructive branch-and-bound with general temporal constraints](https://link.springer.com/article/10.1007/s10951-022-00735-9)
- [MiniZinc RCPSP benchmarks](https://github.com/MiniZinc/minizinc-benchmarks/tree/master/rcpsp)

### Exit Criteria

- `sm_j10` and `sm_j20`: strong optimality rate at `1s`
- `sm_j30`: meaningful optimality proof rate at larger budgets
- `testset_ubo50`: tighter gaps even when proofs are rare

## Phase 5: Full RCPSP/max Support and Polish

### Goal

Make the SGS track robust on the generalized-lag datasets.

### Deliverables

- max-lag support audited in:
  - decoder
  - ALNS repair
  - lower bounds
  - propagation
  - exact search
- UBO-specific regression tests
- restart and portfolio logic only if needed

### Exit Criteria

- `testset_ubo50` is a first-class benchmark, not an afterthought
- no major logic path silently assumes plain DAG RCPSP

## Benchmark Policy

Every accepted `sgs` change should be screened on:

- `sm_j10`
- `sm_j20`
- `sm_j30`
- `testset_ubo50`

The first question for any `sgs` iteration is:

- does it still run `sm_j10` and `sm_j20` well?

If the answer is no, do not treat improvements on harder sets as enough.

Recommended loop:

1. short-budget screen
2. medium-budget rerun on survivors
3. compare against the previous `sgs` baseline
4. only keep changes that improve the target set without obvious guardrail damage

The current CLI already supports this:

```bash
python main.py benchmark sm_j10 --backend sgs --time-limit 0.1
python main.py benchmark sm_j20 --backend sgs --time-limit 0.1
python main.py benchmark sm_j30 --backend sgs --time-limit 0.1
python main.py benchmark testset_ubo50 --backend sgs --time-limit 0.1
```

Use `compare` after every meaningful phase checkpoint.

## Immediate Next Work

Do this next, in order:

1. stabilize Phase 1 serial SGS
2. add a dedicated `sgs` benchmark runner and baseline JSON snapshots
3. implement double justification cleanly
4. add ALNS as the first real Phase 2 metaheuristic
5. only then start Phase 3 bounds and propagation

## What Not To Do

Do not:

- keep tuning random weights in the `hybrid` backend while calling it SGS work
- start with a GA before the serial decoder is strong
- start with branch-and-bound before Phase 1 is reliable
- build a full CP engine inside `sgs`
- claim RCPSP/max support unless max-lag logic is tested end-to-end

## Success Criteria

If this roadmap is followed properly, the desired backend progression is:

- Phase 0:
  - clean data model
- Phase 1:
  - fast reliable feasibility
- Phase 2:
  - strong upper bounds
- Phase 3:
  - strong lower bounds and window pruning
- Phase 4:
  - proofs on small and medium sets
- Phase 5:
  - credible RCPSP/max performance on UBO

That is the path that gives this repo a coherent `SGS` solver instead of another round of disconnected tweaks.
