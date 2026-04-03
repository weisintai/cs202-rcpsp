# Experiment Plan

Four experiments to evaluate the solver's performance and justify design decisions in the report. These experiments explain the core pipeline and the final solver's behavior, but they do not by themselves capture every later tuning step. The benchmark records under `benchmark_results/` remain important for documenting the refinement path that led to the current best solver line.

---

## Experiment 1: Algorithm Component Ablation

**Goal:** Quantify the individual contribution of each core pipeline component (priority rules, GA, forward-backward improvement) by disabling them one at a time and measuring the impact on solution quality.

**Configurations:**

| Config | Priority Rules | GA | Forward-Backward |
|--------|:-:|:-:|:-:|
| Baseline (random topo + SSGS) | No | No | No |
| Priority only | Yes | No | No |
| GA only (random init) | No | Yes | No |
| Full pipeline | Yes | Yes | Yes |

**Datasets:** J30, J60

**Metrics:**
- Mean gap to best known (%)
- Number of optimal solutions found
- Mean quality vs best known (%)

**Success criteria:**
- All 4 configurations run on J30 and J60 without errors
- Each component shows measurable improvement over the configuration without it
- Results clearly show which component contributes the most to solution quality
- Results tabulated for the report

**Interpretation note:** This experiment justifies the main architecture. Later improvements such as stronger mutation, restart tuning, duplicate-aware diversity control, and hot-path optimisation should be documented separately as refinement work rather than folded back into this ablation.

---

## Experiment 2: Scaling Across Instance Sizes

**Goal:** Demonstrate how the current full solver degrades as instance size increases, using the same time budget across all datasets.

**Configurations:**
- Full pipeline solver on J30, J60, J90, J120
- 3s GA budget (already collected), optionally 28s for a second data point

**Datasets:** J30, J60, J90, J120

**Metrics:**
- Mean gap to best known (%)
- Optimal match rate (%)
- Max gap to best known (%)
- Mean wall time (s)

**Success criteria:**
- Results available for all 4 datasets
- Clear trend visible: performance degrades with instance size
- Results tabulated and suitable for a line/bar chart in the report

**Interpretation note:** This is the main report-facing benchmark for the final solver line, so sequential reruns are preferable when refreshing these numbers.

---

## Experiment 3: Time Budget Sensitivity

**Goal:** Show the current solver's anytime property -- solution quality improves with more computation time, and a valid schedule is always available.

**Configurations:**
- GA time budgets: 1s, 3s, 10s, 28s
- Wrapper scripts set `--time` to 1s less than the benchmark timeout to allow for parsing/output overhead

**Datasets:** J30, J60

**Metrics:**
- Mean gap to best known (%) at each time budget
- Optimal match rate (%) at each time budget
- Mean quality vs best known (%) at each time budget

**Success criteria:**
- All 4 time budgets complete without errors on both datasets
- Monotonic improvement: longer time budget never produces worse mean results
- Diminishing returns visible (large improvement 1s to 3s, smaller 10s to 28s)
- Results tabulated for a quality-vs-time chart

**Interpretation note:** This experiment measures the submitted solver's time-quality tradeoff. If the final solver line changes materially, this experiment should be refreshed for that line.

---

## Experiment 4: Priority Rule Comparison

**Goal:** Compare the effectiveness of each individual priority rule (LFT, MTS, GRD, SPT) as standalone heuristics, to understand which scheduling intuitions work best for RCPSP.

**Configurations:**
- Each of the 4 priority rules used alone (single biased topo sort + SSGS)
- Random topological order + SSGS as a control
- Total: 5 configurations

**Datasets:** J30, J60

**Metrics:**
- Mean gap to best known (%) per rule
- Optimal match rate (%) per rule
- Number of times each rule produces the best result among the 4 rules

**Success criteria:**
- All 5 configurations run on J30 and J60 without errors
- Clear ranking emerges among the priority rules
- Results tabulated for comparison in the report

**Interpretation note:** This is a heuristic-side study, not a full explanation of the final solver. Its main value is to justify seeding choices such as the later LFT/MTS-biased initialisation.

---

## Change-Validation Workflow

This is the default workflow to use when evaluating future solver changes.

1. **Smoke test first**
   - run a few direct solver commands on representative instances
2. **Internal schedule-budget comparison**
   - compare under a fixed number of generated schedules when the goal is algorithm comparison
3. **Targeted subset run**
   - use regression sets or difficult subsets before any full sweep
4. **Full `3s` wall-clock run**
   - use only for changes that already look promising
   - for cleaner report-facing numbers, run datasets sequentially rather than through a parallel convenience wrapper
5. **Long-budget confirmation**
   - use `10s` or `28s` only for candidate changes that survive the `3s` comparison

Use wall-clock runs for the report and assignment-facing claims.
Use schedule-budget runs for internal A/B testing and search-method comparisons.
For report-quality wall-clock numbers, prefer running datasets sequentially; the parallel helper scripts are primarily convenience wrappers for bulk reruns.
For the final report, pair the four main experiments with a short solver-refinement summary table drawn from the canonical records under `benchmark_results/`.

One exploratory branch also tried multithreading to push more schedule generations through the same wall-clock budget. That did increase throughput, but it also exposed the more important question: were we finding better schedules, or just more schedules? That is what led to the follow-up search-quality checks under a fixed schedule budget, and to a small search experiment aimed at using the extra generations more deliberately. We kept that branch separate from the frozen solver because the threading and search changes landed together, which makes them harder to attribute cleanly in the final submission.

---

## Folder Structure

```
experiments/
├── experiment1/          # Algorithm Component Ablation
│   ├── scripts/          # Wrapper scripts and run script
│   ├── results/          # Benchmark output (summary.json, results.csv)
│   └── README.md         # Experiment description
├── experiment2/          # Scaling Across Instance Sizes
│   ├── scripts/
│   ├── results/
│   └── README.md
├── experiment3/          # Time Budget Sensitivity
│   ├── scripts/
│   ├── results/
│   └── README.md
└── experiment4/          # Priority Rule Comparison
    ├── scripts/
    ├── results/
    └── README.md
```

General benchmark results (non-experiment) are stored in `benchmark_results/`.
