from __future__ import annotations

import time

from ..models import Schedule
from .models import SgsInstance
from .priorities import priority_from_schedule, reverse_priority_from_schedule
from .serial import decode_priority_list


def forward_backward_improve(
    instance: SgsInstance,
    schedule: Schedule,
    *,
    deadline: float,
) -> tuple[Schedule, int]:
    best = schedule
    passes = 0
    priority_candidates = (
        priority_from_schedule(instance, best),
        reverse_priority_from_schedule(instance, best),
    )

    for priority in priority_candidates:
        if time.perf_counter() >= deadline:
            break
        candidate, _ = decode_priority_list(instance, priority, deadline=deadline)
        passes += 1
        if candidate is not None and candidate.makespan < best.makespan:
            best = candidate

    return best, passes
