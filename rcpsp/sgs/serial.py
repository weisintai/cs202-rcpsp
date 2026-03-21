from __future__ import annotations

import time
from dataclasses import dataclass

from ..models import Schedule
from ..validate import validate_schedule
from .models import SgsInstance
from .time_windows import window_slack

NEG_INF = float("-inf")
POS_INF = 10**12
ELIGIBLE_LOOKAHEAD = 3
WINDOW_LOOKAHEAD = 6
BOOTSTRAP_BEAM_WIDTH = 6
BOOTSTRAP_BRANCH_LIMIT = 6


@dataclass(frozen=True)
class DecodeStats:
    scheduled_activities: int
    attempts: int


@dataclass
class _PartialState:
    pending: tuple[int, ...]
    scheduled_starts: tuple[int, ...]
    lower_bounds: tuple[int, ...]
    upper_bounds: tuple[int, ...]
    profile: list[list[int]]
    scheduled: frozenset[int]
    current_makespan: int
    scheduled_count: int


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


def _copy_profile(profile: list[list[int]]) -> list[list[int]]:
    return [row[:] for row in profile]


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
    latest_starts: list[int] | None = None,
) -> tuple[list[int], list[int]]:
    lower = [0] * instance.n_activities
    upper = [POS_INF] * instance.n_activities if latest_starts is None else latest_starts[:]
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


def _dynamic_lower_bound(
    instance: SgsInstance,
    activity: int,
    lower_bounds: list[int],
    scheduled: set[int],
) -> int:
    candidate = lower_bounds[activity]
    for other in range(instance.n_activities):
        if other == activity or other in scheduled:
            continue
        to_activity = instance.lag_dist[other][activity]
        if to_activity != NEG_INF:
            candidate = max(candidate, lower_bounds[other] + int(to_activity))
    return candidate


def _schedule_activity(
    instance: SgsInstance,
    state: _PartialState,
    activity: int,
    *,
    deadline: float | None,
) -> tuple[_PartialState | None, int]:
    lower = _dynamic_lower_bound(instance, activity, list(state.lower_bounds), set(state.scheduled))
    upper = state.upper_bounds[activity]
    if lower > upper:
        return None, 0

    limit = _search_limit(lower, upper, state.current_makespan)
    attempts = 0
    for candidate_start in range(lower, limit + 1):
        attempts += 1
        if deadline is not None and time.perf_counter() >= deadline:
            return None, attempts
        if not _resource_feasible(instance, activity, candidate_start, state.profile):
            continue

        trial_lower = list(state.lower_bounds)
        trial_upper = list(state.upper_bounds)
        _tighten_windows(instance, trial_lower, trial_upper, activity, candidate_start)
        trial_scheduled = set(state.scheduled)
        trial_scheduled.add(activity)
        if not _windows_feasible(instance, trial_scheduled, trial_lower, trial_upper):
            continue

        trial_profile = _copy_profile(state.profile)
        _commit_profile(instance, activity, candidate_start, trial_profile)
        trial_pending = tuple(item for item in state.pending if item != activity)
        trial_starts = list(state.scheduled_starts)
        trial_starts[activity] = candidate_start
        child = _PartialState(
            pending=trial_pending,
            scheduled_starts=tuple(trial_starts),
            lower_bounds=tuple(trial_lower),
            upper_bounds=tuple(trial_upper),
            profile=trial_profile,
            scheduled=frozenset(trial_scheduled),
            current_makespan=max(
                state.current_makespan,
                candidate_start + instance.activities[activity].duration,
            ),
            scheduled_count=state.scheduled_count + 1,
        )
        return child, attempts

    return None, attempts


def _eligible_candidates(
    instance: SgsInstance,
    state: _PartialState,
) -> list[int]:
    scheduled = state.scheduled
    scored: list[tuple[tuple[int, ...], int]] = []
    for index, activity in enumerate(state.pending):
        if not all(
            predecessor.activity in scheduled
            for predecessor in instance.activities[activity].min_predecessors
        ):
            continue
        lower = _dynamic_lower_bound(instance, activity, list(state.lower_bounds), set(scheduled))
        upper = state.upper_bounds[activity]
        if lower > upper:
            continue
        slack = upper - lower
        scored.append(
            (
                (
                    slack,
                    upper,
                    -len(instance.activities[activity].max_successors),
                    -len(instance.activities[activity].min_successors),
                    index,
                    activity,
                ),
                activity,
            )
        )

    scored.sort(key=lambda item: item[0])
    return [activity for _, activity in scored[:BOOTSTRAP_BRANCH_LIMIT]]


def _state_rank(
    instance: SgsInstance,
    state: _PartialState,
) -> tuple[int, int, int, int]:
    sink_lower = state.lower_bounds[instance.sink]
    sink_upper = state.upper_bounds[instance.sink]
    pending_window = 0
    for activity in state.pending[: min(5, len(state.pending))]:
        upper = state.upper_bounds[activity]
        lower = state.lower_bounds[activity]
        pending_window += 10_000 if upper >= POS_INF else max(0, upper - lower)
    return (
        sink_lower,
        state.current_makespan,
        sink_upper if sink_upper < POS_INF else POS_INF,
        pending_window,
    )


def beam_decode_priority_list(
    instance: SgsInstance,
    priority_list: tuple[int, ...] | list[int],
    *,
    deadline: float | None = None,
    beam_width: int = BOOTSTRAP_BEAM_WIDTH,
    latest_starts: list[int] | None = None,
) -> tuple[Schedule | None, DecodeStats]:
    pending = [
        activity
        for activity in priority_list
        if activity in instance.internal_activities
    ]
    seen = set(pending)
    if len(seen) != len(instance.internal_activities):
        for activity in instance.internal_activities:
            if activity not in seen:
                pending.append(activity)
                seen.add(activity)

    starts = [-1] * instance.n_activities
    starts[instance.source] = 0
    lower_bounds, upper_bounds = _initial_windows(instance, latest_starts)
    states = [
        _PartialState(
            pending=tuple(pending),
            scheduled_starts=tuple(starts),
            lower_bounds=tuple(lower_bounds),
            upper_bounds=tuple(upper_bounds),
            profile=[],
            scheduled=frozenset({instance.source}),
            current_makespan=0,
            scheduled_count=0,
        )
    ]
    attempts = 0

    while states:
        if deadline is not None and time.perf_counter() >= deadline:
            break

        next_states: list[_PartialState] = []
        for state in states:
            if not state.pending:
                final_starts = list(state.scheduled_starts)
                final_starts[instance.sink] = state.lower_bounds[instance.sink]
                schedule = Schedule(
                    start_times=tuple(final_starts),
                    makespan=final_starts[instance.sink],
                )
                if not validate_schedule(instance.base_instance, schedule):
                    return schedule, DecodeStats(
                        scheduled_activities=state.scheduled_count,
                        attempts=attempts,
                    )
                continue

            candidates = _eligible_candidates(instance, state)
            if not candidates:
                continue

            for activity in candidates:
                child, child_attempts = _schedule_activity(
                    instance,
                    state,
                    activity,
                    deadline=deadline,
                )
                attempts += child_attempts
                if child is not None:
                    next_states.append(child)

        if not next_states:
            break

        next_states.sort(key=lambda state: _state_rank(instance, state))
        states = next_states[:beam_width]

    best_scheduled = max((state.scheduled_count for state in states), default=0)
    return None, DecodeStats(scheduled_activities=best_scheduled, attempts=attempts)


def decode_priority_list(
    instance: SgsInstance,
    priority_list: tuple[int, ...] | list[int],
    *,
    deadline: float | None = None,
    latest_starts: list[int] | None = None,
) -> tuple[Schedule | None, DecodeStats]:
    scheduled_starts: dict[int, int] = {instance.source: 0}
    lower_bounds, upper_bounds = _initial_windows(instance, latest_starts)
    profile: list[list[int]] = []
    pending = [
        activity
        for activity in priority_list
        if activity in instance.internal_activities
    ]
    seen = set(pending)
    if len(seen) != len(instance.internal_activities):
        for activity in instance.internal_activities:
            if activity not in seen:
                pending.append(activity)
                seen.add(activity)
    scheduled = {instance.source}
    scheduled_count = 0
    attempts = 0
    current_makespan = 0

    while pending:
        if deadline is not None and time.perf_counter() >= deadline:
            break

        eligible_indices: list[int] = []
        candidate_indices: list[int] = []
        for index, activity in enumerate(pending):
            if not all(
                predecessor.activity in scheduled_starts
                for predecessor in instance.activities[activity].min_predecessors
            ):
                continue
            candidate_indices.append(index)
            limit = ELIGIBLE_LOOKAHEAD if latest_starts is None else WINDOW_LOOKAHEAD
            if len(candidate_indices) >= limit:
                break

        if latest_starts is None:
            eligible_indices = candidate_indices
        else:
            scored_eligible: list[tuple[tuple[int, int, int], int]] = []
            for index in candidate_indices:
                activity = pending[index]
                lower = _dynamic_lower_bound(instance, activity, lower_bounds, scheduled)
                upper = upper_bounds[activity]
                slack = window_slack(lower, upper)
                scored_eligible.append(((slack, index, upper), index))
            scored_eligible.sort(key=lambda item: item[0])
            eligible_indices = [index for _, index in scored_eligible]

        if not eligible_indices:
            return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)

        placed = False
        for next_index in eligible_indices:
            activity = pending[next_index]
            lower = _dynamic_lower_bound(instance, activity, lower_bounds, scheduled)
            upper = upper_bounds[activity]
            if lower > upper:
                continue

            limit = _search_limit(lower, upper, current_makespan)
            for candidate_start in range(lower, limit + 1):
                attempts += 1
                if deadline is not None and time.perf_counter() >= deadline:
                    return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)
                if not _resource_feasible(instance, activity, candidate_start, profile):
                    continue

                trial_lower = lower_bounds[:]
                trial_upper = upper_bounds[:]
                _tighten_windows(instance, trial_lower, trial_upper, activity, candidate_start)
                if not _windows_feasible(instance, scheduled | {activity}, trial_lower, trial_upper):
                    continue

                trial_profile = _copy_profile(profile)
                _commit_profile(instance, activity, candidate_start, trial_profile)
                trial_makespan = max(
                    current_makespan,
                    candidate_start + instance.activities[activity].duration,
                )

                pending.pop(next_index)
                scheduled_starts[activity] = candidate_start
                scheduled.add(activity)
                lower_bounds = trial_lower
                upper_bounds = trial_upper
                profile = trial_profile
                current_makespan = trial_makespan
                scheduled_count += 1
                placed = True
                break

            if placed:
                break

        if not placed:
            return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)

    if pending:
        return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)

    final_starts = [0] * instance.n_activities
    for activity, start in scheduled_starts.items():
        final_starts[activity] = start
    final_starts[instance.sink] = lower_bounds[instance.sink]

    schedule = Schedule(start_times=tuple(final_starts), makespan=final_starts[instance.sink])
    if validate_schedule(instance.base_instance, schedule):
        return None, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)
    return schedule, DecodeStats(scheduled_activities=scheduled_count, attempts=attempts)
