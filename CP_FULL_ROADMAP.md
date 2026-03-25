# CP Full Roadmap

This document defines the purpose of the experimental `cp_full` backend.

`cp_full` is not the submission backend. The stable submission path remains `cp`.

## Why This Backend Exists

The current `cp` solver is close enough to its local architectural ceiling that larger changes should no longer be developed directly in the submission path.

`cp_full` exists to:

- preserve `cp` as the stable control backend
- allow larger architectural experiments
- test whether a fuller scheduling-CP design can beat the current `cp` solver on the project benchmarks

## What Counts As A Valid `cp_full` Change

This backend is for changes that are too invasive for the main `cp` path, such as:

- incremental propagation worklists
- watched-state reruns
- explicit `fast` versus `deep` propagation modes
- stronger cumulative reasoning such as `not-first / not-last`
- richer explanation and failure-core reuse
- more structured node restoration and derived-state ownership

This backend is not for generic churn, cosmetic rewrites, or small hot-path tweaks that can be tested safely in `cp`.

## Immediate Plan

The first `cp_full` phase should focus on architecture, not benchmark polishing.

Current status:

- [x] split `cp_full` out as a separate experimental backend
- [x] add explicit `fast` versus `deep` propagation modes
- [x] replace the old universal propagation loop with a small worklist-style scheduler
- [ ] make propagator families more explicit in state and metadata
- [ ] decide which propagators are always-on versus deep-only
- [ ] start comparing `cp_full` against `cp` on the guardrail presets

Priority order:

1. make propagator families more explicit:
   - temporal
   - cumulative
   - order inference
   - explanation
2. improve reusable failure explanations
3. only then revisit stronger cumulative inference

## Evaluation Policy

`cp_full` should be compared against `cp`, not judged in isolation.

For each meaningful experiment:

- state the hypothesis
- name the primary target
- compare against current `cp`
- record the result in [ITERATION_NOTES.md](ITERATION_NOTES.md)

A `cp_full` idea should only be considered for promotion back into `cp` if it:

- is stable
- survives `submission_quick`
- survives `broad_generalization`
- is structurally clear enough to maintain

## Non-Goals

`cp_full` is not trying to become:

- a general-purpose CP-SAT engine
- a full trailing-based industrial solver clone
- a place to hide unmeasured regressions

It should stay focused on stronger `RCPSP/max` scheduling-specific CP ideas that make sense for [Project.pdf](Project.pdf) and the assignment constraints.
