from __future__ import annotations

import random
from dataclasses import dataclass

from ..models import Schedule
from .alns import SearchStats, run_alns_batch
from .models import SgsInstance


@dataclass(frozen=True)
class RestartStats:
    restarts: int
    decode_attempts: int
    improvement_passes: int


def run_restart_batch(
    instance: SgsInstance,
    temporal_lower: list[int],
    *,
    deadline: float,
    rng: random.Random,
    max_restarts: int | None = None,
    initial_schedule: Schedule | None = None,
):
    best, stats = run_alns_batch(
        instance,
        temporal_lower,
        deadline=deadline,
        rng=rng,
        max_iterations=max_restarts,
        initial_schedule=initial_schedule,
    )
    return best, RestartStats(
        restarts=stats.iterations,
        decode_attempts=stats.decode_attempts,
        improvement_passes=stats.improvement_passes,
    )
