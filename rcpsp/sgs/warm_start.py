from __future__ import annotations

import random
import time

from ..config import HeuristicConfig, sample_heuristic_config
from ..core.metrics import resource_intensity
from ..heuristic.construct import construct_schedule
from ..models import Instance, Schedule
from ..temporal import longest_tail_to_sink
from ..validate import validate_schedule


def warm_start_budget_seconds(
    time_limit: float,
    n_jobs: int,
) -> float:
    if time_limit <= 0:
        return 0.0

    fraction = 0.18 if n_jobs <= 20 else 0.12
    cap = 0.03 if n_jobs <= 20 else 0.05
    return min(cap, max(0.005, time_limit * fraction))


def generate_warm_start(
    instance: Instance,
    *,
    rng: random.Random,
    deadline: float,
    base_config: HeuristicConfig | None = None,
) -> Schedule | None:
    if time.perf_counter() >= deadline:
        return None

    tail = longest_tail_to_sink(instance)
    intensity = resource_intensity(instance)
    config = base_config or HeuristicConfig()
    best: Schedule | None = None
    attempts = 0

    while time.perf_counter() < deadline:
        attempts += 1
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break

        candidate = construct_schedule(
            instance=instance,
            rng=rng,
            tail=tail,
            intensity=intensity,
            config=sample_heuristic_config(config, rng),
            deadline=deadline,
        )
        if validate_schedule(instance, candidate):
            if attempts >= 2:
                break
            continue
        if best is None or candidate.makespan < best.makespan:
            best = candidate
            if best.makespan == tail[instance.source]:
                break

    return best
