# CS202 RCPSP Project

## Session Initialisation
At the start of every session:
1. Read implementation.md and ./changelog/currentState.md
2. Internally list the project criteria, steps taken, and decisions made
3. Print current project status and the next step before doing anything else
Do not proceed with any work until this is complete.

## File Structure
- implementation.md: implementation plan and algorithm decisions
- changelog/currentState.md: running log of progress, next steps, and decisions
- programFlow.md: end-to-end walkthrough of how the solver works
- cpp_performance.md: C++ optimisation strategy and Python comparison
- Makefile: build config
- src/: solver source code (C++17, multi-file)
  - types.h: Problem and Schedule structs
  - parser.h/.cpp: format detection + .sm and .SCH parsers
  - graph.h/.cpp: topological sort + cycle-breaking cleanup
  - ssgs.h/.cpp: Serial Schedule Generation Scheme decoder
  - validator.h/.cpp: feasibility checker (precedence + resource)
  - main.cpp: entry point
- sm_j10/: J10 benchmark instances (270 .SCH files, ProGenMax format)
- sm_j20/: J20 benchmark instances (270 .SCH files, ProGenMax format)
- datasets/psplib/: standard PSPLIB benchmark instances (.sm format)
  - j30/instances/: 480 files (30 activities)
  - j60/instances/: 480 files (60 activities)
  - j90/instances/: 480 files (90 activities)
  - j120/instances/: 600 files (120 activities)
- scripts/benchmark_rcpsp.py: benchmarking script
- experiments.md: experiment plan (goals, metrics, success criteria)
- experiments/: experiment scripts and results

## Datasets
All test datasets live under `./datasets/`. Within each dataset folder, the
`instances/` subfolder contains the actual instance files. For example:
`./datasets/psplib/j30/instances/j3010_1.sm`

## Run Command
```bash
make                              # compile (optimised)
make debug                        # compile (debug + sanitizer)
./solver <instance_file>          # run (default 28s GA budget)
./solver <instance_file> --time 5 # run with 5s GA budget
make bench-j30                    # benchmark all J30 instances
make bench-j60                    # benchmark all J60 instances
make bench-j120                   # benchmark all J120 instances
```

## Status Updates
After every implementation step, decision, or meaningful change, immediately
update changelog/currentState.md before continuing to the next step. Update programFlow.md accordingly if any changes or updates were made to the algorithm.
Do not batch updates. Write to changelog/currentState.md after each discrete action.


At the end of every session, append a session summary to changelog/currentState.md containing:
- What was implemented or changed this session
- Any decisions made that deviate from plan.md
- Benchmark results from this session
- Next steps for the following session

## Hard Constraints
- No external optimisation libraries (OR-Tools, Gurobi, PuLP, CPLEX are banned)
- Standard library only, including standard library threading
- Solution must return within 30 seconds per instance
- Resource capacity must never be exceeded at any timestep
- Do not overfit to J10 and J20. Grading includes unseen instances.
- Output: start times for activities 1 through n, one integer per line to stdout

## Deliverables
- Code: solver with README stating exact run command (40% of grade)
- Report: 6 to 10 pages PDF with sections: problem definition, algorithm design 
  with pseudocode, complexity analysis, experiments on J10 and J20 vs best known 
  values, and discussion of strengths and failure cases (35% of grade)
- Slides: 8 to 12 slides covering motivation, algorithm walkthrough with worked 
  example, experimental results, and conclusion (25% of grade)
- All member names and student IDs must appear in report and README
- Submit as GroupXX_CS202_Project.zip