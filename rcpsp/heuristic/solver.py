from __future__ import annotations

import random
import time

from ..config import HeuristicConfig, sample_heuristic_config
from ..core.lag import (
    all_pairs_longest_lags,
    forced_resource_order_edges_from_dist,
    pairwise_infeasibility_reason_from_dist,
)
from ..core.metrics import resource_intensity
from ..models import Instance, Schedule, SolveResult
from ..temporal import TemporalInfeasibleError, longest_feasible_starts, longest_tail_to_sink
from ..validate import validate_schedule
from .construct import construct_schedule
from .exact import branch_and_bound_search
from .improve import improve_incumbent


def solve(
    instance: Instance,
    time_limit: float = 30.0,
    seed: int = 0,
    config: HeuristicConfig | None = None,
) -> SolveResult:
    solver_config = config or HeuristicConfig()
    rng = random.Random(seed)
    started = time.perf_counter()

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
        forced_edges, lag_dist = forced_resource_order_edges_from_dist(instance, lag_dist)
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

    temporal_lower_bound = temporal_lb_schedule[instance.sink]
    forced_edge_count = len(forced_edges)

    intensity = resource_intensity(instance)

    best = Schedule(
        start_times=tuple(temporal_lb_schedule),
        makespan=10**12,
    )
    best_valid = False
    restarts = 0
    search_nodes = 0
    search_timed_out = False
    improvement_iterations = 0
    final_deadline = started + time_limit
    safety_margin = min(max(0.001, time_limit * 0.005), max(0.001, time_limit * 0.05))
    soft_deadline = max(started, final_deadline - safety_margin)
    heuristic_deadline = min(soft_deadline, started + min(1.0, max(0.01, time_limit * 0.2)))

    while True:
        now = time.perf_counter()
        if now >= heuristic_deadline:
            break
        if solver_config.max_restarts is not None and restarts >= solver_config.max_restarts:
            break

        local_config = sample_heuristic_config(solver_config, rng)
        schedule = construct_schedule(
            instance,
            rng,
            tail,
            intensity,
            local_config,
            deadline=heuristic_deadline,
            base_extra_edges=forced_edges,
            initial_starts=temporal_lb_schedule,
        )
        restarts += 1
        if validate_schedule(instance, schedule):
            continue
        if schedule.makespan < best.makespan:
            best = schedule
            best_valid = True
        if best.makespan == temporal_lower_bound:
            break

    exact_deadline = final_deadline
    if (
        best_valid
        and best.makespan > temporal_lower_bound
        and time.perf_counter() < soft_deadline
    ):
        improvement_budget = min(5.0, max(0.02, time_limit * 0.35))
        improve_until = min(soft_deadline, time.perf_counter() + improvement_budget)
        improved_best, improvement_iterations = improve_incumbent(
            instance=instance,
            incumbent=best,
            tail=tail,
            intensity=intensity,
            solver_config=solver_config,
            rng=rng,
            deadline=improve_until,
            base_extra_edges=tuple(forced_edges),
        )
        if improved_best.makespan < best.makespan:
            best = improved_best
        exact_deadline = soft_deadline

    exact_best, exact_stats = branch_and_bound_search(
        instance=instance,
        tail=tail,
        intensity=intensity,
        deadline=exact_deadline,
        incumbent=best if best_valid else None,
        incremental_pairwise=time_limit >= 0.5,
        base_extra_edges=tuple(forced_edges),
    )
    search_nodes = exact_stats.nodes
    search_timed_out = exact_stats.timed_out
    if exact_best is not None and (not best_valid or exact_best.makespan < best.makespan):
        best = exact_best
        best_valid = True

    if (
        best_valid
        and best.makespan > temporal_lower_bound
        and time_limit >= 0.5
        and time.perf_counter() < soft_deadline
    ):
        polished_best, extra_iterations = improve_incumbent(
            instance=instance,
            incumbent=best,
            tail=tail,
            intensity=intensity,
            solver_config=solver_config,
            rng=rng,
            deadline=soft_deadline,
            base_extra_edges=tuple(forced_edges),
        )
        improvement_iterations += extra_iterations
        if polished_best.makespan < best.makespan:
            best = polished_best

    if not best_valid:
        runtime = time.perf_counter() - started
        return SolveResult(
            instance_name=instance.name,
            status="unknown" if search_timed_out else "infeasible",
            schedule=None,
            runtime_seconds=runtime,
            temporal_lower_bound=temporal_lower_bound,
            restarts=restarts,
            metadata={
                "time_limit": time_limit,
                "seed": seed,
                "activities": instance.n_activities,
                "resources": instance.n_resources,
                "improvement_iterations": improvement_iterations,
                "search_nodes": search_nodes,
                "search_timed_out": search_timed_out,
                "forced_resource_orders": forced_edge_count,
                "reason": "exact search exhausted without finding a feasible schedule"
                if not search_timed_out
                else "time limit reached before exact search could prove feasibility or infeasibility",
            },
        )

    errors = validate_schedule(instance, best)
    if errors:
        runtime = time.perf_counter() - started
        return SolveResult(
            instance_name=instance.name,
            status="unknown",
            schedule=None,
            runtime_seconds=runtime,
            temporal_lower_bound=temporal_lower_bound,
            restarts=restarts,
            metadata={
                "reason": errors[0],
                "seed": seed,
                "time_limit": time_limit,
                "improvement_iterations": improvement_iterations,
                "search_nodes": search_nodes,
                "search_timed_out": search_timed_out,
                "forced_resource_orders": forced_edge_count,
            },
        )

    runtime = time.perf_counter() - started
    return SolveResult(
        instance_name=instance.name,
        status="feasible",
        schedule=best,
        runtime_seconds=runtime,
        temporal_lower_bound=temporal_lower_bound,
        restarts=restarts,
        metadata={
            "time_limit": time_limit,
            "seed": seed,
            "activities": instance.n_activities,
            "resources": instance.n_resources,
            "improvement_iterations": improvement_iterations,
            "search_nodes": search_nodes,
            "search_timed_out": search_timed_out,
            "forced_resource_orders": forced_edge_count,
        },
    )
