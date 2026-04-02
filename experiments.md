# Experiment Plan

Four experiments to evaluate the solver's performance and justify design decisions in the report.

---

## Experiment 1: Algorithm Component Ablation

**Goal:** Quantify the individual contribution of each algorithm component (priority rules, GA, forward-backward improvement) by disabling them one at a time and measuring the impact on solution quality.

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

---

## Experiment 2: Scaling Across Instance Sizes

**Goal:** Demonstrate how solver performance degrades as instance size increases, using the same time budget across all datasets.

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

---

## Experiment 3: Time Budget Sensitivity

**Goal:** Show the solver's anytime property -- solution quality improves with more computation time, and a valid schedule is always available.

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
5. **Long-budget confirmation**
   - use `10s` or `28s` only for candidate changes that survive the `3s` comparison

Use wall-clock runs for the report and assignment-facing claims.
Use schedule-budget runs for internal A/B testing and search-method comparisons.

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
