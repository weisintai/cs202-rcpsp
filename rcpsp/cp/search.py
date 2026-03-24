from __future__ import annotations

import random
import time

from ..config import HeuristicConfig, sample_heuristic_config
from ..core.branching import branch_order
from ..core.compress import compress_valid_schedule_relaxed
from ..core.conflicts import minimal_conflict_set
from ..core.lag import (
    all_pairs_longest_lags,
    forced_resource_order_edges_from_dist,
    pairwise_infeasibility_reason_from_dist,
)
from ..core.metrics import resource_intensity
from ..models import Edge, Instance, Schedule, SolveResult
from ..temporal import TemporalInfeasibleError, longest_feasible_starts, longest_tail_to_sink
from ..validate import build_resource_profile, validate_schedule
from .construct import construct_schedule
from .guided_seed import solve as solve_guided_seed
from .propagation import propagate_cp_node
from .state import CpNode, CpSearchStats


def node_signature(
    node: CpNode,
) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, ...] | None]:
    return tuple(sorted(node.pairs)), node.lower, node.latest


def failure_cache_hit(
    pairs: frozenset[tuple[int, int]],
    failed_pair_sets: set[frozenset[tuple[int, int]]],
) -> bool:
    return any(failed.issubset(pairs) for failed in failed_pair_sets)


_FAILURE_CACHE_MAX = 400


def record_failed_pairs(
    pairs: frozenset[tuple[int, int]],
    failed_pair_sets: set[frozenset[tuple[int, int]]],
    stats: CpSearchStats,
) -> None:
    if not pairs:
        return
    redundant = []
    for failed in failed_pair_sets:
        if failed.issubset(pairs):
            return  # Already covered by a more general failure
        if pairs.issubset(failed):
            redundant.append(failed)  # pairs is more general; drop this superset
    for failed in redundant:
        failed_pair_sets.remove(failed)
    # Evict the most specific (largest) entry when cache is full, so the most
    # general (smallest) failure reasons are preserved for maximum pruning power.
    if len(failed_pair_sets) >= _FAILURE_CACHE_MAX:
        to_evict = max(failed_pair_sets, key=len)
        failed_pair_sets.discard(to_evict)
    failed_pair_sets.add(pairs)
    stats.failure_cache_inserts += 1
    stats.failure_cache_size = len(failed_pair_sets)


def try_cp_incumbent(
    instance: Instance,
    node: CpNode,
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
    search_stats: CpSearchStats | None = None,
) -> Schedule | None:
    schedule = construct_schedule(
        instance=instance,
        rng=rng,
        tail=tail,
        intensity=intensity,
        config=sample_heuristic_config(solver_config, rng),
        deadline=deadline,
        base_extra_edges=node.edges,
        initial_starts=list(node.lower),
    )
    if schedule is None:
        if search_stats is not None:
            search_stats.node_local_construct_failures += 1
        return None
    return schedule


def update_incumbent(
    incumbent: Schedule | None,
    candidate: Schedule | None,
    stats: CpSearchStats,
) -> Schedule | None:
    if candidate is None:
        return incumbent
    if incumbent is None or candidate.makespan < incumbent.makespan:
        stats.incumbent_updates += 1
        return candidate
    return incumbent


def use_failure_cache(
    instance: Instance,
    time_limit: float,
) -> bool:
    return time_limit >= 0.5 or (instance.n_jobs >= 20 and time_limit >= 0.1)


def cp_budget_mode(time_limit: float) -> str:
    if time_limit >= 5.0:
        return "deep"
    if time_limit >= 1.0:
        return "medium"
    return "fast"


def allow_node_local_heuristic(
    instance: Instance,
    time_limit: float,
    incumbent: Schedule | None,
    stats: CpSearchStats | None = None,
) -> bool:
    if incumbent is None:
        budget_mode = cp_budget_mode(time_limit)
        if instance.n_jobs < 20:
            return True
        if stats is None:
            return False
        large_instance = instance.n_jobs >= 50
        very_large_instance = instance.n_jobs >= 100
        if budget_mode == "fast":
            if very_large_instance:
                return False
            if not large_instance:
                return True
            if stats.nodes <= 2:
                return True
            return stats.nodes % 8 == 0
        if large_instance and budget_mode == "deep":
            return False
        if stats.nodes <= 4:
            return True
        if budget_mode == "medium":
            return stats.nodes % (32 if large_instance else 16) == 0
        return stats.nodes % (64 if large_instance else 32) == 0
    if instance.n_jobs < 20 or time_limit < 1.0:
        return True
    return False


def allow_deep_node_local_heuristic(
    instance: Instance,
    time_limit: float,
    node: CpNode,
    incumbent: Schedule | None,
    stats: CpSearchStats,
) -> bool:
    if cp_budget_mode(time_limit) != "deep":
        return False
    if incumbent is None or instance.n_jobs < 100:
        return False
    sink_gap = incumbent.makespan - node.lower[instance.sink]
    if sink_gap <= 1:
        return False
    if stats.nodes <= 32:
        return True
    if sink_gap >= max(3, instance.n_jobs // 12):
        return True
    return stats.nodes % 32 == 0


def _search_metadata(
    *,
    seed: int,
    time_limit: float,
    forced_resource_orders: int,
    budget_mode: str,
    stats: CpSearchStats,
    guided_seed_meta: dict[str, object],
    no_incumbent_before_dfs: bool,
) -> dict[str, object]:
    return {
        "backend": "cp",
        "seed": seed,
        "time_limit": time_limit,
        "search_nodes": stats.nodes,
        "timed_out": stats.timed_out,
        "propagation_calls": stats.propagation_calls,
        "propagation_rounds": stats.propagation_rounds,
        "propagation_pruned_nodes": stats.propagation_pruned_nodes,
        "incumbent_updates": stats.incumbent_updates,
        "heuristic_construct_failures": stats.heuristic_construct_failures,
        "node_local_attempts": stats.node_local_attempts,
        "node_local_improvements": stats.node_local_improvements,
        "node_local_construct_failures": stats.node_local_construct_failures,
        "construct_failures": stats.heuristic_construct_failures + stats.node_local_construct_failures,
        "deep_node_local_attempts": stats.deep_node_local_attempts,
        "deep_node_local_improvements": stats.deep_node_local_improvements,
        "branches": stats.branches,
        "timetable_failures": stats.timetable_failures,
        "max_timetable_explanation": stats.max_timetable_explanation,
        "failure_cache_hits": stats.failure_cache_hits,
        "failure_cache_inserts": stats.failure_cache_inserts,
        "failure_cache_size": stats.failure_cache_size,
        "conflict_events": stats.conflict_events,
        "avg_conflict_size": (
            stats.total_conflict_size / stats.conflict_events if stats.conflict_events else 0.0
        ),
        "max_conflict_size": stats.max_conflict_size,
        "forced_resource_orders": forced_resource_orders,
        "budget_mode": budget_mode,
        "no_incumbent_before_dfs": no_incumbent_before_dfs,
        **guided_seed_meta,
    }


def node_local_heuristic_deadline(
    time_limit: float,
    *,
    now: float,
    soft_deadline: float,
    deep_mode: bool,
) -> float:
    if deep_mode:
        return min(soft_deadline, now + min(0.1, max(0.01, time_limit * 0.005)))
    return min(soft_deadline, now + min(0.02, max(0.002, time_limit * 0.01)))


def child_order_key(
    instance: Instance,
    node: CpNode,
    order_index: int,
) -> tuple[int, int, int, int]:
    if instance.n_jobs < 30 or node.latest is None:
        return (node.lower[instance.sink], order_index, 0, 0)

    sink_slack = max(0, node.latest[instance.sink] - node.lower[instance.sink])
    sampled_window = 0
    for activity in range(1, min(instance.sink, 7)):
        sampled_window += max(0, node.latest[activity] - node.lower[activity])

    return (
        node.lower[instance.sink],
        sink_slack,
        sampled_window,
        order_index,
    )


def select_branch_conflict(
    instance: Instance,
    start_times: list[int],
    latest: tuple[int, ...] | None,
) -> tuple[int, int, list[int], list[int]] | None:
    profile = build_resource_profile(instance, start_times)
    best: tuple[tuple[int, int, int, int, int], tuple[int, int, list[int], list[int]]] | None = None

    for time_index, usage in enumerate(profile):
        overloaded = [resource for resource in range(instance.n_resources) if usage[resource] > instance.capacities[resource]]
        if not overloaded:
            continue

        # Compute all active activities at this time once, then filter per resource.
        all_active_here = [
            activity
            for activity in range(1, instance.sink)
            if start_times[activity] <= time_index < start_times[activity] + instance.durations[activity]
        ]

        overload = [
            max(0, usage[resource_idx] - instance.capacities[resource_idx])
            for resource_idx in range(instance.n_resources)
        ]

        for resource in overloaded:
            active = [a for a in all_active_here if instance.demands[a][resource] > 0]
            # Sort once by removal priority, then strip from front greedily.
            active.sort(key=lambda a: (instance.demands[a][resource], instance.durations[a], a))
            total = sum(instance.demands[a][resource] for a in active)
            i = 0
            while i < len(active):
                if total - instance.demands[active[i]][resource] > instance.capacities[resource]:
                    total -= instance.demands[active[i]][resource]
                    i += 1
                else:
                    break
            conflict = sorted(active[i:], key=lambda a: (start_times[a], a))
            if len(conflict) <= 1:
                continue

            total_slack = 0
            if latest is not None:
                total_slack = sum(max(0, latest[activity] - start_times[activity]) for activity in conflict)

            key = (
                len(conflict),
                total_slack,
                -overload[resource],
                time_index,
                -sum(instance.demands[activity][resource] for activity in conflict),
            )
            candidate = (time_index, resource, conflict, overload)
            if best is None or key < best[0]:
                best = (key, candidate)

    if best is None:
        return None
    return best[1]


def required_pair_gap(
    instance: Instance,
    node: CpNode,
    before: int,
    after: int,
) -> int:
    required_gap = instance.durations[before]
    if node.lag_dist is not None:
        lag = node.lag_dist[before][after]
        if lag != float("-inf"):
            required_gap = max(required_gap, int(lag))
    return required_gap


def pair_direction_possible(
    instance: Instance,
    node: CpNode,
    before: int,
    after: int,
) -> bool:
    if node.latest is None:
        return True
    return node.lower[before] + required_pair_gap(instance, node, before, after) <= node.latest[after]


def run_guided_seed(
    *,
    instance: Instance,
    seed: int,
    solver_config: HeuristicConfig,
    heuristic_deadline: float,
    stats: CpSearchStats,
    incumbent: Schedule | None,
) -> tuple[Schedule | None, int, dict[str, object], bool]:
    restarts = 0
    metadata: dict[str, object] = {
        "guided_seed_used": False,
        "guided_seed_infeasible": False,
        "guided_seed_found_incumbent": False,
        "guided_seed_failed": False,
    }

    remaining = heuristic_deadline - time.perf_counter()
    if remaining <= 0:
        return incumbent, restarts, metadata, False

    if remaining > 0 and time.perf_counter() < heuristic_deadline:
        guided = solve_guided_seed(
            instance=instance,
            time_limit=remaining,
            seed=seed,
            config=solver_config,
        )
        metadata["guided_seed_used"] = True
        for key, value in guided.metadata.items():
            if key.startswith("seed_"):
                metadata[key] = value
        if guided.status == "feasible" and guided.schedule is not None:
            metadata["guided_seed_found_incumbent"] = True
            incumbent = update_incumbent(incumbent, guided.schedule, stats)
        elif guided.status == "infeasible":
            metadata["guided_seed_infeasible"] = True
            reason = guided.metadata.get("reason")
            if isinstance(reason, str) and reason:
                metadata["guided_seed_reason"] = reason
        else:
            reason = guided.metadata.get("reason")
            if isinstance(reason, str) and reason:
                metadata["guided_seed_reason"] = reason
        restarts += guided.restarts

    metadata["guided_seed_failed"] = bool(
        metadata["guided_seed_used"]
        and not metadata["guided_seed_infeasible"]
        and not metadata["guided_seed_found_incumbent"]
    )

    return incumbent, restarts, metadata, bool(metadata["guided_seed_infeasible"])


def branch_children(
    instance: Instance,
    node: CpNode,
    tail: list[int],
    intensity: list[float],
    conflict_set: list[int] | tuple[int, ...],
    resource: int,
    overload: list[int],
    incumbent_makespan: int | None,
    seen: set[tuple[tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, ...] | None]],
    failed_pair_sets: set[frozenset[tuple[int, int]]],
    failure_cache_enabled: bool,
    stats: CpSearchStats,
    resource_conflict_pairs: frozenset[tuple[int, int]] | None = None,
) -> list[tuple[int, int, frozenset[tuple[int, int]], CpNode]]:
    ordered = branch_order(
        instance=instance,
        start_times=list(node.lower),
        tail=tail,
        intensity=intensity,
        conflict=list(conflict_set),
        overload=overload,
    )
    children: list[tuple[int, int, frozenset[tuple[int, int]], CpNode]] = []
    for order_index, selected in enumerate(ordered):
        for other in conflict_set:
            if other == selected or instance.demands[other][resource] == 0:
                continue
            pair = (other, selected)
            if pair in node.pairs:
                continue
            if not pair_direction_possible(instance, node, other, selected):
                continue

            child_pairs = frozenset((*node.pairs, pair))
            if failure_cache_enabled and failure_cache_hit(child_pairs, failed_pair_sets):
                stats.failure_cache_hits += 1
                continue
            child = propagate_cp_node(
                instance=instance,
                tail=tail,
                pairs=child_pairs,
                incumbent_makespan=incumbent_makespan,
                base_lag_dist=node.lag_dist,
                new_edges=(Edge(source=other, target=selected, lag=instance.durations[other]),),
                resource_conflict_pairs=resource_conflict_pairs,
            )
            stats.propagation_calls += 1
            stats.propagation_rounds += child.rounds
            if child.overload is not None:
                stats.propagation_pruned_nodes += 1
                stats.timetable_failures += 1
                stats.max_timetable_explanation = max(
                    stats.max_timetable_explanation,
                    child.overload.size,
                )
                if failure_cache_enabled:
                    record_failed_pairs(child_pairs, failed_pair_sets, stats)
                continue
            if child.node is None:
                stats.propagation_pruned_nodes += 1
                if failure_cache_enabled:
                    record_failed_pairs(child_pairs, failed_pair_sets, stats)
                continue
            if failure_cache_enabled and failure_cache_hit(child.node.pairs, failed_pair_sets):
                stats.failure_cache_hits += 1
                continue
            child_key = node_signature(child.node)
            if child_key in seen:
                continue
            children.append((child.node.lower[instance.sink], order_index, child.node.pairs, child.node))
    children.sort(key=lambda item: child_order_key(instance, item[3], item[1]))
    return children


def solve_cp(
    instance: Instance,
    time_limit: float = 30.0,
    seed: int = 0,
    config: HeuristicConfig | None = None,
) -> SolveResult:
    solver_config = config or HeuristicConfig()
    rng = random.Random(seed)
    started = time.perf_counter()
    final_deadline = started + time_limit
    safety_margin = min(max(0.005, time_limit * 0.005), max(0.005, time_limit * 0.05))
    soft_deadline = max(started, final_deadline - safety_margin)

    try:
        root_lag_dist = all_pairs_longest_lags(instance)
        pairwise_reason = pairwise_infeasibility_reason_from_dist(instance, root_lag_dist)
        if pairwise_reason is not None:
            runtime = time.perf_counter() - started
            temporal_lower = longest_feasible_starts(instance)
            return SolveResult(
                instance_name=instance.name,
                status="infeasible",
                schedule=None,
                runtime_seconds=runtime,
                temporal_lower_bound=temporal_lower[instance.sink],
                restarts=0,
                metadata={"backend": "cp", "reason": pairwise_reason, "seed": seed, "time_limit": time_limit},
            )
        forced_edges, root_lag_dist = forced_resource_order_edges_from_dist(instance, root_lag_dist)
        temporal_lower = longest_feasible_starts(instance, extra_edges=forced_edges)
        tail = longest_tail_to_sink(instance)
    except TemporalInfeasibleError as exc:
        runtime = time.perf_counter() - started
        return SolveResult(
            instance_name=instance.name,
            status="infeasible",
            schedule=None,
            runtime_seconds=runtime,
            temporal_lower_bound=-1,
            restarts=0,
            metadata={"backend": "cp", "reason": str(exc), "seed": seed, "time_limit": time_limit},
        )

    intensity = resource_intensity(instance)
    stats = CpSearchStats()
    seen: set[tuple[tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, ...] | None]] = set()
    failed_pair_sets: set[frozenset[tuple[int, int]]] = set()
    failure_cache_enabled = use_failure_cache(instance, time_limit)
    budget_mode = cp_budget_mode(time_limit)
    incumbent: Schedule | None = None
    restarts = 0
    forced_pairs = frozenset((edge.source, edge.target) for edge in forced_edges)

    # Precompute pairs that share at least one resource beyond capacity.
    # Used to skip non-conflicting pairs in forced_pair_order_propagation.
    resource_conflict_pairs: frozenset[tuple[int, int]] | None = None
    if instance.n_jobs >= 20:
        resource_conflict_pairs = frozenset(
            (first, second)
            for first in range(1, instance.sink)
            for second in range(first + 1, instance.sink)
            if any(
                instance.demands[first][r] + instance.demands[second][r] > instance.capacities[r]
                for r in range(instance.n_resources)
            )
        )
    guided_seed_meta: dict[str, object] = {
        "guided_seed_used": False,
        "guided_seed_infeasible": False,
        "guided_seed_found_incumbent": False,
        "guided_seed_failed": False,
    }

    heuristic_budget = min(0.75, max(0.01, time_limit * 0.25))
    heuristic_deadline = min(soft_deadline, started + heuristic_budget)
    if heuristic_budget >= 0.15 and time.perf_counter() < heuristic_deadline:
        incumbent, guided_restarts, guided_seed_meta, guided_infeasible = run_guided_seed(
            instance=instance,
            seed=seed,
            solver_config=solver_config,
            heuristic_deadline=heuristic_deadline,
            stats=stats,
            incumbent=incumbent,
        )
        restarts += guided_restarts
        if guided_infeasible:
            runtime = time.perf_counter() - started
            return SolveResult(
                instance_name=instance.name,
                status="infeasible",
                schedule=None,
                runtime_seconds=runtime,
                temporal_lower_bound=temporal_lower[instance.sink],
                restarts=restarts,
                metadata=_search_metadata(
                    seed=seed,
                    time_limit=time_limit,
                    forced_resource_orders=len(forced_edges),
                    budget_mode=budget_mode,
                    stats=stats,
                    guided_seed_meta=guided_seed_meta,
                    no_incumbent_before_dfs=True,
                ),
            )
        if incumbent is not None and incumbent.makespan == temporal_lower[instance.sink]:
            runtime = time.perf_counter() - started
            return SolveResult(
                instance_name=instance.name,
                status="feasible",
                schedule=incumbent,
                runtime_seconds=runtime,
                temporal_lower_bound=temporal_lower[instance.sink],
                restarts=restarts,
                metadata=_search_metadata(
                    seed=seed,
                    time_limit=time_limit,
                    forced_resource_orders=len(forced_edges),
                    budget_mode=budget_mode,
                    stats=stats,
                    guided_seed_meta=guided_seed_meta,
                    no_incumbent_before_dfs=False,
                ),
            )

    while time.perf_counter() < heuristic_deadline:
        schedule = construct_schedule(
            instance=instance,
            rng=rng,
            tail=tail,
            intensity=intensity,
            config=sample_heuristic_config(solver_config, rng),
            deadline=heuristic_deadline,
            base_extra_edges=forced_edges,
            initial_starts=temporal_lower,
        )
        if schedule is None:
            stats.heuristic_construct_failures += 1
            restarts += 1
            continue
        incumbent = update_incumbent(incumbent, schedule, stats)
        restarts += 1
        if incumbent is not None and incumbent.makespan == temporal_lower[instance.sink]:
            break

    def dfs(pairs: frozenset[tuple[int, int]], node: CpNode | None = None) -> bool:
        nonlocal incumbent
        if time.perf_counter() >= soft_deadline:
            stats.timed_out = True
            return False
        stats.nodes += 1

        if failure_cache_enabled and failure_cache_hit(pairs, failed_pair_sets):
            stats.failure_cache_hits += 1
            return False

        if node is None:
            propagation = propagate_cp_node(
                instance=instance,
                tail=tail,
                pairs=pairs,
                incumbent_makespan=incumbent.makespan if incumbent is not None else None,
                base_lag_dist=root_lag_dist if pairs == forced_pairs else None,
                resource_conflict_pairs=resource_conflict_pairs,
            )
            stats.propagation_calls += 1
            stats.propagation_rounds += propagation.rounds
            if propagation.overload is not None:
                stats.propagation_pruned_nodes += 1
                stats.timetable_failures += 1
                stats.max_timetable_explanation = max(
                    stats.max_timetable_explanation,
                    propagation.overload.size,
                )
                if failure_cache_enabled:
                    record_failed_pairs(pairs, failed_pair_sets, stats)
                return False
            node = propagation.node
            if node is None:
                stats.propagation_pruned_nodes += 1
                if failure_cache_enabled:
                    record_failed_pairs(pairs, failed_pair_sets, stats)
                return False
            if failure_cache_enabled and failure_cache_hit(node.pairs, failed_pair_sets):
                stats.failure_cache_hits += 1
                return False

        key = node_signature(node)
        if key in seen:
            return True
        seen.add(key)

        lower = list(node.lower)
        lower_schedule = Schedule(start_times=tuple(lower), makespan=lower[instance.sink])
        if not validate_schedule(instance, lower_schedule):
            candidate_starts = compress_valid_schedule_relaxed(instance, lower)
            candidate = Schedule(start_times=tuple(candidate_starts), makespan=candidate_starts[instance.sink])
            if not validate_schedule(instance, candidate):
                if incumbent is None or candidate.makespan < incumbent.makespan:
                    incumbent = candidate
                    stats.incumbent_updates += 1
                return True
            if failure_cache_enabled:
                record_failed_pairs(node.pairs, failed_pair_sets, stats)
            return False

        found_feasible = False
        use_local_heuristic = allow_node_local_heuristic(
            instance,
            time_limit,
            incumbent,
            stats,
        )
        deep_local_heuristic = False
        if not use_local_heuristic:
            deep_local_heuristic = allow_deep_node_local_heuristic(
                instance=instance,
                time_limit=time_limit,
                node=node,
                incumbent=incumbent,
                stats=stats,
            )
            use_local_heuristic = deep_local_heuristic

        if use_local_heuristic and time.perf_counter() < soft_deadline:
            stats.node_local_attempts += 1
            if deep_local_heuristic:
                stats.deep_node_local_attempts += 1
            local_budget = node_local_heuristic_deadline(
                time_limit,
                now=time.perf_counter(),
                soft_deadline=soft_deadline,
                deep_mode=deep_local_heuristic,
            )
            candidate = try_cp_incumbent(
                instance=instance,
                node=node,
                tail=tail,
                intensity=intensity,
                solver_config=solver_config,
                rng=rng,
                deadline=local_budget,
                search_stats=stats,
            )
            if candidate is not None:
                found_feasible = True
                if incumbent is None or candidate.makespan < incumbent.makespan:
                    incumbent = candidate
                    stats.incumbent_updates += 1
                    stats.node_local_improvements += 1
                    if deep_local_heuristic:
                        stats.deep_node_local_improvements += 1
                    if incumbent.makespan == temporal_lower[instance.sink]:
                        return True

        conflict = select_branch_conflict(instance, lower, node.latest)
        if conflict is None:
            conflict = minimal_conflict_set(instance, lower)
        if conflict is None:
            candidate_starts = compress_valid_schedule_relaxed(instance, lower)
            candidate = Schedule(start_times=tuple(candidate_starts), makespan=candidate_starts[instance.sink])
            if not validate_schedule(instance, candidate):
                found_feasible = True
                if incumbent is None or candidate.makespan < incumbent.makespan:
                    incumbent = candidate
                    stats.incumbent_updates += 1
                return True
            if failure_cache_enabled:
                record_failed_pairs(node.pairs, failed_pair_sets, stats)
            return False

        _, resource, conflict_set, overload = conflict
        if len(conflict_set) <= 1:
            if not found_feasible:
                if failure_cache_enabled:
                    record_failed_pairs(node.pairs, failed_pair_sets, stats)
            return found_feasible

        stats.conflict_events += 1
        stats.total_conflict_size += len(conflict_set)
        stats.max_conflict_size = max(stats.max_conflict_size, len(conflict_set))

        children = branch_children(
            instance=instance,
            node=node,
            tail=tail,
            intensity=intensity,
            conflict_set=conflict_set,
            resource=resource,
            overload=overload,
            incumbent_makespan=incumbent.makespan if incumbent is not None else None,
            seen=seen,
            failed_pair_sets=failed_pair_sets,
            failure_cache_enabled=failure_cache_enabled,
            stats=stats,
            resource_conflict_pairs=resource_conflict_pairs,
        )

        for _, _, child_pairs, child in children:
            stats.branches += 1
            child_found_feasible = dfs(child_pairs, child)
            found_feasible = found_feasible or child_found_feasible
            if stats.timed_out:
                return False
            if incumbent is not None and incumbent.makespan == temporal_lower[instance.sink]:
                return True

        if not found_feasible:
            if failure_cache_enabled:
                record_failed_pairs(node.pairs, failed_pair_sets, stats)
        return found_feasible

    no_incumbent_before_dfs = incumbent is None
    dfs(forced_pairs)

    runtime = time.perf_counter() - started
    if incumbent is None:
        return SolveResult(
            instance_name=instance.name,
            status="unknown" if stats.timed_out else "infeasible",
            schedule=None,
            runtime_seconds=runtime,
            temporal_lower_bound=temporal_lower[instance.sink],
            restarts=restarts,
            metadata=_search_metadata(
                seed=seed,
                time_limit=time_limit,
                forced_resource_orders=len(forced_edges),
                budget_mode=budget_mode,
                stats=stats,
                guided_seed_meta=guided_seed_meta,
                no_incumbent_before_dfs=no_incumbent_before_dfs,
            ),
        )

    return SolveResult(
        instance_name=instance.name,
        status="feasible",
        schedule=incumbent,
        runtime_seconds=runtime,
        temporal_lower_bound=temporal_lower[instance.sink],
        restarts=restarts,
        metadata=_search_metadata(
            seed=seed,
            time_limit=time_limit,
            forced_resource_orders=len(forced_edges),
            budget_mode=budget_mode,
            stats=stats,
            guided_seed_meta=guided_seed_meta,
            no_incumbent_before_dfs=no_incumbent_before_dfs,
        ),
    )
