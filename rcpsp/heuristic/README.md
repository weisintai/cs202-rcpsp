# Heuristic Backend

This is the accepted main solver backend.

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
  - thin public wrapper and orchestration

## Scope

This backend owns:

- heuristic construction
- local repair and compression
- pairwise conflict branch-and-bound
- incumbent polishing

It should stay focused on `anytime performance`, since this is still the submission-quality default backend.
