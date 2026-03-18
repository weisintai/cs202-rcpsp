# CP Backend

This is the experimental CP-style backend.

## Purpose

- provide a separate branch-and-propagate architecture
- make CP-style changes without destabilizing the accepted heuristic backend

## Main file

- `solver.py`

## Scope

This backend currently owns:

- CP node state over resource-ordering decisions
- temporal propagation under added order edges
- incumbent-based latest-start bounds
- compulsory-part / timetable pruning on EST/LST windows
- conflict-set branching that can add several disjunctive orders at once
- a small warm-start phase that leaves most of the budget to CP search

It is currently a scaffold, not the accepted main solver. Changes here should target `stronger propagation and branching`, not heuristic polishing.
