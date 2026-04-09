# RCPSP Solver Report for Dummies

This is the quick intuition-first version of [`reportDraft.md`](./reportDraft.md), written for teammates who have already looked at the code and want the "what is this algorithm really doing?" explanation without reading the full report first.

The short version:

- We do **not** search directly for start times.
- We search for a good **activity order**.
- We use **SSGS** to turn that order into an actual valid schedule.
- We use **priority rules** to get decent starting orders.
- We use a **genetic algorithm** with hybrid crossover and adaptive mutation to keep improving those orders under a time limit.
- We use **forward-backward improvement** both during search and at the end to squeeze out leftover slack.

## 1. The problem in normal language

Each activity has:

- a duration
- predecessors that must finish first
- resource demands like workers or machines

The schedule is good if:

- no activity starts before its predecessors finish
- resource capacity is never exceeded
- the whole project finishes as early as possible

The annoying part is that these constraints interact. A task may be ready by precedence, but still blocked because the resources it needs are busy.

That is why the solver separates the problem into two layers:

1. decide a promising **order** in which activities should be considered
2. let a decoder figure out the earliest legal start time for each activity

That design choice is the whole solver.

## 2. The single most important mental model

An individual in the GA is **not a schedule**.

It is an **activity list**:

```text
[0, 4, 2, 7, 1, 3, 5, 6, n+1]
```

This list means:

"When building a schedule, try to place activity 4 before 2, 2 before 7, 7 before 1, and so on."

It does **not** mean:

- activity 4 starts at time 0
- activity 2 starts at time 1
- the index in the list is the start time

The actual start times only appear after we run `ssgs()`.

If you remember one thing, remember this:

> The GA searches over orderings, and SSGS translates an ordering into a feasible schedule.

## 3. End-to-end flow in this codebase

```text
input file
  -> parse instance
  -> build several good initial activity orders
  -> decode each order with SSGS
  -> evolve orders with GA using hybrid crossover and adaptive mutation
  -> selectively tighten strong candidates with forward-backward improvement
  -> validate final schedule
  -> print start times
```

In files:

| File | What it does |
|---|---|
| `src/parser.cpp` | Reads `.sm` and `.SCH` into `Problem` |
| `src/priority.cpp` | Creates heuristic activity orders |
| `src/ssgs.cpp` | Turns an activity order into a real schedule |
| `src/ga.cpp` | Runs the search loop over activity orders using hybrid crossover, adaptive mutation, duplicate control, and restarts |
| `src/improvement.cpp` | Applies double justification to tighten promising schedules and the final best schedule |
| `src/validator.cpp` | Checks precedence and resource feasibility |
| `src/main.cpp` | Wires the whole pipeline together |

## 4. The data structures

The two structs in `src/types.h` are the core objects:

- `Problem`: the instance data
- `Schedule`: the output schedule

`Problem` contains:

- `duration[i]`
- `resource[i][k]`
- `successors[i]`
- `predecessors[i]`
- `capacity[k]`
- `horizon`

`Schedule` contains:

- `start_time[i]`
- `makespan`

The solver also uses dummy source and sink nodes:

- `0` = super-source
- `n + 1` = super-sink

This makes precedence handling cleaner because everything can be treated as one graph.

## 5. What SSGS is really doing

`ssgs()` in `src/ssgs.cpp` is the feasibility engine.

For each activity in the chosen order:

1. Find the earliest time allowed by precedence.
2. Starting from that time, scan forward until resources are available for the full duration.
3. Place the activity there.
4. Reserve its resource usage in the time-indexed usage table.

That is it.

### Intuition

Think of SSGS as a very disciplined clerk:

- "You told me activity 7 should be considered now."
- "Its predecessors finish by time 12."
- "Time 12 does not fit because resource 2 is full."
- "Time 13 also does not fit."
- "Time 14 works."
- "So activity 7 starts at 14."

The key consequence:

- the activity list decides **priority**
- SSGS decides **actual placement**

### Why this is a good design

If we searched directly over start times, every mutation would risk breaking feasibility in messy ways.

By searching over activity lists instead:

- the GA handles a simpler combinatorial object
- precedence is easier to preserve
- SSGS guarantees the evaluated schedule is valid

So SSGS is doing the hard constraint-handling work for the GA.

## 6. Why the priority rules exist

The GA needs a starting population. Purely random starts work, but they waste time. `src/priority.cpp` gives the GA smarter starting guesses.

The rules are:

| Rule | Plain-English intuition |
|---|---|
| `lft` | Activities with tighter latest-finish deadlines should be considered earlier |
| `mts` | Activities that unlock lots of downstream work should be considered earlier |
| `grd` | Resource-hungry activities should be considered earlier while the schedule is still open |
| `spt` | Short activities go earlier to free things up quickly |
| `random` | No bias, just a feasible random topological order |

Important detail: these rules do **not** directly assign times either.

They only bias the order in which eligible activities are selected during a topological sort.

### Deterministic vs randomized bias

The code uses two versions:

- deterministic priority sort: always pick the currently best eligible activity
- randomized biased sort: sort eligible activities by priority, then randomly pick from a small top pool

That second version matters because it gives diversity without throwing away the heuristic guidance.

In other words:

- deterministic rules give strong anchors
- randomized biased rules give nearby variants

This is why `generate_initial_solutions()` is more useful than just calling `priority_sort()` once.

## 7. What the GA is really searching over

The GA in `src/ga.cpp` is searching over different activity lists to find one that SSGS decodes into a shorter makespan.

The loop is basically:

1. keep a population of activity lists
2. decode each list with SSGS and measure makespan
3. select better parents more often
4. combine parents with one of two crossover styles
5. mutate offspring, with the mutation rate increasing when the search stalls
6. optionally polish strong offspring with forward-backward improvement
7. keep good offspring
8. repeat until time runs out

### Fitness

Fitness is simple:

- smaller makespan = better individual

There is no fancy weighted objective here. The score is just the decoded schedule's makespan.

### Selection

Tournament selection means:

- sample a few individuals
- keep the best one as a parent

This is a cheap way to prefer stronger candidates without making the population too greedy too early.

### Crossover

The crossover is now **hybrid**, not fixed to one operator.

The solver uses two crossover styles:

- **one-point crossover**:
  - take a prefix from parent 1
  - fill the rest from parent 2 in parent-2 order
- **precedence-aware merge crossover**:
  - look only at currently eligible activities
  - prefer activities that both parents place early
  - build the child step by step while always preserving precedence

The merge crossover matters because it is less like copying a chunk and more like asking:

"Among the jobs that are legal right now, which ones do both parents seem to agree should be early?"

The code leans more toward merge crossover when the search has been stuck for a while, and still uses one-point crossover when simple recombination is enough. So crossover is now partly **stagnation-aware**.

### Mutation

The mutation operators make local changes to the list while trying to preserve precedence:

- adjacent swap
- long swap
- insertion

These are not random time edits. They are controlled changes to the ordering.

You can think of them as:

- "swap two nearby priorities"
- "swap two far-apart priorities"
- "move one activity earlier or later, but only within legal bounds"

That last part is important. The code computes valid insertion bounds from predecessor and successor positions, so mutation does not blindly destroy feasibility.

What changed recently is that mutation is now **adaptive**:

- when the search is improving, mutation stays near the base rate
- as the solver goes longer without improvement, the mutation rate ramps up toward a higher maximum

Plain English version:

> If the GA is stuck, it starts taking bigger risks before giving up and restarting.

## 8. Why duplicate control and restarts are needed

If the GA is left alone for too long, populations often become boring:

- many individuals become nearly identical
- crossover stops generating anything new
- the search burns time re-evaluating the same ideas

This solver handles that in two ways.

### Duplicate-aware control

The code fingerprints each activity list with a hash.

If a child is an exact duplicate:

- try a few extra perturbations
- if it is still a duplicate, skip it

That prevents wasted evaluations.

### Restart-on-stagnation

If the search does not improve for a long time:

- keep a small elite set
- rebuild the rest of the population from fresh seeds and random solutions

This is the solver's way of saying:

"We are stuck in one valley. Keep the best ideas, but go explore somewhere else."

## 9. What forward-backward improvement is really doing

`forward_backward_improve()` in `src/improvement.cpp` is no longer just a final clean-up step.

The solver now uses it in three places:

- to periodically tighten the current best solution during long dry spells
- to selectively polish a newly created child if it already looks promising
- to do one final clean-up pass on the best solution before returning

The selective child-polishing rule is pragmatic: the GA only spends this extra work on offspring that already beat their better parent and are close enough to the current best to be worth polishing.

The intuition:

- a forward SSGS schedule is feasible, but it can leave awkward slack
- if we push activities as late as possible from the right side, we can expose unnecessary gaps
- then if we schedule forward again using that new structure, some jobs pack together better

So the move is:

1. start from a good forward schedule
2. build a backward schedule that pushes jobs right
3. sort activities by the new starts
4. run forward SSGS again
5. keep the better result

This is sometimes called double justification.

Plain English version:

> First squeeze everything from the right, then rebuild from the left using that tighter arrangement.

It is still not the main search engine, but it is now used more opportunistically inside the search rather than only after the search.

## 10. Why the solver is hybrid instead of using one idea only

Each part solves a different weakness:

- priority rules give cheap structure fast
- SSGS guarantees feasibility
- GA explores combinations and alternatives the rules alone would miss
- hybrid crossover gives the GA both simple recombination and a more structure-aware merge move
- adaptive mutation makes the GA more exploratory when it starts to stall
- forward-backward improvement removes slack from strong schedules during search and at the end

If we used only one part:

- only priority rules: fast, but too shallow
- only GA from pure random: flexible, but slower to find good regions
- only SSGS: no search at all, just decoding
- only forward-backward improvement: can polish a schedule, but cannot invent a strong one

So the full solver works because the pieces are complementary, not because any one piece is magical.

## 11. The code-level intuition for each mode

`main.cpp` exposes several modes. Think of them like this:

| Mode | What it means |
|---|---|
| `baseline` | "Pick one random order and decode it" |
| `priority` | "Try several heuristic orders and keep the best decoded result" |
| `ga` | "Run GA, but start from random orders and skip final improvement" |
| `full` | "Use good seeds, run GA with hybrid crossover and adaptive mutation, polish strong candidates during search, then polish the best schedule again" |

If someone wants to understand the benefit of each layer, these modes are the easiest mental checkpoints.

## 12. Common misconceptions

### "The priority rule schedules the project."

No. The priority rule only creates an activity order. SSGS still decides actual start times.

### "The GA manipulates schedules directly."

No. The GA manipulates activity lists. The schedule is recomputed after each candidate is decoded.

### "A precedence-feasible order automatically gives a good schedule."

No. It only gives a legal decoding order. Two legal orders can decode to very different makespans.

### "Forward-backward improvement replaces the GA."

No. It usually improves a good solution by a little. It does not replace broad search.

### "Randomness means the solver is uncontrolled."

Not really. The randomness is guided:

- heuristic-biased seed generation
- tournament selection
- hybrid crossover
- precedence-aware mutations
- adaptive mutation pressure when the search stalls
- duplicate control
- elitist restarts

This is not random chaos. It is randomized search around structured candidates.

## 13. If you only have 15 minutes to re-understand the project

Read the files in this order:

1. `src/main.cpp`
2. `src/types.h`
3. `src/ssgs.cpp`
4. `src/priority.cpp`
5. `src/ga.cpp`
6. `src/improvement.cpp`

That order matches the actual mental model:

- what goes in
- what a candidate means
- how a candidate becomes a schedule
- how seeds are made
- how search improves them
- how the final clean-up works

## 14. One-sentence summary for each important file

| File | One-sentence summary |
|---|---|
| `parser.cpp` | Turn input text into a `Problem` object |
| `priority.cpp` | Build smart starting activity orders |
| `ssgs.cpp` | Decode an order into the earliest feasible schedule |
| `ga.cpp` | Search over many orders under a time budget using hybrid crossover, adaptive mutation, selective polishing, and restarts |
| `improvement.cpp` | Tighten a strong schedule by squeezing slack, both during search and at the end |
| `validator.cpp` | Prove the final answer is actually feasible |

## 15. The whole solver in one paragraph

The solver reads an RCPSP instance, cleans the precedence graph if needed, creates several precedence-feasible activity orders using priority rules, and uses SSGS to decode each order into a valid schedule. A genetic algorithm then keeps modifying these orders, now using a hybrid of one-point and precedence-aware merge crossover plus a mutation rate that increases when the search stalls. To avoid wasting time, it rejects duplicates, restarts when progress dries up, and selectively runs forward-backward tightening on children that already look competitive. Finally, it runs one more forward-backward pass on the best schedule and validates the result before output.

## 16. The shortest possible intuition

If you want the ultra-short version:

- the **activity list** says "who gets considered first"
- **SSGS** says "when can this actually start"
- the **GA** says "let's keep trying better orderings, and get more aggressive when stuck"
- **forward-backward improvement** says "squeeze out leftover slack from the strongest schedules"

That is the whole project.
