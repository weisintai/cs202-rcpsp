from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from ..config import HeuristicConfig, sample_heuristic_config
from ..core.compress import normalized_time_loads, resource_order_edges
from ..models import Edge, Instance, Schedule
from ..temporal import TemporalInfeasibleError, longest_feasible_starts
from ..validate import build_resource_profile, validate_schedule
from .construct import construct_schedule

STANDARD_REPAIR_OPERATORS = ("mobility", "non_peak", "segment", "random")
TARGETED_REPAIR_OPERATORS = (
    "critical_chain",
    "peak",
    "pair",
    "mobility",
    "non_peak",
    "segment",
    "random",
)


@dataclass(frozen=True)
class RepairPlan:
    removed: frozenset[int]
    preferred_pairs: tuple[tuple[int, int], ...] = ()
    operator: str = "random"


@dataclass
class AdaptiveOperatorState:
    weight: float = 1.0
    uses: int = 0
    total_reward: float = 0.0
    successes: int = 0


def repair_operator_names(targeted_mode: bool) -> tuple[str, ...]:
    return TARGETED_REPAIR_OPERATORS if targeted_mode else STANDARD_REPAIR_OPERATORS


def initialize_operator_states(targeted_mode: bool) -> dict[str, AdaptiveOperatorState]:
    return {
        operator: AdaptiveOperatorState()
        for operator in repair_operator_names(targeted_mode)
    }


def select_repair_operator(
    states: dict[str, AdaptiveOperatorState],
    rng: random.Random,
) -> str:
    total_uses = sum(state.uses for state in states.values())
    weighted: list[tuple[str, float]] = []
    for operator, state in states.items():
        exploration_bonus = 0.75 * math.sqrt(math.log(total_uses + 2.0) / (state.uses + 1.0))
        weighted.append((operator, max(0.2, state.weight) + exploration_bonus))

    total_weight = sum(weight for _, weight in weighted)
    threshold = rng.random() * total_weight
    cumulative = 0.0
    for operator, weight in weighted:
        cumulative += weight
        if cumulative >= threshold:
            return operator
    return weighted[-1][0]


def score_repair_outcome(
    best: Schedule,
    base: Schedule,
    candidate: Schedule | None,
    valid_candidates: int,
) -> float:
    if candidate is None:
        return 0.1

    reward = 1.0
    if candidate.makespan < base.makespan:
        relative_gain = (base.makespan - candidate.makespan) / max(1, base.makespan)
        reward += 2.0 + min(1.5, 6.0 * relative_gain)
    elif candidate.makespan == base.makespan and candidate.start_times != base.start_times:
        reward += 0.35

    if candidate.makespan < best.makespan:
        relative_gain = (best.makespan - candidate.makespan) / max(1, best.makespan)
        reward += 4.0 + min(2.0, 10.0 * relative_gain)

    reward += min(0.4, 0.1 * max(0, valid_candidates - 1))
    return reward


def update_operator_state(state: AdaptiveOperatorState, reward: float) -> None:
    state.uses += 1
    state.total_reward += reward
    if reward > 1.0:
        state.successes += 1

    reaction = 0.3 if state.uses <= 6 else 0.18
    blended = (1.0 - reaction) * state.weight + reaction * reward
    state.weight = min(8.0, max(0.2, blended))


def sample_removal_size(instance: Instance, rng: random.Random) -> int:
    minimum = 2 if instance.n_jobs <= 10 else 3
    maximum = max(minimum, min(instance.n_jobs - 1, max(3, instance.n_jobs // 3)))
    return rng.randint(minimum, maximum)


def mobility_removal_set(
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


def critical_chain_removal_set(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    intensity: list[float],
    size: int,
) -> set[int]:
    scored = []
    for activity in range(1, instance.sink):
        slack = schedule.makespan - (schedule.start_times[activity] + tail[activity])
        scored.append((slack, -intensity[activity], schedule.start_times[activity], activity))
    scored.sort()
    return {activity for _, _, _, activity in scored[:size]}


def non_peak_removal_set(
    instance: Instance,
    schedule: Schedule,
    rng: random.Random,
    size: int,
) -> set[int]:
    loads = normalized_time_loads(instance, schedule.start_times)
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


def segment_removal_set(
    instance: Instance,
    schedule: Schedule,
    rng: random.Random,
    size: int,
) -> set[int]:
    if schedule.makespan <= 0:
        return mobility_removal_set(instance, schedule, [0] * instance.n_activities, rng, size)

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


def bottleneck_hotspot(instance: Instance, schedule: Schedule) -> tuple[int, int] | None:
    profile = build_resource_profile(instance, schedule.start_times)
    best: tuple[float, int, int, int] | None = None
    for time_index, usage in enumerate(profile):
        for resource, amount in enumerate(usage):
            capacity = instance.capacities[resource]
            if capacity <= 0 or amount <= 0:
                continue
            candidate = (amount / capacity, amount, -time_index, resource)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        return None
    return best[3], -best[2]


def peak_focused_removal_set(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    intensity: list[float],
    size: int,
) -> set[int]:
    hotspot = bottleneck_hotspot(instance, schedule)
    if hotspot is None:
        return critical_chain_removal_set(instance, schedule, tail, intensity, size)

    resource, time_index = hotspot
    half_width = max(1, schedule.makespan // max(8, instance.n_jobs))
    left = max(0, time_index - half_width)
    right = time_index + half_width + 1
    scored = []
    for activity in range(1, instance.sink):
        duration = instance.durations[activity]
        demand = instance.demands[activity][resource]
        if duration <= 0 or demand <= 0:
            continue
        start = schedule.start_times[activity]
        overlap = max(0, min(start + duration, right) - max(start, left))
        if overlap <= 0:
            continue
        slack = schedule.makespan - (start + tail[activity])
        scored.append(
            (
                overlap * demand,
                demand,
                -slack,
                intensity[activity],
                -start,
                activity,
            )
        )
    if not scored:
        return segment_removal_set(instance, schedule, random.Random(time_index + resource), size)
    scored.sort(reverse=True)
    return {activity for _, _, _, _, _, activity in scored[:size]}


def random_removal_set(instance: Instance, rng: random.Random, size: int) -> set[int]:
    activities = list(range(1, instance.sink))
    if len(activities) <= size:
        return set(activities)
    return set(rng.sample(activities, size))


def bottleneck_pair_repair_plans(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    intensity: list[float],
    size: int,
    operator: str = "pair",
) -> tuple[RepairPlan, ...]:
    hotspot = bottleneck_hotspot(instance, schedule)
    if hotspot is None:
        removed = critical_chain_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed), operator=operator),)

    resource, time_index = hotspot
    half_width = max(1, schedule.makespan // max(8, instance.n_jobs))
    left = max(0, time_index - half_width)
    right = time_index + half_width + 1
    relevant = [
        activity
        for activity in range(1, instance.sink)
        if instance.demands[activity][resource] > 0
        and max(0, min(schedule.start_times[activity] + instance.durations[activity], right) - max(schedule.start_times[activity], left)) > 0
    ]
    if len(relevant) < 2:
        removed = peak_focused_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed), operator=operator),)

    pair_candidates: list[tuple[tuple[float, ...], tuple[int, int]]] = []
    for index, first in enumerate(relevant):
        first_slack = schedule.makespan - (schedule.start_times[first] + tail[first])
        for second in relevant[index + 1 :]:
            second_slack = schedule.makespan - (schedule.start_times[second] + tail[second])
            pair_candidates.append(
                (
                    (
                        float(instance.demands[first][resource] + instance.demands[second][resource]),
                        intensity[first] + intensity[second],
                        -(first_slack + second_slack),
                        -abs(schedule.start_times[first] - schedule.start_times[second]),
                        -abs(first - second),
                    ),
                    (first, second),
                )
            )
    if not pair_candidates:
        removed = peak_focused_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed), operator=operator),)

    _, (first, second) = max(pair_candidates, key=lambda item: item[0])
    removed = {first, second}
    if len(removed) < size:
        extras: list[tuple[tuple[float, ...], int]] = []
        for activity in relevant:
            if activity in removed:
                continue
            slack = schedule.makespan - (schedule.start_times[activity] + tail[activity])
            start = schedule.start_times[activity]
            duration = instance.durations[activity]
            overlap = max(0, min(start + duration, right) - max(start, left))
            extras.append(
                (
                    (
                        float(overlap * instance.demands[activity][resource]),
                        intensity[activity],
                        -slack,
                        -abs(start - time_index),
                    ),
                    activity,
                )
            )
        extras.sort(reverse=True)
        for _, activity in extras:
            removed.add(activity)
            if len(removed) >= size:
                break

    current_pair = (first, second)
    if schedule.start_times[second] < schedule.start_times[first]:
        current_pair = (second, first)
    swapped_pair = (current_pair[1], current_pair[0])
    plans = [RepairPlan(frozenset(removed), operator=operator)]
    plans.append(RepairPlan(frozenset(removed), (current_pair,), operator=operator))
    if swapped_pair != current_pair:
        plans.append(RepairPlan(frozenset(removed), (swapped_pair,), operator=operator))
    return tuple(plans)


def sample_standard_repair_plan(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    rng: random.Random,
    operator: str | None = None,
) -> RepairPlan:
    size = sample_removal_size(instance, rng)
    operator_name = operator or rng.choice(STANDARD_REPAIR_OPERATORS)
    if operator_name == "mobility":
        removed = mobility_removal_set(instance, schedule, tail, rng, size)
    elif operator_name == "non_peak":
        removed = non_peak_removal_set(instance, schedule, rng, size)
    elif operator_name == "segment":
        removed = segment_removal_set(instance, schedule, rng, size)
    else:
        removed = random_removal_set(instance, rng, size)
    fallback = removed or random_removal_set(instance, rng, min(size, instance.n_jobs))
    return RepairPlan(frozenset(fallback), operator=operator_name)


def sample_repair_plans(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    intensity: list[float],
    rng: random.Random,
    operator: str | None = None,
) -> tuple[RepairPlan, ...]:
    if instance.n_jobs < 30:
        return (sample_standard_repair_plan(instance, schedule, tail, rng, operator=operator),)

    size = sample_removal_size(instance, rng)
    operator_name = operator or rng.choice(TARGETED_REPAIR_OPERATORS)
    if operator_name == "critical_chain":
        removed = critical_chain_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed), operator=operator_name),)
    if operator_name == "peak":
        removed = peak_focused_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed), operator=operator_name),)
    if operator_name == "pair":
        return bottleneck_pair_repair_plans(instance, schedule, tail, intensity, size, operator=operator_name)
    if operator_name == "mobility":
        removed = mobility_removal_set(instance, schedule, tail, rng, size)
    elif operator_name == "non_peak":
        removed = non_peak_removal_set(instance, schedule, rng, size)
    elif operator_name == "segment":
        removed = segment_removal_set(instance, schedule, rng, size)
    else:
        removed = random_removal_set(instance, rng, size)
    fallback = removed or random_removal_set(instance, rng, min(size, instance.n_jobs))
    return (RepairPlan(frozenset(fallback), operator=operator_name),)


def repair_schedule_subset(
    instance: Instance,
    schedule: Schedule,
    removed: set[int],
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
    pinned_edges: tuple[Edge, ...] = (),
    preferred_pairs: tuple[tuple[int, int], ...] = (),
) -> Schedule | None:
    base_edges = list(pinned_edges) + [
        edge
        for edge in resource_order_edges(instance, list(schedule.start_times))
        if edge.source not in removed and edge.target not in removed
    ]
    seen_pairs = {(edge.source, edge.target) for edge in base_edges}
    for source, target in preferred_pairs:
        if source == target or (source, target) in seen_pairs:
            continue
        base_edges.append(Edge(source=source, target=target, lag=instance.durations[source]))
        seen_pairs.add((source, target))
    try:
        initial_starts = longest_feasible_starts(instance, extra_edges=base_edges)
    except TemporalInfeasibleError:
        return None

    try:
        candidate = construct_schedule(
            instance=instance,
            rng=rng,
            tail=tail,
            intensity=intensity,
            config=sample_heuristic_config(solver_config, rng),
            deadline=deadline,
            base_extra_edges=base_edges,
            initial_starts=initial_starts,
        )
    except TemporalInfeasibleError:
        return None
    if validate_schedule(instance, candidate):
        return None
    return candidate


def update_elite_pool(elite: list[Schedule], candidate: Schedule, limit: int = 4) -> None:
    if any(existing.start_times == candidate.start_times for existing in elite):
        return
    elite.append(candidate)
    elite.sort(key=lambda schedule: (schedule.makespan, schedule.start_times))
    del elite[limit:]


def select_improvement_bases(
    elite: list[Schedule],
    rng: random.Random,
    stagnation: int,
    targeted_mode: bool,
) -> list[Schedule]:
    if not elite:
        return []
    if not targeted_mode:
        return [elite[0]]
    bases = [elite[0]]
    pool = elite[1 : min(len(elite), 2 + stagnation // 3)]
    while pool and len(bases) < 1 + min(2, stagnation // 4):
        selected = rng.choice(pool)
        bases.append(selected)
        pool = [candidate for candidate in pool if candidate.start_times != selected.start_times]
    return bases


def improve_incumbent(
    instance: Instance,
    incumbent: Schedule,
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
    base_extra_edges: tuple[Edge, ...] = (),
) -> tuple[Schedule, int]:
    best = incumbent
    elite = [incumbent]
    iterations = 0
    stagnation = 0
    targeted_mode = instance.n_jobs >= 30
    elite_limit = 6 if targeted_mode else 4
    if not targeted_mode:
        while time.perf_counter() < deadline:
            attempts: list[tuple[Schedule, Schedule]] = []
            bases = select_improvement_bases(elite, rng, stagnation, targeted_mode)
            for base in bases:
                if time.perf_counter() >= deadline:
                    break
                plans = sample_repair_plans(instance, base, tail, intensity, rng)
                for plan in plans:
                    if time.perf_counter() >= deadline:
                        break
                    candidate = repair_schedule_subset(
                        instance=instance,
                        schedule=base,
                        removed=set(plan.removed),
                        tail=tail,
                        intensity=intensity,
                        solver_config=solver_config,
                        rng=rng,
                        deadline=deadline,
                        pinned_edges=base_extra_edges,
                        preferred_pairs=plan.preferred_pairs,
                    )
                    iterations += 1
                    if candidate is None:
                        continue
                    update_elite_pool(elite, candidate, limit=elite_limit)
                    attempts.append((candidate, base))

            if not attempts:
                stagnation += max(1, len(bases))
                continue

            candidate, base = min(
                attempts,
                key=lambda item: (item[0].makespan, item[0].start_times),
            )
            if candidate.makespan < best.makespan:
                best = candidate
                update_elite_pool(elite, best, limit=elite_limit)
                stagnation = 0
            elif any(attempt.makespan < origin.makespan for attempt, origin in attempts):
                stagnation = max(0, stagnation - 1)
            else:
                stagnation += 1

        return best, iterations

    operator_states = initialize_operator_states(targeted_mode)

    while time.perf_counter() < deadline:
        attempts: list[tuple[Schedule, Schedule]] = []
        bases = select_improvement_bases(elite, rng, stagnation, targeted_mode)
        for base in bases:
            if time.perf_counter() >= deadline:
                break
            operator = None if operator_states is None else select_repair_operator(operator_states, rng)
            plans = sample_repair_plans(
                instance,
                base,
                tail,
                intensity,
                rng,
                operator=operator,
            )
            operator_best: Schedule | None = None
            valid_candidates = 0
            for plan in plans:
                if time.perf_counter() >= deadline:
                    break
                candidate = repair_schedule_subset(
                    instance=instance,
                    schedule=base,
                    removed=set(plan.removed),
                    tail=tail,
                    intensity=intensity,
                    solver_config=solver_config,
                    rng=rng,
                    deadline=deadline,
                    pinned_edges=base_extra_edges,
                    preferred_pairs=plan.preferred_pairs,
                )
                iterations += 1
                if candidate is None:
                    continue
                valid_candidates += 1
                if operator_best is None or (candidate.makespan, candidate.start_times) < (
                    operator_best.makespan,
                    operator_best.start_times,
                ):
                    operator_best = candidate
                update_elite_pool(elite, candidate, limit=elite_limit)
                attempts.append((candidate, base))
            if operator_states is not None and operator is not None:
                reward = score_repair_outcome(best, base, operator_best, valid_candidates)
                update_operator_state(operator_states[operator], reward)

        if not attempts:
            stagnation += max(1, len(bases))
            continue

        candidate, base = min(
            attempts,
            key=lambda item: (item[0].makespan, item[0].start_times),
        )
        if candidate.makespan < best.makespan:
            best = candidate
            update_elite_pool(elite, best, limit=elite_limit)
            stagnation = 0
        elif any(attempt.makespan < origin.makespan for attempt, origin in attempts):
            stagnation = max(0, stagnation - 1)
        else:
            stagnation += 1

    return best, iterations
