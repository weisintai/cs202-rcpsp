from __future__ import annotations

import random
import time

from ..config import HeuristicConfig
from ..core.branching import delay_scores
from ..core.compress import compress_valid_schedule, left_shift
from ..core.conflicts import first_conflict, minimal_conflict_set, shared_resource_overload
from ..models import Edge, Instance, Schedule
from ..temporal import TemporalInfeasibleError, longest_feasible_starts
from ..validate import validate_schedule

CONSTRUCT_FAILURE_REASONS = (
    "deadline",
    "step_limit",
    "projection_infeasible",
    "validation",
    "unknown",
)


def construct_failure_reason(diagnostics: dict[str, object] | None) -> str:
    if diagnostics is None:
        return "unknown"
    reason = diagnostics.get("failure_reason")
    if isinstance(reason, str) and reason in CONSTRUCT_FAILURE_REASONS:
        return reason
    return "unknown"


def _construct_failure(
    diagnostics: dict[str, object] | None,
    *,
    reason: str,
    steps: int,
    focused_repair: bool,
    used_release_fallback: bool,
    termination_reason: str | None = None,
) -> None:
    if diagnostics is None:
        return
    diagnostics["status"] = "failed"
    diagnostics["failure_reason"] = reason
    diagnostics["steps"] = steps
    diagnostics["focused_repair"] = focused_repair
    diagnostics["used_release_fallback"] = used_release_fallback
    if termination_reason is not None:
        diagnostics["termination_reason"] = termination_reason


def _construct_success(
    diagnostics: dict[str, object] | None,
    *,
    schedule: Schedule,
    steps: int,
    focused_repair: bool,
    used_release_fallback: bool,
    termination_reason: str,
) -> None:
    if diagnostics is None:
        return
    diagnostics["status"] = "success"
    diagnostics["failure_reason"] = None
    diagnostics["steps"] = steps
    diagnostics["focused_repair"] = focused_repair
    diagnostics["used_release_fallback"] = used_release_fallback
    diagnostics["termination_reason"] = termination_reason
    diagnostics["makespan"] = schedule.makespan


def _schedule_from_starts(
    instance: Instance,
    start_times: list[int],
) -> Schedule:
    return Schedule(start_times=tuple(start_times), makespan=start_times[instance.sink])


def _validated_schedule(
    instance: Instance,
    start_times: list[int],
) -> Schedule | None:
    schedule = _schedule_from_starts(instance, start_times)
    if validate_schedule(instance, schedule):
        return None
    return schedule


def _candidate_from_edges(
    instance: Instance,
    release_times: list[int],
    candidate_edges: list[Edge],
    candidate_pairs: set[tuple[int, int]],
) -> tuple[int, int, list[Edge], set[tuple[int, int]], list[int]] | None:
    try:
        candidate_schedule = longest_feasible_starts(
            instance,
            release_times=release_times,
            extra_edges=candidate_edges,
        )
    except TemporalInfeasibleError:
        return None
    return (
        candidate_schedule[instance.sink],
        len(candidate_edges),
        candidate_edges,
        candidate_pairs,
        candidate_schedule,
    )


def construct_schedule(
    instance: Instance,
    rng: random.Random,
    tail: list[int],
    intensity: list[float],
    config: HeuristicConfig,
    deadline: float | None = None,
    base_extra_edges: list[Edge] | tuple[Edge, ...] = (),
    initial_starts: list[int] | None = None,
    diagnostics: dict[str, object] | None = None,
) -> Schedule | None:
    """Build a valid CP warm-start schedule or return None if construction fails."""
    use_focused_repair = instance.n_jobs >= 20
    release = [0] * instance.n_activities
    extra_edges = list(base_extra_edges)
    if initial_starts is not None:
        current = initial_starts[:]
    else:
        try:
            current = longest_feasible_starts(instance, release, extra_edges=extra_edges)
        except TemporalInfeasibleError:
            _construct_failure(
                diagnostics,
                reason="projection_infeasible",
                steps=0,
                focused_repair=use_focused_repair,
                used_release_fallback=False,
                termination_reason="initial_projection",
            )
            return None
    extra_pairs: set[tuple[int, int]] = {(edge.source, edge.target) for edge in extra_edges}
    max_steps = max(200, instance.n_activities * instance.n_activities * 6)
    steps = 0
    termination_reason = "resolved"
    used_release_fallback = False

    while True:
        if deadline is not None and time.perf_counter() >= deadline:
            termination_reason = "deadline"
            break
        if steps >= max_steps:
            termination_reason = "step_limit"
            break
        if use_focused_repair:
            focused_conflict = minimal_conflict_set(instance, current)
            if focused_conflict is None:
                break
            conflict_time, resource, active, overload = focused_conflict
        else:
            broad_conflict = first_conflict(instance, current)
            if broad_conflict is None:
                break
            conflict_time, overload, active = broad_conflict
            resource = -1
        ranked = delay_scores(
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
                    and (use_focused_repair or shared_resource_overload(instance, selected, activity, overload))
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
                        candidate = _candidate_from_edges(
                            instance=instance,
                            release_times=release,
                            candidate_edges=candidate_edges,
                            candidate_pairs=candidate_pairs,
                        )
                        if candidate is not None:
                            candidate_options.append(candidate)
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
                    candidate = _candidate_from_edges(
                        instance=instance,
                        release_times=release,
                        candidate_edges=candidate_edges,
                        candidate_pairs=candidate_pairs,
                    )
                    if candidate is not None:
                        candidate_options.append(candidate)
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
                if activity != selected and (use_focused_repair or shared_resource_overload(instance, selected, activity, overload))
            ]
            fallback_target = max(
                (current[activity] + instance.durations[activity] for activity in blockers),
                default=conflict_time + 1,
            )
            release[selected] = max(release[selected], fallback_target)
            used_release_fallback = True
            try:
                current = longest_feasible_starts(instance, release_times=release, extra_edges=extra_edges)
            except TemporalInfeasibleError:
                _construct_failure(
                    diagnostics,
                    reason="projection_infeasible",
                    steps=steps,
                    focused_repair=use_focused_repair,
                    used_release_fallback=used_release_fallback,
                    termination_reason=termination_reason,
                )
                return None
        steps += 1

    try:
        current = longest_feasible_starts(instance, release_times=release, extra_edges=extra_edges)
    except TemporalInfeasibleError:
        _construct_failure(
            diagnostics,
            reason="projection_infeasible",
            steps=steps,
            focused_repair=use_focused_repair,
            used_release_fallback=used_release_fallback,
            termination_reason=termination_reason,
        )
        return None
    if any(value > 0 for value in release):
        try:
            release_free = longest_feasible_starts(instance, extra_edges=extra_edges)
        except TemporalInfeasibleError:
            release_free = None
        if release_free is not None:
            release_free_schedule = _validated_schedule(instance, release_free)
            if release_free_schedule is not None:
                current = release_free
    current = left_shift(instance, current, extra_edges)
    current_schedule = _validated_schedule(instance, current)
    if current_schedule is None:
        repaired = left_shift(instance, current, [])
        repaired_schedule = _validated_schedule(instance, repaired)
        if repaired_schedule is not None:
            current = repaired
            current_schedule = repaired_schedule
    if current_schedule is None:
        failure_reason = termination_reason if termination_reason in {"deadline", "step_limit"} else "validation"
        _construct_failure(
            diagnostics,
            reason=failure_reason,
            steps=steps,
            focused_repair=use_focused_repair,
            used_release_fallback=used_release_fallback,
            termination_reason=termination_reason,
        )
        return None
    current = compress_valid_schedule(instance, list(current_schedule.start_times))
    final_schedule = _schedule_from_starts(instance, current)
    _construct_success(
        diagnostics,
        schedule=final_schedule,
        steps=steps,
        focused_repair=use_focused_repair,
        used_release_fallback=used_release_fallback,
        termination_reason=termination_reason,
    )
    return final_schedule
