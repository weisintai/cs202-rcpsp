from __future__ import annotations

from .models import Edge, Instance


class TemporalInfeasibleError(ValueError):
    pass


def longest_feasible_starts(
    instance: Instance,
    release_times: list[int] | tuple[int, ...] | None = None,
    extra_edges: list[Edge] | tuple[Edge, ...] | None = None,
) -> list[int]:
    n = instance.n_activities
    if release_times is None:
        starts = [0] * n
    else:
        if len(release_times) != n:
            raise ValueError("release_times length does not match the instance size")
        starts = [max(0, int(value)) for value in release_times]
    starts[instance.source] = 0

    all_edges = instance.edges if extra_edges is None else tuple(instance.edges) + tuple(extra_edges)

    for _ in range(n - 1):
        updated = False
        for edge in all_edges:
            candidate = starts[edge.source] + edge.lag
            if candidate > starts[edge.target]:
                starts[edge.target] = candidate
                updated = True
        starts[instance.source] = 0
        if not updated:
            return starts

    for edge in all_edges:
        if starts[edge.source] + edge.lag > starts[edge.target]:
            raise TemporalInfeasibleError(
                f"{instance.name} contains an inconsistent lag cycle involving {edge.source}->{edge.target}"
            )
    starts[instance.source] = 0
    return starts


def longest_tail_to_sink(instance: Instance) -> list[int]:
    tail = [-10**12] * instance.n_activities
    tail[instance.sink] = 0

    for _ in range(instance.n_activities - 1):
        updated = False
        for edge in instance.edges:
            if tail[edge.target] == -10**12:
                continue
            candidate = edge.lag + tail[edge.target]
            if candidate > tail[edge.source]:
                tail[edge.source] = candidate
                updated = True
        if not updated:
            break

    for edge in instance.edges:
        if tail[edge.target] == -10**12:
            continue
        if edge.lag + tail[edge.target] > tail[edge.source]:
            raise TemporalInfeasibleError(
                f"{instance.name} contains an inconsistent lag cycle involving {edge.source}->{edge.target}"
            )

    for index, value in enumerate(tail):
        if value == -10**12:
            tail[index] = 0
    return tail
