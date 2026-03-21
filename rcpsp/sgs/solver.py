from __future__ import annotations

import random
import time

from ..config import HeuristicConfig
from ..core.lag import pairwise_infeasibility_reason
from ..models import SolveResult
from ..temporal import TemporalInfeasibleError, longest_feasible_starts
from .adapter import adapt_instance
from .restarts import run_restart_batch


def _build_result(
    *,
    instance_name: str,
    status: str,
    runtime: float,
    temporal_lower_bound: int,
    restarts: int,
    schedule=None,
    metadata: dict[str, object] | None = None,
) -> SolveResult:
    payload = {"backend": "sgs"}
    if metadata:
        payload.update(metadata)
    return SolveResult(
        instance_name=instance_name,
        status=status,
        schedule=schedule,
        runtime_seconds=runtime,
        temporal_lower_bound=temporal_lower_bound,
        restarts=restarts,
        metadata=payload,
    )


def solve_sgs(
    instance,
    time_limit: float = 30.0,
    seed: int = 0,
    config: HeuristicConfig | None = None,
) -> SolveResult:
    rng = random.Random(seed)
    started = time.perf_counter()
    deadline = started + time_limit
    sgs_instance = adapt_instance(instance)

    try:
        temporal_lower = longest_feasible_starts(instance)
    except TemporalInfeasibleError as exc:
        runtime = time.perf_counter() - started
        return _build_result(
            instance_name=instance.name,
            status="infeasible",
            runtime=runtime,
            temporal_lower_bound=-1,
            restarts=0,
            metadata={
                "reason": str(exc),
                "seed": seed,
                "time_limit": time_limit,
            },
        )

    pairwise_reason = pairwise_infeasibility_reason(instance)
    if pairwise_reason is not None:
        runtime = time.perf_counter() - started
        return _build_result(
            instance_name=instance.name,
            status="infeasible",
            runtime=runtime,
            temporal_lower_bound=temporal_lower[instance.sink],
            restarts=0,
            metadata={
                "reason": pairwise_reason,
                "seed": seed,
                "time_limit": time_limit,
            },
        )

    max_restarts = None if config is None else config.max_restarts
    best, stats = run_restart_batch(
        sgs_instance,
        temporal_lower,
        deadline=deadline,
        rng=rng,
        max_restarts=max_restarts,
    )

    runtime = time.perf_counter() - started
    if best is None:
        return _build_result(
            instance_name=instance.name,
            status="unknown",
            runtime=runtime,
            temporal_lower_bound=temporal_lower[instance.sink],
            restarts=stats.restarts,
            metadata={
                "seed": seed,
                "time_limit": time_limit,
                "decode_attempts": stats.decode_attempts,
                "improvement_passes": stats.improvement_passes,
                "reason": "sgs phase-1 decoder did not find a feasible schedule within the time limit",
            },
        )

    return _build_result(
        instance_name=instance.name,
        status="feasible",
        schedule=best,
        runtime=runtime,
        temporal_lower_bound=temporal_lower[instance.sink],
        restarts=stats.restarts,
        metadata={
            "seed": seed,
            "time_limit": time_limit,
            "decode_attempts": stats.decode_attempts,
            "improvement_passes": stats.improvement_passes,
        },
    )
