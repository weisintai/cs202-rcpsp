from __future__ import annotations

import time
from dataclasses import dataclass

from ..core.branching import branch_order
from ..core.compress import compress_valid_schedule
from ..core.conflicts import minimal_conflict_set
from ..core.lag import (
    all_pairs_longest_lags,
    extend_longest_lags,
    pairwise_infeasibility_reason,
    pairwise_infeasibility_reason_from_dist,
)
from ..models import Edge, Instance, Schedule
from ..temporal import TemporalInfeasibleError, longest_feasible_starts


@dataclass
class SearchStats:
    nodes: int = 0
    timed_out: bool = False


def branch_and_bound_search(
    instance: Instance,
    tail: list[int],
    intensity: list[float],
    deadline: float,
    incumbent: Schedule | None = None,
    incremental_pairwise: bool = True,
    base_extra_edges: list[Edge] | tuple[Edge, ...] = (),
) -> tuple[Schedule | None, SearchStats]:
    stats = SearchStats()
    seen: set[tuple[tuple[int, int], ...]] = set()
    best = incumbent
    global_lower_bound = longest_feasible_starts(instance, extra_edges=base_extra_edges)[instance.sink]
    root_lag_dist = all_pairs_longest_lags(instance, extra_edges=base_extra_edges) if incremental_pairwise and incumbent is None else None

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
                if pairwise_infeasibility_reason(instance, extra_edges) is not None:
                    return
            elif pairwise_infeasibility_reason_from_dist(instance, lag_dist) is not None:
                return

        conflict = minimal_conflict_set(instance, start_times)
        if conflict is None:
            candidate_starts = compress_valid_schedule(instance, start_times)
            candidate = Schedule(start_times=tuple(candidate_starts), makespan=candidate_starts[instance.sink])
            if best is None or candidate.makespan < best.makespan:
                best = candidate
            return

        _, resource, conflict_set, overload = conflict
        if len(conflict_set) <= 1:
            return

        ordered = branch_order(instance, start_times, tail, intensity, conflict_set, overload)
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
                        child_lag_dist = extend_longest_lags(child_lag_dist, edge)
                        if pairwise_infeasibility_reason_from_dist(instance, child_lag_dist) is not None:
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

    base_pairs = {(edge.source, edge.target) for edge in base_extra_edges}
    base_edges = list(base_extra_edges)
    root_starts = longest_feasible_starts(instance, extra_edges=base_edges)
    dfs(base_edges, base_pairs, root_starts, root_lag_dist)
    return best, stats
