# RCPSP Glossary

This glossary is written for this project's RCPSP solver. It focuses on the terms that appear in the report and in `src/`.

## Core Problem Terms

| Term | Meaning | Simple Example |
|---|---|---|
| RCPSP | Resource-Constrained Project Scheduling Problem. The goal is to schedule activities while respecting dependencies and limited resources. | 10 tasks share only 5 workers total. |
| Activity / Job / Task | One unit of work to schedule. | "Paint wall" is one activity. |
| Duration | How long an activity runs. | If duration is `4`, starting at time `3` means finishing at `7`. |
| Resource | Something limited that activities consume while running. | Workers, machines, cranes. |
| Renewable Resource | A resource whose capacity is available again at the next time step. | 5 workers available every day. |
| Resource Capacity | Maximum amount of a resource available at one time. | Worker capacity = `5`. |
| Resource Demand / Requirement | How much of each resource an activity needs. | Activity B needs 3 workers. |
| Precedence Constraint | A rule saying one activity must happen before another. | Foundation before walls. |
| Predecessor | An activity that must finish before another can start. | If A must happen before B, A is a predecessor of B. |
| Successor | An activity that depends on another. | If A must happen before B, B is a successor of A. |
| Start Time | When an activity begins. | `start[A] = 5` |
| Finish Time | When an activity ends. | If `start[A] = 5` and `duration[A] = 3`, `finish[A] = 8`. |
| Schedule | A full assignment of start times to all activities. | Every activity has a chosen start time. |
| Feasible Schedule | A schedule that obeys precedence and resource constraints. | No task starts too early and worker usage never exceeds capacity. |
| Makespan | The total project completion time. This is the objective we minimize. | If the last task finishes at time `17`, makespan = `17`. |
| Horizon | A safe upper bound on time used by the solver. In this project it is the sum of durations. | If durations sum to 42, the solver can allocate arrays up to time 42. |

## Graph Terms

| Term | Meaning | Simple Example |
|---|---|---|
| Precedence Graph | A directed graph showing dependency edges between activities. | A -> B means B depends on A. |
| DAG | Directed acyclic graph. A precedence graph should ideally have no cycles. | A -> B -> C is a DAG. |
| Cycle | A loop in the dependency graph. | A -> B -> C -> A |
| Back Edge | An edge that points backward relative to a chosen topological order. The code removes these when cleaning cyclic `.SCH` data. | If order says A comes before B, but there is an edge B -> A, that is a back edge. |
| Dummy Source / Super-Source | Artificial activity `0` with duration 0 that points to initial tasks. | Start node for the whole project. |
| Dummy Sink / Super-Sink | Artificial activity `n + 1` with duration 0 that collects terminal tasks. | End node for the whole project. |
| In-Degree | Number of incoming edges to a node. | If B has predecessors A and C, in-degree of B is `2`. |
| Out-Degree | Number of outgoing edges from a node. | If A points to B, C, and D, out-degree of A is `3`. |
| Topological Order / Topological Sort | An ordering where each predecessor appears before its successors. | If A -> B and A -> C, `[A, B, C]` is valid. |
| Eligible Activity | An activity whose predecessors are already satisfied. | If all parents of D are done, D becomes eligible. |

## Timing and Critical-Path Terms

| Term | Meaning | Simple Example |
|---|---|---|
| EST / Earliest Start Time | Earliest possible start from precedence alone. | If predecessors finish by time 9, EST = `9`. |
| EFT / Earliest Finish Time | Earliest start plus duration. | If EST = `9` and duration = `3`, EFT = `12`. |
| LFT / Latest Finish Time | Latest time an activity can finish without delaying the precedence-only project finish. Used as a priority rule here. | A tighter activity may have LFT `10` while another has LFT `14`. |
| Slack / Float | How much an activity can move without worsening the project finish. | If an activity can start at 5 or 7 with no effect, slack is `2`. |
| Critical Path | A longest dependency chain in the project. Delaying it delays the whole project. | A -> D -> F determines the finish time. |
| CPM | Critical Path Method. Used conceptually to compute values like LFT. | Backward pass on the precedence graph. |

## Representation Terms

| Term | Meaning | Simple Example |
|---|---|---|
| Activity List | The main representation used by the GA: a precedence-feasible ordering of activities. It is not yet a schedule. | `[0, 2, 1, 4, 3, 5, n+1]` |
| Order / Permutation | Another way to describe the activity list. | A reordered list of activities. |
| Precedence-Feasible Activity List | An activity order where no activity appears before any predecessor. | If A -> B, a valid list cannot place B before A. |

## Decoder and Scheduling Terms

| Term | Meaning | Simple Example |
|---|---|---|
| Decoder | The procedure that turns an activity list into a concrete schedule. Here that decoder is SSGS. | Take `[0, 2, 1, 4, 3]` and compute actual start times. |
| SSGS | Serial Schedule Generation Scheme. It scans activities in list order and places each at the earliest feasible time. | If B is next and cannot fit at time 6, try 7, then 8, and so on. |
| Resource Usage Profile | The time-indexed table of how much resource is currently used. | At time 4, workers used = 3 out of 5. |
| Earliest Feasible Start | The first time satisfying both precedence and resources. | EST may be 6, but earliest feasible start may be 8 because workers are busy. |
| Backward SSGS | A reverse-style scheduling pass that pushes activities as late as possible while staying feasible. Used in improvement. | Start from the right side of the schedule instead of the left. |

## Heuristic Seeding Terms

| Term | Meaning | Simple Example |
|---|---|---|
| Priority Rule | A heuristic for deciding which eligible activity should be considered earlier. | Choose tighter or more important jobs first. |
| LFT Rule | Prefer activities with smaller latest finish time. | Activity with LFT 8 is chosen before one with LFT 12. |
| MTS / Most Total Successors | Prefer activities that unlock the most downstream work. | If A eventually enables 8 jobs and B enables 2, A gets higher priority. |
| GRD / Greatest Resource Demand | Prefer more resource-hungry activities earlier. | Activity using 5 units is prioritized over one using 2. |
| SPT / Shortest Processing Time | Prefer shorter activities earlier. | Duration 2 before duration 6. |
| Random Rule | No heuristic bias, just random feasible tie-breaking. | Pick any eligible activity at random. |
| Biased Topological Sort | A topological sort where eligible activities are chosen using a priority rule. | Among ready tasks, pick the one with best LFT score. |
| Randomized Biased Topological Sort | Sort eligible activities by priority, then randomly pick from the top few instead of always taking the single best. | Pick from the top 3 ranked eligible tasks. |
| Seed / Initial Solution | A starting activity list before GA search begins. | One LFT-based topological order. |
| Seeding / Initial Population Construction | The process of generating those starting activity lists. | Build 4 rule-based seeds plus guided/random variants. |

## Genetic Algorithm Terms

| Term | Meaning | Simple Example |
|---|---|---|
| GA / Genetic Algorithm | The metaheuristic that evolves activity lists over time. | Repeatedly select, combine, mutate, and keep better lists. |
| Population | The current set of candidate activity lists. | 100 individuals in memory. |
| Individual | One candidate in the population. | One activity list. |
| Fitness | The score used by the GA. In this project it is the decoded makespan, so lower is better. | Makespan 42 beats makespan 45. |
| Tournament Selection | Sample a few individuals and keep the best as a parent. | Pick 5 random individuals and choose the best of them. |
| Parent | An individual used to create an offspring. | One candidate chosen for crossover. |
| Offspring / Child | A new activity list produced by crossover and or mutation. | New list built from two parents. |
| Crossover | Combine structure from two parents. In this project, take a prefix from one parent and fill the rest using the other parent's order. | Keep early decisions from parent 1, later relative order from parent 2. |
| Mutation | A small random modification to one activity list. | Swap two jobs or move one job. |
| Adjacent Swap | Swap neighboring activities if precedence still holds. | `[A, B, C]` -> `[B, A, C]` if legal. |
| Long Swap / Non-Adjacent Swap | Swap two activities that are farther apart. | Swap positions of A and D. |
| Insertion Move | Remove one activity and insert it elsewhere within legal bounds. | Move C from position 6 to position 3. |
| Neighborhood | The set of small changes allowed by mutation. | Adjacent swap, long swap, insertion. |
| Steady-State Replacement | Replace bad individuals gradually instead of replacing the whole population at once. | Only the worst individual gets replaced by a better child. |
| Elitism / Elite Set | Keep the best individuals safe during replacement or restart. | Preserve top 10 candidates during a restart. |
| Stagnation | A long period with no improvement. | Best makespan stays unchanged for many generations. |
| Restart / Restart-on-Stagnation | Keep a few elites and rebuild the rest of the population to escape a bad search region. | Refresh 90 out of 100 individuals. |
| Diversity Control | Methods to keep the population from becoming too similar. | Reject duplicates and restart if needed. |
| Duplicate-Aware Control | Detect exact duplicate activity lists and avoid wasting evaluations on them. | Skip a child if it is identical to an existing individual. |
| Fingerprint / Hash | A compact identifier for an activity list, used to detect duplicates. | Two identical lists should have the same fingerprint. |

## Improvement Terms

| Term | Meaning | Simple Example |
|---|---|---|
| Forward-Backward Improvement | A post-processing step that tries to tighten a good schedule. | Push jobs right, then rebuild left. |
| Double Justification | Another name for forward-backward improvement. | Squeeze from the right, then reschedule from the left. |
| Justification | Pushing activities earlier or later to reduce unnecessary slack while staying feasible. | Remove idle gaps without breaking constraints. |

## Input and File Format Terms

| Term | Meaning | Simple Example |
|---|---|---|
| `.sm` | Standard PSPLIB file format. | Used for J30, J60, J90, J120. |
| `.SCH` | Local or project file format used in this repo. The code supports two variants. | Used for J10 and J20 local sets. |
| Lag | A time offset attached to a precedence relation in the old lag-bearing `.SCH` format. | `7 -> 10 [0]` |
| Negative Lag Filtering | In this codebase, edges with negative lag in old `.SCH` files are dropped before building the precedence graph. | `7 -> 1 [-1]` is skipped. |
| Lag-Bearing `.SCH` Format | Older `.SCH` rows where successor lists are followed by bracketed lags like `[0]` or `[-1]`. | `7 1 2 1 10 [-1] [0]` |
| Compact `.SCH` Format | Simpler `.SCH` format used in local J10 and J20 data without lag annotations. | `7 2 1 10` |
| Infeasible Input | An instance that cannot be scheduled as given. | Activity needs 7 workers but capacity is only 5. |

## Benchmark and Evaluation Terms

| Term | Meaning | Simple Example |
|---|---|---|
| PSPLIB | Standard benchmark library for project scheduling problems. | The source of J30, J60, J90, J120 instances. |
| J10 / J20 / J30 / J60 / J90 / J120 | Dataset families named roughly by project size. | J30 has about 30 real activities. |
| Best-Known Value | Best reference makespan known for a benchmark instance. | Reference says best known makespan is 43. |
| Gap to Best-Known | How much worse the solver is than the reference. | Best known 100, solver 103, gap = 3 percent. |
| Quality vs Best-Known | Normalized quality score where 100 percent means matching the reference. | Score 100 percent means exact match. |
| Wall-Clock Budget / Time Budget | Real elapsed time limit for the solver. | 3 seconds per instance. |
| Schedule Budget | Limit based on number of schedule generations instead of elapsed seconds. Used for cleaner internal comparisons. | Stop after 5000 decodes. |
| Anytime Algorithm | An algorithm that can return a valid answer quickly and often improves if given more time. | A 1-second answer is valid, and a 10-second answer may be better. |

## Project-Specific Mode Terms

| Term | Meaning | Simple Example |
|---|---|---|
| `baseline` mode | One random feasible order plus SSGS. | Minimal solver. |
| `priority` mode | Several heuristic orders plus SSGS, no GA. | Try multiple rule-based seeds and keep the best. |
| `ga` mode | GA search starting from random orders, no final improvement pass. | Search without heuristic seeding and without cleanup. |
| `full` mode | Heuristic seeds plus GA plus restart and diversity control plus forward-backward improvement. | Full final pipeline. |

## Shortest Summary

If you want the most important four terms only:

- `activity list`: the order the solver searches over
- `SSGS`: the decoder that turns an order into a feasible schedule
- `GA`: the search procedure that improves activity lists
- `makespan`: the final project completion time we want to minimize
