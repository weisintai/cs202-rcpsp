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
   │ Generate Candidates  │  Priority rules + biased randomized seeds
   └────┬─────────────────┘
        │
        ▼
   ┌─────────────────────┐
   │  Genetic Algorithm  │  Evolve population with SSGS decoder, hybrid crossover,
   │                     │  adaptive mutation, restart-on-stagnation, selective FBI
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
- Starts with integers → `.SCH` format → `parse_sch()`

**What gets extracted:**
- `n` — number of real activities (excluding dummy source 0 and dummy sink n+1)
- `K` — number of renewable resource types
- `duration[i]` — processing time for each activity
- `resource[i][k]` — demand of resource k by activity i
- `successors[i]` — list of activities that must come after i
- `predecessors[i]` — list of activities that must come before i
- `capacity[k]` — maximum available units of resource k at any timestep

**SCH-specific handling:** This repo now contains two `.SCH` variants:
- an older lag-bearing variant where successors may be followed by bracketed lags (e.g. `[0]`, `[-3]`)
- a newer compact RCPSP-style variant used in the updated local `J10` and `J20` sets

For the lag-bearing variant, the parser keeps only **non-negative** lag edges. Negative lags represent RCPSP/max constraints and are filtered out so the solver can work on a standard RCPSP precedence graph.

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

**Example:**

```
Before topological sort:

    0 ──→ 1 ──→ 3 ──→ 5
    │           ↑     │
    └──→ 2 ──→ 4 ←───┘    ← back edge 5→4 forms cycle 4→3→5→4
          ↑     │
          └─────┘          ← back edge 4→2 forms cycle 2→4→2

Topological sort forces an order:  [0, 1, 2, 4, 3, 5]

remove_back_edges() checks each successor:
  - edge 5→4:  pos[4]=3, pos[5]=5  →  pos[4] < pos[5]  →  KEEP
    (wait — 5→4 means successor is 4, pos[4]=3 ≤ pos[5]=5?  No: pos[succ] ≤ pos[src] means backward)
    Actually: pos[4]=3 < pos[5]=5  →  pos[succ] < pos[src]  →  backward  →  REMOVE

After cleanup:  clean DAG, no cycles
```

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

```
Example: LFT-biased sort on a 6-activity graph

Precedence:  0 → {1,2},  1 → {3},  2 → {3,4},  3 → {5},  4 → {5},  5 → {6}
LFT values:  0:2  1:8  2:6  3:10  4:9  5:12  6:12

Step 1:  eligible = {0}           → pick 0 (only choice)
Step 2:  eligible = {1, 2}        → pick 2 (LFT=6 < LFT=8)
Step 3:  eligible = {1, 4}        → pick 1 (LFT=8 < LFT=9)
Step 4:  eligible = {3, 4}        → pick 4 (LFT=9 < LFT=10)
Step 5:  eligible = {3}           → pick 3
Step 6:  eligible = {5}           → pick 5
Step 7:  eligible = {6}           → pick 6

Result: [0, 2, 1, 4, 3, 5, 6]  (tighter-deadline activities scheduled first)
```

**Randomized biased sort:** A variant that samples uniformly from the top N eligible activities (candidate pool size 3) instead of always taking the single best. This produces diverse orderings that are still guided by the priority heuristic.

```
Same example with candidate_pool = 3:

Step 2:  eligible sorted by LFT = {2(6), 1(8)}
         pool = top 2 (pool capped at eligible size)
         randomly pick from {2, 1}  →  could pick either

Step 3:  eligible sorted = {1(8), 4(9)}
         randomly pick from {1, 4}  →  could pick either

Each run produces a different ordering, but still biased toward low-LFT activities.
```

**Biased seeding:** Of the 20 additional seeds beyond the 4 deterministic rules:
- 10 use randomized LFT-biased sort (50%)
- 6 use randomized MTS-biased sort (33%)
- 4 use pure random sort (17%)

This allocation is motivated by experiment results showing LFT and MTS are the strongest priority rules across PSPLIB benchmarks.

**In main:** `generate_initial_solutions(prob, num_random, rng)` is called with `num_random = 20`. It returns:
- 4 deterministic rule-based seeds (one per rule: LFT, MTS, GRD, SPT)
- plus `num_random` guided/random seeds, split as:
  - `num_random / 2` = 10 randomized LFT-biased
  - `num_random / 3` = 6 randomized MTS-biased
  - remainder = 4 pure random
- total: 24 seeds

The priority values for LFT and MTS are computed once via `compute_priority_values()` and reused across all biased seeds.

These 24 seeds are used to initialize the GA population in `full` mode (remaining 76 slots are filled with `random_sort()` permutations inside the GA).

```
GA Population (100 individuals)
┌─────────────────────────────────────────────────────────────────────────────┐
│ LFT│ MTS│ GRD│ SPT│  10x LFT-biased   │ 6x MTS-biased  │ 4x  │              │
│ det│ det│ det│ det│  randomized       │ randomized     │rand │  76x random  │
│  1 │  2 │  3 │  4 │  5 ──────── 14    │ 15 ────── 20   │21─24│  25 ─── 100  │
├────┴────┴────┴────┼───────────────────┴────────────────┴─────┼──────────────┤
│  4 deterministic  │       20 guided/random seeds             │  GA random   │
│  priority rules   │    (from generate_initial_solutions)     │    fill      │
└───────────────────┴──────────────────────────────────────────┴──────────────┘
                    ◄─── generate_initial_solutions(p, 20) ───►◄── run_ga ──►
```

In `priority` mode, the same 24 seeds are each decoded with SSGS and the best schedule is kept (no GA).

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

**Output:** A `Schedule` struct containing start times for all activities and the makespan.

**Example:** Scheduling 3 activities with 1 resource (capacity = 5):

```
Activity list: [0, A, B, C, 5]     durations: A=3, B=2, C=2
Resource demands:  A=3, B=3, C=2    capacity = 5
Precedence: 0→A, 0→B, A→C, B→C

Schedule A:  es=0 (pred 0 finishes at 0), resources fit → start at t=0
  time:  0  1  2  3  4  5  6
  usage: 3  3  3  .  .  .  .

Schedule B:  es=0, but check resources:
  t=0: usage[0]+3 = 6 > 5  ✗  → try t=1
  t=1: usage[1]+3 = 6 > 5  ✗  → try t=2
  t=2: usage[2]+3 = 6 > 5  ✗  → try t=3
  t=3: usage[3]+3 = 3 ≤ 5  ✓  check t=4: 0+3 = 3 ≤ 5  ✓  → start at t=3
  time:  0  1  2  3  4  5  6
  usage: 3  3  3  3  3  .  .

Schedule C:  es = max(finish[A], finish[B]) = max(3, 5) = 5  → start at t=5
  time:  0  1  2  3  4  5  6
  usage: 3  3  3  3  3  2  2

  Resource profile (capacity=5):
  5 │ ■ ■ ■ ■ ■ . .
  4 │ ■ ■ ■ ■ ■ . .
  3 │ A A A B B . .
  2 │ A A A B B C C
  1 │ A A A B B C C
  0 ┼───────────────→ time
    0 1 2 3 4 5 6

Makespan = max(finish[C]) = 7
```

**Makespan definition:** The solver now uses the **true project finish time**, i.e. the maximum finish time over all activities, rather than assuming the dummy sink always captures every terminal job. On clean PSPLIB `.sm` instances these are equivalent, but the explicit finish-time definition is safer for the local `.SCH` sets.

**Reference:** `src/ssgs.h`, `src/ssgs.cpp`

---

## Stage 6: Genetic Algorithm — `run_ga()`

**Purpose:** Evolve a population of activity lists over many generations to minimise makespan. Uses SSGS as the decoder for each individual.

**Parameters** (configurable via `GAConfig` / CLI flags):

| Parameter | Default | CLI flag |
|---|---|---|
| Population size | 100 | — |
| Tournament size | 5 | — |
| Crossover rate | 0.9 | — |
| Mutation rate | 0.3 | `--mutation-rate` |
| Max mutation rate under stagnation | 0.6 | — |
| Time limit | 28s | `--time` |
| Schedule limit | disabled | `--schedules` |
| Restart stagnation threshold | 100,000 generations | `--restart-stagnation` |
| Restart elite count | 10 | `--restart-elites` |

**Initialization:** Population of 100 individuals. Seeds are added with duplicate-aware insertion (64-bit FNV-1a fingerprints, reject collisions):
1. Add the 24 Stage-4 seeds (4 deterministic + 20 guided/randomized), skipping any that fingerprint-collide
2. Fill remaining slots with `random_sort()` permutations, again skipping duplicates

All 100 individuals are decoded with SSGS to compute initial fitness. Best and worst indices are tracked.

**Main loop** (one generation = one offspring attempt):

```
                    ┌────────────────────────-─┐
                    │   Budget exhausted?      │──── yes ──→ Final FBI → Return best
                    └────────┬────────────────-┘
                             │ no
                             ▼
                    ┌─────────────────────────┐
                    │ Stagnation ≥ 100k gens? │──── yes ──→ Restart population
                    └────────┬────────────────┘            (keep elites, refresh rest)
                             │ no
                             ▼
                    ┌─────────────────────────┐
                    │ Stagnation ≥ 50k gens?  │──── yes ──→ Apply FBI to best
                    │  (use_improvement=true) │            (reset counter if improved)
                    └────────┬────────────────┘
                             │
                             ▼
               ┌──────────────────────────────┐
               │  Tournament select 2 parents │
               └──────────────┬───────────────┘
                              ▼
               ┌──────────────────────────────┐
               │  Hybrid crossover (rate 0.9) │
               │  one-point or merge          │
               └──────────────┬───────────────┘
                              ▼
               ┌──────────────────────────────┐
               │  Adaptive mutation           │
               │  swap / long-swap / insert   │
               └──────────────┬───────────────┘
                              ▼
               ┌──────────────────────────────┐
               │  Duplicate in population?    │──── yes ──→ Perturb up to 3x
               └──────────────┬───────────────┘            (discard if still dup)
                              │ unique
                              ▼
               ┌──────────────────────────────┐
               │  Decode with SSGS            │
               └──────────────┬───────────────┘
                              ▼
               ┌──────────────────────────────┐
               │  Promising child?            │──── yes ──→ Selective FBI polish
               └──────────────┬───────────────┘
                              │ no / done
                              ▼
               ┌──────────────────────────────┐
               │  Better than worst?          │──── no ──→ next generation
               └──────────────┬───────────────┘
                              │ yes
                              ▼
               ┌──────────────────────────────┐
               │  Replace worst, update       │
               │  best/worst indices          │
               └──────────────┬───────────────┘
                              │
                              └──→ next generation
```

Each generation proceeds as follows:

1. **Budget check:** Exit if wall-clock time or schedule-generation limit is exhausted.

2. **Restart check:** If `generations - last_improve_gen >= restart_stagnation_generations`, trigger a population restart (see below). Reset `last_improve_gen` to the current generation.

3. **Periodic forward-backward improvement:** If `use_improvement` is enabled and `generations - last_improve_gen >= 50,000`, apply forward-backward improvement to the current best individual. If the makespan improves, update the best individual's schedule and activity list (extracted via `order_from_schedule`), re-find the worst individual, and reset `last_improve_gen`. **Note:** there is no guard preventing this from firing every generation once 50k stagnation is reached — if FBI fails to improve, it will be called again on the next generation until either it succeeds or restart triggers at 100k.

4. **Selection:** Two parents chosen by tournament selection (size 5). Parent 2 is re-drawn if it equals parent 1.

5. **Crossover (hybrid, rate 0.9):**
   - Early in the search, the GA often uses the original one-point order-preserving crossover:
     - pick a random cut point
     - copy the prefix from parent 1
     - fill remaining positions from parent 2 in parent 2's order
   - As stagnation grows, the GA increasingly uses a **precedence-aware merge crossover**:
     - maintain the currently precedence-eligible activities
     - rank them by how early both parents place them
     - choose from the top few eligible activities and extend the child in a Kahn-style feasible build
   - If crossover does not fire, the offspring is a copy of parent 1.

   The purpose of the hybrid is to keep broad recombination early and more structure-preserving recombination later.

6. **Mutation (adaptive):** One random neighborhood move, chosen uniformly from three operators:
   - **Adjacent swap:** pick a random adjacent pair, swap if precedence still holds (up to 3 attempts)
   - **Non-adjacent feasible swap:** pick two non-adjacent positions (skipping dummy source/sink), swap if precedence still holds (up to 5 attempts)
   - **Bidirectional insertion:** pick an activity (skipping dummies), compute its valid insertion interval via `insertion_bounds()`, move it to a random valid target position (up to 5 attempts)
   - The probability of applying mutation starts at the base rate (`0.3`) and ramps up toward `0.6` as the search approaches the restart threshold with no improvement

   ```
   Original:           [0, 2, 1, 4, 3, 5, 6]

   Adjacent swap (i=2):
     swap pos 2 & 3:   [0, 2, 4, 1, 3, 5, 6]   ← if precedence OK

   Non-adjacent swap (i=1, j=4):
     swap pos 1 & 4:   [0, 3, 1, 4, 2, 5, 6]   ← if precedence OK

   Insertion (from=4, to=2):
     remove pos 4:     [0, 2, 1, 4, _, 5, 6]
     insert at pos 2:  [0, 2, 3, 1, 4, 5, 6]   ← within valid bounds [lo, hi]
   ```

7. **Duplicate rejection:** Compute the offspring's fingerprint. If it already exists in the population, apply up to 3 extra `perturb_once` perturbation attempts to escape the duplicate. If all 3 fail, discard the offspring and advance to the next generation.

8. **Evaluation:** Decode the offspring with SSGS (counted toward schedule budget).

9. **Selective offspring polishing:** If the decoded offspring already beats its better parent and lies close to the incumbent, apply forward-backward improvement to that offspring. Keep the polished version only if it improves the makespan and does not create a population duplicate.

10. **Replacement (steady-state):** If the offspring's makespan is strictly better than the worst individual, replace the worst. Update the population fingerprint set. If the offspring is also better than the current best, update `best_idx` and reset `last_improve_gen`. Re-scan to find the new worst individual.

**Restart-on-stagnation** (`restart_population`):
When triggered, the restart procedure:
1. Sort the current population by fitness (ascending)
2. Keep the top `restart_elite_count` (default 10) unique individuals
3. Generate 24 fresh guided seeds via `generate_initial_solutions()` (4 deterministic + 20 biased/random)
4. Fill remaining slots with `random_sort()` permutations
5. All new members are deduplicated and decoded with SSGS
6. Rebuild best/worst indices and the population fingerprint set

```
Before restart (stagnated population):
┌─────────────────────────────────────────────────────────────-┐
│ converged / similar individuals .... many near-duplicates    │
│  best ◄──────── mediocre ──────────────────────► worst       │
└──────────────────────────────────────────────────────────────┘

After restart:
┌────────────┬────────────────────┬─────────────────────────────┐
│ 10 elites  │ 24 fresh guided    │ 66 fresh random             │
│ (kept)     │ seeds              │ permutations                │
├────────────┼────────────────────┼─────────────────────────────┤
│ preserved  │ LFT/MTS-biased     │ new diversity               │
│ best known │ + deterministic    │                             │
└────────────┴────────────────────┴─────────────────────────────┘
```

**Final pass:** After the main loop exits, if `use_improvement` is enabled and the schedule budget is not exhausted, apply one final forward-backward improvement to the best individual.

**Termination:** The GA can stop on either:
- wall-clock time (`--time`)
- schedule-generation budget (`--schedules`)

The schedule-budget mode counts `SSGS` decodes (via `counted_ssgs()`) and is mainly used for internal A/B testing.

**Performance notes:** The current implementation precomputes a safe scheduling horizon once during parsing, moves single-activity infeasibility checks out of the `SSGS` hot loop, and uses compact 64-bit FNV-1a fingerprints instead of strings for duplicate detection. These changes improve throughput without changing solver behavior.

**Throughput:** depends on instance size and stopping rule. Under wall-clock mode the solver is anytime: a valid schedule exists from generation 0 and improves as search continues.

**Reference:** `src/ga.h`, `src/ga.cpp`

---

## Stage 7: Forward-Backward Improvement — `forward_backward_improve()`

**Purpose:** Improve a schedule by shifting activities to close gaps. Applied both during the GA (periodically after 50k stagnation) and as a final pass after the GA loop.

**Algorithm (double justification):**
1. **Backward pass** (`backward_ssgs`): Take the current schedule and schedule activities as **late** as possible. Process activities in reverse order of their forward start times (latest-scheduled first). For each activity, compute the latest finish time as the minimum start time among all successors, then scan backwards for resource feasibility. If the scan fails to find a feasible slot, the activity is clamped to time 0 (the intermediate backward schedule is a heuristic reordering device, not a final output).
2. **Extract new order:** Sort activities by their backward start times (ascending) to get a new precedence-feasible ordering.
3. **Forward pass:** Re-decode the new ordering with standard forward SSGS (counted toward the schedule budget if a counter is provided).
4. **Iterate:** If the forward pass produced a better makespan, repeat from step 1. Stop after 10 iterations or when no improvement is found.

**Schedule budget integration:** The function accepts an optional `schedule_counter` pointer and `schedule_limit`. Each forward SSGS decode increments the counter. If the schedule budget is exhausted, the improvement loop exits early. Backward passes are not counted because they do not produce a valid forward schedule.

**Why it works:** The backward pass pushes activities to the right (as late as possible), then the forward pass compresses them to the left (as early as possible). This "breathing" motion closes resource gaps that the original schedule left open, often shaving 1-3 time units off the makespan.

```
Forward schedule (original):          Makespan = 10
  A: ████░░░░░░      (t=0..3)
  B: ░░░░████░░      (t=4..7)       ← gap at t=3 before B
  C: ░░░░░░░░██      (t=8..9)
     0123456789

Backward pass (schedule as late as possible):
  C: ░░░░░░░░██      (t=8..9)       ← stays
  B: ░░░░░░████      (t=6..9)       ← pushed right
  A: ░░░░░████░      (t=5..7)       ← pushed right

Extract order from backward start times: [C, B, A] → sorted ascending: [A, B, C]

Forward pass (re-decode with new order):    Makespan = 9
  A: ████░░░░░        (t=0..3)
  B: ░░░████░░        (t=3..6)      ← gap closed, B starts right after A
  C: ░░░░░░███        (t=6..8)
     012345678

Improvement: 10 → 9  (saved 1 time unit)
```

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

The current solver pipeline is: Parse → Graph Cleanup → Guided Seed Generation (LFT/MTS-biased + random) → GA with SSGS decoder + Hybrid Crossover + Adaptive Mutation + Restart-on-Stagnation + Duplicate-Aware Diversity Control + Periodic/Selective Forward-Backward Improvement → Final FBI Pass → Validate → Output.

```
CLI mode pipeline comparison:

--rule <r>:   Parse → Graph → 1 priority sort → SSGS → Validate → Output

--mode baseline: Parse → Graph → 1 random sort → SSGS → Validate → Output

--mode priority: Parse → Graph → 24 guided seeds → SSGS each → best → Validate → Output

--mode ga:    Parse → Graph → 20 random seeds → GA (no FBI) → Validate → Output

--mode full:  Parse → Graph → 24 guided seeds → GA + hybrid crossover + adaptive mutation
              + FBI + restart → Validate → Output
              (default)
```
