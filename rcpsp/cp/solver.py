from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..models import Edge, Instance, Schedule, SolveResult
from ..heuristic.solver import (
    HeuristicConfig,
    _compress_valid_schedule,
    _pairwise_infeasibility_reason,
    _resource_intensity,
    _sample_heuristic_config,
    construct_schedule,
)
from ..temporal import TemporalInfeasibleError, longest_feasible_starts, longest_tail_to_sink
from ..validate import build_resource_profile, validate_schedule


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


def _overloaded_conflict(
    instance: Instance,
    start_times: list[int] | tuple[int, ...],
) -> tuple[int, int, list[int], list[int]] | None:
    profile = build_resource_profile(instance, start_times)
    for time_index, usage in enumerate(profile):
        overload = [max(0, usage[r] - instance.capacities[r]) for r in range(instance.n_resources)]
        if not any(amount > 0 for amount in overload):
            continue
        resource = max(range(instance.n_resources), key=lambda idx: overload[idx])
        active = [
            activity
            for activity in range(1, instance.sink)
            if start_times[activity] <= time_index < start_times[activity] + instance.durations[activity]
            and instance.demands[activity][resource] > 0
        ]
        if active:
            return time_index, resource, active, overload
    return None


def _mandatory_part_conflict(
    instance: Instance,
    lower: list[int],
    latest: list[int],
) -> tuple[int, int, int, list[int]] | None:
    for resource in range(instance.n_resources):
        boundaries: set[int] = set()
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
            boundaries.add(left)
            boundaries.add(right)

        if len(boundaries) <= 1:
            continue

        ordered = sorted(boundaries)
        for left_index, window_start in enumerate(ordered[:-1]):
            for window_end in ordered[left_index + 1 :]:
                if window_end <= window_start:
                    continue
                active = [
                    activity
                    for activity, left, right in mandatory
                    if left < window_end and right > window_start
                ]
                if len(active) <= 1:
                    continue
                usage = sum(instance.demands[activity][resource] for activity in active)
                if usage > instance.capacities[resource]:
                    return window_start, window_end, resource, active
    return None


def _choose_branch_pair(
    instance: Instance,
    lower: list[int],
    tail: list[int],
    intensity: list[float],
    activities: list[int],
    resource: int,
    existing_pairs: frozenset[tuple[int, int]],
    rng: random.Random,
) -> tuple[int, int] | None:
    def slack(activity: int) -> int:
        return lower[instance.sink] - (lower[activity] + tail[activity])

    scored: list[tuple[float, float, int, int]] = []
    for first_index, first in enumerate(activities):
        for second in activities[first_index + 1 :]:
            if (first, second) in existing_pairs or (second, first) in existing_pairs:
                continue
            if instance.demands[first][resource] == 0 or instance.demands[second][resource] == 0:
                continue
            shared = (
                instance.demands[first][resource] + instance.demands[second][resource]
            ) / max(1, instance.capacities[resource])
            urgency = -min(slack(first), slack(second))
            score = shared + 0.15 * (intensity[first] + intensity[second]) + 0.05 * urgency
            scored.append((score, rng.random(), first, second))
    if not scored:
        return None
    scored.sort(reverse=True)
    _, _, first, second = scored[0]
    return first, second


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
) -> CpNode | None:
    edges = tuple(
        Edge(source=source, target=target, lag=instance.durations[source])
        for source, target in sorted(pairs)
    )
    try:
        lower = longest_feasible_starts(instance, extra_edges=edges)
    except TemporalInfeasibleError:
        return None

    if incumbent_makespan is not None and lower[instance.sink] >= incumbent_makespan:
        return None

    latest = _improving_latest_starts(instance, tail, incumbent_makespan)
    if latest is not None:
        for activity in range(instance.n_activities):
            if lower[activity] > latest[activity]:
                return None
        if _mandatory_part_conflict(instance, lower, latest) is not None:
            return None

    return CpNode(
        lower=tuple(lower),
        latest=tuple(latest) if latest is not None else None,
        edges=edges,
        pairs=pairs,
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

    heuristic_deadline = min(final_deadline, started + min(1.0, max(0.05, time_limit * 0.2)))
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

    def dfs(pairs: frozenset[tuple[int, int]]) -> None:
        nonlocal incumbent
        if time.perf_counter() >= final_deadline:
            stats.timed_out = True
            return
        stats.nodes += 1

        key = tuple(sorted(pairs))
        if key in seen:
            return
        seen.add(key)

        node = _propagate_cp_node(
            instance=instance,
            tail=tail,
            pairs=pairs,
            incumbent_makespan=incumbent.makespan if incumbent is not None else None,
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

        conflict = _overloaded_conflict(instance, node.lower)
        if conflict is None:
            candidate_starts = _compress_valid_schedule(instance, lower)
            candidate = Schedule(start_times=tuple(candidate_starts), makespan=candidate_starts[instance.sink])
            if not validate_schedule(instance, candidate) and (
                incumbent is None or candidate.makespan < incumbent.makespan
            ):
                incumbent = candidate
                stats.incumbent_updates += 1
            return

        _, resource, active, _ = conflict
        pair = _choose_branch_pair(
            instance=instance,
            lower=lower,
            tail=tail,
            intensity=intensity,
            activities=active,
            resource=resource,
            existing_pairs=node.pairs,
            rng=rng,
        )
        if pair is None:
            return

        first, second = pair
        children: list[tuple[int, frozenset[tuple[int, int]]]] = []
        for source, target in ((first, second), (second, first)):
            child_pairs = frozenset(set(node.pairs) | {(source, target)})
            child = _propagate_cp_node(
                instance=instance,
                tail=tail,
                pairs=child_pairs,
                incumbent_makespan=incumbent.makespan if incumbent is not None else None,
            )
            if child is None:
                continue
            children.append((child.lower[instance.sink], child_pairs))
        children.sort(key=lambda item: item[0])

        for _, child_pairs in children:
            stats.branches += 1
            dfs(child_pairs)
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
