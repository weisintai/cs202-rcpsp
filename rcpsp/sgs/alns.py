from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..models import Schedule
from ..validate import build_resource_profile
from .fbi import forward_backward_improve
from .models import SgsInstance
from .priorities import priority_from_schedule, priority_order_for_restart, repair_priority_order, seed_priority_lists
from .serial import beam_decode_priority_list, decode_priority_list

DESTROY_NEW_BEST = 25.0
DESTROY_ACCEPTED = 5.0
DESTROY_FEASIBLE = 1.0
DESTROY_REJECTED = 0.0
WEIGHT_DECAY = 0.9
HIGH_UTIL_THRESHOLD = 0.75


@dataclass(frozen=True)
class SearchStats:
    iterations: int
    decode_attempts: int
    improvement_passes: int


@dataclass(frozen=True)
class SearchState:
    priority: tuple[int, ...]
    schedule: Schedule


def _removal_count(order: tuple[int, ...] | list[int]) -> int:
    return max(1, min(6, max(1, len(order) // 5)))


def _segment_destroy(
    instance: SgsInstance,
    state: SearchState,
    rng: random.Random,
) -> tuple[int, ...]:
    order = list(state.priority)
    if len(order) <= 2:
        return tuple(order)

    count = _removal_count(order)
    start = rng.randrange(0, max(1, len(order) - count + 1))
    del order[start : start + count]
    return tuple(order)


def _mobility_destroy(
    instance: SgsInstance,
    state: SearchState,
    rng: random.Random,
) -> tuple[int, ...]:
    order = list(state.priority)
    if len(order) <= 2:
        return tuple(order)

    indices = {activity: index for index, activity in enumerate(order)}
    weighted: list[tuple[float, int]] = []
    for activity in order:
        left = max(
            (indices[pred.activity] for pred in instance.activities[activity].min_predecessors if pred.activity in indices),
            default=-1,
        )
        right = min(
            (indices[succ.activity] for succ in instance.activities[activity].min_successors if succ.activity in indices),
            default=len(order),
        )
        mobility = max(0, right - left)
        weighted.append((float(mobility), activity))

    if not any(weight > 0 for weight, _ in weighted):
        return _segment_destroy(instance, state, rng)

    chosen: set[int] = set()
    count = _removal_count(order)
    while len(chosen) < count and len(chosen) < len(order):
        remaining = [(weight, activity) for weight, activity in weighted if activity not in chosen]
        total = sum(weight for weight, _ in remaining)
        if total <= 0:
            break
        target = rng.random() * total
        acc = 0.0
        for weight, activity in remaining:
            acc += weight
            if acc >= target:
                chosen.add(activity)
                break

    if not chosen:
        return _segment_destroy(instance, state, rng)
    return tuple(activity for activity in order if activity not in chosen)


def _non_peak_destroy(
    instance: SgsInstance,
    state: SearchState,
    rng: random.Random,
) -> tuple[int, ...]:
    order = list(state.priority)
    if len(order) <= 2:
        return tuple(order)

    profile = build_resource_profile(instance.base_instance, state.schedule.start_times)
    loads: list[float] = []
    for usage in profile:
        normalized = []
        for resource, amount in enumerate(usage):
            capacity = instance.capacities[resource]
            if capacity > 0:
                normalized.append(amount / capacity)
        loads.append(sum(normalized) / max(1, len(normalized)))

    removable: list[int] = []
    for activity in order:
        start = state.schedule.start_times[activity]
        duration = instance.activities[activity].duration
        if duration <= 0:
            continue
        end = start + duration
        if end > len(loads):
            end = len(loads)
        if all(loads[t] <= HIGH_UTIL_THRESHOLD for t in range(start, end)):
            removable.append(activity)

    if not removable:
        return _segment_destroy(instance, state, rng)

    count = min(_removal_count(order), len(removable))
    chosen = set(rng.sample(removable, count))
    return tuple(activity for activity in order if activity not in chosen)


DESTROY_OPERATORS = {
    "mobility": _mobility_destroy,
    "non_peak": _non_peak_destroy,
    "segment": _segment_destroy,
}


def _select_operator(
    weights: dict[str, float],
    rng: random.Random,
) -> str:
    total = sum(max(0.01, weight) for weight in weights.values())
    threshold = rng.random() * total
    acc = 0.0
    for name, weight in weights.items():
        acc += max(0.01, weight)
        if acc >= threshold:
            return name
    return next(iter(weights))


def _update_weight(
    weights: dict[str, float],
    name: str,
    reward: float,
) -> None:
    weights[name] = WEIGHT_DECAY * weights[name] + (1.0 - WEIGHT_DECAY) * reward


def _decode_and_improve(
    instance: SgsInstance,
    priority: tuple[int, ...],
    *,
    deadline: float,
    bootstrap: bool,
    latest_starts: list[int] | None = None,
) -> tuple[Schedule | None, int, int]:
    candidate, stats = decode_priority_list(
        instance,
        priority,
        deadline=deadline,
        latest_starts=latest_starts,
    )
    decode_attempts = stats.attempts
    passes = 0
    if candidate is None and bootstrap and time.perf_counter() < deadline:
        candidate, stats = beam_decode_priority_list(
            instance,
            priority,
            deadline=deadline,
            latest_starts=latest_starts,
        )
        decode_attempts += stats.attempts
    if candidate is None:
        return None, decode_attempts, passes
    if time.perf_counter() < deadline:
        candidate, passes = forward_backward_improve(instance, candidate, deadline=deadline)
    return candidate, decode_attempts, passes


def run_alns_batch(
    instance: SgsInstance,
    temporal_lower: list[int],
    *,
    deadline: float,
    rng: random.Random,
    max_iterations: int | None = None,
    initial_schedule: Schedule | None = None,
) -> tuple[Schedule | None, SearchStats]:
    iterations = 0
    decode_attempts = 0
    improvement_passes = 0
    best: SearchState | None = None
    current: SearchState | None = None
    operator_weights = {name: 1.0 for name in DESTROY_OPERATORS}
    project_lower = temporal_lower[instance.sink]
    use_bootstrap_beam = instance.base_instance.n_jobs <= 20
    seeded = seed_priority_lists(instance, temporal_lower)

    if initial_schedule is not None:
        warm_priority = priority_from_schedule(instance, initial_schedule)
        seeded = [warm_priority, *[priority for priority in seeded if priority != warm_priority]]
        warm_state = SearchState(priority=warm_priority, schedule=initial_schedule)
        best = warm_state
        current = warm_state
        if warm_state.schedule.makespan == project_lower:
            return warm_state.schedule, SearchStats(
                iterations=iterations,
                decode_attempts=decode_attempts,
                improvement_passes=improvement_passes,
            )

    for priority in seeded:
        if time.perf_counter() >= deadline:
            break
        candidate, attempts, passes = _decode_and_improve(
            instance,
            priority,
            deadline=deadline,
            bootstrap=best is None and use_bootstrap_beam,
        )
        iterations += 1
        decode_attempts += attempts
        improvement_passes += passes
        if candidate is None:
            continue
        state = SearchState(priority=priority_from_schedule(instance, candidate), schedule=candidate)
        if current is None or state.schedule.makespan <= current.schedule.makespan:
            current = state
        if best is None or state.schedule.makespan < best.schedule.makespan:
            best = state
        if best is not None and best.schedule.makespan == project_lower:
            return best.schedule, SearchStats(iterations, decode_attempts, improvement_passes)

    while time.perf_counter() < deadline:
        if max_iterations is not None and iterations >= max_iterations:
            break

        if current is None:
            priority = priority_order_for_restart(
                instance,
                temporal_lower,
                rng,
                iterations,
                seeded,
                incumbent_priority=None if best is None else best.priority,
            )
            operator_name = "seed"
        else:
            operator_name = _select_operator(operator_weights, rng)
            partial = DESTROY_OPERATORS[operator_name](instance, current, rng)
            priority = repair_priority_order(instance, partial, rng)

        candidate, attempts, passes = _decode_and_improve(
            instance,
            priority,
            deadline=deadline,
            bootstrap=False,
        )
        iterations += 1
        decode_attempts += attempts
        improvement_passes += passes
        if candidate is None:
            if operator_name in operator_weights:
                _update_weight(operator_weights, operator_name, DESTROY_REJECTED)
            continue

        candidate_state = SearchState(priority=priority_from_schedule(instance, candidate), schedule=candidate)
        accepted = current is None or candidate.makespan <= current.schedule.makespan
        improved_best = best is None or candidate.makespan < best.schedule.makespan

        if accepted:
            current = candidate_state
        if improved_best:
            best = candidate_state
            current = candidate_state

        if operator_name in operator_weights:
            if improved_best:
                reward = DESTROY_NEW_BEST
            elif accepted:
                reward = DESTROY_ACCEPTED
            else:
                reward = DESTROY_FEASIBLE
            _update_weight(operator_weights, operator_name, reward)

        if best is not None and best.schedule.makespan == project_lower:
            break

    return None if best is None else best.schedule, SearchStats(
        iterations=iterations,
        decode_attempts=decode_attempts,
        improvement_passes=improvement_passes,
    )
