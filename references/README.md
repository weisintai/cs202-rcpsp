# CP-Style References

These repositories are cloned here as `reference-only` material for algorithm ideas, model structure, and search architecture. They are **not** runtime dependencies of this project.

## Included repositories

- `kobe-scheduling`
  - source: <https://github.com/ptal/kobe-scheduling>
  - why it matters:
    - includes public RCPSP/max benchmark data and reference values
    - includes a MiniZinc RCPSP/max model using `cumulative`
  - most relevant files:
    - `references/kobe-scheduling/model/minizinc/rcpsp-cumulative.mzn`
    - `references/kobe-scheduling/README.md`

- `minicp`
  - source: <https://github.com/minicp/minicp>
  - why it matters:
    - compact educational CP solver architecture
    - useful for state, propagation, and DFS branching structure
  - most relevant files:
    - `references/minicp/src/main/java/minicp/engine/constraints/Cumulative.java`
    - `references/minicp/src/main/java/minicp/search/DFSearch.java`
    - `references/minicp/src/main/java/minicp/examples/RCPSP.java`

- `chuffed`
  - source: <https://github.com/chuffed/chuffed>
  - why it matters:
    - lazy clause generation / CP-SAT style reference
    - useful for long-term branching, nogood, and restart ideas
  - most relevant files:
    - `references/chuffed/README.md`
    - `references/chuffed/chuffed/examples/rcpsp.cpp`
    - `references/chuffed/chuffed/core/engine.cpp`

## How we are using them

- `kobe-scheduling`: RCPSP/max semantics and cumulative-model reference
- `minicp`: lightweight CP engine structure for our separate `cp` backend
- `chuffed`: search-learning reference, not something we plan to reimplement fully for this assignment

## Guardrail

These references are for `ideas and architecture only`. Our solver code remains in this repository under `rcpsp/`.
