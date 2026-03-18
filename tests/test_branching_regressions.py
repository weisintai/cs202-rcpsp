from __future__ import annotations

import random
import unittest
from pathlib import Path

from rcpsp.config import HeuristicConfig
from rcpsp.core.metrics import resource_intensity
from rcpsp.cp.search import solve_cp
from rcpsp.heuristic.construct import construct_schedule
from rcpsp.heuristic.solver import solve
from rcpsp.models import Edge, Instance
from rcpsp.temporal import longest_tail_to_sink


def _make_single_resource_instance(
    name: str,
    durations: tuple[int, ...],
    demands: tuple[int, ...],
    capacity: int,
    extra_edges: tuple[tuple[int, int, int], ...] = (),
) -> Instance:
    n_jobs = len(durations)
    n_activities = n_jobs + 2
    full_durations = (0, *durations, 0)
    full_demands = ((0,), *((demand,) for demand in demands), (0,))

    edges: list[Edge] = []
    for activity in range(1, n_jobs + 1):
        edges.append(Edge(source=0, target=activity, lag=0))
        edges.append(Edge(source=activity, target=n_jobs + 1, lag=full_durations[activity]))
    edges.extend(Edge(source, target, lag) for source, target, lag in extra_edges)

    outgoing = [[] for _ in range(n_activities)]
    incoming = [[] for _ in range(n_activities)]
    for edge in edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)

    return Instance(
        name=name,
        path=Path(name),
        n_jobs=n_jobs,
        n_resources=1,
        durations=tuple(full_durations),
        demands=tuple(full_demands),
        capacities=(capacity,),
        edges=tuple(edges),
        outgoing=tuple(tuple(values) for values in outgoing),
        incoming=tuple(tuple(values) for values in incoming),
    )


class BranchingRegressionTests(unittest.TestCase):
    def test_exact_branchers_can_find_weaker_single_activity_delay(self) -> None:
        instance = _make_single_resource_instance(
            name="branching-toy",
            durations=(2, 5, 1, 3),
            demands=(1, 2, 2, 2),
            capacity=5,
            extra_edges=((1, 3, 0),),
        )
        config = HeuristicConfig(max_restarts=4, noise_weight=0.0)

        heuristic = solve(instance, time_limit=0.2, seed=0, config=config)
        cp = solve_cp(instance, time_limit=0.2, seed=0, config=config)

        self.assertEqual("feasible", heuristic.status)
        self.assertIsNotNone(heuristic.schedule)
        self.assertEqual(5, heuristic.schedule.makespan)
        self.assertEqual((0, 0, 0, 3, 0, 5), heuristic.schedule.start_times)

        self.assertEqual("feasible", cp.status)
        self.assertIsNotNone(cp.schedule)
        self.assertEqual(5, cp.schedule.makespan)
        self.assertEqual((0, 0, 0, 3, 0, 5), cp.schedule.start_times)

    def test_small_instance_repair_uses_weaker_single_blocker_move(self) -> None:
        instance = _make_single_resource_instance(
            name="repair-toy",
            durations=(1, 3, 5, 4),
            demands=(3, 3, 1, 2),
            capacity=5,
            extra_edges=((3, 4, 0),),
        )

        schedule = construct_schedule(
            instance=instance,
            rng=random.Random(0),
            tail=longest_tail_to_sink(instance),
            intensity=resource_intensity(instance),
            config=HeuristicConfig(noise_weight=0.0, max_restarts=1),
        )

        self.assertEqual(7, schedule.makespan)
        self.assertEqual((0, 5, 0, 0, 3, 7), schedule.start_times)


if __name__ == "__main__":
    unittest.main()
