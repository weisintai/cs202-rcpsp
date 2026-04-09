# RCPSP Solver — Implementation Notes

## Language: C++17

## Algorithm: Genetic Algorithm with Serial Schedule Generation Scheme (SSGS) Decoder

---

## Step 1: PSPLIB Parser

- Parse both `.sm` (standard PSPLIB) and `.SCH` formats
- Support the compact `.SCH` format used by the local J10/J20 sets
- Extract: n, K, durations, resource requirements, successor lists, resource capacities
- Build predecessor/successor adjacency lists
- Handle dummy activities 0 and n+1 (zero duration, zero resources)

## Step 2: Serial Schedule Generation Scheme (SSGS)

- Input: an activity list (precedence-feasible permutation)
- For each activity in list order: schedule at the earliest time where all predecessors are finished AND resource capacity is not exceeded at any timestep during the activity's execution
- Track resource usage via a time-indexed array `usage[t][k]`
- Output: start times for all activities, and the makespan
- Define makespan as the true project finish time `max_i(start[i] + duration[i])`

## Step 3: Priority-Rule Initial Solutions

- Implement multiple priority rules to seed the GA population:
  - Latest Finish Time (LFT)
  - Most Total Successors (MTS)
  - Greatest Resource Demand (GRD)
  - Shortest Processing Time (SPT)
  - Random feasible permutations
- Generate topological orderings biased by each priority rule
- These provide diverse, high-quality individuals for the initial population
- **Biased seeding enhancement:** Randomized priority-biased topological sort that samples from a candidate pool of the top N eligible activities (instead of always picking the single best). Initial population uses a weighted mix: 50% LFT-biased, 33% MTS-biased, 17% pure random (motivated by experiment 4 showing LFT and MTS are the strongest rules)

## Step 4: Genetic Algorithm

- **Representation:** activity list (permutation that respects precedence)
- **Population:** 100 individuals, initialised from Step 3 seeds and topped up with random feasible permutations
- **Selection:** tournament selection (size 5)
- **Crossover:** hybrid operator:
  - early in the search, the GA often uses one-point order-preserving crossover for broad recombination
  - as stagnation grows, it increasingly uses a precedence-aware merge crossover that builds a feasible child from activities both parents place early
- **Mutation:** one random neighborhood move from:
  - adjacent feasible swap
  - non-adjacent feasible swap
  - bidirectional insertion within the precedence-feasible interval
- **Adaptive exploration:** the mutation rate ramps up from the base rate when the search stagnates
- **Replacement:** steady-state (replace worst individual if offspring is better)
- **Diversification:** restart-on-stagnation keeps a small elite set and refreshes the rest of the population with fresh guided/random seeds
- **Diversity control:** exact-duplicate offspring are rejected unless a few extra perturbations escape the duplicate; fingerprints are tracked with compact 64-bit hashes
- **Selective polishing:** promising offspring near the incumbent receive a cheap forward-backward improvement pass before replacement
- **Alternative stopping rule:** optional schedule-budget mode via `--schedules <count>` for internal A/B testing
- **Termination:** wall-clock time budget (default 28 seconds) or schedule-generation budget
- **Elitism:** always keep the best individual

## Step 5: Forward-Backward Improvement

- Apply a forward-backward improvement pass in two places:
  - periodically on the best solution during GA search and once again at the end
  - selectively on promising offspring before population insertion
  - Forward pass: schedule as-is via SSGS
  - Backward pass: reverse the schedule (schedule from the end), producing new latest-start times
  - Forward again: use the backward-derived order, schedule forward
  - This "double justification" often shaves 1-3 time units off the makespan

## Step 6: Output

- Print start times for activities 1 through n, one integer per line to stdout
- Validate feasibility before output (debug mode)

## Step 7: Testing & Benchmarking

- Run on all 270 J10 instances and 270 J20 instances
- Compare against known optimal/best-known values from PSPLIB where reference tables are available
- For the updated local J10/J20 `.SCH` sets, use the benchmark primarily for feasibility/runtime checking because the harness does not have built-in reference tables for them

## Step 8: Experiments for Report

- See `experiments.md` for full experiment plan with goals, metrics, and success criteria
- **Experiment 1:** Algorithm component ablation (baseline vs priority vs GA vs full)
- **Experiment 2:** Scaling across instance sizes (J30/J60/J90/J120)
- **Experiment 3:** Time budget sensitivity (1s/3s/10s/28s), frozen on the previous solver line because its main purpose is to show anytime behaviour rather than to serve as the latest absolute-quality benchmark
- **Experiment 4:** Priority rule comparison (LFT/MTS/GRD/SPT vs random)
- Scripts in `experiments/`, results in `experiments/results/`

---

## Complexity Analysis

| Component | Time Complexity | Space Complexity |
|---|---|---|
| Parsing | O(n · K) | O(n · K) |
| Priority-value preprocessing / CPM | O(n + E) where E = edges | O(n + E) |
| Single SSGS decode | O(n · T_max · K) worst case, O(n² · K) typical | O(T_max · K) |
| Priority-rule initial population | O(P · n² · K) | O(P · n) |
| GA per generation | O(P · n² · K) for decode of offspring | O(P · n) |
| Total GA | O(G · P · n² · K) where G = generations in time budget | O(P · n + T_max · K) |
| Forward-backward improvement | O(n² · K) per pass | O(T_max · K) |

### Analysis Notes

- **Best case:** loosely constrained instances (large resource capacity) — SSGS with LFT gives near-optimal in O(n² · K)
- **Worst case:** tightly constrained instances where the GA must explore many generations — bounded by the 30-second time budget
- **Empirical scaling:** measure wall-clock time vs n to show sub-linear growth relative to the budget
