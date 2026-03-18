from __future__ import annotations

import random
import time

from ..config import HeuristicConfig, sample_heuristic_config
from ..core.branching import branch_order
from ..core.compress import compress_valid_schedule
from ..core.conflicts import minimal_conflict_set
from ..core.lag import all_pairs_longest_lags, pairwise_infeasibility_reason
from ..core.metrics import resource_intensity
from ..models import Edge, Instance, Schedule, SolveResult
from ..temporal import TemporalInfeasibleError, longest_feasible_starts, longest_tail_to_sink
from ..validate import validate_schedule
from ..heuristic.construct import construct_schedule
from ..heuristic.solver import solve as solve_heuristic
from .propagation import propagate_cp_node
from .state import CpNode, CpSearchStats


def try_cp_incumbent(
    instance: Instance,
    node: CpNode,
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
) -> Schedule | None:
    schedule = construct_schedule(
        instance=instance,
        rng=rng,
        tail=tail,
        intensity=intensity,
        config=sample_heuristic_config(solver_config, rng),
        deadline=deadline,
        base_extra_edges=node.edges,
        initial_starts=list(node.lower),
    )
    if validate_schedule(instance, schedule):
        return None
    return schedule


def branch_children(
    instance: Instance,
    node: CpNode,
    tail: list[int],
    intensity: list[float],
    conflict_set: list[int] | tuple[int, ...],
    resource: int,
    overload: list[int],
    incumbent_makespan: int | None,
    seen: set[tuple[tuple[tuple[int, int], ...], tuple[int, ...]]],
    stats: CpSearchStats,
) -> list[tuple[int, int, frozenset[tuple[int, int]], CpNode]]:
    ordered = branch_order(
        instance=instance,
        start_times=list(node.lower),
        tail=tail,
        intensity=intensity,
        conflict=list(conflict_set),
        overload=overload,
    )
    children: list[tuple[int, int, frozenset[tuple[int, int]], CpNode]] = []
    for order_index, selected in enumerate(ordered):
        for other in conflict_set:
            if other == selected or instance.demands[other][resource] == 0:
                continue
            pair = (other, selected)
            if pair in node.pairs:
                continue

            child_pairs = frozenset((*node.pairs, pair))
            child = propagate_cp_node(
                instance=instance,
                tail=tail,
                pairs=child_pairs,
                incumbent_makespan=incumbent_makespan,
                base_lag_dist=node.lag_dist if incumbent_makespan is None else None,
                new_edges=(Edge(source=other, target=selected, lag=instance.durations[other]),),
            )
            if child.overload is not None:
                stats.timetable_failures += 1
                stats.max_timetable_explanation = max(
                    stats.max_timetable_explanation,
                    child.overload.size,
                )
                continue
            if child.node is None:
                continue
            child_key = (tuple(sorted(child.node.pairs)), child.node.lower)
            if child_key in seen:
                continue
            children.append((child.node.lower[instance.sink], order_index, child.node.pairs, child.node))
    children.sort(key=lambda item: (item[0], item[1]))
    return children


def solve_cp(
    instance: Instance,
    time_limit: float = 30.0,
    seed: int = 0,
    config: HeuristicConfig | None = None,
) -> SolveResult:
    solver_config = config or HeuristicConfig()
    rng = random.Random(seed)
    started = time.perf_counter()
    final_deadline = started + time_limit

    try:
        temporal_lower = longest_feasible_starts(instance)
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
            metadata={"backend": "cp", "reason": str(exc), "seed": seed, "time_limit": time_limit},
        )

    pairwise_reason = pairwise_infeasibility_reason(instance)
    if pairwise_reason is not None:
        runtime = time.perf_counter() - started
        return SolveResult(
            instance_name=instance.name,
            status="infeasible",
            schedule=None,
            runtime_seconds=runtime,
            temporal_lower_bound=temporal_lower[instance.sink],
            restarts=0,
            metadata={"backend": "cp", "reason": pairwise_reason, "seed": seed, "time_limit": time_limit},
        )

    intensity = resource_intensity(instance)
    stats = CpSearchStats()
    seen: set[tuple[tuple[tuple[int, int], ...], tuple[int, ...]]] = set()
    incumbent: Schedule | None = None
    restarts = 0
    root_lag_dist = all_pairs_longest_lags(instance)

    heuristic_budget = min(0.75, max(0.01, time_limit * 0.25))
    heuristic_deadline = min(final_deadline, started + heuristic_budget)
    if heuristic_budget >= 0.15 and time.perf_counter() < heuristic_deadline:
        guided_budget = min(heuristic_budget * 0.8, heuristic_deadline - time.perf_counter())
        if guided_budget > 0:
            guided = solve_heuristic(
                instance=instance,
                time_limit=guided_budget,
                seed=seed,
                config=solver_config,
            )
            if guided.status == "feasible" and guided.schedule is not None:
                incumbent = guided.schedule
                stats.incumbent_updates += 1
            restarts += guided.restarts

    while time.perf_counter() < heuristic_deadline:
        schedule = construct_schedule(
            instance=instance,
            rng=rng,
            tail=tail,
            intensity=intensity,
            config=sample_heuristic_config(solver_config, rng),
            deadline=heuristic_deadline,
        )
        if validate_schedule(instance, schedule):
            restarts += 1
            continue
        if incumbent is None or schedule.makespan < incumbent.makespan:
            incumbent = schedule
            stats.incumbent_updates += 1
        restarts += 1
        if incumbent.makespan == temporal_lower[instance.sink]:
            break

    def dfs(pairs: frozenset[tuple[int, int]], node: CpNode | None = None) -> None:
        nonlocal incumbent
        if time.perf_counter() >= final_deadline:
            stats.timed_out = True
            return
        stats.nodes += 1

        if node is None:
            propagation = propagate_cp_node(
                instance=instance,
                tail=tail,
                pairs=pairs,
                incumbent_makespan=incumbent.makespan if incumbent is not None else None,
                base_lag_dist=root_lag_dist if not pairs and incumbent is None else None,
            )
            if propagation.overload is not None:
                stats.timetable_failures += 1
                stats.max_timetable_explanation = max(
                    stats.max_timetable_explanation,
                    propagation.overload.size,
                )
                return
            node = propagation.node
            if node is None:
                return

        key = (tuple(sorted(node.pairs)), node.lower)
        if key in seen:
            return
        seen.add(key)

        lower = list(node.lower)
        lower_schedule = Schedule(start_times=tuple(lower), makespan=lower[instance.sink])
        if not validate_schedule(instance, lower_schedule):
            candidate_starts = compress_valid_schedule(instance, lower)
            candidate = Schedule(start_times=tuple(candidate_starts), makespan=candidate_starts[instance.sink])
            if incumbent is None or candidate.makespan < incumbent.makespan:
                incumbent = candidate
                stats.incumbent_updates += 1
            return

        if time.perf_counter() < final_deadline:
            local_budget = min(final_deadline, time.perf_counter() + min(0.02, max(0.002, time_limit * 0.01)))
            candidate = try_cp_incumbent(
                instance=instance,
                node=node,
                tail=tail,
                intensity=intensity,
                solver_config=solver_config,
                rng=rng,
                deadline=local_budget,
            )
            if candidate is not None and (incumbent is None or candidate.makespan < incumbent.makespan):
                incumbent = candidate
                stats.incumbent_updates += 1
                if incumbent.makespan == temporal_lower[instance.sink]:
                    return

        conflict = minimal_conflict_set(instance, lower)
        if conflict is None:
            candidate_starts = compress_valid_schedule(instance, lower)
            candidate = Schedule(start_times=tuple(candidate_starts), makespan=candidate_starts[instance.sink])
            if not validate_schedule(instance, candidate) and (
                incumbent is None or candidate.makespan < incumbent.makespan
            ):
                incumbent = candidate
                stats.incumbent_updates += 1
            return

        _, resource, conflict_set, overload = conflict
        if len(conflict_set) <= 1:
            return

        children = branch_children(
            instance=instance,
            node=node,
            tail=tail,
            intensity=intensity,
            conflict_set=conflict_set,
            resource=resource,
            overload=overload,
            incumbent_makespan=incumbent.makespan if incumbent is not None else None,
            seen=seen,
            stats=stats,
        )

        for _, _, child_pairs, child in children:
            stats.branches += 1
            dfs(child_pairs, child)
            if stats.timed_out:
                return
            if incumbent is not None and incumbent.makespan == temporal_lower[instance.sink]:
                return

    dfs(frozenset())

    runtime = time.perf_counter() - started
    if incumbent is None:
        return SolveResult(
            instance_name=instance.name,
            status="unknown" if stats.timed_out else "infeasible",
            schedule=None,
            runtime_seconds=runtime,
            temporal_lower_bound=temporal_lower[instance.sink],
            restarts=restarts,
            metadata={
                "backend": "cp",
                "seed": seed,
                "time_limit": time_limit,
                "search_nodes": stats.nodes,
                "timed_out": stats.timed_out,
                "incumbent_updates": stats.incumbent_updates,
                "branches": stats.branches,
                "timetable_failures": stats.timetable_failures,
                "max_timetable_explanation": stats.max_timetable_explanation,
            },
        )

    return SolveResult(
        instance_name=instance.name,
        status="feasible",
        schedule=incumbent,
        runtime_seconds=runtime,
        temporal_lower_bound=temporal_lower[instance.sink],
        restarts=restarts,
        metadata={
            "backend": "cp",
            "seed": seed,
            "time_limit": time_limit,
            "search_nodes": stats.nodes,
            "timed_out": stats.timed_out,
            "incumbent_updates": stats.incumbent_updates,
            "branches": stats.branches,
            "timetable_failures": stats.timetable_failures,
            "max_timetable_explanation": stats.max_timetable_explanation,
        },
    )
