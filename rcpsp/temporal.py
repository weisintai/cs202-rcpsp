from __future__ import annotations

from collections import deque

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

    if extra_edges is None:
        outgoing: tuple[tuple[Edge, ...], ...] | list[list[Edge]] = instance.outgoing
    else:
        outgoing = [list(edges) for edges in instance.outgoing]
        for edge in extra_edges:
            outgoing[edge.source].append(edge)

    queue = deque(range(n))
    in_queue = [True] * n
    update_counts = [0] * n

    while queue:
        source = queue.popleft()
        in_queue[source] = False
        source_start = starts[source]

        for edge in outgoing[source]:
            candidate = source_start + edge.lag
            target = edge.target
            if target == instance.source:
                if candidate > 0:
                    raise TemporalInfeasibleError(
                        f"{instance.name} contains an inconsistent lag cycle involving {edge.source}->{edge.target}"
                    )
                continue
            if candidate <= starts[target]:
                continue
            starts[target] = candidate
            update_counts[target] += 1
            if update_counts[target] >= n:
                raise TemporalInfeasibleError(
                    f"{instance.name} contains an inconsistent lag cycle involving {edge.source}->{edge.target}"
                )
            if not in_queue[target]:
                queue.append(target)
                in_queue[target] = True

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
