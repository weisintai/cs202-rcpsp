# Program Flow

How `solver.cpp` works, end to end.

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
   ┌────────┐
   │  SSGS  │  Decode activity order into a feasible schedule
   └────┬───┘
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

**Reference:** `solver.cpp` lines 36-233

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

**Reference:** `solver.cpp` lines 235-286

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

**Reference:** `solver.cpp` lines 288-312

---

## Stage 4: SSGS — `ssgs()`

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

**Reference:** `solver.cpp` lines 314-387

---

## Stage 5: Validate — `validate()`

**Purpose:** Independent correctness check. Verifies the schedule produced by SSGS satisfies both constraint types.

**Precedence check:** For every edge i→j: `start_time[j] >= start_time[i] + duration[i]`

**Resource check:** For every timestep t from 0 to makespan: sum resource demands of all active activities (those where `start_time[i] <= t < start_time[i] + duration[i]`) and verify the sum does not exceed capacity for any resource k.

Prints `FEASIBLE` or detailed violation messages to stderr.

**Reference:** `solver.cpp` lines 389-430

---

## Stage 6: Output

Prints start times for activities 1 through n (one integer per line) to stdout. Dummy activities 0 and n+1 are not included in the output.

**Reference:** `solver.cpp` lines 478-481

---

## What's Not Yet Implemented

- **Step 3:** Priority-rule initial solutions (LFT, MTS, GRD, SPT) to seed GA population
- **Step 4:** Genetic Algorithm (selection, crossover, mutation)
- **Step 5:** Forward-backward improvement (double justification)
