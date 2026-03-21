from __future__ import annotations

import heapq
import random

from .models import SgsInstance


def stable_topological_order(
    n_activities: int,
    source: int,
    sink: int,
    edges: list[tuple[int, int]],
) -> tuple[int, ...]:
    indegree = [0] * n_activities
    outgoing = [[] for _ in range(n_activities)]
    for tail, head in edges:
        outgoing[tail].append(head)
        indegree[head] += 1

    heap = [source]
    seen = {source}
    for activity in range(n_activities):
        if activity == source:
            continue
        if indegree[activity] == 0:
            heapq.heappush(heap, activity)
            seen.add(activity)

    order: list[int] = []
    while heap:
        activity = heapq.heappop(heap)
        order.append(activity)
        for successor in outgoing[activity]:
            indegree[successor] -= 1
            if indegree[successor] == 0 and successor not in seen:
                heapq.heappush(heap, successor)
                seen.add(successor)

    if len(order) != n_activities:
        remainder = [activity for activity in range(n_activities) if activity not in set(order)]
        order.extend(sorted(remainder))

    if sink in order:
        order = [activity for activity in order if activity != sink] + [sink]
    if source in order:
        order = [source] + [activity for activity in order if activity != source]
    return tuple(order)


def random_topological_order(
    instance: SgsInstance,
    rng: random.Random,
) -> tuple[int, ...]:
    n_activities = instance.n_activities
    indegree = [0] * n_activities
    outgoing = [[] for _ in range(n_activities)]
    for activity in instance.activities:
        for arc in activity.min_successors:
            outgoing[activity.id].append(arc.activity)
            indegree[arc.activity] += 1

    ready = [instance.source]
    ready.extend(
        activity
        for activity in range(n_activities)
        if activity != instance.source and indegree[activity] == 0
    )
    order: list[int] = []

    while ready:
        index = rng.randrange(len(ready))
        activity = ready.pop(index)
        if activity in order:
            continue
        order.append(activity)
        for successor in outgoing[activity]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)

    if len(order) != n_activities:
        remainder = [activity for activity in range(n_activities) if activity not in set(order)]
        rng.shuffle(remainder)
        order.extend(remainder)

    if instance.sink in order:
        order = [activity for activity in order if activity != instance.sink] + [instance.sink]
    if instance.source in order:
        order = [instance.source] + [activity for activity in order if activity != instance.source]
    return tuple(order)
