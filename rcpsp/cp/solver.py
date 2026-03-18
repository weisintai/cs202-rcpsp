from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..models import Edge, Instance, Schedule, SolveResult
from ..heuristic.solver import (
    _all_pairs_longest_lags,
    _branch_order,
    HeuristicConfig,
    _compress_valid_schedule,
    _extend_longest_lags,
    _minimal_conflict_set,
    _pairwise_infeasibility_reason_from_dist,
    _pairwise_infeasibility_reason,
    _resource_intensity,
    _sample_heuristic_config,
    construct_schedule,
)
from ..temporal import TemporalInfeasibleError, longest_feasible_starts, longest_tail_to_sink
from ..validate import validate_schedule


@dataclass
class CpSearchStats:
    nodes: int = 0
    timed_out: bool = False
    incumbent_updates: int = 0
    branches: int = 0


@dataclass(frozen=True)
class CpNode:
    lower: tuple[int, ...]
    latest: tuple[int, ...] | None
    edges: tuple[Edge, ...]
    pairs: frozenset[tuple[int, int]]
    lag_dist: list[list[float]] | None = None


def _tighten_latest_starts(
    instance: Instance,
    extra_edges: tuple[Edge, ...] | list[Edge],
    latest: list[int],
) -> list[int]:
    upper = latest[:]
    upper[instance.source] = 0
    all_edges = tuple(instance.edges) + tuple(extra_edges)

    for _ in range(instance.n_activities - 1):
        updated = False
        for edge in all_edges:
            candidate = upper[edge.target] - edge.lag
            if candidate < upper[edge.source]:
                upper[edge.source] = candidate
                updated = True
        upper[instance.source] = 0
        if not updated:
            return upper

    upper[instance.source] = 0
    return upper


def _build_mandatory_profile(
    instance: Instance,
    lower: list[int],
    latest: list[int],
) -> tuple[list[list[int]], list[tuple[list[tuple[int, int, int]], int]]]:
    horizon = max(
        lower[instance.sink],
        max((max(lower[activity], latest[activity]) + instance.durations[activity] for activity in range(instance.n_activities)), default=0),
    )
    profiles = [[0] * max(0, horizon) for _ in range(instance.n_resources)]
    mandatory_intervals: list[tuple[list[tuple[int, int, int]], int]] = []

    for resource in range(instance.n_resources):
        mandatory: list[tuple[int, int, int]] = []
        for activity in range(1, instance.sink):
            duration = instance.durations[activity]
            demand = instance.demands[activity][resource]
            if duration <= 0 or demand <= 0:
                continue
            left = latest[activity]
            right = lower[activity] + duration
            if left >= right:
                continue
            mandatory.append((activity, left, right))
            for time_index in range(max(0, left), min(horizon, right)):
                profiles[resource][time_index] += demand

        mandatory_intervals.append((mandatory, horizon))

    return profiles, mandatory_intervals


def _propagate_compulsory_parts(
    instance: Instance,
    lower: list[int],
    latest: list[int],
) -> tuple[bool, list[int], list[int]] | None:
    changed = False
    profiles, mandatory_intervals = _build_mandatory_profile(instance, lower, latest)

    for resource, (mandatory, horizon) in enumerate(mandatory_intervals):
        profile = profiles[resource]
        for time_index, usage in enumerate(profile):
            if usage <= instance.capacities[resource]:
                continue
            active = [
                activity
                for activity, left, right in mandatory
                if left <= time_index < right
            ]
            return None

        for activity in range(1, instance.sink):
            demand = instance.demands[activity][resource]
            duration = instance.durations[activity]
            if demand <= 0 or duration <= 0:
                continue

            own_left = latest[activity]
            own_right = lower[activity] + duration

            new_lower = lower[activity]
            while new_lower <= latest[activity]:
                moved = False
                for time_index in range(new_lower, min(horizon, new_lower + duration)):
                    load = profile[time_index]
                    if own_left < own_right and own_left <= time_index < own_right:
                        load -= demand
                    if load + demand > instance.capacities[resource]:
                        new_lower = time_index + 1
                        moved = True
                        break
                if not moved:
                    break

            if new_lower > latest[activity]:
                return None
            if new_lower > lower[activity]:
                lower[activity] = new_lower
                changed = True

            own_left = latest[activity]
            own_right = lower[activity] + duration
            new_latest = latest[activity]
            while new_latest >= lower[activity]:
                moved = False
                for time_index in range(new_latest, min(horizon, new_latest + duration)):
                    load = profile[time_index]
                    if own_left < own_right and own_left <= time_index < own_right:
                        load -= demand
                    if load + demand > instance.capacities[resource]:
                        new_latest = time_index - duration
                        moved = True
                        break
                if not moved:
                    break

            if new_latest < lower[activity]:
                return None
            if new_latest < latest[activity]:
                latest[activity] = new_latest
                changed = True

    return changed, lower, latest


def _improving_latest_starts(
    instance: Instance,
    tail: list[int],
    incumbent_makespan: int | None,
) -> list[int] | None:
    if incumbent_makespan is None:
        return None
    latest = [incumbent_makespan - 1 - tail[activity] for activity in range(instance.n_activities)]
    latest[instance.source] = 0
    return latest


def _propagate_cp_node(
    instance: Instance,
    tail: list[int],
    pairs: frozenset[tuple[int, int]],
    incumbent_makespan: int | None,
    base_lag_dist: list[list[float]] | None = None,
    new_edges: tuple[Edge, ...] = (),
) -> CpNode | None:
    local_pairs = set(pairs)
    if new_edges:
        for edge in new_edges:
            local_pairs.add((edge.source, edge.target))
    edges = [
        Edge(source=source, target=target, lag=instance.durations[source])
        for source, target in sorted(local_pairs)
    ]

    lag_dist = base_lag_dist
    if lag_dist is not None:
        updated = lag_dist
        for edge in new_edges:
            updated = _extend_longest_lags(updated, edge)
        lag_dist = updated
    elif incumbent_makespan is None:
        lag_dist = _all_pairs_longest_lags(instance, extra_edges=edges)

    latest = _improving_latest_starts(instance, tail, incumbent_makespan)
    release_times = [0] * instance.n_activities

    while True:
        try:
            lower = longest_feasible_starts(instance, release_times=release_times, extra_edges=edges)
        except TemporalInfeasibleError:
            return None

        if incumbent_makespan is not None and lower[instance.sink] >= incumbent_makespan:
            return None

        if incumbent_makespan is None and lag_dist is not None:
            if _pairwise_infeasibility_reason_from_dist(instance, lag_dist) is not None:
                return None

        if latest is None:
            break

        latest = _tighten_latest_starts(instance, edges, latest)
        if any(lower[activity] > latest[activity] for activity in range(instance.n_activities)):
            return None

        propagated = _propagate_compulsory_parts(instance, lower[:], latest[:])
        if propagated is None:
            return None

        changed, new_lower, new_latest = propagated
        if not changed:
            lower = new_lower
            latest = new_latest
            break

        release_times = new_lower
        latest = new_latest

    return CpNode(
        lower=tuple(lower),
        latest=tuple(latest) if latest is not None else None,
        edges=tuple(edges),
        pairs=frozenset(local_pairs),
        lag_dist=lag_dist,
    )


def _try_cp_incumbent(
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
        config=_sample_heuristic_config(solver_config, rng),
        deadline=deadline,
        base_extra_edges=node.edges,
        initial_starts=list(node.lower),
    )
    if validate_schedule(instance, schedule):
        return None
    return schedule


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

    pairwise_reason = _pairwise_infeasibility_reason(instance)
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

    intensity = _resource_intensity(instance)
    stats = CpSearchStats()
    seen: set[tuple[tuple[int, int], ...]] = set()
    incumbent: Schedule | None = None
    restarts = 0
    root_lag_dist = _all_pairs_longest_lags(instance)

    # Leave most of the budget to branch-and-propagate; the warm start only needs
    # enough time to find a usable incumbent.
    heuristic_budget = min(0.5, max(0.01, time_limit * 0.25))
    heuristic_deadline = min(final_deadline, started + heuristic_budget)
    while time.perf_counter() < heuristic_deadline:
        schedule = construct_schedule(
            instance=instance,
            rng=rng,
            tail=tail,
            intensity=intensity,
            config=_sample_heuristic_config(solver_config, rng),
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

        key = tuple(sorted(pairs))
        if key in seen:
            return
        seen.add(key)

        if node is None:
            node = _propagate_cp_node(
                instance=instance,
                tail=tail,
                pairs=pairs,
                incumbent_makespan=incumbent.makespan if incumbent is not None else None,
                base_lag_dist=root_lag_dist if not pairs and incumbent is None else None,
            )
            if node is None:
                return

        lower = list(node.lower)
        lower_schedule = Schedule(start_times=tuple(lower), makespan=lower[instance.sink])
        if not validate_schedule(instance, lower_schedule):
            candidate_starts = _compress_valid_schedule(instance, lower)
            candidate = Schedule(start_times=tuple(candidate_starts), makespan=candidate_starts[instance.sink])
            if incumbent is None or candidate.makespan < incumbent.makespan:
                incumbent = candidate
                stats.incumbent_updates += 1
            return

        if time.perf_counter() < final_deadline:
            local_budget = min(final_deadline, time.perf_counter() + min(0.02, max(0.002, time_limit * 0.01)))
            candidate = _try_cp_incumbent(
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

        conflict = _minimal_conflict_set(instance, lower)
        if conflict is None:
            candidate_starts = _compress_valid_schedule(instance, lower)
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

        ordered = _branch_order(
            instance=instance,
            start_times=lower,
            tail=tail,
            intensity=intensity,
            conflict=conflict_set,
            overload=overload,
        )
        children: list[tuple[int, int, frozenset[tuple[int, int]], CpNode]] = []
        for order_index, selected in enumerate(ordered):
            additions: list[Edge] = []
            child_pairs_set = set(node.pairs)
            for other in conflict_set:
                if other == selected or instance.demands[other][resource] == 0:
                    continue
                pair = (other, selected)
                if pair in child_pairs_set:
                    continue
                child_pairs_set.add(pair)
                additions.append(Edge(source=other, target=selected, lag=instance.durations[other]))

            if not additions:
                continue

            child_pairs = frozenset(child_pairs_set)
            child = _propagate_cp_node(
                instance=instance,
                tail=tail,
                pairs=child_pairs,
                incumbent_makespan=incumbent.makespan if incumbent is not None else None,
                base_lag_dist=node.lag_dist,
                new_edges=tuple(additions),
            )
            if child is None:
                continue
            children.append((child.lower[instance.sink], order_index, child_pairs, child))
        children.sort(key=lambda item: (item[0], item[1]))

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
        },
    )
