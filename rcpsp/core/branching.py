from __future__ import annotations

import random

from ..config import HeuristicConfig
from ..models import Instance


def delay_scores(
    instance: Instance,
    start_times: list[int],
    makespan: int,
    tail: list[int],
    overload: list[int],
    active: list[int],
    intensity: list[float],
    rng: random.Random,
    config: HeuristicConfig,
) -> list[tuple[float, int]]:
    ranked: list[tuple[float, int]] = []
    for activity in active:
        slack = makespan - (start_times[activity] + tail[activity])
        overload_contribution = 0.0
        for resource, overload_amount in enumerate(overload):
            if overload_amount <= 0:
                continue
            overload_contribution += min(instance.demands[activity][resource], overload_amount)
        score = (
            config.slack_weight * slack
            - config.tail_weight * tail[activity]
            + config.overload_weight * overload_contribution
            + config.resource_weight * intensity[activity]
            + config.late_weight * start_times[activity]
            + config.noise_weight * rng.random()
        )
        ranked.append((score, activity))
    ranked.sort(reverse=True)
    return ranked


def branch_order(
    instance: Instance,
    start_times: list[int],
    tail: list[int],
    intensity: list[float],
    conflict: list[int],
    overload: list[int],
) -> list[int]:
    makespan = start_times[instance.sink]
    ranked = delay_scores(
        instance=instance,
        start_times=start_times,
        makespan=makespan,
        tail=tail,
        overload=overload,
        active=conflict,
        intensity=intensity,
        rng=random.Random(0),
        config=HeuristicConfig(noise_weight=0.0),
    )
    return [activity for _, activity in ranked]
