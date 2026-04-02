# Report Notes

This file is a staging area for report-ready points that have already been supported by our experiments.

## Experiment-Guided Biased Seeding

### What changed

We changed the initial GA population from being mostly generic random topological orders to a more guided mix:
- randomized `LFT`-biased seeds
- randomized `MTS`-biased seeds
- a smaller pure-random remainder

This is not a blind tweak. It was motivated directly by the priority-rule experiment.

### Why we changed it

Experiment 4 compared the standalone priority rules on `J30` and `J60`:
- `LFT` was the strongest rule overall
- `MTS` was consistently the second-strongest
- `GRD` and `SPT` were much weaker and often close to or worse than random

So instead of spending most of the initial population budget on uninformed random seeds, we biased the population toward the two rules that actually worked best in our own experiments.

### How to describe it in the report

Suggested framing:

> We first evaluated several priority rules independently. The experiment showed that `LFT` produced the best schedules most often, with `MTS` consistently second. This motivated a refinement of the GA initialisation strategy: rather than filling the population mainly with pure-random feasible permutations, we generated a larger share of randomized `LFT`- and `MTS`-biased activity lists. The goal was to preserve diversity while concentrating the search near stronger heuristic regions.

### Evidence we already have

From the recorded experiment results:
- priority-only mode improved after biased seeding
- the full pipeline also improved after biased seeding
- the gains were most visible on harder datasets such as `J60` and `J120`

Numbers already documented in `currentState.md`:
- Experiment 1:
  - `J30` priority mode: `57.7% -> 60.0%` optimal
  - `J60` priority mode: `59.4% -> 62.5%` optimal
  - full pipeline gap improved on both `J30` and `J60`
- Experiment 2:
  - mean gap improved across `J30`, `J60`, `J90`, and `J120`

### Short version for the report

> The seeding strategy was refined using evidence from Experiment 4. Since `LFT` and `MTS` clearly outperformed the other priority rules, we shifted the GA initial population toward randomized `LFT`/`MTS`-biased seeds instead of relying mainly on pure-random topological orders. This produced better aggregate results in the later benchmarks.
