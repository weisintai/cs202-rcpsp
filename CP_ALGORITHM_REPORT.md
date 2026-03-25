# CP Backend — Algorithm Deep Dive

This report walks through every section of the CP backend (`rcpsp/cp/`) in plain language. The goal is to give a clear mental model of what each piece does and why it exists.

---

## 1. The Problem Being Solved

The solver tackles **RCPSP/max**: a project scheduling problem where:

- There are **activities** (jobs), each with a fixed duration and resource demands.
- Activities are connected by **lag constraints** — "activity B cannot start until at least `lag` time units after activity A starts" — covering both minimum and maximum gaps.
- There are **shared resources** with limited capacity. At any point in time, the total demand of running activities cannot exceed a resource's capacity.
- The goal is to find a **start time** for each activity that satisfies all constraints while **minimising the project makespan** (the finish time of the last activity).

The CP backend has a strict **30-second wall-clock budget** and must never claim a feasible instance is infeasible.

---

## 2. Big Picture: How a Solve Runs

The solver does **not** enumerate complete schedules directly. Instead, it searches over **pairwise resource-ordering decisions**: "should activity A finish before activity B starts?" Each decision is represented as an extra precedence edge. The solver incrementally adds edges, propagates their consequences, and prunes search branches that cannot beat the best schedule found so far.

```
Instance
  │
  ▼
Temporal preprocessing (lag closure, forced orders)
  │
  ▼
Guided Seed Phase — try to get a good schedule quickly
  │
  ▼
DFS over pair-order decisions
  │  ├─ Propagate constraints (tighten time windows)
  │  ├─ Prune if infeasible or worse than incumbent
  │  ├─ At a leaf with no conflicts: compress and record schedule
  │  └─ Otherwise: find a resource conflict → branch → recurse
  │
  ▼
Return best schedule found
```

---

## 3. File-by-File Walkthrough

### 3.1 `state.py` — Data Structures

**What it contains:** The dataclasses (structs) that carry information through the search.

**Key types:**

| Type | Role |
|---|---|
| `CpNode` | A single node in the search tree. Holds the current time windows (`lower`, `latest`), all ordering edges committed so far (`edges`, `pairs`), the full lag-distance matrix (`lag_dist`), and the next conflict to branch on (`branch_conflict`). |
| `CpNodePropagation` | The result returned after propagating a node. Either contains a valid `CpNode`, or `None` if the node was proved infeasible, along with an optional `OverloadExplanation`. |
| `OverloadExplanation` | Explains *why* a resource overload happened: which resource, which time window, which activities are involved, and by how much the capacity was exceeded. Used for pruning and caching. |
| `CpSearchStats` | A bag of counters (nodes visited, propagation calls, incumbents found, cache hits, etc.) used for logging and diagnostics. |

**Key concept — time windows:**
Each activity has an **earliest start** (`lower[i]`) and a **latest start** (`latest[i]`). As the solver commits to more ordering decisions, these windows shrink. If `lower[i] > latest[i]` for any activity, the node is infeasible.

---

### 3.2 `propagation.py` — Constraint Propagation Kernel

**What it does:** Given a set of committed ordering edges (pairs), compute the tightest possible time windows for each activity, and detect infeasibility early.

This is the heart of the CP approach. It runs in a loop until no more tightening is possible ("propagation to fixpoint").

#### Step 1 — Compute the All-Pairs Lag Closure (`all_pairs_longest_lags`)

Before any search begins, the solver computes the **longest-path distance** between every pair of activities in the lag graph. This is like running Floyd-Warshall on the temporal constraint network. The result is a matrix `lag_dist[i][j]` = "the minimum time that must pass between the start of activity `i` and the start of activity `j`".

If `lag_dist[i][i] > 0` for any activity (a positive cycle), the instance is temporally infeasible.

#### Step 2 — Tighten Earliest Starts (`tighten_earliest_starts`)

Given the lag distances and a set of release times (lower bounds), compute a tight earliest start for every activity by propagating forward through the constraint graph. For each pair `(source, target)`, if `lower[source] + lag >= lower[target]`, then `lower[target]` must be raised.

This is equivalent to a forward pass of the longest-path algorithm.

#### Step 3 — Tighten Latest Starts (`tighten_latest_starts`)

Using the incumbent makespan as an upper bound: if we know the best schedule so far finishes in `T` time units, then activity `i` must start no later than `T - 1 - tail[i]`, where `tail[i]` is the longest path from the *end* of activity `i` to the sink.

The backward pass propagates this: if activity A must precede B (with lag `d`), and B must start by time `LST_B`, then A must start by `LST_B - d`.

#### Step 4 — Build the Mandatory (Compulsory) Resource Profile (`build_mandatory_profile`)

Some activities have a **compulsory part** — a time interval during which they *must* be running regardless of exactly when they start. An activity with earliest start `EST` and latest start `LST` has a compulsory part `[LST, EST + duration)` if `LST < EST + duration`.

The solver builds a resource profile by summing up all compulsory parts for each resource over time. If at any time slot the compulsory load exceeds the resource capacity, the node is infeasible.

```
  Compulsory part of activity A: ████
  Compulsory part of activity B:        ████
  Compulsory part of activity C:    ████████

  If the overlap exceeds capacity → infeasible
```

#### Step 5 — Propagate Compulsory Parts / Timetable Pruning (`propagate_compulsory_parts`)

Using the mandatory profile, the solver tightens time windows further:

- **EST tightening:** If placing an activity at its current earliest start would push a resource over capacity (because other activities must also be running then), the activity's EST is pushed forward past that overloaded interval.
- **LST tightening:** The same check in reverse — if starting too late would create an overload, the LST is pulled back.

If an activity's EST is pushed past its LST, the node is infeasible.

#### Step 6 — Forced Pair-Order Propagation (`forced_pair_order_propagation`)

For pairs of activities that share a resource and whose combined demand exceeds the capacity, the solver checks whether only *one* ordering is still feasible given the current time windows. If `A` cannot possibly finish before `B` starts in any remaining order, but `B` finishing before `A` starts is also impossible, then the node is infeasible (detected as an `OverloadExplanation`). If exactly one order remains possible, that ordering is added as a new constraint and propagation continues.

This step is skipped on small instances (fewer than 20 jobs) where it would be more expensive than helpful.

#### The Propagation Loop

Steps 2–6 run in a loop. Any time new edges are inferred or time windows change, the loop repeats. It exits when nothing changes (fixpoint reached) or infeasibility is detected.

The final result is either:
- A `CpNode` with tightened windows and a `branch_conflict` identifying the next resource overload to branch on, or
- `None` (the node is proved infeasible).

---

### 3.3 `search.py` — DFS Orchestration

**What it does:** Implements the full Depth-First Search over pair-order decisions, manages the incumbent (best schedule found so far), and decides when to branch.

#### Initialisation (inside `solve_cp`)

1. **Temporal preprocessing:** Compute the all-pairs lag closure. Check for pairwise infeasibility (e.g., activity A must start after itself — cycle detected). Extract any **forced resource orders**: pairs of activities where one *must* come before the other on every feasible schedule, because their combined demand always exceeds capacity regardless of timing. Add these as free constraints.

2. **Compute tail values:** For each activity, `tail[i]` = the longest path from the *end of activity i* to the project sink. This is used as a lower bound: any schedule must take at least `start[i] + duration[i] + tail[i]` time.

3. **Resource intensity:** Precompute a per-activity measure of how heavily it uses resources relative to capacity. Used to guide branching.

4. **Budget allocation:** Depending on the time limit, select a "budget mode" (`fast` / `medium` / `deep`) that controls how aggressively the search spends time on local heuristics versus pure tree search.

#### Guided Seed Phase

Before starting DFS, the solver runs `guided_seed` (see §3.5) to try to find a good first schedule quickly. If a schedule at the temporal lower bound (optimal) is found immediately, the solver returns without DFS.

#### Short Constructive Warm Start

If guided seed did not find an incumbent, the solver runs `construct_schedule` in a tight loop until the heuristic budget is exhausted, keeping the best schedule found. This gives DFS a useful upper bound to prune with.

#### The DFS (`dfs` inner function)

```
dfs(pairs, node):
  1. Check time limit → stop if exceeded
  2. Check failure cache → skip if this pair-set is known to fail
  3. Propagate constraints for this node (if not already done)
     → prune if infeasible
  4. If no resource conflict remains:
     → the schedule is feasible, compress it, update incumbent
  5. Optionally try a local heuristic construction from this node
  6. Identify the branch conflict (resource overload to resolve)
  7. For each candidate ordering of the conflicting activities:
     → build child node with the new pair committed
     → propagate the child
     → sort children by lower bound
     → recurse into each child
```

#### Branch Selection (`branch_children`)

When the solver must branch on a resource conflict, it picks the "best activity to sequence first" using `branch_order` (see §3.7). For each activity in the conflict set, it generates a child node where that activity is scheduled *before* each other conflicting activity on that resource. Children are sorted by their projected lower bound so the most promising branches are explored first.

#### Failure Cache

The solver maintains a cache of **pair-sets that have been proved to lead to infeasibility**. Before propagating any new node, it checks whether the current pair-set is a *superset* of any known failing set (if A ⊆ B and A fails, then B also fails because it contains all of A's constraints plus more). This avoids redundant work.

The cache stores at most 400 entries, evicting the most specific (largest) sets first to maximise pruning power.

#### Node-Local Heuristic

At each DFS node, the solver may optionally run `construct_schedule` using the current node's time windows as a warm start. This can quickly find a good schedule deep in the tree without completing the full DFS. How often this is allowed depends on the budget mode and instance size — for large instances in fast mode, it's only attempted every 8th node.

#### Incumbent Management (`update_incumbent`)

Whenever a schedule is found (either from construction or from a conflict-free DFS leaf), it's compared to the current best. If it's better, it replaces the incumbent. The incumbent's makespan is then used in all future propagations as an upper bound, pruning any node whose lower bound is already ≥ incumbent makespan.

---

### 3.4 `construct.py` — Schedule Construction

**What it does:** Given the current CP state (a set of committed ordering edges and initial start times), tries to build a *complete, valid* feasible schedule by iteratively resolving resource conflicts.

This is a **conflict-repair heuristic**:

1. Start with a schedule where each activity starts as early as its constraints allow (longest-path forward pass).
2. Find the first resource overload:
   - For **small instances** (< 20 jobs): find any conflicting pair of activities.
   - For **large instances** (≥ 20 jobs): find the *minimal conflict set* — the smallest set of activities that, together, cause an overload at some time point.
3. Score each activity in the conflict using `delay_scores` (a weighted combination of slack, tail length, resource intensity, etc.).
4. Pick the highest-scoring activity to "protect" (keep in place) and push the others later by adding ordering edges.
5. Repeat until no conflicts remain.

If the solver cannot resolve a conflict within a step budget, or the time deadline is reached, construction fails and returns `None`.

**Focused repair mode (large instances):** Instead of sequencing one activity before one other, it sequences the selected activity before *all* other conflicting activities at once. This is more aggressive and avoids creating many micro-steps.

**Release-time fallback:** If no ordering resolves a conflict (all edges would create cycles), the solver artificially forces the activity to start *after* all conflicting activities have finished (a "release time"). This is a softer constraint that avoids cycles but may not give the tightest result.

After the repair loop:
- A final forward pass recomputes start times.
- If release times were used, the solver tries removing them to see if a tighter schedule is possible.
- A **left-shift** pass (`compress`) moves activities as early as possible without violating constraints.
- The schedule is validated; if it's still infeasible, construction fails.

---

### 3.5 `guided_seed.py` — Pre-DFS Warm-Start

**What it does:** Runs a structured three-phase mini-solver before the main DFS begins, to give DFS the best possible starting bound.

The three phases run within a time budget (up to 25% of the total time limit):

| Phase | What it does |
|---|---|
| **Construct** | Runs `construct_schedule` repeatedly (with randomised configs) to find an initial feasible schedule. Keeps the best. |
| **Improve** | Runs ALNS (`improve_incumbent`, see §3.6) to polish the best construction. |
| **Proof** | Runs a small exact branch-and-bound (`branch_and_bound_search`) to try to prove optimality or find an even better schedule. |
| **Polish** | If time remains after proof, runs another ALNS pass. |

The phases are time-budgeted: construct gets ~20% of the seed budget, improve gets ~35%, and the rest goes to proof and polish.

If the guided seed determines the instance is infeasible (the exact search exhausts the tree with no feasible schedule), the main solver returns immediately with status "infeasible" without entering DFS.

---

### 3.6 `improve.py` — ALNS Improvement

**What it does:** Implements an **Adaptive Large Neighbourhood Search (ALNS)** loop that improves an existing feasible schedule by repeatedly destroying a part of it and rebuilding it.

#### How Each Iteration Works

1. **Select a base schedule** from an elite pool (up to 6 best distinct schedules seen so far). Under high stagnation, occasionally try a second base.
2. **Choose a removal operator** (randomly from several strategies):
   - **Mobility removal:** Remove activities with the most scheduling slack (they're easiest to reschedule).
   - **Non-peak removal:** Remove activities that run during low-load periods (they're contributing least).
   - **Segment removal:** Remove all activities overlapping a random time window.
   - **Random removal:** Remove a random subset.
   - *(Large instances only)* **Critical chain removal:** Remove the least-slack, most resource-intensive activities.
   - *(Large instances only)* **Peak-focused removal:** Remove activities near the busiest resource bottleneck.
   - *(Large instances only)* **Bottleneck pair removal:** Find the most conflicting pair of activities at the bottleneck; try reordering them.
3. **Rebuild** the removed activities using `repair_schedule_subset`. The rest of the schedule is pinned in its existing order (their resource-ordering edges are kept), and the removed activities are re-inserted using `construct_schedule`.
4. **Update the elite pool** and check if the overall best has improved.

The loop runs until the time deadline.

**Stagnation handling:** If many iterations pass without improvement, the `stagnation` counter increases, which causes the loop to pull from a wider pool of base schedules. This helps escape local optima.

---

### 3.7 `exact.py` — Exact Branch & Bound

**What it does:** A simpler, self-contained DFS branch-and-bound that tries to *prove* the optimality of an incumbent schedule, or find an even better one by exhaustive search.

It uses the same conflict-branching structure as the main DFS in `search.py`, but without the full CP propagation infrastructure (no timetable propagation, no failure cache, no node-local heuristic). It is intentionally simpler and faster per node — useful for small subproblems or short proof budgets.

**Two modes:**
- **Without incumbent:** Searches freely; uses the incremental lag-distance matrix to detect pairwise infeasibility early and prune.
- **With incumbent:** Propagates start times at each node and prunes any branch whose lower bound already meets or exceeds the incumbent makespan.

When a conflict-free node is reached, the schedule is compressed with `compress_valid_schedule_relaxed` and compared against the best known.

---

## 4. Key Concepts Summary

| Concept | Plain-English Explanation |
|---|---|
| **Lag constraint** | "Activity B must start at least `d` time units after activity A starts." Negative lags enforce *maximum* gaps. |
| **Lag closure (all-pairs longest lags)** | Propagating all lag constraints transitively: if A→B with lag 3 and B→C with lag 2, then A→C has implied lag 5. Detected via Floyd-Warshall. |
| **EST / LST** | Earliest Start Time and Latest Start Time for each activity. The window `[EST, LST]` narrows as more constraints are added. |
| **Compulsory part** | The intersection of `[LST, EST + duration]` — the time when an activity *must* be running regardless of its exact start. |
| **Timetable propagation** | Checking that compulsory parts don't collectively overload a resource; tightening EST/LST if they would. |
| **Forced pair order** | A resource ordering that is *the only feasible option* given current time windows: both "A before B" and "B before A" are technically possible in isolation, but one of them would cause an overload. |
| **Incumbent** | The best complete feasible schedule found so far. Its makespan serves as an upper bound for pruning. |
| **Branch on conflict** | When resource conflicts remain, pick a set of activities that overload a resource and add a constraint forcing one to finish before another starts. Recurse into the resulting sub-problem. |
| **Failure cache** | A set of committed-ordering sets (pair-sets) that are known to lead to infeasibility. Any superset of a cached failure is also infeasible and can be skipped. |
| **Tail** | For each activity, the longest path from the end of that activity to the project sink. Used as a lower-bound contribution: `start[i] + duration[i] + tail[i] ≤ makespan`. |
| **Resource intensity** | A per-activity metric reflecting how heavily it uses resources relative to capacity. Used to prioritise branching decisions. |

---

## 5. Algorithm Flow Diagram

```
solve_cp(instance, time_limit)
│
├── Compute lag closure (all_pairs_longest_lags)
├── Detect pairwise infeasibility → return "infeasible" if found
├── Extract forced resource orders (free ordering constraints)
├── Compute temporal lower bound (EST of sink)
│
├── [Guided Seed Phase — up to 25% of time budget]
│   ├── construct_schedule() × many restarts → best schedule
│   ├── improve_incumbent() (ALNS) → polish
│   ├── branch_and_bound_search() → short proof attempt
│   └── improve_incumbent() again → final polish
│   │
│   └── If incumbent = lower bound → return immediately (optimal!)
│
├── [Short constructive warm start — remaining heuristic budget]
│   └── construct_schedule() × restarts
│
└── [DFS — remaining time budget]
    │
    └── dfs(pairs, node):
        ├── Check time limit
        ├── Check failure cache
        ├── propagate_cp_node():
        │   ├── Tighten EST via lag closure
        │   ├── Tighten LST via incumbent makespan
        │   ├── Build mandatory resource profiles
        │   ├── Propagate compulsory parts (timetable)
        │   ├── Detect forced pair orders
        │   └── Repeat to fixpoint → node or None
        │
        ├── Pruned (None) → record in failure cache, backtrack
        │
        ├── No conflict → compress schedule, update incumbent
        │
        ├── (optional) Node-local heuristic: construct_schedule()
        │   from current node's time windows → update incumbent
        │
        └── Conflict found → branch_children():
            ├── Score each activity (delay_scores)
            ├── For each ordering of conflicting activities:
            │   └── Propagate child → sort by lower bound
            └── Recurse into each child in order
```

---

## 6. File Quick Reference

| File | One-line purpose |
|---|---|
| `state.py` | Data structures: node state, propagation result, overload explanation, search statistics |
| `propagation.py` | CP reasoning kernel: tighten time windows, detect resource overloads, infer forced orderings |
| `search.py` | Main DFS: branching policy, incumbent management, failure cache, node-local heuristic |
| `construct.py` | Conflict-repair schedule builder: start from lower bounds, iteratively fix resource overloads |
| `improve.py` | ALNS improvement: destroy-and-repair loop with multiple removal strategies and elite pool |
| `guided_seed.py` | Pre-DFS warm-start: orchestrates construct → improve → proof → polish within a time budget |
| `exact.py` | Exact branch-and-bound helper: simpler DFS used for short proof attempts inside guided seed |
| `solver.py` | Thin entry point: just re-exports `solve_cp` from `search.py` |
