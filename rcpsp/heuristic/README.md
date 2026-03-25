# Heuristic Backend

This is the archived `hybrid` comparison backend.

## Purpose

- build good feasible schedules quickly
- improve them with incumbent polishing
- use a lightweight exact layer for extra classification and tightening

## Layout

- `construct.py`
  - constructive scheduling and repair
- `improve.py`
  - ALNS-style incumbent polishing
- `exact.py`
  - pairwise exact-search intensification
- `solver.py`
  - backend entrypoint and orchestration

## Scope

This backend owns:

- heuristic construction
- local repair and compression
- pairwise conflict branch-and-bound
- incumbent polishing

It should stay focused on `anytime performance`, because that is the main reason to keep it as a comparison baseline.

Current practical read on this checkout:

- `hybrid` is no longer the submission default; `cp` is
- `hybrid` is still useful as the short-budget comparison baseline
- in fresh reruns, `hybrid` beat `cp` on `sm_j30 @ 0.1s`
  - `83/120` exact for `hybrid`
  - `75/120` exact for `cp`
- on `sm_j20 @ 1.0s`, `hybrid` is clearly behind `cp`
  - `125/158` exact for `hybrid`
  - `155/158` exact for `cp`

This backend remains worth keeping for side-by-side checks, but active submission-facing work should go into `rcpsp/cp`.
