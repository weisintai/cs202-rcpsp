# SGS Backend

This backend is the clean third solver track for the SGS-first plan.

The implementation contract for this backend lives in [SGS_ROADMAP.md](../../SGS_ROADMAP.md).

## Scope today

- separate positive min-lag arcs from reverse max-lag arcs
- build a precedence DAG and topological priority lists
- decode priority lists with a serial SGS module
- use a very small conflict-repair warm start to get a first feasible incumbent quickly
- generate deterministic and sampled activity-list priorities in a separate module
- run a light forward/backward re-decoding pass
- run incumbent-centered ALNS-style restart batches from a dedicated Phase 1 orchestration module
- keep latest-start / time-window helpers available as Phase 3 infrastructure without forcing them into the hot path yet
- expose a backend-local guardrail benchmark entrypoint

## Current role

Right now, `sgs` should be treated as the repo's `upper-bound engine`.

That means:

- find a valid schedule quickly
- improve that schedule within the remaining budget
- leave stronger lower bounds, propagation, and exact proofs to later phases

## What it is not yet

- not a full RCPSP/max propagation engine
- not a competitive exact solver yet
- not expected to beat optimization-backed RCPSP/max references
- not a plain-RCPSP SGS copied from PSPLIB examples

This track is for clean iteration by phase, not for replacing the current default backend on day one.
