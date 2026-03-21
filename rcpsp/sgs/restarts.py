from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..models import Schedule
from .fbi import forward_backward_improve
from .models import SgsInstance
from .priorities import priority_order_for_restart, seed_priority_lists
from .serial import decode_priority_list


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
) -> tuple[Schedule | None, RestartStats]:
    best = None
    restarts = 0
    decode_attempts = 0
    improvement_passes = 0
    seeded_priorities = seed_priority_lists(instance, temporal_lower)
    project_lower = temporal_lower[instance.sink]
    soft_restart_cap = max(len(seeded_priorities) * 2, instance.n_activities * 4)

    while time.perf_counter() < deadline:
        if max_restarts is not None and restarts >= max_restarts:
            break

        priority = priority_order_for_restart(
            instance,
            temporal_lower,
            rng,
            restarts,
            seeded_priorities,
        )
        candidate, stats = decode_priority_list(instance, priority, deadline=deadline)
        decode_attempts += stats.attempts
        if candidate is not None and (best is None or candidate.makespan < best.makespan):
            best = candidate
            if time.perf_counter() < deadline:
                improved, passes = forward_backward_improve(instance, candidate, deadline=deadline)
                improvement_passes += passes
                if improved.makespan < best.makespan:
                    best = improved

        restarts += 1
        if best is not None and best.makespan == project_lower:
            break
        if best is not None and restarts >= soft_restart_cap:
            break

    return best, RestartStats(
        restarts=restarts,
        decode_attempts=decode_attempts,
        improvement_passes=improvement_passes,
    )
