# CP Backend Algorithm Report

A detailed walkthrough of the Constraint Programming backend for the RCPSP/max solver, written so that someone with no prior exposure to the codebase can follow the logic from start to finish.

---

## 1. What Problem Are We Solving?

**RCPSP/max** stands for *Resource-Constrained Project Scheduling Problem with generalised (min/max) lag constraints*. You have a project made up of activities, and you need to decide when each one starts. Three things make this hard:

1. **Durations and precedence.** Every activity takes a fixed number of time units. Some activities depend on others through *lag constraints*: "Activity B cannot start until at least 5 time units after Activity A starts" (minimum lag), or "Activity B must start no more than 10 time units after Activity A starts" (maximum lag, encoded as a negative lag in the reverse direction).

2. **Shared resources.** There are a handful of resource types (machines, workers, etc.), each with a limited capacity. Every activity uses some amount of each resource while it runs. At any moment in time, the total demand of all running activities must not exceed the capacity of any resource.

3. **Objective.** Minimise the *makespan* — the time at which the very last activity finishes. There is a dummy "source" activity (index 0) that starts at time 0, and a dummy "sink" activity (index `n_jobs + 1`) whose start time equals the makespan.

The solver has a strict wall-clock time budget (up to 30 seconds). Within that budget, it must find a valid schedule or determine the instance is infeasible — while never misclassifying a feasible instance as infeasible.

---

## 2. The Core Idea: Searching Over Ordering Decisions

The key insight of the CP backend is that resource conflicts can be resolved by deciding the *order* in which activities use a resource. If activities A and B both need more of resource R than is available simultaneously, then either A must finish before B starts, or B must finish before A starts. Each such decision is encoded as a new precedence edge in the constraint graph.

The solver explores a tree of these ordering decisions:
- At each node, it holds a set of committed orderings plus the tightest time windows those orderings imply.
- It uses *constraint propagation* to shrink time windows and detect dead ends early.
- It uses the best schedule found so far (the *incumbent*) to prune branches that cannot possibly improve on it.

```
                         Root: only original precedences
                        /              |              \
              A before B          B before A         A before C
             /     \                 |                   |
        C before D  D before C     ...                  ...
```

Each path from root to leaf represents a complete set of ordering decisions. If the resulting time windows contain no resource overload, a feasible schedule exists for that path.

---

## 3. Data Structures (`state.py`)

Before diving into the algorithms, it helps to know the four data structures that flow through the entire backend.

### CpNode — A Single Search Tree Node

```python
@dataclass(frozen=True)
class CpNode:
    lower: tuple[int, ...]         # EST (Earliest Start Time) for each activity
    latest: tuple[int, ...] | None # LST (Latest Start Time), or None if no incumbent yet
    edges: tuple[Edge, ...]        # all committed ordering edges
    pairs: frozenset[tuple[int, int]]  # the set of (before, after) ordering decisions
    lag_dist: list[list[float]] | None  # full shortest-path distance matrix
    branch_conflict: BranchConflict | None  # the next resource overload to branch on
```

**Time windows** are the most important part. Every activity `i` has a window `[lower[i], latest[i]]` in which it is allowed to start. As the solver commits more ordering decisions, these windows shrink. When `lower[i] > latest[i]` for any activity, the node is impossible — we prune it.

When `branch_conflict` is `None`, there are no remaining resource overloads and the schedule at the earliest start times is feasible (after compression). When it is not `None`, it tells the solver exactly which activities on which resource to branch on next.

### OverloadExplanation — Why Propagation Failed

```python
@dataclass(frozen=True)
class OverloadExplanation:
    kind: str           # "point" (single time slot) or "pair" (two-activity conflict)
    resource: int       # which resource is overloaded
    window_start: int   # start of the overloaded time window
    window_end: int     # end of the overloaded time window
    activities: tuple[int, ...]  # the set of activities causing the overload
    required: int       # total demand of those activities
    limit: int          # capacity of the resource
```

This tells you exactly *why* propagation detected a problem. Two flavours:
- **"point"**: at a single time slot, the compulsory parts of several activities collectively exceed the capacity. This is detected by timetable propagation.
- **"pair"**: two activities that must overlap (their time windows force them to run simultaneously) but whose combined demand exceeds the capacity. This is detected by forced-pair-order propagation.

### CpNodePropagation — The Result of Propagating a Node

```python
@dataclass(frozen=True)
class CpNodePropagation:
    node: CpNode | None              # the propagated node, or None if proved infeasible
    overload: OverloadExplanation | None  # present if timetable found an overload to branch on
    rounds: int = 0                   # how many propagation rounds were needed
```

Three outcomes are possible:
- `node is not None, overload is None` — propagation succeeded, the node is consistent, `branch_conflict` on the node tells you what to do next.
- `node is not None, overload is not None` — there is a timetable overload the solver may want to branch on.
- `node is None` — the node is provably infeasible (temporal cycle, or lower bound exceeds incumbent, or windows crossed).

### CpSearchStats — Counters for Diagnostics

A mutable bag of integers tracking everything that happens during the search: nodes visited, propagation calls, cache hits, construct failures broken down by reason, etc. Not algorithmically important, but essential for tuning and debugging.

---

## 4. Constraint Propagation (`propagation.py`)

This is the algorithmic core. Given a set of ordering decisions (pairs), propagation computes the tightest possible time window for every activity and checks whether any resource is still overloaded.

### 4.1 All-Pairs Lag Closure

**What:** Compute the longest path between every pair of activities in the constraint graph.

**Why:** Lag constraints are transitive. If A must precede B by at least 3 time units, and B must precede C by at least 2 time units, then A must precede C by at least 5 time units. The lag closure captures all such implied constraints in one matrix.

**How:** Standard Floyd-Warshall algorithm (`all_pairs_longest_lags` in `core/lag.py`):

```
For each intermediate activity k:
    For each source activity i:
        For each target activity j:
            dist[i][j] = max(dist[i][j], dist[i][k] + dist[k][j])
```

The result is `lag_dist[i][j]` = the minimum number of time units that must separate the start of `i` from the start of `j`. If `lag_dist[i][i] > 0`, there is a positive cycle and the instance is infeasible.

**Incremental updates:** When the solver adds a single new ordering edge, it does not recompute the full Floyd-Warshall. Instead, `extend_longest_lags` updates only the entries affected by the new edge, in O(n^2) time instead of O(n^3). This is critical for performance during search.

### 4.2 Tighten Earliest Starts

**What:** Given the lag distance matrix, compute the earliest possible start time for every activity.

**How:** For each activity `target`, look at every other activity `source`. If `source` must start at time `lower[source]` and the lag from `source` to `target` is `d`, then `target` cannot start before `lower[source] + d`. Take the maximum over all sources:

```
lower[target] = max over all sources of (lower[source] + lag_dist[source][target])
```

This is a single forward pass — not an iterative loop — because the lag closure already accounts for all transitive constraints. If a positive diagonal is found (`lag_dist[i][i] > 0`), a `TemporalInfeasibleError` is raised.

### 4.3 Tighten Latest Starts

**What:** If we have an incumbent schedule with makespan `T`, then every activity `i` has a latest possible start: `T - 1 - tail[i]`, where `tail[i]` is the longest path from the end of activity `i` to the project sink. This gives the initial latest-start vector.

**How the backward pass works:** The function `tighten_latest_starts` propagates backward. If activity `source` must precede activity `target` with lag `d`, then:

```
latest[source] = min(latest[source], latest[target] - d)
```

When the lag distance matrix is available, this is a single-pass matrix multiply. Otherwise, it runs Bellman-Ford on the reversed edge set.

**Key point:** Latest-start information only exists when there is an incumbent. Without one, the solver has no upper bound and `latest` is `None`. In that case, timetable propagation (Steps 4.4 and 4.5) is skipped entirely, and only temporal propagation applies.

### 4.4 Compulsory Part Detection (Timetable Propagation)

This is the technique that makes the CP backend powerful at detecting resource infeasibility early.

**The idea:** Even though we do not know exactly when an activity will start (it could be anywhere in `[EST, LST]`), there may be a time interval where the activity *must* be running regardless of its exact start time. This is called the **compulsory part** (or mandatory part).

**Example:**
```
Activity A: duration = 5, EST = 3, LST = 6

If A starts at time 3 (earliest):  ■■■■■
                                    3 4 5 6 7
If A starts at time 6 (latest):        ■■■■■
                                    3 4 5 6 7 8 9 10

The overlap — where A MUST be running — is [6, 8):
                                    3 4 5 6 7
                                          ██
```

**Formally:** Activity `i` has a compulsory part `[LST[i], EST[i] + duration[i])` if `LST[i] < EST[i] + duration[i]`. The solver computes a **mandatory resource profile** by summing the resource demands of all compulsory parts at each time slot. If any time slot exceeds the resource capacity, the node is infeasible.

**Implementation detail:** The profile is built using a delta-sweep approach (increment at start, decrement at end, then prefix-sum) for efficiency, rather than looping over every time slot of every activity.

### 4.5 Timetable-Based Window Tightening

Beyond detecting overloads, the mandatory profile also lets the solver *tighten* time windows.

**EST tightening:** If activity `i` were placed at its current EST, would it cause an overload? The solver checks every time slot in the range `[EST[i], EST[i] + duration[i])`. At each slot, it computes the *other* activities' mandatory load (excluding `i`'s own compulsory contribution). If adding `i`'s demand would exceed capacity, then `i` cannot start that early — its EST is pushed forward past the overloaded slot.

```
Before:  EST = 2
         Time:  2  3  4  5  6  7
         Other: 3  3  7  7  4  4    (capacity = 8, activity demand = 3)
                         ^  ^
                    slots 4,5 would cause overload (7+3=10 > 8)
After:   EST = 6  (pushed past the overloaded region)
```

**LST tightening:** The mirror image. If placing `i` at its current LST would cause an overload, the LST is pulled back.

**Infeasibility:** If EST gets pushed past LST, the activity has no valid placement — the node is infeasible (returns `None`).

### 4.6 Forced Pair-Order Propagation

**What:** For every pair of activities that share a resource and whose combined demand exceeds the capacity, check whether the current time windows force a specific ordering.

**How:** Given activities A and B on a shared resource:
- "A before B" is possible if `EST[A] + duration[A] <= LST[B]` — A can finish before B's latest start.
- "B before A" is possible if `EST[B] + duration[B] <= LST[A]`.

Three outcomes:
1. **Both orderings possible** — nothing to infer, move on.
2. **Exactly one ordering possible** — that ordering is forced. Add it as a new edge and re-propagate.
3. **Neither ordering possible** — the two activities must overlap, but their combined demand exceeds capacity. The node is infeasible.

This is only run on instances with 20+ jobs (smaller instances are fast enough without it). It uses a precomputed set of `resource_conflict_pairs` to avoid checking pairs that do not actually conflict on any resource.

### 4.7 The Propagation Loop (`propagate_cp_node`)

All the pieces above are wired together in a fixpoint loop:

```
repeat:
    1. Tighten earliest starts using lag closure
    2. Bound-check: if EST[sink] >= incumbent makespan, prune
    3. Check pairwise infeasibility from lag distance matrix
    4. Tighten latest starts (backward pass)
    5. Check for crossed windows (EST > LST anywhere → prune)
    6. Build mandatory profile and run timetable propagation
       - If overload detected → return the overload for branching
       - If windows tightened → update and continue
    7. Run forced pair-order propagation
       - If infeasible pair found → return the overload
       - If new orderings inferred → add edges, update lag closure, continue
    8. If nothing changed → fixpoint reached, exit loop
```

After the loop, the solver calls `select_branch_conflict` to find the "best" remaining resource overload to branch on (smallest conflict set, tightest slack). If none exists, the schedule is feasible.

---

## 5. The Main Search (`search.py`)

`solve_cp` is the top-level entry point. It orchestrates everything: preprocessing, seeding, and the DFS.

### 5.1 Preprocessing

Before any search happens:

1. **Lag closure:** Compute `all_pairs_longest_lags` for the original instance.
2. **Pairwise infeasibility check:** Scan for pairs of activities that *must* overlap (their lag constraints force it) and whose combined demand exceeds a resource's capacity. If found, the instance is provably infeasible — return immediately.
3. **Forced resource orders:** Find pairs where the lag closure already forces one ordering (e.g., the only way to avoid a resource conflict is A before B). These edges are "free" — they do not require branching. They are added to the root and the lag closure is updated.
4. **Temporal lower bound:** Compute `longest_feasible_starts` with the forced edges. The sink's start time is the *temporal lower bound* — no schedule can possibly have a shorter makespan.
5. **Tail values:** For each activity, compute the longest path from the end of that activity to the sink. Used in branching heuristics and for computing latest starts.
6. **Resource intensity:** For each activity, compute a normalised score of how heavily it uses resources. Activities with high intensity are more likely to cause conflicts and are prioritised during branching.
7. **Resource conflict pairs:** Precompute the set of all activity pairs that share at least one resource beyond capacity. This speeds up forced-pair-order propagation.

### 5.2 Budget Management

The solver divides its time budget into phases:

| Time limit | Budget mode | Behaviour |
|---|---|---|
| < 1.0s | `fast` | Minimal heuristic work, aggressive search |
| 1.0s–5.0s | `medium` | Moderate heuristic work at each node |
| >= 5.0s | `deep` | More heuristic attempts, deeper local search |

A `soft_deadline` is computed slightly before the actual time limit (with a safety margin of 0.5–5% depending on the budget) so the solver can wrap up cleanly without going over.

### 5.3 Guided Seed Phase

Before the main DFS, the solver calls `run_guided_seed` (which delegates to `guided_seed.py`, see Section 7). This attempts to find a good incumbent quickly through construction, improvement, and a short exact proof. It consumes up to 25% of the time budget (capped at 0.75 seconds).

If the guided seed:
- **Proves infeasibility** — the solver returns immediately.
- **Finds an optimal schedule** (makespan equals the temporal lower bound) — the solver returns immediately.
- **Finds a suboptimal schedule** — great, the DFS will use this as its starting incumbent.
- **Finds nothing** — the DFS starts without an incumbent (this makes propagation weaker since there are no latest-start bounds).

### 5.4 Constructive Warm Start

If the guided seed did not produce an incumbent, the solver runs `construct_schedule` in a tight loop (see Section 6) using the remaining heuristic budget, keeping the best schedule found. Each restart uses a randomly perturbed version of the heuristic config (`sample_heuristic_config`), introducing diversity.

### 5.5 The DFS

The DFS is an inner function that captures `incumbent` via closure. Here is the logic at each node:

**Step 1 — Time check.** If the soft deadline has passed, set `timed_out = True` and backtrack.

**Step 2 — Failure cache lookup.** If the current pair-set is a superset of any known-failing pair-set, skip this node (see Section 5.7).

**Step 3 — Propagation.** Call `propagate_cp_node` with the current pairs, the incumbent makespan (for latest-start bounds), and the lag distance matrix. Three outcomes:
- **Overload returned:** The node has a timetable conflict. Record in the failure cache, backtrack.
- **Node is `None`:** Proved infeasible (temporal cycle, bounds exceeded, or windows crossed). Cache and backtrack.
- **Valid node returned:** Continue to step 4.

**Step 4 — Duplicate check.** Compute a signature `(pairs, lower, latest)` and check whether this exact node has been seen before. If so, skip it.

**Step 5 — Feasible leaf.** If `branch_conflict is None`, propagation found no remaining resource overload. The earliest-start schedule is feasible. Compress it (`compress_valid_schedule_relaxed` shifts activities left where possible without creating new conflicts) and update the incumbent if it improves.

**Step 6 — Node-local heuristic.** If budget allows (controlled by `allow_node_local_heuristic`), try to build a complete schedule from this node's state using `construct_schedule`. This is a fast way to find incumbents deep in the tree without fully resolving the search. The budget and frequency depend on instance size and budget mode — for example, on very large instances in fast mode, this only runs every 8th node.

There is also a "deep" variant for instances with 100+ jobs in deep budget mode, which gets a larger time slice per attempt. This triggers when the gap between the node's lower bound and the incumbent is large enough to be worth the effort.

**Step 7 — Branch.** Unpack the `branch_conflict` to get the conflicting activities and resource. Call `branch_children` to generate and evaluate all child nodes.

**Step 8 — Recurse.** Iterate through the children (sorted by their lower bound — best-first) and recurse. If the incumbent reaches the temporal lower bound, stop immediately (it is optimal). If a timeout occurs, stop.

**Step 9 — Cache failures.** If no child produced a feasible schedule, record this pair-set in the failure cache.

### 5.6 Branch Child Generation (`branch_children`)

Given a conflict set (the activities overloading a resource at some time point), the solver must decide which activity to delay. The process:

1. **Rank activities** using `branch_order`: score each activity by a weighted combination of slack, tail length, overload contribution, resource intensity, and start time. Activities that score highest are the most "expendable" — delaying them is least likely to worsen the makespan.

2. **Generate children:** For each activity `selected` (in ranked order), and for each other activity `other` in the conflict set, create a child node with the new edge `other → selected` (meaning "`other` must finish before `selected` starts").

3. **Pre-filter children:**
   - Skip if the pair is already committed.
   - Skip if the ordering is impossible given current windows (`pair_direction_possible` checks whether `EST[other] + gap <= LST[selected]`, where `gap` accounts for transitive lags).
   - Skip if the child's pair-set matches a cached failure.

4. **Propagate each child** to get its tightened time windows and lower bound. Skip children that are pruned by propagation.

5. **Sort surviving children** by `child_order_key`: primarily by lower bound at the sink (prefer children closer to optimality), then by slack and window size (prefer tighter, more constrained children that will be easier to resolve or prune).

### 5.7 Failure Cache

The failure cache is a set of `frozenset[tuple[int, int]]` — each entry is a set of ordering decisions that has been proved to lead to infeasibility (either by propagation or by exhaustive subtree search).

**Key property:** ordering decisions are *monotone*. If a set of pairs S is infeasible, then any superset of S is also infeasible (adding more constraints can only make things worse). So before propagating a new node, the solver checks:

```python
any(failed.issubset(pairs) for failed in failed_pair_sets)
```

**Cache management:**
- Maximum 400 entries.
- When full, evict the *largest* (most specific) entry, since smaller entries prune more branches.
- When inserting, drop any existing entry that is a superset of the new one (the new entry is more general and therefore more useful).
- Only enabled when the time limit is >= 0.5s, or for instances with >= 20 jobs at >= 0.1s.

### 5.8 Wrapping Up

After the DFS finishes (either exhausting the tree or hitting the deadline), the solver returns a `SolveResult`:
- `"feasible"` with the best schedule found, or
- `"infeasible"` if the tree was fully explored with no feasible leaf, or
- `"unknown"` if the search timed out without finding a schedule.

---

## 6. Schedule Construction (`construct.py`)

`construct_schedule` is a conflict-repair heuristic that tries to build a valid schedule from a starting point (usually the earliest-start-time schedule, which satisfies all temporal constraints but may violate resource limits).

### 6.1 The Repair Loop

```
Start: schedule where each activity is at its earliest possible start time

Repeat until no conflicts or budget exhausted:
    1. Find the worst resource overload
    2. Score each activity in the conflict
    3. Pick the "best" activity to protect; push others out of its way
    4. Recompute start times with the new ordering edges
```

**Conflict detection** comes in two flavours based on instance size:

- **Small instances (< 20 jobs):** `first_conflict` — find the earliest time slot with any resource overload, list all active activities at that slot. This is simple but can produce large conflict sets.

- **Large instances (>= 20 jobs):** `minimal_conflict_set` — find the most overloaded resource at the earliest conflict, then strip away activities until only the *minimal* set whose combined demand exceeds capacity remains. This produces smaller, more focused conflicts that lead to better repair decisions.

### 6.2 Activity Scoring (`delay_scores`)

Each activity in the conflict is scored by a weighted sum:

```
score = slack_weight * slack
      - tail_weight * tail
      + overload_weight * overload_contribution
      + resource_weight * intensity
      + late_weight * start_time
      + noise_weight * random()
```

- **Slack:** How much room the activity has before it affects the makespan. High-slack activities are safer to delay.
- **Tail:** The longest path from this activity to the sink. Long-tail activities are critical — delaying them is risky.
- **Overload contribution:** How much of the current overload this activity is responsible for.
- **Resource intensity:** How heavily this activity uses resources relative to capacity.
- **Start time:** Later-starting activities are slightly preferred for delaying.
- **Noise:** A small random perturbation to introduce diversity across restarts.

The highest-scoring activity is "protected" (kept in place), and the others are pushed after it.

### 6.3 Edge-Based Repair vs. Focused Repair

**Small instances (edge-based):** For each blocker activity, try both orderings (blocker before selected, selected before blocker). Evaluate each by computing the resulting makespan. Pick the combination that yields the lowest makespan.

**Large instances (focused repair):** Instead of trying each blocker individually, push *all* blockers to one side of the selected activity at once. Try both directions (all blockers before selected, or selected before all blockers) and pick the better one. This is faster because it resolves the entire conflict in one step.

### 6.4 Release-Time Fallback

If neither ordering direction produces a valid schedule (both cause temporal cycles), the solver falls back to *release times*: it sets `release[selected] = max finish time of all blockers`, forcing the activity to start after the conflict point. This avoids cycles but is less precise.

### 6.5 Post-Processing

After the repair loop resolves all conflicts (or the budget expires):

1. **Final forward pass:** Recompute start times from release times and edges.
2. **Release cleanup:** If release times were used, try removing them to see if a tighter schedule is possible with just the edges.
3. **Left shift:** Move each activity as early as possible without violating precedence or resource constraints. This is a greedy pass that processes activities in start-time order.
4. **Compression:** `compress_valid_schedule` extracts the resource-ordering edges implied by the current schedule and recomputes the longest-path schedule, potentially tightening the makespan further.
5. **Validation:** Check the final schedule against all constraints. If it fails, construction returns `None`.

### 6.6 Failure Diagnostics

Construction tracks why it failed via a `diagnostics` dictionary:
- `"deadline"` — ran out of time.
- `"step_limit"` — exceeded the maximum number of repair steps (default: `max(200, n^2 * 6)`).
- `"projection_infeasible"` — adding edges created a temporal cycle (negative cycle in the constraint graph).
- `"validation"` — the schedule passed the repair loop but failed final validation.

---

## 7. Guided Seed Phase (`guided_seed.py`)

The guided seed is a self-contained mini-solver that runs before the main DFS. It shares the same preprocessing (lag closure, forced orders, tails, intensity) but has its own time budget and phase structure. It is called from `search.py` through the `run_guided_seed` wrapper.

### 7.1 Four Phases

| Phase | Budget | What it does |
|---|---|---|
| **Construct** | ~20% of seed budget (up to 1.0s) | Runs `construct_schedule` in a loop with randomised configs. Keeps the best schedule. Stops early if it matches the temporal lower bound. |
| **Improve** | ~35% of seed budget (up to 5.0s) | Runs the ALNS improvement loop (Section 8) on the best construction. |
| **Proof** | Remaining budget until soft deadline | Runs `branch_and_bound_search` (Section 9) — a simpler exact search that can prove optimality or find an even better schedule. |
| **Polish** | Whatever remains after proof | Runs ALNS one more time on whatever the proof phase returned, if there is time and the schedule is not already optimal. |

### 7.2 When Is It Used?

The guided seed is only invoked when the heuristic budget is >= 0.15 seconds. For very short time limits (< 0.15s), it is skipped entirely and the solver goes straight to construction + DFS.

### 7.3 Status Tracking

The guided seed reports back:
- Whether it was used, found an incumbent, proved infeasibility, or failed.
- The best source of the schedule (construct, improve, proof, or polish).
- Construction failure counts by reason.
- Exact search statistics (nodes, timed out).

---

## 8. ALNS Improvement (`improve.py`)

Once a feasible schedule exists, the solver can try to improve it using **Adaptive Large Neighbourhood Search**: repeatedly destroy part of the schedule and rebuild it, hoping to find a shorter makespan.

### 8.1 The Destroy-Repair Loop

```
Initialise: elite pool = [incumbent], stagnation = 0

Repeat until deadline:
    1. Select one or more base schedules from the elite pool
    2. For each base:
        a. Choose a removal operator (randomly)
        b. Choose a removal size (randomly, 2-33% of activities)
        c. Remove selected activities from the schedule
        d. Rebuild using construct_schedule with remaining activities pinned
    3. Update elite pool and best schedule
    4. Track stagnation
```

### 8.2 Removal Operators

The solver randomly picks one of these strategies to decide *which* activities to remove:

**Available to all instances:**

| Operator | Strategy | Rationale |
|---|---|---|
| **Mobility** | Remove activities with the *most* scheduling slack | High-slack activities have the most room to be repositioned |
| **Non-peak** | Remove activities running during low-load periods | Rearranging under-utilised activities might free up room elsewhere |
| **Segment** | Remove all activities overlapping a random time window | Neighbourhood-focused: lets you rearrange a local region |
| **Random** | Remove a random subset | Pure diversification |

**Additional operators for large instances (>= 30 jobs):**

| Operator | Strategy | Rationale |
|---|---|---|
| **Critical chain** | Remove the *least*-slack, most resource-intensive activities | These are the activities most directly responsible for the makespan |
| **Peak-focused** | Remove activities near the single busiest resource bottleneck | Directly targets the tightest constraint |
| **Bottleneck pair** | Find the most conflicting pair of activities at the bottleneck; generate three repair plans: one without pair preference, one favouring the current order, one swapping them | Explores whether reversing a critical ordering decision helps |

### 8.3 The Repair Step

`repair_schedule_subset` extracts the ordering edges from the current schedule, removes any edge involving a removed activity, adds `preferred_pairs` if the bottleneck-pair operator specified them, then calls `construct_schedule` to rebuild. This means the removed activities are free to be re-inserted in any feasible position, while the rest of the schedule stays mostly fixed.

### 8.4 Elite Pool

The solver maintains a pool of up to 4–6 distinct schedules (sorted by makespan). Each repair attempt's result is considered for the pool. This prevents the search from getting stuck on a single local optimum — the solver can restart repairs from a different base schedule.

### 8.5 Stagnation Handling

- If an iteration improves on some base schedule but not the overall best: stagnation decreases slightly.
- If no iteration produces anything useful: stagnation increases.
- Higher stagnation causes the solver to select bases from deeper in the elite pool (worse schedules), increasing diversity.

---

## 9. Exact Branch-and-Bound (`exact.py`)

A simpler, stripped-down DFS that tries to either prove the incumbent is optimal or find a better schedule. It is used inside the guided seed phase and shares no state with the main DFS.

### 9.1 How It Differs From the Main DFS

| Feature | Main DFS (`search.py`) | Exact B&B (`exact.py`) |
|---|---|---|
| Propagation | Full CP: timetable, forced pairs, lag closure | Only temporal (longest path) |
| Pruning | Failure cache, timetable, pairwise infeasibility | Bound check, pairwise infeasibility |
| Heuristic at nodes | Node-local construction | None |
| State | `CpNode` with lag distance matrix | Raw edge list + start times |
| Purpose | Find best schedule within time limit | Prove optimality or improve incumbent |

### 9.2 The Search

```
dfs(edges, pairs, start_times, lag_dist):
    1. Check deadline
    2. Duplicate check (sorted pair set)
    3. Compute start times (longest path with all edges)
    4. Bound check: if lower_bound >= incumbent makespan, prune
    5. Pairwise infeasibility check (only when no incumbent yet)
    6. Find minimal resource conflict
    7. If no conflict → compress schedule, update incumbent
    8. Otherwise → branch on conflict, recurse into children
```

**Two modes:**
- **Without incumbent:** Explores freely. Uses the incremental lag distance matrix to catch pairwise infeasibility early (two activities forced to overlap beyond capacity). Children are generated and recursed into immediately.
- **With incumbent:** More aggressive pruning. Each child's start times are computed *before* recursing, and any child whose lower bound is not strictly less than the incumbent is dropped. Surviving children are sorted by lower bound.

---

## 10. Putting It All Together

Here is the complete flow of a solve, showing how all the pieces connect:

```
solve_cp(instance, time_limit=30.0, seed=0)
│
│  ┌─────────────────────────────────────────────────┐
│  │  PREPROCESSING                                   │
│  │  1. Compute all-pairs lag closure (Floyd-Warshall)│
│  │  2. Check pairwise infeasibility → early exit?   │
│  │  3. Extract forced resource orderings            │
│  │  4. Compute temporal lower bound (EST of sink)   │
│  │  5. Compute tail values (longest path to sink)   │
│  │  6. Compute resource intensity per activity      │
│  │  7. Precompute resource-conflicting pairs        │
│  └─────────────────────────────────────────────────┘
│
├── GUIDED SEED PHASE (up to 25% of budget, if >= 0.15s available)
│   │
│   │  guided_seed.py → solve()
│   │  ├── Construct: construct_schedule() x N restarts
│   │  ├── Improve:   ALNS destroy/repair loop
│   │  ├── Proof:     exact branch-and-bound
│   │  └── Polish:    ALNS again if time remains
│   │
│   ├── If proved infeasible → RETURN "infeasible"
│   └── If optimal (makespan = lower bound) → RETURN immediately
│
├── CONSTRUCTIVE WARM START (remaining heuristic budget)
│   │  construct_schedule() x N restarts with random config perturbation
│   └── Keep best schedule as incumbent
│
└── DFS OVER ORDERING DECISIONS (remaining time until soft deadline)
    │
    └── dfs(forced_pairs, node=None):
        │
        ├── Time check → stop if deadline passed
        ├── Failure cache check → skip if known-failing superset
        │
        ├── PROPAGATE (propagation.py):
        │   │  ┌─ Tighten EST via lag closure
        │   │  ├─ Bound check vs incumbent
        │   │  ├─ Pairwise infeasibility check
        │   │  ├─ Tighten LST (backward pass)
        │   │  ├─ Check EST > LST anywhere
        │   │  ├─ Build mandatory profile
        │   │  ├─ Timetable propagation (EST/LST tightening)
        │   │  ├─ Forced pair-order propagation
        │   │  └─ Repeat until fixpoint
        │   │
        │   ├── Pruned → record in failure cache, backtrack
        │   └── Consistent → continue
        │
        ├── LEAF: branch_conflict is None
        │   └── Compress schedule, update incumbent
        │
        ├── NODE-LOCAL HEURISTIC (if budget allows):
        │   └── construct_schedule() from this node → update incumbent
        │
        └── BRANCH on conflict:
            ├── Score activities with delay_scores
            ├── Generate children: for each (other → selected) edge
            │   ├── Check feasibility of direction
            │   ├── Check failure cache
            │   ├── Propagate child
            │   └── Filter by lower bound
            ├── Sort children by lower bound (best first)
            └── Recurse into each child
                └── Stop early if incumbent = lower bound (optimal)
```

---

## 11. Glossary

| Term | Definition |
|---|---|
| **Activity** | A unit of work with a fixed duration and resource demands. Indexed 0 to `n_jobs + 1`, where 0 is the dummy source and `n_jobs + 1` is the dummy sink. |
| **Makespan** | The start time of the sink activity — equivalently, the total project duration. This is what we minimise. |
| **Edge / Lag constraint** | A directed constraint `(source, target, lag)` meaning "target cannot start until at least `lag` time units after source starts". Negative lags encode maximum-gap constraints. |
| **Lag closure** | The all-pairs longest-path matrix. `dist[i][j]` is the tightest lower bound on `start[j] - start[i]` implied by all constraints. |
| **EST / LST** | Earliest Start Time / Latest Start Time. The window `[EST, LST]` for each activity shrinks as ordering decisions are added. |
| **Tail** | For activity `i`, the longest path from `end(i)` to the sink. Gives a lower bound: `makespan >= start[i] + duration[i] + tail[i]`. |
| **Compulsory part** | The time interval `[LST, EST + duration)` where an activity must be running regardless of its exact start. Exists only when `LST < EST + duration`. |
| **Timetable propagation** | Summing compulsory-part demands to detect resource overloads and tighten windows. |
| **Forced pair order** | When time windows make only one ordering feasible for a pair of conflicting activities, that ordering is inferred as a free constraint. |
| **Incumbent** | The best complete valid schedule found so far. Its makespan provides an upper bound for pruning. |
| **Temporal lower bound** | The makespan of the earliest-start-time schedule (ignoring resources). No valid schedule can be shorter. |
| **Failure cache** | Stores sets of ordering decisions proven to lead to infeasibility. Any superset of a cached set is also infeasible, enabling fast pruning. |
| **Resource intensity** | A per-activity score measuring how heavily it uses resources. Used to guide branching and scoring. |
| **ALNS** | Adaptive Large Neighbourhood Search. A metaheuristic that repeatedly destroys and repairs parts of a solution. |
| **Elite pool** | A small set of the best distinct schedules seen so far, used as starting points for ALNS iterations. |

---

## 12. File Reference

| File | Lines | Role |
|---|---|---|
| `state.py` | ~80 | Data structures: `CpNode`, `CpNodePropagation`, `OverloadExplanation`, `CpSearchStats` |
| `propagation.py` | ~480 | Constraint propagation kernel: EST/LST tightening, timetable propagation, forced pair-order inference, the main `propagate_cp_node` fixpoint loop |
| `search.py` | ~790 | Main DFS search: preprocessing, guided seed orchestration, branch-and-propagate loop, failure cache, node-local heuristic, incumbent management |
| `construct.py` | ~330 | Conflict-repair schedule builder: finds resource overloads, adds ordering edges to resolve them, left-shifts and compresses the result |
| `improve.py` | ~450 | ALNS improvement: 7 removal operators, repair via pinned-edge reconstruction, elite pool management, stagnation tracking |
| `guided_seed.py` | ~410 | Pre-DFS warm-start: 4-phase pipeline (construct, improve, proof, polish) with its own time budgeting |
| `exact.py` | ~160 | Exact branch-and-bound: simpler DFS for short proof attempts, used inside the guided seed phase |
| `solver.py` | ~4 | Entry point: re-exports `solve_cp` from `search.py` |
| `__init__.py` | ~2 | Package exports |
