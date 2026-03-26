from __future__ import annotations

from pathlib import Path

from rcpsp.models import Edge, Instance, Schedule


def _probe_instance() -> Instance:
    edge01 = Edge(source=0, target=1, lag=0)
    edge12 = Edge(source=1, target=2, lag=1)
    return Instance(
        name="restart-probe",
        path=Path("restart-probe.sch"),
        n_jobs=1,
        n_resources=1,
        durations=(0, 1, 0),
        demands=((0,), (1,), (0,)),
        capacities=(1,),
        edges=(edge01, edge12),
        outgoing=((edge01,), (edge12,), ()),
        incoming=((), (edge01,), (edge12,)),
    )


def test_hybrid_solver_counts_invalid_attempts_toward_max_restarts(monkeypatch) -> None:
    from rcpsp.config import HeuristicConfig
    from rcpsp.heuristic.exact import SearchStats
    from rcpsp.heuristic.solver import solve

    instance = _probe_instance()
    calls = {"count": 0}

    def fake_construct(*args, **kwargs) -> Schedule:
        calls["count"] += 1
        return Schedule(start_times=(1, 0, 0), makespan=0)

    def fake_exact(*args, **kwargs):
        return None, SearchStats()

    monkeypatch.setattr("rcpsp.heuristic.solver.construct_schedule", fake_construct)
    monkeypatch.setattr("rcpsp.heuristic.solver.branch_and_bound_search", fake_exact)

    result = solve(instance, time_limit=0.02, seed=0, config=HeuristicConfig(max_restarts=1))

    assert calls["count"] == 1
    assert result.restarts == 1


def test_cp_guided_seed_counts_invalid_attempts_toward_max_restarts(monkeypatch) -> None:
    from rcpsp.config import HeuristicConfig
    from rcpsp.cp.guided_seed import solve

    instance = _probe_instance()
    calls = {"count": 0}

    def fake_construct(*args, **kwargs) -> None:
        calls["count"] += 1
        return None

    monkeypatch.setattr("rcpsp.cp.guided_seed.construct_schedule", fake_construct)

    result = solve(instance, time_limit=0.02, seed=0, config=HeuristicConfig(max_restarts=1))

    assert calls["count"] == 1
    assert result.restarts == 1
