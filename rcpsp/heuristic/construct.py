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
                if activity != selected and (use_focused_repair or shared_resource_overload(instance, selected, activity, overload))
            ]
            fallback_target = max(
                (current[activity] + instance.durations[activity] for activity in blockers),
                default=conflict_time + 1,
            )
            prior_release = release[selected]
            release[selected] = max(release[selected], fallback_target)
            try:
                current = longest_feasible_starts(instance, release_times=release, extra_edges=extra_edges)
            except TemporalInfeasibleError:
                # A fallback release move can contradict the current order edges.
                # Treat that move as a dead end instead of aborting the whole solve.
                release[selected] = prior_release
                break
        steps += 1

    try:
        current = longest_feasible_starts(instance, release_times=release, extra_edges=extra_edges)
    except TemporalInfeasibleError:
        pass
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
    current = left_shift(instance, current, extra_edges)
    current_schedule = Schedule(start_times=tuple(current), makespan=current[instance.sink])
    if validate_schedule(instance, current_schedule):
        repaired = left_shift(instance, current, [])
        repaired_schedule = Schedule(start_times=tuple(repaired), makespan=repaired[instance.sink])
        if not validate_schedule(instance, repaired_schedule):
            current = repaired
            current_schedule = repaired_schedule
    if not validate_schedule(instance, current_schedule):
        current = compress_valid_schedule(instance, current)
    return Schedule(start_times=tuple(current), makespan=current[instance.sink])
