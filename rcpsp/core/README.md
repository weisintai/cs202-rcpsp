# Shared Solver Core

The `rcpsp/core/` package holds backend-agnostic scheduling primitives used by both solver families.

## Modules

- `metrics.py`
  - resource intensity scoring
- `lag.py`
  - difference-constraint closure and pairwise infeasibility checks
- `conflicts.py`
  - resource conflict extraction and minimal overload sets
- `branching.py`
  - delay scoring and branch ordering
- `compress.py`
  - left-shift, resource-order extraction, and schedule compression

## Intent

This layer exists so:

- CP does not depend on heuristic internals
- heuristic and CP can share bug fixes in one place
- backend wrappers stay thin and focused on orchestration
