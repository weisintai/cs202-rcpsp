# RCPSP Package Layout

The `rcpsp/` package is split into `shared` project infrastructure plus separate solver backends.

## Shared modules

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

## Solver backends

- [heuristic/README.md](/Users/weisintai/Library/Mobile%20Documents/com~apple~CloudDocs/SMU/Y2S2/CS202/Project/rcpsp/heuristic/README.md)
  - accepted main solver
  - heuristic repair, exact improvement, incumbent polishing
- [cp/README.md](/Users/weisintai/Library/Mobile%20Documents/com~apple~CloudDocs/SMU/Y2S2/CS202/Project/rcpsp/cp/README.md)
  - experimental CP-style backend
  - separate branch-and-propagate architecture

## Entry points

- package exports are re-exported from `rcpsp/__init__.py`
- CLI dispatch lives in `main.py`

The goal of this layout is to keep backend-specific work isolated so heuristic and CP iterations do not interfere with each other.
