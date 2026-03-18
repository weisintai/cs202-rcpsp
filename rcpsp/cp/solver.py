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
    solve as solve_heuristic,
)
from ..temporal import TemporalInfeasibleError, longest_feasible_starts, longest_tail_to_sink
from ..validate import validate_schedule


@dataclass
class CpSearchStats:
    nodes: int = 0
    timed_out: bool = False
    incumbent_updates: int = 0
    branches: int = 0
    timetable_failures: int = 0
    max_timetable_explanation: int = 0


@dataclass(frozen=True)
class CpNode:
    lower: tuple[int, ...]
    latest: tuple[int, ...] | None
    edges: tuple[Edge, ...]
    pairs: frozenset[tuple[int, int]]
    lag_dist: list[list[float]] | None = None


@dataclass(frozen=True)
class OverloadExplanation:
    kind: str
    resource: int
    window_start: int
    window_end: int
    activities: tuple[int, ...]
    required: int
    limit: int

    @property
    def size(self) -> int:
        return len(self.activities)

    def summary(self) -> str:
        activities = ",".join(str(activity) for activity in self.activities)
        return (
            f"{self.kind} overload on resource {self.resource} in "
            f"[{self.window_start},{self.window_end}) by activities [{activities}] "
            f"with load {self.required}>{self.limit}"
        )


@dataclass(frozen=True)
class CpNodePropagation:
    node: CpNode | None
    overload: OverloadExplanation | None = None


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


def _minimal_overload_explanation(
    instance: Instance,
    resource: int,
    time_index: int,
    mandatory: list[tuple[int, int, int]],
) -> OverloadExplanation:
    active = [
        activity
        for activity, left, right in mandatory
        if left <= time_index < right
    ]
    total = sum(instance.demands[activity][resource] for activity in active)
    conflict = active[:]
    while conflict:
        smallest = min(
            conflict,
            key=lambda activity: (
                instance.demands[activity][resource],
                instance.durations[activity],
                activity,
            ),
        )
        if total - instance.demands[smallest][resource] > instance.capacities[resource]:
            total -= instance.demands[smallest][resource]
            conflict.remove(smallest)
        else:
            break
    conflict.sort()
    return OverloadExplanation(
        kind="point",
        resource=resource,
        window_start=time_index,
        window_end=time_index + 1,
        activities=tuple(conflict),
        required=total,
        limit=instance.capacities[resource],
    )


def _minimum_overlap_in_window(
    est: int,
    lst: int,
    duration: int,
    window_start: int,
    window_end: int,
) -> int:
    before = max(0, window_start - est)
    after = max(0, lst + duration - window_end)
    return max(0, duration - before - after)


def _propagate_compulsory_parts(
    instance: Instance,
    lower: list[int],
    latest: list[int],
) -> tuple[bool, list[int], list[int], OverloadExplanation | None] | None:
    changed = False
    profiles, mandatory_intervals = _build_mandatory_profile(instance, lower, latest)

    for resource, (mandatory, horizon) in enumerate(mandatory_intervals):
        profile = profiles[resource]
        for time_index, usage in enumerate(profile):
            if usage <= instance.capacities[resource]:
                continue
            explanation = _minimal_overload_explanation(instance, resource, time_index, mandatory)
            return changed, lower, latest, explanation

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

    return changed, lower, latest, None


def _forced_pair_order_propagation(
    instance: Instance,
    lower: list[int],
    latest: list[int],
    pairs: set[tuple[int, int]],
) -> tuple[tuple[tuple[int, int], ...], OverloadExplanation | None]:
    if instance.n_jobs < 20:
        return (), None

    inferred: list[tuple[int, int]] = []
    pending = set(pairs)

    for first in range(1, instance.sink):
        for second in range(first + 1, instance.sink):
            if (first, second) in pending or (second, first) in pending:
                continue

            forced_pair: tuple[int, int] | None = None
            blocking_resource: int | None = None

            for resource in range(instance.n_resources):
                combined_demand = instance.demands[first][resource] + instance.demands[second][resource]
                if combined_demand <= instance.capacities[resource]:
                    continue

                first_before_second = lower[first] + instance.durations[first] <= latest[second]
                second_before_first = lower[second] + instance.durations[second] <= latest[first]

                if not first_before_second and not second_before_first:
                    window_start = max(lower[first], lower[second])
                    window_end = min(
                        latest[first] + instance.durations[first],
                        latest[second] + instance.durations[second],
                    )
                    return (), OverloadExplanation(
                        kind="pair",
                        resource=resource,
                        window_start=window_start,
                        window_end=max(window_start + 1, window_end),
                        activities=(first, second),
                        required=combined_demand,
                        limit=instance.capacities[resource],
                    )

                if first_before_second == second_before_first:
                    continue

                candidate = (first, second) if first_before_second else (second, first)
                if forced_pair is not None and forced_pair != candidate:
                    window_start = max(lower[first], lower[second])
                    window_end = min(
                        latest[first] + instance.durations[first],
                        latest[second] + instance.durations[second],
                    )
                    resource = blocking_resource if blocking_resource is not None else resource
                    return (), OverloadExplanation(
                        kind="pair",
                        resource=resource,
                        window_start=window_start,
                        window_end=max(window_start + 1, window_end),
                        activities=(first, second),
                        required=combined_demand,
                        limit=instance.capacities[resource],
                    )
                forced_pair = candidate
                blocking_resource = resource

            if forced_pair is not None and forced_pair not in pending:
                pending.add(forced_pair)
                inferred.append(forced_pair)

    return tuple(inferred), None


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
    release_times: tuple[int, ...] | list[int] | None = None,
) -> CpNodePropagation:
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
    release_bounds = [0] * instance.n_activities if release_times is None else [max(0, int(value)) for value in release_times]

    while True:
        try:
            lower = longest_feasible_starts(instance, release_times=release_bounds, extra_edges=edges)
        except TemporalInfeasibleError:
            return CpNodePropagation(node=None)

        if incumbent_makespan is not None and lower[instance.sink] >= incumbent_makespan:
            return CpNodePropagation(node=None)

        if incumbent_makespan is None and lag_dist is not None:
            if _pairwise_infeasibility_reason_from_dist(instance, lag_dist) is not None:
                return CpNodePropagation(node=None)

        if latest is None:
            break

        latest = _tighten_latest_starts(instance, edges, latest)
        if any(lower[activity] > latest[activity] for activity in range(instance.n_activities)):
            return CpNodePropagation(node=None)

        propagated = _propagate_compulsory_parts(instance, lower[:], latest[:])
        if propagated is None:
            return CpNodePropagation(node=None)

        changed, new_lower, new_latest, overload = propagated
        if overload is not None:
            return CpNodePropagation(
                node=CpNode(
                    lower=tuple(new_lower),
                    latest=tuple(new_latest),
                    edges=tuple(edges),
                    pairs=frozenset(local_pairs),
                    lag_dist=lag_dist,
                ),
                overload=overload,
            )
        lower = new_lower
        latest = new_latest

        inferred_pairs, pair_overload = _forced_pair_order_propagation(instance, lower, latest, local_pairs)
        if pair_overload is not None:
            return CpNodePropagation(
                node=CpNode(
                    lower=tuple(lower),
                    latest=tuple(latest),
                    edges=tuple(edges),
                    pairs=frozenset(local_pairs),
                    lag_dist=lag_dist,
                ),
                overload=pair_overload,
            )

        if inferred_pairs:
            for source, target in inferred_pairs:
                local_pairs.add((source, target))
                edge = Edge(source=source, target=target, lag=instance.durations[source])
                edges.append(edge)
                if lag_dist is not None:
                    lag_dist = _extend_longest_lags(lag_dist, edge)
            release_bounds = lower
            continue

        if not changed:
            break

        release_bounds = lower

    return CpNodePropagation(
        node=CpNode(
            lower=tuple(lower),
            latest=tuple(latest) if latest is not None else None,
            edges=tuple(edges),
            pairs=frozenset(local_pairs),
            lag_dist=lag_dist,
        )
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


def _branch_children(
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
    ordered = _branch_order(
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
            child = _propagate_cp_node(
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
    seen: set[tuple[tuple[tuple[int, int], ...], tuple[int, ...]]] = set()
    incumbent: Schedule | None = None
    restarts = 0
    root_lag_dist = _all_pairs_longest_lags(instance)

    # Leave most of the budget to branch-and-propagate, but use a stronger
    # heuristic warm start on larger budgets so timetable propagation gets a
    # meaningful incumbent bound to work with.
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

        if node is None:
            propagation = _propagate_cp_node(
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

        children = _branch_children(
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
