from __future__ import annotations

from .propagation import (
    build_mandatory_profile,
    forced_pair_order_propagation,
    improving_latest_starts,
    minimal_overload_explanation,
    minimum_overlap_in_window,
    propagate_compulsory_parts,
    propagate_cp_node,
    tighten_latest_starts,
)
from .search import branch_children, solve_cp, try_cp_incumbent
from .state import CpNode, CpNodePropagation, CpSearchStats, OverloadExplanation

# Backward-compatible helper exports for experimentation and notes.
_tighten_latest_starts = tighten_latest_starts
_build_mandatory_profile = build_mandatory_profile
_minimal_overload_explanation = minimal_overload_explanation
_minimum_overlap_in_window = minimum_overlap_in_window
_propagate_compulsory_parts = propagate_compulsory_parts
_forced_pair_order_propagation = forced_pair_order_propagation
_improving_latest_starts = improving_latest_starts
_propagate_cp_node = propagate_cp_node
_try_cp_incumbent = try_cp_incumbent
_branch_children = branch_children
