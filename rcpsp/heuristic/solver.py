from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..models import Edge, Instance, Schedule, SolveResult
from ..temporal import TemporalInfeasibleError, longest_feasible_starts, longest_tail_to_sink
from ..validate import build_resource_profile, validate_schedule


@dataclass(frozen=True)
class HeuristicConfig:
    slack_weight: float = 3.5
    tail_weight: float = 1.2
    overload_weight: float = 2.5
    resource_weight: float = 0.6
    late_weight: float = 0.3
    noise_weight: float = 0.2
    max_restarts: int | None = None


@dataclass
class SearchStats:
    nodes: int = 0
    timed_out: bool = False


def _resource_intensity(instance: Instance) -> list[float]:
    values = [0.0] * instance.n_activities
    for activity in range(instance.n_activities):
        intensity = 0.0
        for resource in range(instance.n_resources):
            capacity = instance.capacities[resource]
            if capacity == 0:
                continue
            intensity += instance.demands[activity][resource] / capacity
        values[activity] = intensity
    return values


def _all_pairs_longest_lags(instance: Instance, extra_edges: list[Edge] | tuple[Edge, ...] = ()) -> list[list[float]]:
    n = instance.n_activities
    neg_inf = float("-inf")
    dist = [[neg_inf] * n for _ in range(n)]
    for activity in range(n):
        dist[activity][activity] = 0
    for edge in tuple(instance.edges) + tuple(extra_edges):
        dist[edge.source][edge.target] = max(dist[edge.source][edge.target], edge.lag)
    for via in range(n):
        for source in range(n):
            if dist[source][via] == neg_inf:
                continue
            for target in range(n):
                if dist[via][target] == neg_inf:
                    continue
                candidate = dist[source][via] + dist[via][target]
                if candidate > dist[source][target]:
                    dist[source][target] = candidate
    return dist


def _extend_longest_lags(dist: list[list[float]], edge: Edge) -> list[list[float]]:
    if dist[edge.source][edge.target] >= edge.lag:
        return dist

    neg_inf = float("-inf")
    n = len(dist)
    updated = [row[:] for row in dist]
    updated[edge.source][edge.target] = edge.lag

    for source in range(n):
        left = dist[source][edge.source]
        if left == neg_inf:
            continue
        for target in range(n):
            right = dist[edge.target][target]
            if right == neg_inf:
                continue
            candidate = left + edge.lag + right
            if candidate > updated[source][target]:
                updated[source][target] = candidate
    return updated


def _pairwise_infeasibility_reason_from_dist(instance: Instance, dist: list[list[float]]) -> str | None:
    for first in range(1, instance.sink):
        for second in range(first + 1, instance.sink):
            lower = dist[first][second]
            upper = float("inf") if dist[second][first] == float("-inf") else -dist[second][first]
            mandatory_overlap = lower > -instance.durations[second] and upper < instance.durations[first]
            if not mandatory_overlap:
                continue
            for resource in range(instance.n_resources):
                demand = instance.demands[first][resource] + instance.demands[second][resource]
                if demand > instance.capacities[resource]:
                    return (
                        f"activities {first} and {second} must overlap and need {demand} units "
                        f"of resource {resource}, exceeding capacity {instance.capacities[resource]}"
                    )
    return None


def _pairwise_infeasibility_reason(
    instance: Instance,
    extra_edges: list[Edge] | tuple[Edge, ...] = (),
) -> str | None:
    for activity in range(instance.n_activities):
        for resource in range(instance.n_resources):
            if instance.demands[activity][resource] > instance.capacities[resource]:
                return (
                    f"activity {activity} exceeds capacity of resource {resource}: "
                    f"{instance.demands[activity][resource]} > {instance.capacities[resource]}"
                )

    dist = _all_pairs_longest_lags(instance, extra_edges)
    return _pairwise_infeasibility_reason_from_dist(instance, dist)


def _first_conflict(instance: Instance, start_times: list[int]) -> tuple[int, list[int], list[int]] | None:
    profile = build_resource_profile(instance, start_times)
    for t, usage in enumerate(profile):
        overload = [max(0, usage[r] - instance.capacities[r]) for r in range(instance.n_resources)]
        if any(amount > 0 for amount in overload):
            active = [
                activity
                for activity in range(1, instance.sink)
                if start_times[activity] <= t < start_times[activity] + instance.durations[activity]
            ]
            return t, overload, active
    return None


def _delay_scores(
    instance: Instance,
    start_times: list[int],
    makespan: int,
    tail: list[int],
    overload: list[int],
    active: list[int],
    intensity: list[float],
    rng: random.Random,
    config: HeuristicConfig,
) -> list[tuple[float, int]]:
    ranked: list[tuple[float, int]] = []
    for activity in active:
        slack = makespan - (start_times[activity] + tail[activity])
        overload_contribution = 0.0
        for resource, overload_amount in enumerate(overload):
            if overload_amount <= 0:
                continue
            overload_contribution += min(instance.demands[activity][resource], overload_amount)
        score = (
            config.slack_weight * slack
            - config.tail_weight * tail[activity]
            + config.overload_weight * overload_contribution
            + config.resource_weight * intensity[activity]
            + config.late_weight * start_times[activity]
            + config.noise_weight * rng.random()
        )
        ranked.append((score, activity))
    ranked.sort(reverse=True)
    return ranked


def _shared_resource_overload(
    instance: Instance,
    selected: int,
    other: int,
    overload: list[int],
) -> bool:
    return any(
        overload[resource] > 0
        and instance.demands[selected][resource] > 0
        and instance.demands[other][resource] > 0
        for resource in range(instance.n_resources)
    )


def _left_shift(instance: Instance, start_times: list[int], extra_edges: list[Edge]) -> list[int]:
    schedule = start_times[:]
    profile = build_resource_profile(instance, schedule)
    extra_incoming: list[list[Edge]] = [[] for _ in range(instance.n_activities)]
    for edge in extra_edges:
        extra_incoming[edge.target].append(edge)

    def ensure_horizon(horizon: int) -> None:
        while len(profile) < horizon:
            profile.append([0] * instance.n_resources)

    for _ in range(instance.n_activities):
        changed = False
        ordered = sorted(range(1, instance.n_activities), key=lambda activity: (schedule[activity], activity))
        for activity in ordered:
            duration = instance.durations[activity]
            current_start = schedule[activity]

            if duration > 0:
                for t in range(current_start, current_start + duration):
                    row = profile[t]
                    for resource in range(instance.n_resources):
                        row[resource] -= instance.demands[activity][resource]

            earliest = 0
            for edge in instance.incoming[activity]:
                earliest = max(earliest, schedule[edge.source] + edge.lag)
            for edge in extra_incoming[activity]:
                earliest = max(earliest, schedule[edge.source] + edge.lag)

            candidate = earliest
            if duration > 0:
                while candidate < current_start:
                    ensure_horizon(candidate + duration)
                    feasible = True
                    for t in range(candidate, candidate + duration):
                        row = profile[t]
                        for resource in range(instance.n_resources):
                            if row[resource] + instance.demands[activity][resource] > instance.capacities[resource]:
                                feasible = False
                                candidate = t + 1
                                break
                        if not feasible:
                            break
                    if feasible:
                        break
                if candidate >= current_start:
                    candidate = current_start

            if candidate < current_start:
                schedule[activity] = candidate
                changed = True

            new_start = schedule[activity]
            if duration > 0:
                ensure_horizon(new_start + duration)
                for t in range(new_start, new_start + duration):
                    row = profile[t]
                    for resource in range(instance.n_resources):
                        row[resource] += instance.demands[activity][resource]

        if not changed:
            break

    schedule[instance.source] = 0
    schedule[instance.sink] = max(
        (schedule[edge.source] + edge.lag for edge in instance.incoming[instance.sink]),
        default=0,
    )
    return schedule


def _resource_order_edges(instance: Instance, start_times: list[int]) -> list[Edge]:
    edges: list[Edge] = []
    for first in range(1, instance.sink):
        for second in range(first + 1, instance.sink):
            shared = any(
                instance.demands[first][resource] > 0 and instance.demands[second][resource] > 0
                for resource in range(instance.n_resources)
            )
            if not shared:
                continue

            first_end = start_times[first] + instance.durations[first]
            second_end = start_times[second] + instance.durations[second]
            if first_end <= start_times[second]:
                edges.append(Edge(source=first, target=second, lag=instance.durations[first]))
            elif second_end <= start_times[first]:
                edges.append(Edge(source=second, target=first, lag=instance.durations[second]))
    return edges


def _compress_valid_schedule(instance: Instance, start_times: list[int]) -> list[int]:
    current = start_times[:]
    resource_edges = _resource_order_edges(instance, current)
    if not resource_edges:
        return current

    try:
        compressed = longest_feasible_starts(instance, extra_edges=resource_edges)
    except TemporalInfeasibleError:
        return current

    candidate = Schedule(start_times=tuple(compressed), makespan=compressed[instance.sink])
    if validate_schedule(instance, candidate):
        return current
    return compressed


def _normalized_time_loads(instance: Instance, start_times: list[int] | tuple[int, ...]) -> list[float]:
    profile = build_resource_profile(instance, start_times)
    loads: list[float] = []
    for usage in profile:
        load = 0.0
        for resource, amount in enumerate(usage):
            capacity = instance.capacities[resource]
            if capacity == 0:
                continue
            load += amount / capacity
        loads.append(load)
    return loads


def _sample_removal_size(instance: Instance, rng: random.Random) -> int:
    minimum = 2 if instance.n_jobs <= 10 else 3
    maximum = max(minimum, min(instance.n_jobs - 1, max(3, instance.n_jobs // 3)))
    return rng.randint(minimum, maximum)


def _mobility_removal_set(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    rng: random.Random,
    size: int,
) -> set[int]:
    scored = []
    for activity in range(1, instance.sink):
        slack = schedule.makespan - (schedule.start_times[activity] + tail[activity])
        scored.append((slack, rng.random(), activity))
    scored.sort(reverse=True)
    pool = [activity for _, _, activity in scored[: max(size, min(len(scored), size * 2))]]
    if len(pool) <= size:
        return set(pool)
    return set(rng.sample(pool, size))


def _non_peak_removal_set(
    instance: Instance,
    schedule: Schedule,
    rng: random.Random,
    size: int,
) -> set[int]:
    loads = _normalized_time_loads(instance, schedule.start_times)
    scored = []
    for activity in range(1, instance.sink):
        start = schedule.start_times[activity]
        duration = instance.durations[activity]
        if duration == 0 or start >= len(loads):
            average_load = 0.0
        else:
            window = loads[start : start + duration]
            average_load = sum(window) / max(1, len(window))
        scored.append((average_load, rng.random(), activity))
    scored.sort()
    pool = [activity for _, _, activity in scored[: max(size, min(len(scored), size * 2))]]
    if len(pool) <= size:
        return set(pool)
    return set(rng.sample(pool, size))


def _segment_removal_set(
    instance: Instance,
    schedule: Schedule,
    rng: random.Random,
    size: int,
) -> set[int]:
    if schedule.makespan <= 0:
        return _mobility_removal_set(instance, schedule, [0] * instance.n_activities, rng, size)

    center = rng.randrange(max(1, schedule.makespan))
    half_width = max(1, schedule.makespan // max(6, instance.n_jobs))
    left = max(0, center - half_width)
    right = center + half_width + 1
    overlapping = [
        activity
        for activity in range(1, instance.sink)
        if schedule.start_times[activity] < right
        and schedule.start_times[activity] + instance.durations[activity] > left
    ]
    if len(overlapping) <= size:
        return set(overlapping)
    return set(rng.sample(overlapping, size))


def _random_removal_set(instance: Instance, rng: random.Random, size: int) -> set[int]:
    activities = list(range(1, instance.sink))
    if len(activities) <= size:
        return set(activities)
    return set(rng.sample(activities, size))


def _sample_removal_set(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    rng: random.Random,
) -> set[int]:
    size = _sample_removal_size(instance, rng)
    operator = rng.choice(("mobility", "non_peak", "segment", "random"))
    if operator == "mobility":
        removed = _mobility_removal_set(instance, schedule, tail, rng, size)
    elif operator == "non_peak":
        removed = _non_peak_removal_set(instance, schedule, rng, size)
    elif operator == "segment":
        removed = _segment_removal_set(instance, schedule, rng, size)
    else:
        removed = _random_removal_set(instance, rng, size)
    return removed or _random_removal_set(instance, rng, min(size, instance.n_jobs))


def _repair_schedule_subset(
    instance: Instance,
    schedule: Schedule,
    removed: set[int],
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
) -> Schedule | None:
    base_edges = [
        edge
        for edge in _resource_order_edges(instance, list(schedule.start_times))
        if edge.source not in removed and edge.target not in removed
    ]
    try:
        initial_starts = longest_feasible_starts(instance, extra_edges=base_edges)
    except TemporalInfeasibleError:
        return None

    candidate = construct_schedule(
        instance=instance,
        rng=rng,
        tail=tail,
        intensity=intensity,
        config=_sample_heuristic_config(solver_config, rng),
        deadline=deadline,
        base_extra_edges=base_edges,
        initial_starts=initial_starts,
    )
    if validate_schedule(instance, candidate):
        return None
    return candidate


def _update_elite_pool(elite: list[Schedule], candidate: Schedule, limit: int = 4) -> None:
    if any(existing.start_times == candidate.start_times for existing in elite):
        return
    elite.append(candidate)
    elite.sort(key=lambda schedule: (schedule.makespan, schedule.start_times))
    del elite[limit:]


def _improve_incumbent(
    instance: Instance,
    incumbent: Schedule,
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
) -> tuple[Schedule, int]:
    best = incumbent
    elite = [incumbent]
    iterations = 0
    stagnation = 0

    while time.perf_counter() < deadline:
        base = elite[0] if stagnation < 4 else rng.choice(elite[: min(len(elite), 3)])
        removed = _sample_removal_set(instance, base, tail, rng)
        candidate = _repair_schedule_subset(
            instance=instance,
            schedule=base,
            removed=removed,
            tail=tail,
            intensity=intensity,
            solver_config=solver_config,
            rng=rng,
            deadline=deadline,
        )
        iterations += 1
        if candidate is None:
            stagnation += 1
            continue

        _update_elite_pool(elite, candidate)
        if candidate.makespan < best.makespan:
            best = candidate
            elite[0] = best
            elite.sort(key=lambda schedule: (schedule.makespan, schedule.start_times))
            stagnation = 0
        elif candidate.makespan < base.makespan:
            stagnation = max(0, stagnation - 1)
        else:
            stagnation += 1

    return best, iterations


def _minimal_conflict_set(
    instance: Instance,
    start_times: list[int],
) -> tuple[int, int, list[int], list[int]] | None:
    profile = build_resource_profile(instance, start_times)
    for t, usage in enumerate(profile):
        overloaded = [resource for resource in range(instance.n_resources) if usage[resource] > instance.capacities[resource]]
        if not overloaded:
            continue
        resource = max(overloaded, key=lambda idx: usage[idx] - instance.capacities[idx])
        active = [
            activity
            for activity in range(1, instance.sink)
            if start_times[activity] <= t < start_times[activity] + instance.durations[activity]
            and instance.demands[activity][resource] > 0
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
        conflict.sort(key=lambda activity: (start_times[activity], activity))
        overload = [max(0, usage[r] - instance.capacities[r]) for r in range(instance.n_resources)]
        return t, resource, conflict, overload
    return None


def _branch_order(
    instance: Instance,
    start_times: list[int],
    tail: list[int],
    intensity: list[float],
    conflict: list[int],
    overload: list[int],
) -> list[int]:
    makespan = start_times[instance.sink]
    ranked = _delay_scores(
        instance=instance,
        start_times=start_times,
        makespan=makespan,
        tail=tail,
        overload=overload,
        active=conflict,
        intensity=intensity,
        rng=random.Random(0),
        config=HeuristicConfig(noise_weight=0.0),
    )
    return [activity for _, activity in ranked]


def _sample_heuristic_config(base: HeuristicConfig, rng: random.Random) -> HeuristicConfig:
    return HeuristicConfig(
        slack_weight=max(0.0, base.slack_weight + rng.uniform(-0.8, 0.8)),
        tail_weight=max(0.0, base.tail_weight + rng.uniform(-0.4, 0.4)),
        overload_weight=max(0.0, base.overload_weight + rng.uniform(-0.6, 0.6)),
        resource_weight=max(0.0, base.resource_weight + rng.uniform(-0.2, 0.2)),
        late_weight=max(0.0, base.late_weight + rng.uniform(-0.2, 0.2)),
        noise_weight=max(0.0, base.noise_weight + rng.uniform(-0.1, 0.1)),
        max_restarts=base.max_restarts,
    )


def _branch_and_bound_search(
    instance: Instance,
    tail: list[int],
    intensity: list[float],
    deadline: float,
    incumbent: Schedule | None = None,
    incremental_pairwise: bool = True,
) -> tuple[Schedule | None, SearchStats]:
    stats = SearchStats()
    seen: set[tuple[tuple[int, int], ...]] = set()
    best = incumbent
    global_lower_bound = longest_feasible_starts(instance)[instance.sink]
    root_lag_dist = _all_pairs_longest_lags(instance) if incremental_pairwise and incumbent is None else None

    def dfs(
        extra_edges: list[Edge],
        extra_pairs: set[tuple[int, int]],
        start_times: list[int] | None = None,
        lag_dist: list[list[float]] | None = None,
    ) -> None:
        nonlocal best
        if time.perf_counter() >= deadline:
            stats.timed_out = True
            return
        stats.nodes += 1

        key = tuple(sorted(extra_pairs))
        if key in seen:
            return
        seen.add(key)

        if start_times is None:
            try:
                start_times = longest_feasible_starts(instance, extra_edges=extra_edges)
            except TemporalInfeasibleError:
                return

        lower_bound = start_times[instance.sink]
        if best is not None and lower_bound >= best.makespan:
            return

        if best is None:
            if lag_dist is None:
                if _pairwise_infeasibility_reason(instance, extra_edges) is not None:
                    return
            elif _pairwise_infeasibility_reason_from_dist(instance, lag_dist) is not None:
                return

        conflict = _minimal_conflict_set(instance, start_times)
        if conflict is None:
            candidate_starts = _compress_valid_schedule(instance, start_times)
            candidate = Schedule(start_times=tuple(candidate_starts), makespan=candidate_starts[instance.sink])
            if best is None or candidate.makespan < best.makespan:
                best = candidate
            return

        conflict_time, resource, conflict_set, overload = conflict
        if len(conflict_set) <= 1:
            return

        ordered = _branch_order(instance, start_times, tail, intensity, conflict_set, overload)
        if best is None:
            for selected in ordered:
                if time.perf_counter() >= deadline:
                    stats.timed_out = True
                    return

                for other in conflict_set:
                    if other == selected or instance.demands[other][resource] == 0:
                        continue
                    pair = (other, selected)
                    if pair in extra_pairs:
                        continue

                    edge = Edge(source=other, target=selected, lag=instance.durations[other])
                    child_edges = extra_edges + [edge]
                    child_pairs = set(extra_pairs)
                    child_pairs.add(pair)
                    child_lag_dist = lag_dist
                    if child_lag_dist is not None:
                        child_lag_dist = _extend_longest_lags(child_lag_dist, edge)
                        if _pairwise_infeasibility_reason_from_dist(instance, child_lag_dist) is not None:
                            continue

                    dfs(child_edges, child_pairs, None, child_lag_dist)
                    if best is not None and best.makespan == global_lower_bound:
                        return
                    if stats.timed_out:
                        return
            return

        children: list[tuple[int, int, list[Edge], set[tuple[int, int]], list[int]]] = []
        for order_index, selected in enumerate(ordered):
            if time.perf_counter() >= deadline:
                stats.timed_out = True
                return

            for other in conflict_set:
                if other == selected or instance.demands[other][resource] == 0:
                    continue
                pair = (other, selected)
                if pair in extra_pairs:
                    continue

                child_edges = extra_edges + [Edge(source=other, target=selected, lag=instance.durations[other])]
                child_pairs = set(extra_pairs)
                child_pairs.add(pair)

                try:
                    child_starts = longest_feasible_starts(instance, extra_edges=child_edges)
                except TemporalInfeasibleError:
                    continue

                child_lower_bound = child_starts[instance.sink]
                if child_lower_bound >= best.makespan:
                    continue

                children.append((child_lower_bound, order_index, child_edges, child_pairs, child_starts))

        children.sort(key=lambda child: (child[0], child[1]))

        for _, _, child_edges, child_pairs, child_starts in children:
            dfs(child_edges, child_pairs, child_starts)
            if best is not None and best.makespan == global_lower_bound:
                return
            if stats.timed_out:
                return

    dfs([], set(), None, root_lag_dist)
    return best, stats


def construct_schedule(
    instance: Instance,
    rng: random.Random,
    tail: list[int],
    intensity: list[float],
    config: HeuristicConfig,
    deadline: float | None = None,
    base_extra_edges: list[Edge] | tuple[Edge, ...] = (),
    initial_starts: list[int] | None = None,
) -> Schedule:
    use_focused_repair = instance.n_jobs >= 20
    release = [0] * instance.n_activities
    extra_edges = list(base_extra_edges)
    current = (
        initial_starts[:]
        if initial_starts is not None
        else longest_feasible_starts(instance, release, extra_edges=extra_edges)
    )
    extra_pairs: set[tuple[int, int]] = {(edge.source, edge.target) for edge in extra_edges}
    max_steps = max(200, instance.n_activities * instance.n_activities * 6)
    steps = 0

    while True:
        if deadline is not None and time.perf_counter() >= deadline:
            break
        if steps >= max_steps:
            break
        if use_focused_repair:
            focused_conflict = _minimal_conflict_set(instance, current)
            if focused_conflict is None:
                break
            conflict_time, resource, active, overload = focused_conflict
        else:
            broad_conflict = _first_conflict(instance, current)
            if broad_conflict is None:
                break
            conflict_time, overload, active = broad_conflict
            resource = -1
        ranked = _delay_scores(
            instance=instance,
            start_times=current,
            makespan=current[instance.sink],
            tail=tail,
            overload=overload,
            active=active,
            intensity=intensity,
            rng=rng,
            config=config,
        )
        updated = False
        for _, selected in ranked:
            blockers = sorted(
                (
                    activity
                    for activity in active
                    if activity != selected
                    and (use_focused_repair or _shared_resource_overload(instance, selected, activity, overload))
                ),
                key=lambda activity: (current[activity] + instance.durations[activity], current[activity], activity),
            )
            if not use_focused_repair:
                candidate_options: list[tuple[int, int, list[Edge], set[tuple[int, int]], list[int]]] = []
                for blocker in blockers:
                    for direction in ("after", "before"):
                        if direction == "after":
                            pair = (blocker, selected)
                            edge = Edge(source=blocker, target=selected, lag=instance.durations[blocker])
                        else:
                            pair = (selected, blocker)
                            edge = Edge(source=selected, target=blocker, lag=instance.durations[selected])
                        if pair in extra_pairs:
                            continue
                        candidate_edges = extra_edges + [edge]
                        candidate_pairs = set(extra_pairs)
                        candidate_pairs.add(pair)
                        try:
                            candidate_schedule = longest_feasible_starts(
                                instance,
                                release_times=release,
                                extra_edges=candidate_edges,
                            )
                        except TemporalInfeasibleError:
                            continue
                        candidate_options.append(
                            (
                                candidate_schedule[instance.sink],
                                len(candidate_edges),
                                candidate_edges,
                                candidate_pairs,
                                candidate_schedule,
                            )
                        )
                if candidate_options:
                    _, _, extra_edges, extra_pairs, current = min(
                        candidate_options,
                        key=lambda option: (option[0], option[1]),
                    )
                    updated = True
                    break
            else:
                candidate_options: list[tuple[int, int, list[Edge], set[tuple[int, int]], list[int]]] = []
                for direction in ("after", "before"):
                    candidate_edges = extra_edges[:]
                    candidate_pairs = set(extra_pairs)
                    changed = False
                    for blocker in blockers:
                        if direction == "after":
                            pair = (blocker, selected)
                            edge = Edge(source=blocker, target=selected, lag=instance.durations[blocker])
                        else:
                            pair = (selected, blocker)
                            edge = Edge(source=selected, target=blocker, lag=instance.durations[selected])
                        if pair in candidate_pairs:
                            continue
                        candidate_pairs.add(pair)
                        candidate_edges.append(edge)
                        changed = True
                    if not changed:
                        continue
                    try:
                        candidate_schedule = longest_feasible_starts(
                            instance,
                            release_times=release,
                            extra_edges=candidate_edges,
                        )
                    except TemporalInfeasibleError:
                        continue
                    candidate_options.append(
                        (
                            candidate_schedule[instance.sink],
                            len(candidate_edges),
                            candidate_edges,
                            candidate_pairs,
                            candidate_schedule,
                        )
                    )
                if candidate_options:
                    _, _, extra_edges, extra_pairs, current = min(
                        candidate_options,
                        key=lambda option: (option[0], option[1]),
                    )
                    updated = True
                    break

        if not updated:
            selected = ranked[0][1]
            blockers = [
                activity
                for activity in active
                if activity != selected and (use_focused_repair or _shared_resource_overload(instance, selected, activity, overload))
            ]
            fallback_target = max(
                (current[activity] + instance.durations[activity] for activity in blockers),
                default=conflict_time + 1,
            )
            release[selected] = max(release[selected], fallback_target)
            current = longest_feasible_starts(instance, release_times=release, extra_edges=extra_edges)
        steps += 1

    current = longest_feasible_starts(instance, release_times=release, extra_edges=extra_edges)
    if any(value > 0 for value in release):
        try:
            release_free = longest_feasible_starts(instance, extra_edges=extra_edges)
        except TemporalInfeasibleError:
            release_free = None
        if release_free is not None:
            release_free_schedule = Schedule(
                start_times=tuple(release_free),
                makespan=release_free[instance.sink],
            )
            if not validate_schedule(instance, release_free_schedule):
                current = release_free
    current = _left_shift(instance, current, extra_edges)
    current_schedule = Schedule(start_times=tuple(current), makespan=current[instance.sink])
    if validate_schedule(instance, current_schedule):
        repaired = _left_shift(instance, current, [])
        repaired_schedule = Schedule(start_times=tuple(repaired), makespan=repaired[instance.sink])
        if not validate_schedule(instance, repaired_schedule):
            current = repaired
            current_schedule = repaired_schedule
    if not validate_schedule(instance, current_schedule):
        current = _compress_valid_schedule(instance, current)
    return Schedule(start_times=tuple(current), makespan=current[instance.sink])


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
        temporal_lb_schedule = longest_feasible_starts(instance)
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
    pairwise_reason = _pairwise_infeasibility_reason(instance)
    if pairwise_reason is not None:
        runtime = time.perf_counter() - started
        return SolveResult(
            instance_name=instance.name,
            status="infeasible",
            schedule=None,
            runtime_seconds=runtime,
            temporal_lower_bound=temporal_lower_bound,
            restarts=0,
            metadata={"reason": pairwise_reason, "seed": seed, "time_limit": time_limit},
        )

    intensity = _resource_intensity(instance)

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
    heuristic_deadline = min(final_deadline, started + min(1.0, max(0.01, time_limit * 0.2)))

    while True:
        now = time.perf_counter()
        if now >= heuristic_deadline:
            break
        if solver_config.max_restarts is not None and restarts >= solver_config.max_restarts:
            break

        local_config = _sample_heuristic_config(solver_config, rng)
        schedule = construct_schedule(
            instance,
            rng,
            tail,
            intensity,
            local_config,
            deadline=heuristic_deadline,
        )
        if validate_schedule(instance, schedule):
            continue
        if schedule.makespan < best.makespan:
            best = schedule
            best_valid = True
        restarts += 1
        if best.makespan == temporal_lower_bound:
            break

    exact_deadline = final_deadline
    if (
        best_valid
        and best.makespan > temporal_lower_bound
        and time.perf_counter() < final_deadline
    ):
        improvement_budget = min(5.0, max(0.02, time_limit * 0.35))
        improve_until = min(final_deadline, time.perf_counter() + improvement_budget)
        improved_best, improvement_iterations = _improve_incumbent(
            instance=instance,
            incumbent=best,
            tail=tail,
            intensity=intensity,
            solver_config=solver_config,
            rng=rng,
            deadline=improve_until,
        )
        if improved_best.makespan < best.makespan:
            best = improved_best
        exact_deadline = final_deadline

    exact_best, exact_stats = _branch_and_bound_search(
        instance=instance,
        tail=tail,
        intensity=intensity,
        deadline=exact_deadline,
        incumbent=best if best_valid else None,
        incremental_pairwise=time_limit >= 0.5,
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
        and time.perf_counter() < final_deadline
    ):
        polished_best, extra_iterations = _improve_incumbent(
            instance=instance,
            incumbent=best,
            tail=tail,
            intensity=intensity,
            solver_config=solver_config,
            rng=rng,
            deadline=final_deadline,
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
        },
    )
