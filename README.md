# RCPSP Solver

A solver for the Resource Constrained Project Scheduling Problem (RCPSP) built for CS202. Given a set of activities with durations, resource demands, and precedence constraints, the solver minimises the project makespan while ensuring resource capacity is never exceeded at any timestep.

## Algorithm

The submission solver uses a Genetic Algorithm with a Serial Schedule Generation Scheme (SSGS) decoder. The pipeline is fixed:

1. **Parse** input file (`.sm` or `.SCH` format)
2. **Generate initial solutions** using priority rules (LFT, MTS, GRD, SPT) and biased randomized permutations (LFT/MTS-weighted seeding)
3. **Decode** each activity order with SSGS to obtain a feasible schedule
4. **Evolve** the population using tournament selection, hybrid crossover, adaptive mutation, and a richer activity-list mutation neighborhood
5. **Diversify** with restart-on-stagnation and duplicate-aware population control when the GA plateaus
6. **Improve** strong candidates with forward-backward double justification
7. **Validate and output** start times for each activity

## Build

Requires a C++17 compiler (g++ or clang++).

```bash
make              # optimised build
make debug        # debug build with AddressSanitizer
make clean        # remove binaries
```

## Usage

```bash
./solver <instance_file>
```

This is the exact submission command. The binary always runs the full solver pipeline:

1. priority-rule seeding
2. genetic search
3. restart-on-stagnation and duplicate-aware diversity control
4. forward-backward improvement

The solver is anytime: it keeps track of the incumbent best schedule throughout the search and returns the best schedule found so far. The default wall-clock budget is `29s`, with the solver still enforcing an internal cap below the hard `30s` grading deadline.

### Optional Flag

| Flag | Description | Default |
|------|-------------|---------|
| `--time <seconds>` | Optional wall-clock search budget, capped at `29` seconds for submission safety | `29` |

### Examples

```bash
# Submission command
./solver datasets/psplib/j30/instances/j301_1.sm

# Run with a 5-second wall-clock search budget
./solver datasets/psplib/j30/instances/j301_1.sm --time 5
```

### Output

- **stdout:** Start times for activities 1 through n, comma-separated on one line
- **stderr:** Feasibility check result and makespan

If no feasible schedule is found, the solver prints `-1` to stdout.

The reported makespan is the true project finish time, i.e. the maximum finish time over all activities. On well-formed PSPLIB instances this is the same as the dummy-sink start time, but the true finish-time definition is more robust for local `.SCH` files where some terminal jobs may not be connected to the sink.

## Datasets

| Dataset | Instances | Activities | Format |
|---------|-----------|------------|--------|
| J10 | 270 | 10 | `.SCH` (local compact RCPSP-style format) |
| J20 | 270 | 20 | `.SCH` (local compact RCPSP-style format) |
| J30 | 480 | 30 | `.sm` (PSPLIB) |
| J60 | 480 | 60 | `.sm` (PSPLIB) |
| J90 | 480 | 90 | `.sm` (PSPLIB) |
| J120 | 600 | 120 | `.sm` (PSPLIB) |

Datasets live under `datasets/psplib/` (`.sm` format) and `sm_j10/`, `sm_j20/` (`.SCH` format).

## Team

- Anson Koh — 01458387
- Darrius Ng — 01518085
- Htet Shwe — 01506183
- Joe Tan — 01458659
- Tai Wei Sin — 01508341
