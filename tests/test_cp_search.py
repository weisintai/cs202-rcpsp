from __future__ import annotations

import random
import time
from pathlib import Path

from rcpsp.config import HeuristicConfig
from rcpsp.cp.search import (
    allow_node_local_heuristic,
    allow_deep_node_local_heuristic,
    child_order_key,
    cp_budget_mode,
    failure_cache_hit,
    node_signature,
    node_local_heuristic_deadline,
    pair_direction_possible,
    required_pair_gap,
    record_failed_pairs,
    run_guided_seed,
    select_branch_conflict,
    solve_cp,
    try_cp_incumbent,
    use_failure_cache,
)
from rcpsp.cp.state import CpNode, CpSearchStats
from rcpsp.models import Instance, Schedule, SolveResult


def _dummy_instance(n_jobs: int) -> Instance:
    n_activities = n_jobs + 2
    durations = tuple(0 for _ in range(n_activities))
    demands = tuple((0,) for _ in range(n_activities))
    return Instance(
        name=f"dummy-{n_jobs}",
        path=Path(f"dummy-{n_jobs}.sch"),
        n_jobs=n_jobs,
        n_resources=1,
        durations=durations,
        demands=demands,
        capacities=(1,),
        edges=(),
        outgoing=tuple(() for _ in range(n_activities)),
        incoming=tuple(() for _ in range(n_activities)),
    )


def test_failure_cache_prunes_supersets_and_keeps_minimal_sets() -> None:
    stats = CpSearchStats()
    failed_pair_sets: set[frozenset[tuple[int, int]]] = set()

    parent = frozenset({(1, 2), (3, 4)})
    superset = frozenset({(1, 2), (3, 4), (5, 6)})
    subset = frozenset({(1, 2)})

    record_failed_pairs(parent, failed_pair_sets, stats)
    assert failure_cache_hit(superset, failed_pair_sets)

    record_failed_pairs(subset, failed_pair_sets, stats)
    assert failed_pair_sets == {subset}
    assert failure_cache_hit(parent, failed_pair_sets)


def test_node_signature_distinguishes_tighter_latest_bounds() -> None:
    loose = CpNode(
        lower=(0, 1, 3),
        latest=(0, 4, 6),
        edges=(),
        pairs=frozenset({(1, 2)}),
    )
    tight = CpNode(
        lower=(0, 1, 3),
        latest=(0, 3, 5),
        edges=(),
        pairs=frozenset({(1, 2)}),
    )

    assert node_signature(loose) != node_signature(tight)


def test_select_branch_conflict_prefers_tighter_conflict() -> None:
    instance = _dummy_instance(3)
    instance = Instance(
        name=instance.name,
        path=instance.path,
        n_jobs=3,
        n_resources=1,
        durations=(0, 3, 2, 1, 0),
        demands=((0,), (1,), (1,), (1,), (0,)),
        capacities=(2,),
        edges=(
            instance.edges
            + ()
        ),
        outgoing=instance.outgoing,
        incoming=instance.incoming,
    )
    start_times = [0, 0, 0, 1, 3]
    latest = (0, 0, 1, 2, 3)

    conflict = select_branch_conflict(instance, start_times, latest)

    assert conflict is not None
    _, resource, activities, overload = conflict
    assert resource == 0
    assert activities == (1, 2, 3)
    assert overload == (1,)


def test_run_guided_seed_updates_incumbent_from_local_seed(monkeypatch) -> None:
    instance = _dummy_instance(30)
    stats = CpSearchStats()
    config = HeuristicConfig()

    seed_schedule = Schedule(start_times=(0,) * instance.n_activities, makespan=12)

    def fake_seed(**kwargs) -> SolveResult:
        return SolveResult(
            instance_name=instance.name,
            status="feasible",
            schedule=seed_schedule,
            runtime_seconds=0.01,
            temporal_lower_bound=0,
            restarts=3,
            metadata={"seed_construct_makespan": 12, "seed_best_source": "construct"},
        )

    monkeypatch.setattr("rcpsp.cp.search.solve_guided_seed", fake_seed)

    incumbent, restarts, metadata, guided_infeasible = run_guided_seed(
        instance=instance,
        seed=0,
        solver_config=config,
        heuristic_deadline=time.perf_counter() + 1.0,
        temporal_lower=[0] * instance.n_activities,
        forced_edges=(),
        tail=[0] * instance.n_activities,
        intensity=[0.0] * instance.n_activities,
        stats=stats,
        incumbent=None,
    )

    assert incumbent is not None
    assert incumbent.makespan == 12
    assert restarts == 3
    assert stats.incumbent_updates == 1
    assert metadata["guided_seed_used"] is True
    assert metadata["guided_seed_found_incumbent"] is True
    assert metadata["guided_seed_failed"] is False
    assert metadata["seed_construct_makespan"] == 12
    assert metadata["seed_best_source"] == "construct"
    assert guided_infeasible is False


def test_run_guided_seed_marks_infeasible_from_local_seed(monkeypatch) -> None:
    instance = _dummy_instance(30)
    stats = CpSearchStats()
    config = HeuristicConfig()

    def fake_seed(**kwargs) -> SolveResult:
        return SolveResult(
            instance_name=instance.name,
            status="infeasible",
            schedule=None,
            runtime_seconds=0.01,
            temporal_lower_bound=0,
            restarts=2,
            metadata={"reason": "seed proved infeasible"},
        )

    monkeypatch.setattr("rcpsp.cp.search.solve_guided_seed", fake_seed)

    incumbent, restarts, metadata, guided_infeasible = run_guided_seed(
        instance=instance,
        seed=0,
        solver_config=config,
        heuristic_deadline=time.perf_counter() + 1.0,
        temporal_lower=[0] * instance.n_activities,
        forced_edges=(),
        tail=[0] * instance.n_activities,
        intensity=[0.0] * instance.n_activities,
        stats=stats,
        incumbent=None,
    )

    assert incumbent is None
    assert restarts == 2
    assert metadata["guided_seed_used"] is True
    assert metadata["guided_seed_infeasible"] is True
    assert metadata["guided_seed_found_incumbent"] is False
    assert metadata["guided_seed_failed"] is False
    assert metadata["guided_seed_reason"] == "seed proved infeasible"
    assert guided_infeasible is True


def test_run_guided_seed_marks_unknown_seed_as_failed(monkeypatch) -> None:
    instance = _dummy_instance(30)
    stats = CpSearchStats()
    config = HeuristicConfig()

    def fake_seed(**kwargs) -> SolveResult:
        return SolveResult(
            instance_name=instance.name,
            status="unknown",
            schedule=None,
            runtime_seconds=0.01,
            temporal_lower_bound=0,
            restarts=2,
            metadata={"reason": "seed could not build an incumbent"},
        )

    monkeypatch.setattr("rcpsp.cp.search.solve_guided_seed", fake_seed)

    incumbent, restarts, metadata, guided_infeasible = run_guided_seed(
        instance=instance,
        seed=0,
        solver_config=config,
        heuristic_deadline=time.perf_counter() + 1.0,
        temporal_lower=[0] * instance.n_activities,
        forced_edges=(),
        tail=[0] * instance.n_activities,
        intensity=[0.0] * instance.n_activities,
        stats=stats,
        incumbent=None,
    )

    assert incumbent is None
    assert restarts == 2
    assert metadata["guided_seed_used"] is True
    assert metadata["guided_seed_infeasible"] is False
    assert metadata["guided_seed_found_incumbent"] is False
    assert metadata["guided_seed_failed"] is True
    assert metadata["guided_seed_reason"] == "seed could not build an incumbent"
    assert guided_infeasible is False


def test_solve_cp_accepts_guided_seed_infeasible_result(monkeypatch) -> None:
    instance = _dummy_instance(30)

    def fake_seed(**kwargs) -> SolveResult:
        return SolveResult(
            instance_name=instance.name,
            status="infeasible",
            schedule=None,
            runtime_seconds=0.01,
            temporal_lower_bound=0,
            restarts=1,
            metadata={"reason": "seed proved infeasible"},
        )

    monkeypatch.setattr("rcpsp.cp.search.solve_guided_seed", fake_seed)

    result = solve_cp(instance, time_limit=1.0, seed=0)

    assert result.status == "infeasible"
    assert result.metadata["guided_seed_used"] is True
    assert result.metadata["guided_seed_infeasible"] is True


def test_solve_cp_accepts_first_incumbent_probe_result(monkeypatch) -> None:
    instance = _dummy_instance(30)
    probe_schedule = Schedule(start_times=(0,) * instance.n_activities, makespan=7)
    probe_node = CpNode(
        lower=probe_schedule.start_times,
        latest=None,
        edges=(),
        pairs=frozenset(),
    )

    def fake_seed(**kwargs) -> SolveResult:
        return SolveResult(
            instance_name=instance.name,
            status="unknown",
            schedule=None,
            runtime_seconds=0.01,
            temporal_lower_bound=0,
            restarts=1,
            metadata={"reason": "seed could not build an incumbent"},
        )

    def fake_probe(**kwargs):
        return (
            probe_schedule,
            probe_node,
            False,
            {
                "first_incumbent_probe_used": True,
                "first_incumbent_probe_found_incumbent": True,
                "first_incumbent_probe_budget_seconds": 0.2,
                "first_incumbent_probe_expanded_nodes": 3,
                "first_incumbent_probe_frontier_peak": 2,
                "first_incumbent_probe_source": "node_local",
            },
        )

    monkeypatch.setattr("rcpsp.cp.search.solve_guided_seed", fake_seed)
    monkeypatch.setattr("rcpsp.cp.search.run_first_incumbent_probe", fake_probe)

    result = solve_cp(instance, time_limit=1.0, seed=0)

    assert result.status == "feasible"
    assert result.schedule is not None
    assert result.metadata["first_incumbent_probe_used"] is True
    assert result.metadata["first_incumbent_probe_found_incumbent"] is True
    assert result.metadata["first_incumbent_probe_source"] == "node_local"
    assert result.metadata["no_incumbent_before_dfs"] is False


def test_solve_cp_reports_conflict_counters_on_trivial_instance() -> None:
    result = solve_cp(_dummy_instance(2), time_limit=0.1, seed=0)

    assert result.status == "feasible"
    assert result.metadata["conflict_events"] == 0
    assert result.metadata["avg_conflict_size"] == 0.0
    assert result.metadata["max_conflict_size"] == 0
    assert result.metadata["heuristic_construct_failures"] == 0
    assert result.metadata["heuristic_construct_top_failure_reason"] == "none"
    assert result.metadata["node_local_attempts"] == 0
    assert result.metadata["node_local_improvements"] == 0
    assert result.metadata["node_local_construct_failures"] == 0
    assert result.metadata["node_local_construct_top_failure_reason"] == "none"
    assert result.metadata["deep_node_local_attempts"] == 0
    assert result.metadata["deep_node_local_improvements"] == 0
    assert result.metadata["propagation_pruned_nodes"] >= 0
    assert "no_incumbent_before_dfs" in result.metadata
    assert "first_incumbent_probe_used" in result.metadata
    assert "first_incumbent_probe_found_incumbent" in result.metadata


def test_guided_seed_reports_seed_phase_metadata() -> None:
    from rcpsp.cp.guided_seed import solve

    result = solve(_dummy_instance(2), time_limit=0.05, seed=0)

    assert "seed_construct_failures" in result.metadata
    assert "seed_construct_top_failure_reason" in result.metadata
    assert "seed_construct_makespan" in result.metadata
    assert "seed_improve_makespan" in result.metadata
    assert "seed_proof_makespan" in result.metadata
    assert "seed_polish_makespan" in result.metadata
    assert result.metadata["seed_best_source"] in {"none", "construct", "improve", "polish"}


def test_use_failure_cache_enables_large_short_runs() -> None:
    small = _dummy_instance(10)
    large = _dummy_instance(30)

    assert not use_failure_cache(small, 0.1)
    assert use_failure_cache(large, 0.1)
    assert use_failure_cache(small, 0.5)


def test_cp_budget_mode_separates_fast_medium_and_deep_runs() -> None:
    assert cp_budget_mode(0.1) == "fast"
    assert cp_budget_mode(1.0) == "medium"
    assert cp_budget_mode(30.0) == "deep"


def test_allow_node_local_heuristic_skips_medium_deep_nodes_with_incumbent() -> None:
    instance = _dummy_instance(20)
    incumbent = Schedule(start_times=(0,) * instance.n_activities, makespan=10)
    stats = CpSearchStats(nodes=16)

    assert not allow_node_local_heuristic(instance, 1.0, incumbent, stats)
    assert allow_node_local_heuristic(instance, 0.1, incumbent, stats)
    assert allow_node_local_heuristic(instance, 1.0, None, CpSearchStats(nodes=4))
    assert allow_node_local_heuristic(instance, 1.0, None, stats)
    assert not allow_node_local_heuristic(instance, 1.0, None, CpSearchStats(nodes=17))


def test_allow_node_local_heuristic_throttles_more_for_large_no_incumbent_nodes() -> None:
    instance = _dummy_instance(50)

    assert allow_node_local_heuristic(instance, 0.1, None, CpSearchStats(nodes=1))
    assert allow_node_local_heuristic(instance, 0.1, None, CpSearchStats(nodes=2))
    assert not allow_node_local_heuristic(instance, 0.1, None, CpSearchStats(nodes=4))
    assert allow_node_local_heuristic(instance, 0.1, None, CpSearchStats(nodes=8))
    assert allow_node_local_heuristic(instance, 1.0, None, CpSearchStats(nodes=32))
    assert not allow_node_local_heuristic(instance, 1.0, None, CpSearchStats(nodes=16))
    assert not allow_node_local_heuristic(instance, 30.0, None, CpSearchStats(nodes=4))
    assert not allow_node_local_heuristic(instance, 30.0, None, CpSearchStats(nodes=64))


def test_allow_node_local_heuristic_skips_very_large_fast_nodes_without_incumbent() -> None:
    instance = _dummy_instance(100)

    assert not allow_node_local_heuristic(instance, 0.1, None, CpSearchStats(nodes=1))


def test_try_cp_incumbent_returns_none_when_construct_fails(monkeypatch) -> None:
    instance = _dummy_instance(4)
    node = CpNode(lower=(0,) * instance.n_activities, latest=None, edges=(), pairs=frozenset())
    stats = CpSearchStats()

    monkeypatch.setattr("rcpsp.cp.search.construct_schedule", lambda *args, **kwargs: None)

    candidate = try_cp_incumbent(
        instance=instance,
        node=node,
        tail=[0] * instance.n_activities,
        intensity=[0.0] * instance.n_activities,
        solver_config=HeuristicConfig(),
        rng=random.Random(0),
        deadline=time.perf_counter() + 0.01,
        search_stats=stats,
    )

    assert candidate is None
    assert stats.node_local_construct_failures == 1


def test_try_cp_incumbent_records_construct_failure_reason(monkeypatch) -> None:
    instance = _dummy_instance(4)
    node = CpNode(lower=(0,) * instance.n_activities, latest=None, edges=(), pairs=frozenset())
    stats = CpSearchStats()

    def fake_construct(*args, **kwargs):
        diagnostics = kwargs.get("diagnostics")
        if isinstance(diagnostics, dict):
            diagnostics["failure_reason"] = "deadline"
        return None

    monkeypatch.setattr("rcpsp.cp.search.construct_schedule", fake_construct)

    candidate = try_cp_incumbent(
        instance=instance,
        node=node,
        tail=[0] * instance.n_activities,
        intensity=[0.0] * instance.n_activities,
        solver_config=HeuristicConfig(),
        rng=random.Random(0),
        deadline=time.perf_counter() + 0.01,
        search_stats=stats,
    )

    assert candidate is None
    assert stats.node_local_construct_failures == 1
    assert stats.node_local_construct_deadline_failures == 1


def test_allow_deep_node_local_heuristic_only_for_deep_promising_nodes() -> None:
    instance = _dummy_instance(120)
    node = CpNode(
        lower=tuple(0 if idx != instance.sink else 5 for idx in range(instance.n_activities)),
        latest=None,
        edges=(),
        pairs=frozenset(),
    )
    incumbent = Schedule(start_times=(0,) * instance.n_activities, makespan=12)
    stats = CpSearchStats(nodes=8)

    assert allow_deep_node_local_heuristic(instance, 30.0, node, incumbent, stats)
    assert not allow_deep_node_local_heuristic(instance, 1.0, node, incumbent, stats)
    assert not allow_deep_node_local_heuristic(instance, 30.0, node, None, stats)
    assert not allow_deep_node_local_heuristic(_dummy_instance(30), 30.0, node, incumbent, stats)


def test_node_local_heuristic_deadline_is_larger_in_deep_mode() -> None:
    now = 10.0
    soft_deadline = 20.0

    fast_deadline = node_local_heuristic_deadline(1.0, now=now, soft_deadline=soft_deadline, deep_mode=False)
    deep_deadline = node_local_heuristic_deadline(30.0, now=now, soft_deadline=soft_deadline, deep_mode=True)

    assert deep_deadline > fast_deadline
    assert deep_deadline <= soft_deadline


def test_child_order_key_prefers_tighter_large_instance_nodes() -> None:
    instance = _dummy_instance(30)
    looser = CpNode(
        lower=(0,) * instance.n_activities,
        latest=tuple(10 if idx not in (0, instance.sink) else 0 for idx in range(instance.n_activities)),
        edges=(),
        pairs=frozenset(),
    )
    tighter = CpNode(
        lower=(0,) * instance.n_activities,
        latest=tuple(4 if idx not in (0, instance.sink) else 0 for idx in range(instance.n_activities)),
        edges=(),
        pairs=frozenset(),
    )

    assert child_order_key(instance, tighter, 1) < child_order_key(instance, looser, 0)


def test_pair_direction_possible_uses_current_windows() -> None:
    instance = Instance(
        name="windows",
        path=Path("windows.sch"),
        n_jobs=2,
        n_resources=1,
        durations=(0, 4, 2, 0),
        demands=((0,), (0,), (0,), (0,)),
        capacities=(1,),
        edges=(),
        outgoing=((), (), (), ()),
        incoming=((), (), (), ()),
    )
    node = CpNode(
        lower=(0, 3, 0, 0),
        latest=(0, 10, 6, 0),
        edges=(),
        pairs=frozenset(),
    )

    assert not pair_direction_possible(instance, node, 1, 2)
    assert pair_direction_possible(instance, node, 2, 1)


def test_pair_direction_possible_respects_lag_closure() -> None:
    instance = Instance(
        name="lagdist",
        path=Path("lagdist.sch"),
        n_jobs=2,
        n_resources=1,
        durations=(0, 2, 1, 0),
        demands=((0,), (0,), (0,), (0,)),
        capacities=(1,),
        edges=(),
        outgoing=((), (), (), ()),
        incoming=((), (), (), ()),
    )
    neg_inf = float("-inf")
    lag_dist = [
        [0.0, 0.0, 0.0, 0.0],
        [neg_inf, 0.0, 5.0, 0.0],
        [neg_inf, neg_inf, 0.0, 0.0],
        [neg_inf, neg_inf, neg_inf, 0.0],
    ]
    node = CpNode(
        lower=(0, 1, 0, 0),
        latest=(0, 10, 5, 0),
        edges=(),
        pairs=frozenset(),
        lag_dist=lag_dist,
    )

    assert not pair_direction_possible(instance, node, 1, 2)


def test_select_branch_conflict_prefers_smaller_tighter_conflict() -> None:
    instance = Instance(
        name="conflict-choice",
        path=Path("conflict-choice.sch"),
        n_jobs=4,
        n_resources=1,
        durations=(0, 2, 2, 2, 2, 0),
        demands=((0,), (2,), (2,), (2,), (1,), (0,)),
        capacities=(3,),
        edges=(),
        outgoing=((), (), (), (), (), ()),
        incoming=((), (), (), (), (), ()),
    )
    start_times = [0, 0, 0, 0, 1, 0]
    latest = (0, 5, 1, 4, 5, 0)

    conflict = select_branch_conflict(instance, start_times, latest)

    assert conflict is not None
    time_index, resource, activities, overload = conflict
    assert time_index == 1
    assert resource == 0
    assert activities == (2, 3)
    assert overload == (4,)


def test_select_branch_conflict_uses_minimal_conflict_without_latest_on_large_instance() -> None:
    instance = _dummy_instance(50)
    durations = list(instance.durations)
    demands = [list(row) for row in instance.demands]
    durations[1] = 3
    durations[2] = 2
    durations[3] = 1
    demands[1][0] = 1
    demands[2][0] = 1
    demands[3][0] = 1
    instance = Instance(
        name="conflict-no-latest-large",
        path=Path("conflict-no-latest-large.sch"),
        n_jobs=50,
        n_resources=1,
        durations=tuple(durations),
        demands=tuple(tuple(row) for row in demands),
        capacities=(2,),
        edges=(),
        outgoing=instance.outgoing,
        incoming=instance.incoming,
    )
    start_times = [0] * instance.n_activities
    start_times[3] = 1
    start_times[instance.sink] = 3

    conflict = select_branch_conflict(instance, start_times, None)

    assert conflict is not None
    _, resource, activities, overload = conflict
    assert resource == 0
    assert activities == (1, 2, 3)
    assert overload == (1,)


def test_required_pair_gap_uses_lag_closure_when_tighter() -> None:
    instance = Instance(
        name="gap",
        path=Path("gap.sch"),
        n_jobs=2,
        n_resources=1,
        durations=(0, 2, 1, 0),
        demands=((0,), (0,), (0,), (0,)),
        capacities=(1,),
        edges=(),
        outgoing=((), (), (), ()),
        incoming=((), (), (), ()),
    )
    neg_inf = float("-inf")
    lag_dist = [
        [0.0, 0.0, 0.0, 0.0],
        [neg_inf, 0.0, 5.0, 0.0],
        [neg_inf, neg_inf, 0.0, 0.0],
        [neg_inf, neg_inf, neg_inf, 0.0],
    ]
    node = CpNode(
        lower=(0, 0, 0, 0),
        latest=(0, 10, 10, 0),
        edges=(),
        pairs=frozenset(),
        lag_dist=lag_dist,
    )

    assert required_pair_gap(instance, node, 1, 2) == 5
