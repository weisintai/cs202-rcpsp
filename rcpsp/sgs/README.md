# SGS Backend

This backend is the clean third solver track for the SGS-first plan.

The implementation contract for this backend lives in [SGS_ROADMAP.md](/Users/weisintai/development/smu/modules/y2s2/cs202/project/SGS_ROADMAP.md).

## Scope today

- separate positive min-lag arcs from reverse max-lag arcs
- build a precedence DAG and topological priority lists
- decode priority lists with a serial SGS module
- generate deterministic and sampled activity-list priorities in a separate module
- run a light forward/backward re-decoding pass
- run restart batches from a dedicated Phase 1 orchestration module
- expose a backend-local guardrail benchmark entrypoint

## What it is not yet

- not a full RCPSP/max propagation engine
- not a competitive exact solver yet
- not expected to beat the hybrid or CP backends immediately

This track is for clean iteration by phase, not for replacing the current default backend on day one.
