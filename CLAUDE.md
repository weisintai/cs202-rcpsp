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
- programFlow.md: end-to-end walkthrough of how solver.cpp works
- cpp_performance.md: C++ optimisation strategy and Python comparison
- solver.cpp: main solver implementation (C++17, single file)
- Makefile: build config
- sm_j10/: J10 benchmark instances (270 .SCH files)
- sm_j20/: J20 benchmark instances (270 .SCH files)

## Run Command
```bash
make                              # compile (optimised)
make debug                        # compile (debug + sanitizer)
./solver <instance_file>          # run on a single instance
./solver sm_j10/PSP1.SCH          # example: J10 instance 1
./solver sm_j20/PSP1.SCH          # example: J20 instance 1
```

## Status Updates
After every implementation step, decision, or meaningful change, immediately
update changelog/currentState.md before continuing to the next step. Do not
batch updates. Write to changelog/currentState.md after each discrete action.

At the end of every session, append a session summary to status.md containing:
- What was implemented or changed this session
- Any decisions made that deviate from plan.md
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