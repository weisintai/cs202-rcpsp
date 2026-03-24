# RCPSP Package Layout

The `rcpsp/` package is split into shared infrastructure, a reusable solver core, and backend-specific orchestration. In the current project phase, `cp` is the active solver path; the other backends are kept for baseline comparison and historical reference.

## Shared infrastructure

- `models.py`
  - core dataclasses for instances, schedules, and solve results
- `parser.py`
  - `.SCH` parser
- `temporal.py`
  - temporal propagation utilities for lag constraints
- `validate.py`
  - schedule validation and resource-profile construction
- `reference.py`
  - public benchmark reference loading and normalization
- `config.py`
  - backend-agnostic heuristic search configuration

## Shared solver core

- `core/metrics.py`
  - resource intensity scoring
- `core/lag.py`
  - difference-constraint closure and pairwise infeasibility checks
- `core/conflicts.py`
  - resource conflict extraction and minimal overload sets
- `core/branching.py`
  - conflict scoring and branch ordering
- `core/compress.py`
  - left-shift, resource-order extraction, and schedule compression
- [core/README.md](core/README.md)
  - design intent for the shared core layer

## Solver backends

- [heuristic/README.md](heuristic/README.md)
  - archived heuristic-style baseline
  - layered into construction, improvement, exact search, and a thin public wrapper
- [cp/README.md](cp/README.md)
  - active submission-oriented CP backend
  - layered into explicit state, propagation, search, and a thin public wrapper
- [../CP_ROADMAP.md](../CP_ROADMAP.md)
  - phased implementation roadmap for turning `cp` into the strongest exact-oriented backend
- [sgs/README.md](sgs/README.md)
  - archived SGS-style comparison backend
  - layered into instance adaptation, graph utilities, SGS decoding, and light improvement
- [../SGS_ROADMAP.md](../SGS_ROADMAP.md)
  - historical SGS roadmap

## Entry points

- package exports are re-exported from `rcpsp/__init__.py`
- CLI dispatch lives in `main.py`
- backend entrypoints live in `heuristic/solver.py`, `cp/solver.py`, and `sgs/solver.py`

The goal of this layout is to isolate backend-specific work while keeping shared scheduling primitives in one place. For active solver work, teammates should start in [cp/README.md](cp/README.md) and ignore the archived backends unless they are explicitly doing a comparison run.
