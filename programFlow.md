# Program Flow

How the current solver works, end to end. Source code lives in `src/`.

---

## Overview

```
Input File (.sm or .SCH)
        │
        ▼
   ┌─────────┐
   │  Parse  │  Detect format, extract problem data
   └────┬────┘
        │
        ▼
   ┌──────────────────────┐
   │ Generate Candidates  │  Priority rules + biased randomized seeds
   └────┬─────────────────┘
        │
        ▼
   ┌────────────┐
   │    SSGS    │  Decode each activity order into a feasible schedule
   └────┬───────┘
        │
        ▼
   ┌─────────────────────┐
   │  Genetic Algorithm  │  Evolve activity orders with hybrid crossover,
   │                     │  adaptive mutation, restart-on-stagnation,
   │                     │  and duplicate-aware diversity control
   └────┬────────────────┘
        │
        ▼
   ┌──────────────────────┐
   │ Forward-Backward Imp │  Tighten strong schedules with double justification
   └────┬─────────────────┘
        │
        ▼
   ┌────────────┐
   │  Validate  │  Check precedence + resource constraints
   └────┬───────┘
        │
        ▼
   Output start times (stdout)
```

The most important modeling decision is:

> The solver does not search directly over start times.
> It searches over precedence-feasible activity orders, then uses SSGS to decode an order into a concrete schedule.

---

## Stage 1: Parse — `parse()` → `parse_sm()` or `parse_sch()`

**Purpose:** Read the input file and populate the `Problem` struct.

**Format detection:**
- first line starts with `*` → standard PSPLIB `.sm`
- otherwise → local `.SCH`

**What gets extracted:**
- `n`: number of real activities
- `K`: number of renewable resource types
- `duration[i]`
- `resource[i][k]`
- `successors[i]`
- `predecessors[i]`
- `capacity[k]`
- `horizon`

**`.SCH` handling:**
- the checked-in local `J10`/`J20` sets use a compact `.SCH` format
- infeasible inputs where one activity alone exceeds a resource capacity are rejected immediately

**Note on cycles:**
- the current checked-in `sm_j10` and `sm_j20` files are already acyclic
- the solver does not perform any extra precedence-graph repair step

**Reference:** `src/parser.cpp`

---

## Stage 2: Generate Initial Activity Orders — `generate_initial_solutions()`

**Purpose:** Build several good precedence-feasible activity orders to seed the search.

The solver generates:
- one deterministic order for each priority rule:
  - `lft`
  - `mts`
  - `grd`
  - `spt`
- additional randomized but biased orders:
  - LFT-biased
  - MTS-biased
  - pure random topological orders

**Priority rules:**

| Rule | Idea |
|---|---|
| `lft` | activities with tighter latest-finish deadlines first |
| `mts` | activities with more downstream successors first |
| `grd` | more resource-demanding activities first |
| `spt` | shorter activities first |

**How the order construction works:**
- maintain the set of currently precedence-eligible activities
- pick one eligible activity according to the priority rule
- append it to the order
- update eligibility
- repeat

The randomized biased version samples from the top few eligible activities instead of always taking the single best one. This keeps diversity while preserving heuristic guidance.

**Reference:** `src/priority.cpp`

---

## Stage 3: Decode an Order with SSGS — `ssgs()`

**Purpose:** Convert one activity order into a valid schedule.

For each activity in order:
1. compute the earliest start allowed by predecessors
2. scan forward to find the first time where enough resources are available for the whole duration
3. place the activity there
4. update the resource usage profile

This is the Serial Schedule Generation Scheme.

**Key idea:**
- the order says which activity should be considered earlier
- SSGS decides the actual legal start time

**Reference:** `src/ssgs.cpp`

---

## Stage 4: Genetic Algorithm — `run_ga()`

**Purpose:** Improve the activity orders over time.

Population setup:
- start from the guided seeds produced in Stage 2
- fill the remaining population slots with random feasible orders
- decode everyone with SSGS
- use makespan as fitness

Each generation:
1. select two parents by tournament selection
2. create an offspring by crossover
3. mutate the offspring with adaptive probability
4. reject duplicates if needed
5. decode the offspring with SSGS
6. optionally polish it with forward-backward improvement
7. replace the current worst individual if the child is better

Additional behavior:
- restart-on-stagnation keeps elites and refreshes the rest
- duplicate-aware fingerprints help maintain diversity

**Reference:** `src/ga.cpp`

---

## Stage 5: Forward-Backward Improvement — `forward_backward_improve()`

**Purpose:** Tighten good schedules by removing slack.

The improvement loop:
1. schedule the current solution backward as late as possible
2. extract a new activity order from those backward start times
3. run forward SSGS again on that new order
4. keep the result only if makespan improves

This is a local improvement step, often called double justification.

It is applied:
- periodically to the current best solution during long stagnation
- selectively to promising offspring
- once again at the end

**Reference:** `src/improvement.cpp`

---

## Stage 6: Validate — `validate()`

**Purpose:** Independently check correctness.

The validator checks:
- every precedence relation
- resource usage at every timestep

If both pass, the schedule is feasible.

**Reference:** `src/validator.cpp`

---

## Stage 7: Output

**Purpose:** Improve a schedule by shifting activities to close gaps. In the current implementation this is used in three places:
- periodically on the incumbent best solution during long stagnation
- selectively on newly created offspring that already look competitive
- as a final pass after the GA loop
The solver prints start times for activities `1..n`, one integer per line.

Dummy source `0` and dummy sink `n+1` are not printed.

**Reference:** `src/main.cpp`

---

## Mode Summary

```text
--rule <r>:  Parse -> one priority/rand order -> SSGS -> Validate -> Output

baseline:    Parse -> random order -> SSGS -> Validate -> Output

priority:    Parse -> 24 guided/random orders -> SSGS each -> best -> Validate -> Output

ga:          Parse -> random seeds -> GA (no forward-backward improvement) -> Validate -> Output

full:        Parse -> guided seeds -> GA + restart + hybrid crossover
             + adaptive mutation + selective forward-backward improvement
             -> Validate -> Output
```

Notes on the current `full` implementation:
- forward-backward improvement is used periodically on the incumbent best solution during stagnation
- forward-backward improvement is also used selectively to polish newly created offspring that already look competitive
- after the GA loop ends, the solver runs one final forward-backward improvement pass on the best solution
