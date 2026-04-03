# Report Format

6 to 10 pages PDF. 35% of grade. All member names and student IDs must appear.

---

## 1. Introduction (0.5-1 page)

- Problem definition: RCPSP, precedence constraints, resource constraints, makespan minimisation
- Brief overview of approach and results

## 2. Algorithm Design (2-3 pages)

- 2.1 Solution representation (activity list)
- 2.2 SSGS decoder (pseudocode)
- 2.3 Priority rule heuristics (LFT, MTS, GRD, SPT)
- 2.4 Genetic algorithm (pseudocode for selection, crossover, mutation)
- 2.5 Forward-backward improvement (pseudocode)
- 2.6 Design decisions and justification (why GA over other metaheuristics, why activity list + SSGS)

## 3. Complexity Analysis (0.5-1 page)

- Time and space complexity per component
- Overall complexity bounded by time budget
- Complexity table (from implementation.md)

## 4. Experiments (2-3 pages)

- 4.1 Experiment 1: Algorithm component ablation — contribution of each component
- 4.2 Experiment 2: Scaling across instance sizes — J30 through J120
- 4.3 Experiment 3: Time budget sensitivity — anytime property
- 4.4 Experiment 4: Priority rule comparison — which heuristic works best
- Add a short refinement-history table or subsection after the four experiments so later solver improvements from benchmark-driven tuning are documented explicitly
- Each experiment includes: setup, results table/chart, brief analysis
- J10 and J20 can be discussed briefly for parser support and feasibility/runtime status, but the main quality comparisons should focus on PSPLIB datasets where reference values are available

## 5. Discussion (1-1.5 pages)

- 5.1 Strengths: what works well and why
- 5.2 Failure cases: where the solver struggles (large instances, tight resources)
- 5.3 Limitations and future work

## 6. Conclusion (0.5 page)

- Summary of results and key takeaways

## References (not counted in page limit)

---

## Notes

- Target: ~7-9 pages within the 6-10 range
- Pseudocode required in algorithm design section
- Use J30-J120 as the main quantitative benchmark set because the harness includes PSPLIB reference values there
- Use J10/J20 mainly as assignment-format support and feasibility/runtime evidence unless separate reference tables are added
- Treat Experiments 1 and 4 mainly as design-justification evidence, Experiment 2 as the main final-solver benchmark, and Experiment 3 as the final-solver time-quality curve
