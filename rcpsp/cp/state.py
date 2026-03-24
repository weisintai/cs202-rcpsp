from __future__ import annotations

from dataclasses import dataclass

from ..models import Edge


@dataclass
class CpSearchStats:
    nodes: int = 0
    timed_out: bool = False
    incumbent_updates: int = 0
    heuristic_construct_failures: int = 0
    heuristic_construct_deadline_failures: int = 0
    heuristic_construct_step_limit_failures: int = 0
    heuristic_construct_projection_infeasible_failures: int = 0
    heuristic_construct_validation_failures: int = 0
    heuristic_construct_unknown_failures: int = 0
    node_local_attempts: int = 0
    node_local_improvements: int = 0
    node_local_construct_failures: int = 0
    node_local_construct_deadline_failures: int = 0
    node_local_construct_step_limit_failures: int = 0
    node_local_construct_projection_infeasible_failures: int = 0
    node_local_construct_validation_failures: int = 0
    node_local_construct_unknown_failures: int = 0
    deep_node_local_attempts: int = 0
    deep_node_local_improvements: int = 0
    branches: int = 0
    propagation_calls: int = 0
    propagation_rounds: int = 0
    propagation_pruned_nodes: int = 0
    timetable_failures: int = 0
    max_timetable_explanation: int = 0
    failure_cache_hits: int = 0
    failure_cache_inserts: int = 0
    failure_cache_size: int = 0
    conflict_events: int = 0
    total_conflict_size: int = 0
    max_conflict_size: int = 0


@dataclass(frozen=True)
class CpNode:
    lower: tuple[int, ...]
    latest: tuple[int, ...] | None
    edges: tuple[Edge, ...]
    pairs: frozenset[tuple[int, int]]
    lag_dist: list[list[float]] | None = None


@dataclass(frozen=True)
class OverloadExplanation:
    kind: str
    resource: int
    window_start: int
    window_end: int
    activities: tuple[int, ...]
    required: int
    limit: int

    @property
    def size(self) -> int:
        return len(self.activities)

    def summary(self) -> str:
        activities = ",".join(str(activity) for activity in self.activities)
        return (
            f"{self.kind} overload on resource {self.resource} in "
            f"[{self.window_start},{self.window_end}) by activities [{activities}] "
            f"with load {self.required}>{self.limit}"
        )


@dataclass(frozen=True)
class CpNodePropagation:
    node: CpNode | None
    overload: OverloadExplanation | None = None
    rounds: int = 0
