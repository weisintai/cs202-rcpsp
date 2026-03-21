from __future__ import annotations

from dataclasses import dataclass

from ..models import Instance


@dataclass(frozen=True)
class LagArc:
    activity: int
    lag: int


@dataclass(frozen=True)
class MaxLagArc:
    activity: int
    lag: int


@dataclass(frozen=True)
class Activity:
    id: int
    duration: int
    demands: tuple[int, ...]
    min_predecessors: tuple[LagArc, ...]
    min_successors: tuple[LagArc, ...]
    max_predecessors: tuple[MaxLagArc, ...]
    max_successors: tuple[MaxLagArc, ...]


@dataclass(frozen=True)
class SgsInstance:
    base_instance: Instance
    activities: tuple[Activity, ...]
    capacities: tuple[int, ...]
    topo_order: tuple[int, ...]
    internal_activities: tuple[int, ...]
    lag_dist: tuple[tuple[float, ...], ...]

    @property
    def source(self) -> int:
        return self.base_instance.source

    @property
    def sink(self) -> int:
        return self.base_instance.sink

    @property
    def n_activities(self) -> int:
        return self.base_instance.n_activities
