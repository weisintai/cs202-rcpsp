from __future__ import annotations

import time

from ..models import Schedule
from ..validate import validate_schedule
from .models import SgsInstance
from .priorities import priority_from_schedule
from .serial import (
    POS_INF,
    _commit_profile,
    _resource_feasible,
    _tighten_windows,
    _windows_feasible,
    decode_priority_list,
)


def _right_justify(
    instance: SgsInstance,
    schedule: Schedule,
    *,
    deadline: float,
) -> Schedule | None:
    profile: list[list[int]] = []
    fixed = {instance.source, instance.sink}
    starts: dict[int, int] = {instance.source: 0, instance.sink: schedule.makespan}
    lower = [0] * instance.n_activities
    upper = [POS_INF] * instance.n_activities
    _tighten_windows(instance, lower, upper, instance.source, 0)
    _tighten_windows(instance, lower, upper, instance.sink, schedule.makespan)

    for activity in reversed(priority_from_schedule(instance, schedule)):
        if time.perf_counter() >= deadline:
            return None

        duration = instance.activities[activity].duration
        act_lower = lower[activity]
        act_upper = min(upper[activity], schedule.makespan - duration)
        if act_lower > act_upper:
            return None

        placed = False
        for candidate_start in range(act_upper, act_lower - 1, -1):
            if not _resource_feasible(instance, activity, candidate_start, profile):
                continue

            trial_lower = lower[:]
            trial_upper = upper[:]
            _tighten_windows(instance, trial_lower, trial_upper, activity, candidate_start)
            if not _windows_feasible(instance, fixed | {activity}, trial_lower, trial_upper):
                continue

            starts[activity] = candidate_start
            lower = trial_lower
            upper = trial_upper
            fixed.add(activity)
            _commit_profile(instance, activity, candidate_start, profile)
            placed = True
            break

        if not placed:
            return None

    final_starts = [0] * instance.n_activities
    for activity, start in starts.items():
        final_starts[activity] = start

    candidate = Schedule(start_times=tuple(final_starts), makespan=schedule.makespan)
    if validate_schedule(instance.base_instance, candidate):
        return None
    return candidate


def forward_backward_improve(
    instance: SgsInstance,
    schedule: Schedule,
    *,
    deadline: float,
) -> tuple[Schedule, int]:
    best = schedule
    passes = 0
    right_justified = _right_justify(instance, schedule, deadline=deadline)
    if right_justified is None:
        return best, passes

    passes += 1
    if time.perf_counter() >= deadline:
        return best, passes

    priority = priority_from_schedule(instance, right_justified)
    candidate, _ = decode_priority_list(instance, priority, deadline=deadline)
    passes += 1
    if candidate is not None and candidate.makespan < best.makespan:
        best = candidate

    return best, passes
