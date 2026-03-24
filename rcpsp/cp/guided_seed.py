from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..config import HeuristicConfig, sample_heuristic_config
from ..core.lag import (
    all_pairs_longest_lags,
    forced_resource_order_edges_from_dist,
    pairwise_infeasibility_reason_from_dist,
)
from ..core.metrics import resource_intensity
from ..models import Edge, Instance, Schedule, SolveResult
from ..temporal import TemporalInfeasibleError, longest_feasible_starts, longest_tail_to_sink
from ..validate import validate_schedule
from .construct import construct_schedule
from .exact import SearchStats, branch_and_bound_search
from .improve import improve_incumbent


@dataclass(frozen=True)
class SeedContext:
    instance: Instance
    seed: int
    time_limit: float
    solver_config: HeuristicConfig
    started: float
    soft_deadline: float
    temporal_lower: list[int]
    temporal_lower_bound: int
    forced_edges: tuple[Edge, ...]
    tail: list[int]
    intensity: list[float]


@dataclass(frozen=True)
class SeedBudgets:
    construct_until: float
    improve_budget: float
    proof_until: float
    polish_until: float


def _prepare_seed_context(
    instance: Instance,
    time_limit: float,
    seed: int,
    config: HeuristicConfig | None,
) -> tuple[SeedContext, random.Random] | SolveResult:
    solver_config = config or HeuristicConfig()
    rng = random.Random(seed)
    started = time.perf_counter()
    final_deadline = started + time_limit
    safety_margin = min(max(0.005, time_limit * 0.005), max(0.005, time_limit * 0.05))
    soft_deadline = max(started, final_deadline - safety_margin)

    try:
        lag_dist = all_pairs_longest_lags(instance)
        pairwise_reason = pairwise_infeasibility_reason_from_dist(instance, lag_dist)
        if pairwise_reason is not None:
            runtime = time.perf_counter() - started
            temporal_lb_schedule = longest_feasible_starts(instance)
            return SolveResult(
                instance_name=instance.name,
                status="infeasible",
                schedule=None,
                runtime_seconds=runtime,
                temporal_lower_bound=temporal_lb_schedule[instance.sink],
                restarts=0,
                metadata={"reason": pairwise_reason, "seed": seed, "time_limit": time_limit},
            )
        forced_edges, _ = forced_resource_order_edges_from_dist(instance, lag_dist)
        temporal_lb_schedule = longest_feasible_starts(instance, extra_edges=forced_edges)
        tail = longest_tail_to_sink(instance)
    except TemporalInfeasibleError as exc:
        runtime = time.perf_counter() - started
        return SolveResult(
            instance_name=instance.name,
            status="infeasible",
            schedule=None,
            runtime_seconds=runtime,
            temporal_lower_bound=-1,
            restarts=0,
            metadata={"reason": str(exc), "seed": seed, "time_limit": time_limit},
        )

    context = SeedContext(
        instance=instance,
        seed=seed,
        time_limit=time_limit,
        solver_config=solver_config,
        started=started,
        soft_deadline=soft_deadline,
        temporal_lower=temporal_lb_schedule,
        temporal_lower_bound=temporal_lb_schedule[instance.sink],
        forced_edges=tuple(forced_edges),
        tail=tail,
        intensity=resource_intensity(instance),
    )
    return context, rng


def _seed_budgets(context: SeedContext) -> SeedBudgets:
    started = context.started
    construct_until = min(context.soft_deadline, started + min(1.0, max(0.01, context.time_limit * 0.2)))
    improve_budget = min(5.0, max(0.02, context.time_limit * 0.35))
    proof_until = context.soft_deadline
    polish_until = context.soft_deadline
    return SeedBudgets(
        construct_until=construct_until,
        improve_budget=improve_budget,
        proof_until=proof_until,
        polish_until=polish_until,
    )


def _run_construct_phase(
    context: SeedContext,
    budgets: SeedBudgets,
    rng: random.Random,
) -> tuple[Schedule | None, int]:
    best: Schedule | None = None
    restarts = 0

    while True:
        now = time.perf_counter()
        if now >= budgets.construct_until:
            break
        if context.solver_config.max_restarts is not None and restarts >= context.solver_config.max_restarts:
            break

        schedule = construct_schedule(
            context.instance,
            rng,
            context.tail,
            context.intensity,
            sample_heuristic_config(context.solver_config, rng),
            deadline=budgets.construct_until,
            base_extra_edges=context.forced_edges,
            initial_starts=context.temporal_lower,
        )
        restarts += 1
        if schedule is None:
            continue
        if best is None or schedule.makespan < best.makespan:
            best = schedule
        if best.makespan == context.temporal_lower_bound:
            break

    return best, restarts


def _seed_metadata(
    context: SeedContext,
    budgets: SeedBudgets,
    *,
    construct_makespan: int | None,
    improve_makespan: int | None,
    proof_makespan: int | None,
    polish_makespan: int | None,
    best_source: str,
    improvement_iterations: int,
    exact_stats: SearchStats,
    reason: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "time_limit": context.time_limit,
        "seed": context.seed,
        "activities": context.instance.n_activities,
        "resources": context.instance.n_resources,
        "seed_construct_until_seconds": max(0.0, budgets.construct_until - context.started),
        "seed_improve_budget_seconds": budgets.improve_budget,
        "seed_proof_budget_seconds": max(0.0, budgets.proof_until - budgets.construct_until),
        "seed_construct_makespan": construct_makespan,
        "seed_improve_makespan": improve_makespan,
        "seed_proof_makespan": proof_makespan,
        "seed_polish_makespan": polish_makespan,
        "seed_best_source": best_source,
        "improvement_iterations": improvement_iterations,
        "search_nodes": exact_stats.nodes,
        "search_timed_out": exact_stats.timed_out,
        "forced_resource_orders": len(context.forced_edges),
    }
    if reason is not None:
        metadata["reason"] = reason
    return metadata


def _seed_result(
    context: SeedContext,
    *,
    status: str,
    schedule: Schedule | None,
    restarts: int,
    temporal_lower_bound: int,
    metadata: dict[str, object],
) -> SolveResult:
    runtime = time.perf_counter() - context.started
    return SolveResult(
        instance_name=context.instance.name,
        status=status,
        schedule=schedule,
        runtime_seconds=runtime,
        temporal_lower_bound=temporal_lower_bound,
        restarts=restarts,
        metadata=metadata,
    )


def _run_improve_phase(
    context: SeedContext,
    budgets: SeedBudgets,
    incumbent: Schedule | None,
    rng: random.Random,
) -> tuple[Schedule | None, int]:
    if incumbent is None or incumbent.makespan <= context.temporal_lower_bound:
        return incumbent, 0
    if time.perf_counter() >= context.soft_deadline:
        return incumbent, 0

    improve_until = min(context.soft_deadline, time.perf_counter() + budgets.improve_budget)
    improved_best, iterations = improve_incumbent(
        instance=context.instance,
        incumbent=incumbent,
        tail=context.tail,
        intensity=context.intensity,
        solver_config=context.solver_config,
        rng=rng,
        deadline=improve_until,
        base_extra_edges=context.forced_edges,
    )
    if improved_best.makespan < incumbent.makespan:
        incumbent = improved_best
    return incumbent, iterations


def _run_proof_phase(
    context: SeedContext,
    budgets: SeedBudgets,
    incumbent: Schedule | None,
) -> tuple[Schedule | None, SearchStats]:
    return branch_and_bound_search(
        instance=context.instance,
        tail=context.tail,
        intensity=context.intensity,
        deadline=budgets.proof_until,
        incumbent=incumbent,
        incremental_pairwise=context.time_limit >= 0.5,
        base_extra_edges=context.forced_edges,
    )


def _run_polish_phase(
    context: SeedContext,
    budgets: SeedBudgets,
    incumbent: Schedule | None,
    rng: random.Random,
) -> tuple[Schedule | None, int]:
    if incumbent is None or incumbent.makespan <= context.temporal_lower_bound:
        return incumbent, 0
    if context.time_limit < 0.5 or time.perf_counter() >= budgets.polish_until:
        return incumbent, 0

    polished_best, iterations = improve_incumbent(
        instance=context.instance,
        incumbent=incumbent,
        tail=context.tail,
        intensity=context.intensity,
        solver_config=context.solver_config,
        rng=rng,
        deadline=budgets.polish_until,
        base_extra_edges=context.forced_edges,
    )
    if polished_best.makespan < incumbent.makespan:
        incumbent = polished_best
    return incumbent, iterations


def solve(
    instance: Instance,
    time_limit: float = 30.0,
    seed: int = 0,
    config: HeuristicConfig | None = None,
) -> SolveResult:
    prepared = _prepare_seed_context(instance, time_limit, seed, config)
    if isinstance(prepared, SolveResult):
        return prepared

    context, rng = prepared
    budgets = _seed_budgets(context)

    best, restarts = _run_construct_phase(context, budgets, rng)
    best_source = "construct" if best is not None else "none"
    construct_makespan = best.makespan if best is not None else None
    best, improvement_iterations = _run_improve_phase(context, budgets, best, rng)
    improve_makespan = best.makespan if best is not None else None
    if best is not None and construct_makespan is None:
        best_source = "improve"
    elif best is not None and construct_makespan is not None and best.makespan < construct_makespan:
        best_source = "improve"
    exact_best, exact_stats = _run_proof_phase(context, budgets, best)
    proof_makespan = exact_best.makespan if exact_best is not None else None
    if exact_best is not None and (best is None or exact_best.makespan < best.makespan):
        best = exact_best
        best_source = "proof"
    best, polish_iterations = _run_polish_phase(context, budgets, best, rng)
    polish_makespan = best.makespan if best is not None else None
    proof_base = proof_makespan if proof_makespan is not None else improve_makespan
    if best is not None and proof_base is not None and best.makespan < proof_base:
        best_source = "polish"
    improvement_iterations += polish_iterations

    if best is None:
        return _seed_result(
            context,
            status="unknown" if exact_stats.timed_out else "infeasible",
            schedule=None,
            temporal_lower_bound=context.temporal_lower_bound,
            restarts=restarts,
            metadata=_seed_metadata(
                context,
                budgets,
                construct_makespan=construct_makespan,
                improve_makespan=improve_makespan,
                proof_makespan=proof_makespan,
                polish_makespan=polish_makespan,
                best_source=best_source,
                improvement_iterations=improvement_iterations,
                exact_stats=exact_stats,
                reason=(
                    "exact search exhausted without finding a feasible schedule"
                    if not exact_stats.timed_out
                    else "time limit reached before exact search could prove feasibility or infeasibility"
                ),
            ),
        )

    errors = validate_schedule(context.instance, best)
    if errors:
        return _seed_result(
            context,
            status="unknown",
            schedule=None,
            temporal_lower_bound=context.temporal_lower_bound,
            restarts=restarts,
            metadata=_seed_metadata(
                context,
                budgets,
                construct_makespan=construct_makespan,
                improve_makespan=improve_makespan,
                proof_makespan=proof_makespan,
                polish_makespan=polish_makespan,
                best_source=best_source,
                improvement_iterations=improvement_iterations,
                exact_stats=exact_stats,
                reason=errors[0],
            ),
        )

    return _seed_result(
        context,
        status="feasible",
        schedule=best,
        temporal_lower_bound=context.temporal_lower_bound,
        restarts=restarts,
        metadata=_seed_metadata(
            context,
            budgets,
            construct_makespan=construct_makespan,
            improve_makespan=improve_makespan,
            proof_makespan=proof_makespan,
            polish_makespan=polish_makespan,
            best_source=best_source,
            improvement_iterations=improvement_iterations,
            exact_stats=exact_stats,
        ),
    )
