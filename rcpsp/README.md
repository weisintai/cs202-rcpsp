# RCPSP Package Layout

The `rcpsp/` package is split into shared infrastructure, a reusable solver core, and backend-specific orchestration.

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
  - accepted main solver
  - layered into construction, improvement, exact search, and a thin public wrapper
- [cp/README.md](cp/README.md)
  - experimental CP-style backend
  - layered into explicit state, propagation, search, and a thin public wrapper

## Entry points

- package exports are re-exported from `rcpsp/__init__.py`
- CLI dispatch lives in `main.py`
- backend wrappers stay in `heuristic/solver.py` and `cp/solver.py` for stable imports

The goal of this layout is to isolate backend-specific work while keeping shared scheduling primitives in one place.
