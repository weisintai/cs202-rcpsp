from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class HeuristicConfig:
    slack_weight: float = 3.5
    tail_weight: float = 1.2
    overload_weight: float = 2.5
    resource_weight: float = 0.6
    late_weight: float = 0.3
    noise_weight: float = 0.2
    max_restarts: int | None = None


def sample_heuristic_config(base: HeuristicConfig, rng: random.Random) -> HeuristicConfig:
    return HeuristicConfig(
        slack_weight=max(0.0, base.slack_weight + rng.uniform(-0.8, 0.8)),
        tail_weight=max(0.0, base.tail_weight + rng.uniform(-0.4, 0.4)),
        overload_weight=max(0.0, base.overload_weight + rng.uniform(-0.6, 0.6)),
        resource_weight=max(0.0, base.resource_weight + rng.uniform(-0.2, 0.2)),
        late_weight=max(0.0, base.late_weight + rng.uniform(-0.2, 0.2)),
        noise_weight=max(0.0, base.noise_weight + rng.uniform(-0.1, 0.1)),
        max_restarts=base.max_restarts,
    )
