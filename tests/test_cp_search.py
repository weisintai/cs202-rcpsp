from rcpsp.cp.search import failure_cache_hit, record_failed_pairs
from rcpsp.cp.state import CpSearchStats


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
