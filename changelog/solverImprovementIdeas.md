# Solver Improvement Ideas

This note is for the team to track the next RCPSP improvements we may add to the current solver.

The goal is not to redesign the solver from scratch. The current backbone is already standard RCPSP:
- activity-list representation
- serial SSGS decoding
- GA over precedence-feasible orders
- forward-backward improvement / justification

Our experiments suggest that the current solver saturates early:
- `3s` is already very close to `28s`
- this means extra time is not being used effectively by the current search loop

So the right next step is to add stronger **hybridization**, **local search**, and **diversification** on top of the current architecture.

## TL;DR

If we only add a few things, the most promising order is:

1. **Stronger list-based mutation**
   - non-adjacent feasible swap
   - bidirectional insertion, not just earlier-shift
2. **Local search on elites / new bests**
   - turn the GA into a small memetic GA
3. **Apply justification more aggressively**
   - on every new best, not just occasionally
4. **Restart on stagnation**
   - keep elites, refresh the rest with randomized biased seeds

These fit standard RCPSP practice and are the most likely to make `10s` and `28s` actually outperform `3s`.

For future experiments, we should also tighten the evaluation protocol:

1. **Compare algorithms with a fixed schedule-generation budget**
   - count `SSGS` decodes instead of relying only on wall-clock
2. **Use repeated runs for randomized methods**
   - report mean and best outcome over several seeds
3. **Use targeted regression subsets first**
   - only run full sweeps when a change looks promising

This reduces blind tuning and makes comparisons less sensitive to machine speed.

## Why These Ideas Fit Our Solver

Our current architecture is already aligned with standard RCPSP heuristics:
- the literature commonly uses **activity lists**
- these are typically decoded by **serial SGS**
- population-based methods often add **justification**, **local search**, and **diversification**

So the next improvements should be:
- better neighborhoods over activity lists
- better use of time budget on good solutions
- better recovery from stagnation

not:
- a complete change in representation
- direct start-time chromosomes
- a full rewrite into a different method

## Literature Inspiration

### 1. Activity-list GA + serial SGS is standard

This is the main reason we should keep the current backbone.

What it says:
- Hartmann-style RCPSP GAs use an **activity list** representation
- the list is decoded with **serial SGS**
- randomized priority-rule seeding is standard

Why it matters for us:
- we do not need to abandon activity lists or serial SGS
- we should strengthen the search around them instead

Reference:
- Hartmann-style RCPSP/t GA chapter: <https://www.om-db.wi.tum.de/psplib/files/2015_Book-RCPSP-t_GA.pdf>

### 2. Strong RCPSP methods are usually hybrids, not plain GA

What it says:
- top RCPSP heuristics often combine several mechanisms:
  - genetic search
  - local improvement
  - justification / forward-backward passes
  - diversification

Why it matters for us:
- our solver is currently closer to a plain GA with light improvement
- the next gains are likely to come from hybridization

References:
- Survey / update on RCPSP heuristics: <https://www.hsba.de/fileadmin/user_upload/bereiche/_dokumente/6-forschung/profs-publikationen/Hartmann_2006_Experimental_investigation_of_Heuristics.pdf>
- RCPSP survey: <https://www.sciencedirect.com/science/article/abs/pii/S0377221719300980>

### 3. Exploration remains a key issue

What it says:
- even in recent RCPSP population-based work, effective exploration is still a challenge

Why it matters for us:
- our `3s ~= 28s` behavior is exactly a search-stagnation symptom
- better diversification and better neighborhoods are justified

Reference:
- Recent RCPSP paper discussing exploration challenges: <https://www.sciencedirect.com/science/article/pii/S0020025523007491>

### 4. Stronger experimental protocol exists in the RCPSP literature

What it says:
- RCPSP heuristic comparisons are often run with a stopping rule based on the number of generated schedules, not just wall-clock
- later work also argues for multiple independent runs because most strong RCPSP metaheuristics are randomized

Why it matters for us:
- a fixed schedule budget is better for internal algorithm comparison
- it tells us whether a change improves the search itself, not just the implementation speed
- we should still keep wall-clock runs for the final project requirement

References:
- Kolisch and Hartmann benchmark protocol update: <https://www.om-db.wi.tum.de/psplib/files/KH-18-2-05.pdf>
- Scatter-search paper discussing repeated runs and schedule limits: <https://www.cirrelt.ca/documentstravail/cirrelt-2014-50.pdf>

## Candidate Improvements

## Experimental Protocol We Should Use

### Why the current protocol is not enough

Right now we mostly compare solver changes by:
- one wall-clock budget
- one run per instance
- sometimes a full sweep only after coding

That is good for final reporting, but weak for research iteration:
- wall-clock mixes algorithm quality with implementation speed
- one run can overstate or understate a stochastic change
- full sweeps are expensive

### Better internal protocol

For development and algorithm comparison:
- count the number of schedules generated
- run 3 to 5 seeds for randomized methods
- test on regression subsets first
- only run full wall-clock sweeps after a change looks promising

### How to implement it in this codebase

- add a schedule counter that increments on every `SSGS` decode
- stop the GA when `schedule_count >= budget`
- count extra decode-based improvement passes as well
- keep the current `--time` mode for report-facing experiments

### Recommended use

- use **schedule budget** for internal A/B experiments
- use **`3s` and longer wall-clock** for report results

This gives us:
- fairer algorithm comparison
- cheaper iteration
- less risk of drawing conclusions from noisy one-off wall-clock runs

## What To Run After A Solver Change

Use this as the default test sequence for future solver modifications.

### 1. Smoke test

Run 1 to 3 direct solver invocations first:
- one easy PSPLIB instance
- one harder PSPLIB instance
- if parser/input code changed, one local `.SCH` file too

Purpose:
- catch crashes
- confirm logging and output format
- confirm feasibility still holds

### 2. Internal A/B test under schedule budget

Run the current solver and the modified solver with the same `--schedules` budget.

Use this when:
- comparing search logic
- checking whether a change is algorithmically better rather than just faster

Good first targets:
- `J60`
- `J90` regression subset

### 3. Targeted regression subset

Before any full sweep:
- run only the instances where the previous experiment regressed
- or a known difficult cluster

This is the cheapest high-signal check.

### 4. Full `3s` wall-clock sweep

Only if the targeted result looks promising:
- run the normal `3s` benchmark on the affected datasets

Current default:
- `J30` and `J60` if the change is broad
- `J90` / `J120` if the change is meant to help larger instances

### 5. Longer wall-clock confirmation

Only for changes we may keep:
- run `10s` or `28s`
- use this to check whether the change helps once there is more time to exploit it

### Decision rule

- **Fail at smoke test**: fix immediately
- **Fail at schedule-budget A/B**: do not run a full sweep yet
- **Mixed targeted result**: tune or rethink before broader benchmarking
- **Pass targeted + `3s` sweep**: keep as a candidate improvement
- **Pass longer wall-clock too**: strong candidate for final report

## 1. Stronger Mutation Neighborhood

### What to add

- non-adjacent feasible swap
- bidirectional insertion
- possibly block insertion later

### Why this helps

Current mutation is weak:
- adjacent swap only changes a very small part of the list
- current shift only moves an activity earlier
- neither move can easily reorganize a bad region of the schedule

That likely explains why the GA plateaus quickly.

### Why it matches RCPSP practice

RCPSP local search methods commonly rely on:
- swap
- shift / insertion
- neighborhood search on activity lists

These are standard ways to improve activity-list solvers.

### Expected upside

- better use of long time budgets
- more chance to escape local plateaus
- more meaningful improvement after the first few seconds

### Implementation notes

Likely files:
- [ga.cpp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/src/ga.cpp)

Safe first version:
- add non-adjacent swap only if the two chosen activities are incomparable
- allow insertion both earlier and later within the precedence-feasible interval

### Priority

**Highest**


## 2. Elite Local Search

### What to add

After generating a strong individual:
- run a short hill-climbing pass
- try insertion / swap moves
- keep improving moves only

Possible trigger points:
- every new global best
- every few thousand generations on the top 3 to 5 individuals

### Why this helps

Right now the GA mostly does:
- reproduce
- mutate once
- decode once

That is often too shallow for RCPSP. A local search layer turns the solver into a **memetic GA**, which is a common upgrade path in RCPSP.

### Why it matches RCPSP practice

The literature repeatedly shows that strong RCPSP methods combine:
- a global search framework
- a local search intensification layer

### Expected upside

- much better use of the extra 25 seconds
- cleaner refinement of already-good schedules
- likely stronger improvement on J90/J120

### Implementation notes

Likely files:
- [ga.cpp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/src/ga.cpp)
- maybe a new helper file later if the logic becomes large

Keep it cheap at first:
- cap attempts
- only run on elites / new bests

### Priority

**Very high**

## 3. Stronger Use of Justification

### What to add

Current forward-backward improvement should be used more aggressively:
- apply on every new best
- occasionally apply to a few elites
- possibly chain:
  - local search
  - justification
  - local search

### Why this helps

We already have justification infrastructure, but it is underused.

Since justification is already known to help RCPSP schedules, using it more effectively is lower risk than inventing a brand new operator.

### Why it matches RCPSP practice

Forward-backward improvement / justification is a well-known RCPSP ingredient and appears frequently in strong hybrids.

### Expected upside

- cheap improvement on already-good solutions
- easy way to convert spare runtime into schedule polishing

### Implementation notes

Likely files:
- [ga.cpp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/src/ga.cpp)
- [improvement.cpp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/src/improvement.cpp)

### Priority

**High**

## 4. Restart on Stagnation

### What to add

If no best improvement for a long time:
- keep the top `k` elites
- regenerate the rest of the population using:
  - randomized `LFT`
  - randomized `MTS`
  - some pure randoms

### Why this helps

Our current GA can spend a lot of time doing unproductive generations after the population has converged.

Restarts are a direct way to buy back exploration.

### Why it matches RCPSP practice

This fits the literature theme of balancing:
- intensification
- diversification

without changing the main representation or decoder.

### Expected upside

- better long-budget behavior
- less wasted runtime after convergence
- more robustness on hard instances

### Implementation notes

Likely files:
- [ga.cpp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/src/ga.cpp)
- [priority.cpp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/src/priority.cpp)

### Priority

**Medium-high**

## 5. Better Crossover

### What to add

Replace or complement the current simple one-point crossover with something more RCPSP-aware, for example:
- a precedence-preserving two-point crossover
- later, possibly a crossover that respects useful blocks from parents

### Why this helps

Current crossover is valid, but generic.
It may not preserve enough useful structure from both parents.

### Why it matches RCPSP practice

Many stronger RCPSP GAs use more careful recombination than plain generic order copying.

### Expected upside

- better heredity of useful suborders
- improved offspring quality before mutation

### Implementation notes

Likely files:
- [ga.cpp](/Users/weisintai/development/smu/modules/y2s2/cs202/project/src/ga.cpp)

### Priority

**Medium**

## Things We Probably Should Not Do First

## 1. Rewrite the solver around a completely different representation

Why not:
- activity lists + serial SGS are already standard and defensible
- the bottleneck is search strength, not basic representation validity

## 2. Jump straight to MIP / CP hybrid solving

Why not:
- too large a jump
- much more engineering complexity
- not the best first use of the remaining runtime budget

## 3. Over-tune constants before strengthening the search

Why not:
- if the neighborhood is weak, tuning population or mutation rate only helps a little
- structural improvements should come first

## Suggested Implementation Order

If we want a practical sequence:

1. add bidirectional insertion
2. add non-adjacent feasible swap
3. add elite local search
4. trigger justification on every new best
5. add restart-on-stagnation
6. revisit crossover

## Team Summary

The important message for the team is:

- our current solver architecture is already valid RCPSP design
- the next gains are likely to come from **hybridizing the GA**, not replacing it
- the strongest immediate targets are:
  - better mutation neighborhoods
  - elite local search
  - stronger use of justification
  - restarts when the population stalls

This is the most defensible path if we want the extra runtime beyond `3s` to actually produce better schedules.
