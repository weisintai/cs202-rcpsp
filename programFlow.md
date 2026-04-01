# Program Flow

How the solver works, end to end. Source code lives in `src/`.

---

## Overview

```
Input File (.sm or .SCH)
        │
        ▼
   ┌─────────-┐
   │  Parse   │  Detect format, extract problem data
   └────┬─────┘
        │
        ▼
   ┌──────────────────┐
   │ Topological Sort │  Order activities respecting precedence
   └────┬─────────────┘
        │
        ▼
   ┌────────────────────┐
   │ Remove Back Edges  │  Clean up any cycles broken during sort
   └────┬───────────────┘
        │
        ▼
   ┌──────────────────────┐
   │ Generate Candidates  │  Priority rules (LFT, MTS, GRD, SPT) + random
   └────┬─────────────────┘
        │
        ▼
   ┌─────────────────────┐
   │  Genetic Algorithm  │  Evolve population for 28s using SSGS decoder
   └────┬────────────────┘
        │
        ▼
   ┌────────────┐
   │  Validate  │  Check precedence + resource constraints
   └────┬───────┘
        │
        ▼
   Output start times (stdout)
```

---

## Stage 1: Parse — `parse()` → `parse_sm()` or `parse_sch()`

**Purpose:** Read the input file and populate the `Problem` struct.

**Format detection:** The first line of the file determines the parser.
- Starts with `*` → standard PSPLIB `.sm` format → `parse_sm()`
- Starts with integers → ProGenMax `.SCH` format → `parse_sch()`

**What gets extracted:**
- `n` — number of real activities (excluding dummy source 0 and dummy sink n+1)
- `K` — number of renewable resource types
- `duration[i]` — processing time for each activity
- `resource[i][k]` — demand of resource k by activity i
- `successors[i]` — list of activities that must come after i
- `predecessors[i]` — list of activities that must come before i
- `capacity[k]` — maximum available units of resource k at any timestep

**SCH-specific handling:** The `.SCH` format includes time lags in brackets after each successor (e.g., `[0]`, `[-3]`). These come from the RCPSP/max formulation. We only keep edges with **non-negative** lags. Negative lags represent maximum time lag constraints (backward edges) that don't apply to standard RCPSP.

Example from `PSP2.SCH`:
```
7   1   2   1  10   [-1] [0]
            │   │    │     │
            │   │    │     lag=0 → KEEP edge 7→10
            │   │    lag=-1 → SKIP edge 7→1
            successors: 1, 10
```

**Reference:** `src/parser.h`, `src/parser.cpp`

---

## Stage 2: Topological Sort — `topological_sort()`

**Purpose:** Produce a linear ordering of all activities (0 through n+1) that respects precedence. Activity i appears before activity j if i is a predecessor of j.

**Algorithm:** Kahn's algorithm.
1. Compute in-degree for each activity (number of predecessors)
2. Add all activities with in-degree 0 to a queue (always includes activity 0)
3. Process the queue: for each activity, decrement the in-degree of its successors. When a successor's in-degree reaches 0, add it to the queue
4. Repeat until all activities are ordered

**Cycle handling:** Some `.SCH` files have cycles even after negative-lag filtering (e.g., `4→6` and `6→4` both with lag `[0]`). When the queue empties before all activities are processed:
- Find the unprocessed activity with the **lowest remaining in-degree**
- Force it into the queue (artificially set its in-degree to 0)
- Continue processing

This breaks the cycle by arbitrarily choosing which direction the precedence goes. The broken edges are cleaned up in the next stage.

Does not affect `.sm` files — they are DAGs by definition.

**Reference:** `src/graph.h`, `src/graph.cpp` — `topological_sort()`

---

## Stage 3: Remove Back Edges — `remove_back_edges()`

**Purpose:** After the topological sort breaks cycles by forcing nodes through, the successor/predecessor lists still contain the original cycle edges. This stage removes them.

**How it works:**
1. Build a position map: `pos[activity] = index in topological order`
2. For each activity u, remove any successor v where `pos[v] <= pos[u]` (v appears before or at u in the order — a backward edge)
3. Rebuild all predecessor lists from the cleaned successor lists

**Why this is needed separately from parsing:** Parsing (Stage 1) removes edges based on the **time lag sign** — a property of the input data. This stage removes edges based on the **topological order** — a structural property discovered at runtime. Some edges pass the lag filter but still form cycles. Example from `PSP123.SCH`:

```
Activity 4 → Activity 6   lag [0]  ← passes lag filter (non-negative)
Activity 6 → Activity 4   lag [0]  ← passes lag filter (non-negative)
                                      But together: cycle 4→6→4
```

After topological sort places 4 before 6, `remove_back_edges` removes the `6→4` edge.

**Reference:** `src/graph.h`, `src/graph.cpp` — `remove_back_edges()`

---

## Stage 4: Generate Candidates — `generate_initial_solutions()`

**Purpose:** Produce multiple precedence-feasible activity orderings using different heuristics. Each ordering will be decoded by SSGS, and the best schedule is kept.

**Priority rules** (each produces one topological order biased by a different criterion):

| Rule | Priority value | Intuition |
|---|---|---|
| **LFT** (Latest Finish Time) | CPM backward-pass latest finish time | Activities with tighter deadlines should go first |
| **MTS** (Most Total Successors) | Count of all transitive successors | Activities blocking the most downstream work go first |
| **GRD** (Greatest Resource Demand) | Sum of resource demands across all types | Heavy activities go first while resources are plentiful |
| **SPT** (Shortest Processing Time) | Duration | Short activities go first to free up resources quickly |

**How it works:** Modified Kahn's algorithm using a min-heap. Among all activities with in-degree 0 (precedence-eligible), the one with the lowest priority value is dequeued first. This biases the topological order without violating precedence.

**Random permutations:** Additionally generates N random feasible orderings using Kahn's with random tie-breaking. These add diversity for the GA population.

**In main:** 4 rule-based + 20 random = 24 candidate orderings. Each is decoded via SSGS; the schedule with the lowest makespan is kept.

**Reference:** `src/priority.h`, `src/priority.cpp`

---

## Stage 5: SSGS — `ssgs()`

**Purpose:** Convert an activity list (topological order) into a concrete schedule with start times.

**Algorithm:** Serial Schedule Generation Scheme.

For each activity in list order:
1. **Precedence check:** Compute the earliest possible start time as the maximum finish time among all predecessors: `es = max(finish_time[pred] for all pred)`
2. **Resource check:** Starting from time `es`, scan forward to find the first time `t` where the activity's resource demands fit within remaining capacity for its **entire duration** `[t, t + dur)`
3. **Schedule it:** Set `start_time[act] = t`, `finish_time[act] = t + dur`
4. **Update resource profile:** Add the activity's resource demands to `usage[tau][k]` for every timestep `tau` in `[t, t + dur)`

**Resource profile:** Stored as a flat array `usage[t * K + k]` for cache efficiency. Size is `horizon * K` where `horizon` is the sum of all durations (worst-case upper bound).

**Early break optimisation:** When checking resource feasibility at timestep `tau`, if any single resource k exceeds capacity, immediately break and jump to `tau + 1` as the next candidate start time. No need to check remaining resources or remaining timesteps in that window.

**Output:** A `Schedule` struct containing start times for all activities and the makespan (`start_time[n+1]`).

**Reference:** `src/ssgs.h`, `src/ssgs.cpp`

---

## Stage 6: Genetic Algorithm — `run_ga()`

**Purpose:** Evolve a population of activity lists over many generations to minimise makespan. Uses SSGS as the decoder for each individual.

**Initialization:** Population of 100 individuals seeded from:
- 4 priority-rule solutions (LFT, MTS, GRD, SPT) from Stage 4
- 20 random feasible permutations from Stage 4
- Remaining slots filled with additional random permutations

**Selection:** Tournament selection (size 5). Pick 5 random individuals, return the one with the lowest makespan.

**Crossover (one-point):**
1. Pick a random cut point in parent 1's activity list
2. Copy the prefix (before cut) from parent 1
3. Fill remaining positions from parent 2, in parent 2's order, skipping activities already in the child
4. The result is always a valid permutation. Precedence feasibility is preserved because parent 2's relative order respects precedence.

**Mutation (two operators, chosen randomly):**
- **Adjacent swap:** Pick a random position i. If swapping `list[i]` and `list[i+1]` doesn't violate precedence (neither is a predecessor of the other), swap them. Tries up to 3 positions.
- **Shift:** Pick a random activity, find the latest predecessor position, and shift the activity to a random earlier valid position.

**Replacement:** Steady-state. If the offspring's makespan is better than the worst individual in the population, replace the worst. The best individual is always tracked (elitism).

**Forward-backward improvement (integrated):** Every 50,000 generations, the GA applies forward-backward improvement to the best individual. If the makespan improves, the improved schedule replaces the best individual and its activity list is updated. A final forward-backward pass is applied before returning.

**Termination:** 28-second wall-clock budget (2s margin before the 30s hard cutoff). The GA has an anytime property — a valid schedule exists from generation 0.

**Throughput:** ~8-17M generations in 28 seconds depending on instance size (J10-J30).

**Reference:** `src/ga.h`, `src/ga.cpp`

---

## Stage 7: Forward-Backward Improvement — `forward_backward_improve()`

**Purpose:** Improve a schedule by shifting activities to close gaps. Applied both during the GA (periodically) and as a final pass.

**Algorithm (double justification):**
1. **Backward pass:** Take the current schedule and schedule activities as **late** as possible. Process activities in reverse order of their forward start times (latest-scheduled first). For each activity, compute the latest finish time as the minimum start time among all successors, then scan backwards for resource feasibility.
2. **Extract new order:** Sort activities by their backward start times (ascending) to get a new precedence-feasible ordering.
3. **Forward pass:** Re-decode the new ordering with standard forward SSGS.
4. **Iterate:** If the forward pass produced a better makespan, repeat from step 1. Stop after 10 iterations or when no improvement is found.

**Why it works:** The backward pass pushes activities to the right (as late as possible), then the forward pass compresses them to the left (as early as possible). This "breathing" motion closes resource gaps that the original schedule left open, often shaving 1-3 time units off the makespan.

**Reference:** `src/improvement.h`, `src/improvement.cpp`

---

## Stage 8: Validate — `validate()`

**Purpose:** Independent correctness check. Verifies the schedule produced by SSGS satisfies both constraint types.

**Precedence check:** For every edge i→j: `start_time[j] >= start_time[i] + duration[i]`

**Resource check:** For every timestep t from 0 to makespan: sum resource demands of all active activities (those where `start_time[i] <= t < start_time[i] + duration[i]`) and verify the sum does not exceed capacity for any resource k.

Prints `FEASIBLE` or detailed violation messages to stderr.

**Reference:** `src/validator.h`, `src/validator.cpp`

---

## Stage 9: Output

Prints start times for activities 1 through n (one integer per line) to stdout. Dummy activities 0 and n+1 are not included in the output.

**Reference:** `src/main.cpp`

---

## All Implementation Steps Complete

The solver pipeline is fully implemented: Parse → Graph Cleanup → Priority Rules → GA with SSGS + Forward-Backward Improvement → Validate → Output.
