from __future__ import annotations

from .models import SgsInstance

NEG_INF = float("-inf")
POS_INF = 10**12


def latest_starts_from_upper_bound(
    instance: SgsInstance,
    upper_bound: int,
) -> list[int]:
    latest = [POS_INF] * instance.n_activities
    latest[instance.sink] = upper_bound

    for activity in range(instance.n_activities):
        tail = instance.lag_dist[activity][instance.sink]
        if tail != NEG_INF:
            latest[activity] = upper_bound - int(tail)

    latest[instance.source] = 0
    return latest


def window_slack(
    lower_bound: int,
    latest_start: int | None,
) -> int:
    if latest_start is None or latest_start >= POS_INF:
        return POS_INF
    return latest_start - lower_bound
