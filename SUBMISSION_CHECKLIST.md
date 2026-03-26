# Submission Checklist

This checklist is for final repo tidying and submission confidence without changing solver logic.

## Requirement-to-Repo Map

- Input parsing in PSPLIB `.SCH` style:
  - `rcpsp/parser.py`
- Activity, precedence, and resource data model:
  - `rcpsp/models.py`
- Schedule validity checks (precedence + renewable resources):
  - `rcpsp/validate.py`
- Main submission backend (no external optimizer dependency):
  - `rcpsp/cp/`
- CLI solve/benchmark entrypoint:
  - `main.py`

## Project-Brief Compliance Checks

- Dummy start/end activity handling is supported by parsed instance structure and solver flow.
- Precedence constraints are enforced via temporal propagation and validated schedules.
- Resource capacities are enforced by construction/propagation and validated schedules.
- Objective is makespan minimization (`cp` search keeps and improves incumbent makespan).
- Time budget is explicit and user-controlled with `--time-limit` in CLI commands.
- No external optimization libraries (OR-Tools, Gurobi, CPLEX, PuLP) are used by solver code.

## Pre-Submission Runbook

1. Run a quick correctness smoke run:
   - `python3 main.py solve benchmarks/data/sm_j10/PSP1.SCH --time-limit 1.0 --backend cp`
2. Run benchmark screens used by your team:
   - `python3 scripts/run_guardrails.py --backend cp --preset submission_quick`
   - `python3 scripts/run_guardrails.py --backend cp --preset cp_acceptance`
3. Confirm no accidental local artifacts are staged:
   - `git status`
4. Review diff one final time:
   - `git diff --stat`
   - `git diff`

## Repo Hygiene Checks

- Keep benchmark data under `benchmarks/data/` unchanged.
- Keep all solver logic files unchanged unless intentionally improving algorithm behavior.
- Keep historical result JSON snapshots that the team relies on for comparison.
- Keep all team-authored architecture/roadmap notes in place; only fix formatting/path hygiene when needed.
