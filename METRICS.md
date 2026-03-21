# RCPSP Metrics To Optimize

## What the course is actually grading

Based on `Project.pdf`, the grading signal for RCPSP is:

- return a **valid schedule**
- within the **30 second wall-clock budget per instance**
- with the **lowest possible makespan**
- on **harder hidden benchmark instances**, not just the public ones

The PDF explicitly says the objective is to minimize project makespan, that late solutions are not scored, and that evaluation is based on solution quality on more complex benchmark instances. It does **not** define a more detailed scoring formula, so the practical inference is:

> the real evaluation metric is makespan quality on unseen instances, with validity and deadline compliance as hard constraints

## Metrics We Should Optimize

### 1. Validity rate

This is non-negotiable. A schedule that violates precedence or resource capacity is effectively useless.

- Why it matters: invalid schedules should be treated as zero-value submissions
- Optimistic target: **100% valid schedules**

### 2. On-time rate

The solver must finish within the grading budget.

- Why it matters: the PDF says a solution returned after the deadline will not be scored
- Optimistic target: **100% of instances finish under 30s**
- Practical runtime target: **p95 runtime under 20s**, **p99 under 28s**

### 3. Makespan

This is the primary optimization objective in the problem definition.

- Why it matters: lower makespan is the core quality metric
- Optimistic target: **minimize makespan as the first priority on every feasible instance**

Because hidden-instance optima are unknown, we should track makespan quality through public-set proxies.

### 4. Generalization / anti-overfitting

The PDF explicitly warns against over-optimizing to the given test instances.

- Why it matters: hidden evaluation instances will be more complex
- Optimistic target: improvements on `sm_j20` should not come with clear regressions on `sm_j30`, `testset_ubo20`, or `testset_ubo50`

## Best Internal Proxy Metrics

These are the metrics we should use during development because they map well to the actual grading goal.

| Metric | Why we should track it | Optimistic target |
| --- | --- | --- |
| `exact_match_rate` on public exact-reference sets | Best proxy for hidden makespan quality when the optimum is known | `sm_j10 @ 1.0s`: **100%**; `sm_j20 @ 1.0s`: **>= 85%** |
| `avg_exact_ratio_to_reference` | Measures how far we are from the known optimum even when we miss exact | `sm_j20 @ 1.0s`: **<= 1.015** |
| `unknown_against_known_reference` | Measures failure to classify or finish strong enough within budget | `sm_j10 @ 1.0s`: **0**; `sm_j20 @ 1.0s`: **0-2** |
| `over_budget` | Counts instances whose wall-clock runtime exceeded the allowed budget | **0** on every guardrail set |
| `false_infeasible` | A severe correctness failure on feasible instances | **0** |
| `avg_ratio` to temporal lower bound | Useful fallback on sets where exact references are weaker or mixed | trend down every iteration; avoid accepting regressions |
| `avg_runtime_seconds`, `p95 runtime`, `p99 runtime` | Protects us from passing public tests but timing out on the grader | well below the 30s cap |

## Suggested Guardrail Targets

These are optimistic but still grounded in the current repo notes and benchmark style.

| Benchmark check | Optimistic target |
| --- | --- |
| `sm_j10 @ 1.0s` | keep **100% exact-match rate** |
| `sm_j20 @ 1.0s` | reach **>= 85% exact-match rate**, `avg_exact_ratio_to_reference <= 1.015`, drive unknowns toward **0**, and keep **0 over-budget** instances |
| `sm_j30 @ 0.1s` | reach **>= 60% exact-match rate**, **<= 15 unknowns**, and **0 over-budget** |
| `testset_ubo20 @ 0.1s` | reach **>= 70% exact-match rate**, **0 unknowns**, and **0 over-budget** |
| `testset_ubo50 @ 0.1s` | reach **>= 45% exact-match rate**, **<= 15 unknowns**, and **0 over-budget** |

## Priority Order

When metrics conflict, optimize in this order:

1. validity
2. under-30s completion
3. lower makespan
4. robustness across benchmark families
5. average runtime improvements beyond the safety margin

That ordering matches the project brief: a fast invalid schedule is worthless, a slow optimal schedule is unscored, and among valid on-time schedules the lower makespan should win.
