from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Edge:
    source: int
    target: int
    lag: int


@dataclass(frozen=True)
class Instance:
    name: str
    path: Path
    n_jobs: int
    n_resources: int
    durations: tuple[int, ...]
    demands: tuple[tuple[int, ...], ...]
    capacities: tuple[int, ...]
    edges: tuple[Edge, ...]
    outgoing: tuple[tuple[Edge, ...], ...]
    incoming: tuple[tuple[Edge, ...], ...]
    source: int = 0
    sink: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sink", self.n_jobs + 1)

    @property
    def n_activities(self) -> int:
        return self.n_jobs + 2


@dataclass(frozen=True)
class Schedule:
    start_times: tuple[int, ...]
    makespan: int


@dataclass(frozen=True)
class SolveResult:
    instance_name: str
    status: str
    schedule: Schedule | None
    runtime_seconds: float
    temporal_lower_bound: int
    restarts: int
    metadata: dict[str, float | int | str]
