from rcpsp.cp.search import failure_cache_hit, node_signature, record_failed_pairs
from rcpsp.cp.state import CpNode, CpSearchStats


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
