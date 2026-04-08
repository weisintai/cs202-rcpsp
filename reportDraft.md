# Optimising Resource-Constrained Scheduling

**Module:** CS202  
**Group:** [Group number]  
**Members:**  
- [Name] ([Student ID])  
- [Name] ([Student ID])  
- [Name] ([Student ID])  
- [Name] ([Student ID])  
- [Name] ([Student ID])

## 1. Introduction

Imagine managing a construction project where plumbing, electrical work, structural work, and inspection all compete for the same workers and equipment. Some jobs can run in parallel, but others must wait for earlier tasks to finish. If we schedule too conservatively, the project drags on. If we schedule too aggressively, we break precedence or overuse a resource. That is the core challenge of the Resource-Constrained Project Scheduling Problem (RCPSP).

In RCPSP, each activity has a duration, a set of predecessor constraints, and a fixed demand for each renewable resource type. The goal is to assign a start time to every activity so that all precedence and resource constraints are respected while the final completion time, or makespan, is as small as possible. The assignment also adds a practical constraint: the solver must always return a valid schedule within a strict 30-second wall-clock budget per instance. That changes the nature of the task. We are not trying to prove optimality on every instance. We are trying to find strong schedules quickly and reliably.

We approached the problem with a hybrid solver built around three ideas. First, we represent a candidate schedule as an activity list, then decode it with a Serial Schedule Generation Scheme (SSGS) [2]. Second, we seed the search with priority-rule heuristics instead of starting entirely from random permutations. Third, we refine those candidates with a genetic algorithm (GA) [3] that combines hybrid crossover, adaptive mutation, and forward-backward improvement. This combination gave us a solver that remained valid on the provided `J10` and `J20` sets as well as the larger PSPLIB benchmark instances [1], and produced strong makespans within short time budgets.

We first used the provided `J10` and `J20` datasets to verify parsing, schedule validity, and runtime behaviour. Our main quantitative result then came from the 3-second benchmark sweep on the larger PSPLIB datasets. Using the final solver line, we matched the best-known makespan on 428 of 480 `J30` instances, 353 of 480 `J60` instances, 352 of 480 `J90` instances, and 180 of 600 `J120` instances. Mean quality relative to the best-known value remained high across all four datasets: `99.783%` on `J30`, `98.961%` on `J60`, `98.573%` on `J90`, and `95.736%` on `J120`. The trend is clear: the solver handles small and medium instances very well, but the gap widens as the instances become larger and more constrained.

## 2. Algorithm design

This section explains the full solver pipeline. We begin with a representation that is easy to manipulate inside a metaheuristic, convert that representation into an actual schedule with SSGS, and then search over the space of feasible activity lists using heuristic seeding, GA operators, and a final improvement pass.

### 2.1 Solution representation

We represent a candidate as an **activity list**, that is, a topological ordering of the non-dummy activities. This representation is compact, easy to mutate, and easy to combine through crossover. More importantly, it separates two concerns that are otherwise tangled together:

- the search procedure decides *which activity should tend to appear earlier or later*,
- the decoder decides *the earliest feasible start time* once an order is fixed.

An activity list by itself is not yet a schedule. It only says which activities should be considered earlier in the decoding process. The actual start times emerge only after SSGS places each activity at the earliest time that respects both precedence and resource limits.

We chose this representation for two reasons. First, it keeps the search space manageable: the GA works over permutations rather than raw time assignments. Second, it works naturally with precedence. A mutation or crossover only needs to preserve topological feasibility, not full time feasibility. The decoder handles the rest.

### 2.2 SSGS decoder

The SSGS decoder takes a precedence-feasible activity list and constructs a concrete schedule. For each activity in list order, it finds the earliest time at which:

1. all predecessors have already finished, and  
2. enough units of every renewable resource remain available for the entire duration of that activity.

This is the core feasibility mechanism in our solver. Every candidate the GA evaluates is passed through SSGS, so the search operates on schedules that are always valid when the input instance itself is feasible.

```text
Algorithm 1: SSGS(activity_list)
Input: precedence-feasible activity list A
Output: start times s and makespan Cmax

initialise all start times to -1
initialise resource-usage table usage[t][k] to 0

for activity i in A do
    earliest <- max finish time among predecessors of i
    t <- earliest
    while resource feasibility fails for i at time t do
        t <- t + 1
    end while
    s[i] <- t
    reserve i's resource demand on interval [t, t + duration[i])
end for

Cmax <- max_i (s[i] + duration[i])
return s, Cmax
```

What makes SSGS useful here is that it gives the GA a stable, deterministic way to interpret each activity list. If two lists differ in a meaningful way, SSGS turns that difference into a different schedule. If a mutation changes the order of a bottleneck activity, SSGS reveals whether that actually helps the makespan.

### 2.3 Priority-rule heuristics

Before the GA starts, we create a seeded initial population using simple priority rules:

- **LFT:** Latest Finish Time from a backward critical-path pass  
- **MTS:** Most Total Successors  
- **GRD:** Greatest Resource Demand  
- **SPT:** Shortest Processing Time  
- **Random:** feasible random topological orders

The goal here is not to solve the instance with a single rule. It is to start the GA from several sensible parts of the search space instead of relying on pure randomness. In practice, not all rules are equally helpful. Later experiments showed that LFT and MTS were consistently the strongest standalone heuristics, so they became the main sources of guided seeding in the final solver.

We also used a **biased randomized topological sort** rather than a fully greedy one. Instead of always taking the single best eligible activity, the generator samples from a small top-ranked candidate pool. This keeps the seed population diverse while still preserving the bias of the chosen rule.

### 2.4 Genetic algorithm

The GA is the main search engine. It improves on the seeded activity lists by combining good structures, applying local perturbations, and keeping the better offspring. Our implementation uses:

- population size `100`,
- tournament selection with size `5`,
- hybrid crossover that mixes one-point recombination with a precedence-aware merge crossover,
- precedence-feasible activity-list mutation with an adaptive mutation rate,
- steady-state replacement,
- restart-on-stagnation for diversification,
- duplicate-aware diversity control,
- selective forward-backward polishing on promising offspring.

The key idea is simple: priority rules give the search a good starting region, then the GA explores nearby and between those regions for better schedules. In the final line, that exploration became more deliberate: the crossover operator became partly precedence-aware, the mutation rate increased as stagnation built up, and only promising offspring were polished with the expensive improvement pass.

```text
Algorithm 2: Genetic algorithm with schedule decoding
Input: instance I, time budget T
Output: best schedule found

P <- seeded initial population
evaluate every individual in P using SSGS
best <- best individual in P

while time budget not exhausted do
    p1 <- tournament_select(P)
    p2 <- tournament_select(P)
    child <- crossover(p1, p2)
    child <- mutate(child)
    if child is an exact duplicate then
        perturb or discard child
    end if
    decode child with SSGS
    if child improves worst member of P then
        replace worst member
    end if
    if child improves best then
        best <- child
    end if
    if search stagnates for too long then
        keep a small elite set and restart the rest of P
    end if
end while

return best
```

The mutation operator matters because activity lists already satisfy precedence, so every move has to preserve that structure. We therefore use only precedence-feasible moves:

- adjacent feasible swap,
- non-adjacent feasible swap,
- insertion within the precedence-feasible interval.

This gives the GA both small local moves and larger structural changes. The restart mechanism is equally important. Without it, the population tends to collapse into a narrow basin and spend too much time evaluating near-duplicate schedules.

### 2.5 Forward-backward improvement

Once the GA has a strong candidate, we run a forward-backward improvement step, also known as double justification. The purpose is to tighten unnecessary slack in the decoded schedule.

```text
Algorithm 3: Forward-backward improvement
Input: best activity list A
Output: improved schedule

1. Decode A forward with SSGS
2. Construct a backward order from the resulting finish structure
3. Schedule backward to tighten latest feasible placements
4. Convert that result into a new forward order
5. Decode forward again with SSGS
6. Keep the better of the old and new schedules
```

The intuition is straightforward. A good GA solution can still contain small idle gaps created by the decoder's local placement decisions. The backward pass exposes some of those gaps, and the final forward pass can then reuse the tighter order to reduce makespan. In our experiments, this step did not dominate the solver by itself, but it consistently cleaned up schedules that the GA alone had already made strong.

### 2.6 Design decisions and justification

We chose a GA over exact optimisation because of the assignment's runtime setting. Exact branch-and-bound or dynamic-programming approaches can be elegant on small instances, but they become difficult to scale once the precedence structure and resource interactions grow dense. The grading setup rewards good schedules within a hard deadline, not proofs of optimality. A GA fits that setting better because it gives an anytime trade-off: even if it has not fully converged, it can still return a valid schedule.

We chose activity lists plus SSGS because the combination is practical and explainable. Activity lists are easy to manipulate with heuristic and evolutionary operators. SSGS turns them into valid schedules under renewable-resource constraints. This separation let us search over compact combinatorial objects while keeping feasibility enforcement simple and deterministic.

Finally, we chose to combine heuristic seeding, GA search, and forward-backward improvement because they solve different parts of the problem:

- priority rules give cheap structure early,
- the GA explores beyond what any one rule can do,
- the improvement pass removes slack the GA may leave behind.

The experiments in Section 4 show that the solver works best when these parts are combined rather than used in isolation.

## 3. Complexity analysis

Table 1 summarises the main time and space costs of the solver components.

| Component | Time complexity | Space complexity |
|---|---:|---:|
| Parsing | `O(nK)` | `O(nK)` |
| Topological sort / CPM | `O(n + E)` | `O(n + E)` |
| Single SSGS decode | `O(n * T_max * K)` worst case, `O(n^2 * K)` typical | `O(T_max * K)` |
| Priority-rule initial population | `O(P * n^2 * K)` | `O(P * n)` |
| GA per offspring evaluation | dominated by one SSGS decode | `O(P * n)` plus decoder state |
| Total GA search | bounded by wall-clock budget rather than a fixed generation count | `O(P * n + T_max * K)` |
| Forward-backward improvement | `O(n^2 * K)` per pass | `O(T_max * K)` |

The important point is that the solver is **time-budgeted**. In theory, the worst-case cost is driven by repeated SSGS decoding, which can become expensive on larger instances with tight resources. In practice, the real design question is how much useful search we can fit inside the deadline. That is why hot-path decoding speed, seeded initial populations, and diversification all matter: each one increases the amount of meaningful search the solver can complete before time runs out.

## 4. Experiments

This section follows the same structure throughout: what question we asked, how we tested it, what the numbers showed, and why that matters for the final solver.

For the final report, the main claims should come from wall-clock runs because the assignment itself is judged under a hard time limit. During development, however, we also used a fixed **schedule-generation budget** with `--schedules <count>` to compare solver changes more fairly. That reduced the noise from raw machine speed and let us ask a cleaner question: if two variants are allowed to generate the same number of schedules, which one actually searches better?

We also separate the role of the datasets. The provided `J10` and `J20` instances were our first validation target, as intended by the project brief: we used them to check parser support, feasibility, and basic runtime behaviour. The main quality comparisons in this report focus on `J30` to `J120`, where the benchmark harness includes consistent reference makespans and the larger instances give a stronger picture of how well the solver generalises beyond the easiest provided cases.

### 4.1 Validation on the provided `J10` and `J20` sets

We did not ignore the datasets provided directly in the assignment. We used `J10` first for correctness checking and `J20` next for slightly harder stress testing, which is exactly the progression suggested in the project brief.

In this repository, the local updated `J10` and `J20` sets are most useful for three things:

- checking that the solver supports the local `.SCH` format as well as standard `.sm`
- confirming that the decoder and validator produce feasible schedules
- checking that the solver behaves sensibly on small instances before we move to larger PSPLIB benchmarks

Under a 3-second budget, the solver completed `253/270` feasible `J10` runs and `266/270` feasible `J20` runs. The remaining files in the updated local sets were infeasible as provided because at least one activity demanded more of a resource than the declared capacity. That is why these two datasets appear in the report mainly as validation evidence rather than as the main makespan-quality benchmark.

### 4.2 Experiment 1: algorithm component ablation

The first experiment asked a simple question: how much does each major component actually contribute? We compared four configurations on `J30` and `J60`:

- baseline: random topological order + SSGS,
- priority only: best of priority-rule seeds without GA,
- GA only: GA from random initial population,
- full pipeline: guided seeding + GA + forward-backward improvement.

Table 2 shows the results.

| Configuration | J30 match rate | J30 mean gap (%) | J60 match rate | J60 mean gap (%) |
|---|---:|---:|---:|---:|
| Baseline | 32.08 | 13.564 | 29.38 | 15.766 |
| Priority only | 60.21 | 2.632 | 63.33 | 3.934 |
| GA only | 89.58 | 0.212 | 73.12 | 1.425 |
| Full pipeline | 89.17 | 0.226 | 73.12 | 1.263 |

The jump from the baseline to priority-only is already large. On `J30`, the mean gap drops from `13.564%` to `2.632%`, and on `J60` it drops from `15.766%` to `3.934%`. That tells us the activity-order bias matters a lot even before we add metaheuristic search.

Adding the GA brings another large improvement. On `J60`, the mean gap falls from `3.934%` to `1.425%`, and the best-known match rate rises from `63.33%` to `73.12%`. The full pipeline then improves the mean gap further to `1.263%`. On `J30`, the GA-only and full variants are very close. In one run the GA-only variant was marginally better on mean gap, which suggests that on easier instances the final improvement step and restart machinery trade a little throughput for robustness. Even so, the ablation supports the overall architecture: heuristic seeding and GA search both matter, and the forward-backward pass still improves the harder `J60` set.

This experiment justified the main solver design. We kept components that produced a measurable gain and dropped the idea that every extra layer was automatically worth its cost.

### 4.3 Experiment 2: scaling across instance sizes

The second experiment measured how the final solver degrades as the instances get larger. This is the main report-facing benchmark because it uses the same 3-second wall-clock budget across `J30`, `J60`, `J90`, and `J120`.

Table 3 shows the final solver line.

| Dataset | Best-known matches | Match rate (%) | Mean gap (%) | Mean quality (%) | Max gap (%) | Mean wall time (s) |
|---|---:|---:|---:|---:|---:|---:|
| J30 | 428 / 480 | 89.17 | 0.222 | 99.783 | 6.897 | 3.005 |
| J60 | 353 / 480 | 73.54 | 1.092 | 98.961 | 8.421 | 3.005 |
| J90 | 352 / 480 | 73.33 | 1.523 | 98.573 | 11.207 | 3.005 |
| J120 | 180 / 600 | 30.00 | 4.594 | 95.736 | 15.508 | 3.006 |

**Figure 1 placeholder.** Scaling of the 3-second solver across `J30`, `J60`, `J90`, and `J120`. A line chart of mean gap or a bar chart of best-known match rate would both work.

The trend is exactly what we would expect from a time-budgeted heuristic solver. On `J30`, the algorithm is already very close to the best-known frontier, with a mean gap below a quarter of a percent. On `J60` and `J90`, performance remains strong but the gap starts to widen. On `J120`, the problem becomes much harder: the solver still returns valid schedules quickly, but matching the best-known makespan becomes much less common.

This tells us where the solver is actually strong. It is especially strong on small and medium instances, still competitive on `J90`, and clearly under more pressure on `J120`. That is a more honest picture than a single aggregate score would give.

### 4.4 Experiment 3: time-budget sensitivity

The third experiment asks whether the solver behaves like a useful anytime algorithm. We tested `1s`, `3s`, `10s`, and `28s` budgets on `J30` and `J60`.

This experiment is intentionally frozen on the solver line immediately before the latest GA upgrade. We did not rerun it after the final scaling improvements because its purpose in the report is qualitative: to show that giving the solver more time improves average results and that the gains flatten over time. Experiment 2 remains the source of the latest absolute benchmark numbers for the current final solver line.

Table 4 shows the final results.

| Time budget | J30 best-known matches | J30 mean gap (%) | J30 mean quality (%) | J60 best-known matches | J60 mean gap (%) | J60 mean quality (%) |
|---|---:|---:|---:|---:|---:|---:|
| 1s | 414 / 480 | 0.343 | 99.667 | 347 / 480 | 1.425 | 98.659 |
| 3s | 426 / 480 | 0.247 | 99.760 | 350 / 480 | 1.311 | 98.762 |
| 10s | 440 / 480 | 0.177 | 99.827 | 353 / 480 | 1.134 | 98.923 |
| 28s | 448 / 480 | 0.142 | 99.862 | 355 / 480 | 1.054 | 98.996 |

**Figure 2 placeholder.** Time-budget sensitivity on `J30` and `J60`. A line chart with time budget on the x-axis and mean gap on the y-axis is the clearest option.

The trend is clean and monotone on both datasets. On `J30`, the best-known match count rises from `414` at `1s` to `448` at `28s`, while the mean gap falls from `0.343%` to `0.142%`. On `J60`, the same pattern appears, although more gradually: matches rise from `347` to `355`, and the mean gap falls from `1.425%` to `1.054%`.

This is the anytime behaviour we wanted to show. More time consistently improves the average result, but the size of the gain changes. The jump from `1s` to `3s` is noticeable, and the later gains from `10s` to `28s` are smaller. That suggests the solver uses extra time productively, but also begins to flatten out once the easier improvements have already been found.

### 4.5 Experiment 4: priority-rule comparison

The fourth experiment compares the four standalone priority rules plus a random control. This was not meant to beat the full solver. It was meant to tell us which scheduling intuitions were worth building into the initial population.

Table 5 compares the five standalone construction rules on `J30` and `J60`.

| Rule | J30 best-known matches | J30 mean gap (%) | J30 mean quality (%) | J60 best-known matches | J60 mean gap (%) | J60 mean quality (%) |
|---|---:|---:|---:|---:|---:|---:|
| Random | 154 / 480 | 13.564 | 89.097 | 141 / 480 | 15.766 | 87.735 |
| LFT | 238 / 480 | 5.386 | 95.293 | 271 / 480 | 5.678 | 95.158 |
| MTS | 202 / 480 | 6.873 | 94.048 | 224 / 480 | 7.105 | 93.958 |
| GRD | 158 / 480 | 11.669 | 90.424 | 139 / 480 | 15.051 | 88.114 |
| SPT | 137 / 480 | 17.625 | 86.475 | 125 / 480 | 19.993 | 85.161 |

We also counted how often each rule produced the best standalone makespan on an instance, splitting ties fractionally.

- `J30`: `LFT 203.05`, `MTS 122.72`, `GRD 65.97`, `Random 51.22`, `SPT 37.05`
- `J60`: `LFT 241.67`, `MTS 142.33`, `Random 37.25`, `GRD 33.33`, `SPT 25.42`

The result is clear. `LFT` is the strongest rule on both datasets, and `MTS` is the consistent runner-up. `GRD` is weaker and often close to random, while `SPT` is the weakest standalone rule. That last result is useful because it shows that scheduling short activities first is not enough when precedence depth and resource bottlenecks matter more.

This experiment directly influenced the final solver. Instead of treating all rules equally, we biased the initial population toward randomized `LFT`- and `MTS`-based seeds. The goal was to keep diversity while starting the GA from stronger parts of the search space.

### 4.6 Refinement history

The four experiments above explain the main architecture, but they do not show how the final solver line was reached. We therefore kept a small refinement log in `benchmark_results/`.

The evolution of the solver was broadly:

1. A basic GA + SSGS backbone with activity lists and a final improvement pass.
2. Guided seeding, after the priority-rule study showed that `LFT` and `MTS` were much stronger than the weaker standalone rules.
3. A stronger mutation neighborhood, replacing overly local search moves with a mix of adjacent swap, non-adjacent swap, and feasible insertion.
4. Restart-on-stagnation and duplicate-aware diversity control, after the search showed clear signs of population collapse and plateauing.
5. Hot-path optimisation and schedule-budget testing, so later tuning could separate raw implementation speed from genuine search-quality improvements.
6. A final hybrid-GA refinement: hybrid crossover, adaptive mutation under stagnation, and selective forward-backward polishing of promising offspring.

This sequence matters because the final solver was not the result of one large redesign. It was the result of keeping a stable RCPSP backbone and improving the parts that experiments showed were actually limiting performance.

One example is restart tuning on `J90` at 3 seconds:

| Solver line | J90 best-known matches | J90 mean gap (%) | J90 mean quality (%) |
|---|---:|---:|---:|
| Restart stagnation baseline | 342 | 2.084 | 98.082 |
| Restart-tuned line | 350 | 1.791 | 98.336 |
| Final hybrid-GA line | 352 | 1.523 | 98.573 |

This shows the sort of tuning we actually trusted: changes that improved the canonical 3-second benchmark on hard instances without abandoning the core design. The last step added a hybrid crossover, adaptive mutation under stagnation, and selective forward-backward polishing of promising offspring. We also explored a separate multithreading branch later in the project. That branch increased schedule throughput and motivated a follow-up search-quality experiment, but we kept it out of the frozen submission because the threading and search changes landed together and were harder to attribute cleanly.

Several of these tuning steps were first checked under a fixed schedule budget before we reran them under the normal wall-clock benchmark. That gave us a fairer algorithm comparison. If one version only looks better because it generates more schedules per second, that is an implementation-speed result, not necessarily a search-quality result.

## 5. Discussion

### 5.1 Strengths

The solver has three main strengths.

First, it is reliable. The SSGS decoder ensures that every accepted schedule respects precedence and renewable-resource limits. Under the grading rules, a schedule that violates constraints is worth zero no matter how short its makespan is.

Second, it is strong under short budgets. That is exactly the behaviour we wanted under a 30-second deadline. We are not relying on a method that needs a long warm-up before it becomes competitive.

Third, the solver combines cheap structure and expensive search in a sensible way. LFT and MTS provide good initial guidance. The GA then improves on that guidance instead of starting from scratch, and the forward-backward pass removes some of the slack left by evolutionary search. The ablation study supports this division of labour.

### 5.2 Failure cases

The clearest failure mode is scale. As the instances grow from `J30` to `J120`, the search space becomes harder and the solver has less time per decision. `J120` is where this shows most clearly: the solver still produces valid schedules quickly, but the gap to the best known values becomes much larger.

Another weakness is search plateauing. The GA can converge to a narrow region of the search space, especially when many individuals decode to very similar schedules. Restart-on-stagnation and duplicate-aware control reduce this problem, but they do not eliminate it. This is one reason we also used fixed schedule-budget checks during development: they gave us a cleaner way to see whether a change genuinely improved the search.

Finally, some tuning changes help harder instances while causing small regressions on easier ones. We saw this during later experiments, which is why we were careful to keep the final frozen solver separate from exploratory branches.

### 5.3 Limitations and future work

The first limitation is attribution. Some later exploratory changes improved benchmark results, but they also changed multiple things at once. For the submitted solver, we preferred the simpler line whose behaviour we understood better.

The second limitation is dataset coverage. The best quantitative comparisons in this report use the PSPLIB-style `J30` to `J120` sets because those include best-known references. The local updated `J10` and `J20` sets were still useful for parser and feasibility testing, but they were not as useful for quality benchmarking because the harness does not provide the same reference tables.

The third limitation is algorithmic. Our solver is still mostly a population-based search wrapped around SSGS. The exploratory multithreading branch suggested that raw schedule throughput can be increased, but that does not automatically mean better schedules. A good next step would therefore be a stronger local search or a more directed neighborhood over critical activities, evaluated under a fixed schedule budget before any new wall-clock claims are made.

Other natural future directions include:

- more informed restart policies,
- adaptive mutation rates,
- critical-path-aware local search,
- comparisons against alternative metaheuristics such as tabu search or simulated annealing.

## 6. Conclusion

We built an RCPSP solver around a clear hybrid pipeline: activity-list representation, SSGS decoding, priority-rule seeding, genetic search, and forward-backward improvement. The experiments show why this combination works. Priority rules provide strong structure, the GA adds most of the search power, and the final improvement pass helps tighten schedules further on harder instances.

Under the final 3-second solver line, we matched the best-known makespan on `89.17%` of `J30`, `73.54%` of `J60`, `73.33%` of `J90`, and `30.00%` of `J120` instances. Those results are not uniform across all problem sizes, but they are strong enough to show that the solver is effective under tight wall-clock limits and remains valid throughout.

The main lesson from this project is practical rather than theoretical. In RCPSP, a good solver under time pressure is usually not the one with the most sophisticated single component. It is the one whose pieces fit together well: a representation that is easy to search, a decoder that preserves feasibility, and a search strategy that spends its limited time in the right parts of the space [4].

## References

[1] J. Kolisch and A. Sprecher, "PSPLIB - A project scheduling problem library," *European Journal of Operational Research*, vol. 96, no. 1, pp. 205-216, 1997.

[2] R. Kolisch, "Serial and parallel resource-constrained project scheduling methods revisited: Theory and computation," *European Journal of Operational Research*, vol. 90, no. 2, pp. 320-333, 1996.

[3] S. Hartmann, "A competitive genetic algorithm for resource-constrained project scheduling," *Naval Research Logistics*, vol. 45, no. 7, pp. 733-750, 1998.

[4] S. Hartmann and D. Briskorn, "A survey of variants and extensions of the resource-constrained project scheduling problem," *European Journal of Operational Research*, vol. 207, no. 1, pp. 1-14, 2010.
