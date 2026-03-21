from __future__ import annotations

import time
from dataclasses import dataclass

from ..models import Schedule
from ..validate import validate_schedule
from .models import SgsInstance

NEG_INF = float("-inf")
POS_INF = 10**12


@dataclass(frozen=True)
class DecodeStats:
    scheduled_activities: int
    attempts: int


def _ensure_profile_length(
    profile: list[list[int]],
    horizon: int,
    n_resources: int,
) -> None:
    while len(profile) < horizon:
        profile.append([0] * n_resources)


def _resource_feasible(
    instance: SgsInstance,
    activity: int,
    start: int,
    profile: list[list[int]],
) -> bool:
    duration = instance.activities[activity].duration
    if duration <= 0:
        return True

    demands = instance.activities[activity].demands
    _ensure_profile_length(profile, start + duration, len(instance.capacities))
    for time_index in range(start, start + duration):
        usage = profile[time_index]
        for resource, demand in enumerate(demands):
            if usage[resource] + demand > instance.capacities[resource]:
                return False
    return True


def _commit_profile(
    instance: SgsInstance,
    activity: int,
    start: int,
    profile: list[list[int]],
) -> None:
    duration = instance.activities[activity].duration
    if duration <= 0:
        return

    demands = instance.activities[activity].demands
    _ensure_profile_length(profile, start + duration, len(instance.capacities))
    for time_index in range(start, start + duration):
        usage = profile[time_index]
        for resource, demand in enumerate(demands):
            usage[resource] += demand


def _tighten_windows(
    instance: SgsInstance,
    lower: list[int],
    upper: list[int],
    fixed_activity: int,
    fixed_start: int,
) -> None:
    for activity in range(instance.n_activities):
        from_fixed = instance.lag_dist[fixed_activity][activity]
        if from_fixed != NEG_INF:
            lower[activity] = max(lower[activity], fixed_start + int(from_fixed))

        to_fixed = instance.lag_dist[activity][fixed_activity]
        if to_fixed != NEG_INF:
            upper[activity] = min(upper[activity], fixed_start - int(to_fixed))

    lower[fixed_activity] = fixed_start
    upper[fixed_activity] = fixed_start


def _initial_windows(
    instance: SgsInstance,
) -> tuple[list[int], list[int]]:
    lower = [0] * instance.n_activities
    upper = [POS_INF] * instance.n_activities
    _tighten_windows(instance, lower, upper, instance.source, 0)
    return lower, upper


def _windows_feasible(
    instance: SgsInstance,
    scheduled: set[int],
    lower: list[int],
    upper: list[int],
) -> bool:
    for activity in range(instance.n_activities):
        if activity in scheduled:
            continue
        if lower[activity] > upper[activity]:
            return False
    return True


def _search_limit(
    lower: int,
    upper: int,
    current_makespan: int,
) -> int:
    if lower >= current_makespan:
        return lower
    return min(upper, current_makespan)


def _find_earliest_start(
    instance: SgsInstance,
    activity: int,
    lower: int,
    upper: int,
    current_makespan: int,
    profile: list[list[int]],
    deadline: float | None,
) -> tuple[int | None, int]:
    if lower > upper:
        return None, 0

    attempts = 0
    limit = _search_limit(lower, upper, current_makespan)
    for candidate_start in range(lower, limit + 1):
        attempts += 1
        if deadline is not None and time.perf_counter() >= deadline:
            return None, attempts
        if _resource_feasible(instance, activity, candidate_start, profile):
            return candidate_start, attempts

    return None, attempts


def decode_priority_list(
    instance: SgsInstance,
    priority_list: tuple[int, ...] | list[int],
    *,
    deadline: float | None = None,
) -> tuple[Schedule | None, DecodeStats]:
    scheduled_starts: dict[int, int] = {instance.source: 0}
    lower_bounds, upper_bounds = _initial_windows(instance)
    profile: list[list[int]] = []
    unscheduled = set(instance.internal_activities)
    scheduled = {instance.source}
    scheduled_count = 0
    attempts = 0
    rank = {activity: index for index, activity in enumerate(priority_list)}
    current_makespan = 0

    while unscheduled:
        if deadline is not None and time.perf_counter() >= deadline:
            break

        eligible = [
            activity
            for activity in unscheduled
            if all(
                predecessor.activity in scheduled_starts
                for predecessor in instance.activities[activity].min_predecessors
            )
        ]
        if not eligible:
            return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)

        eligible.sort(
            key=lambda activity: (
                rank.get(activity, len(priority_list)),
                lower_bounds[activity],
                activity,
            )
        )

        placed = False
        for activity in eligible:
            lower = lower_bounds[activity]
            upper = upper_bounds[activity]
            if lower > upper:
                continue

            candidate_start, local_attempts = _find_earliest_start(
                instance=instance,
                activity=activity,
                lower=lower,
                upper=upper,
                current_makespan=current_makespan,
                profile=profile,
                deadline=deadline,
            )
            attempts += local_attempts
            if candidate_start is None:
                continue

            trial_lower = lower_bounds[:]
            trial_upper = upper_bounds[:]
            _tighten_windows(instance, trial_lower, trial_upper, activity, candidate_start)
            if not _windows_feasible(instance, scheduled | {activity}, trial_lower, trial_upper):
                continue

            scheduled_starts[activity] = candidate_start
            scheduled.add(activity)
            lower_bounds = trial_lower
            upper_bounds = trial_upper
            _commit_profile(instance, activity, candidate_start, profile)
            current_makespan = max(
                current_makespan,
                candidate_start + instance.activities[activity].duration,
            )
            unscheduled.remove(activity)
            scheduled_count += 1
            placed = True
            break

        if not placed:
            return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)

    if unscheduled:
        return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)

    final_starts = [0] * instance.n_activities
    for activity, start in scheduled_starts.items():
        final_starts[activity] = start
    final_starts[instance.sink] = lower_bounds[instance.sink]

    schedule = Schedule(start_times=tuple(final_starts), makespan=final_starts[instance.sink])
    if validate_schedule(instance.base_instance, schedule):
        return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)
    return schedule, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)

