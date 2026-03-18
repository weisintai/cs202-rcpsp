# Heuristic Backend

This is the accepted main solver backend.

## Purpose

- build good feasible schedules quickly
- improve them with incumbent polishing
- use a lightweight exact layer for extra classification and tightening

## Main file

- `solver.py`

## Scope

This backend owns:

- heuristic construction
- local repair and compression
- conflict-set branch-and-bound
- incumbent polishing

It should stay focused on `anytime performance`, since this is still the submission-quality default backend.
