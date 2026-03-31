# C++ Performance Optimisations for RCPSP Solver

## Memory Layout & Cache Efficiency

- **Flat arrays over nested containers:** store the resource usage profile as a contiguous `int usage[T_max * K]` instead of `vector<vector<int>>`. This keeps data in a single cache line during SSGS inner loops, avoiding pointer chasing.
- **Struct of Arrays (SoA):** store activity data as separate arrays (`int durations[N]`, `int resources[N][K]`) rather than an array of Activity structs. The SSGS inner loop reads durations and resources in separate passes — SoA keeps each sweep cache-hot.
- **Pre-allocate everything:** reserve all vectors and arrays at startup using the known `n`, `K`, `T_max` bounds. Zero heap allocation during the GA loop. Python reallocates on every list append; C++ with pre-sized arrays does not.
- **Stack-allocate small arrays:** for J10/J20 (n <= 22 including dummies, K <= 5), activity lists and resource vectors fit in stack arrays (`std::array` or plain C arrays), avoiding heap allocation entirely.

## SSGS Hot Loop

- **Inline the resource feasibility check:** the innermost loop checks `usage[t][k] + r[activity][k] <= capacity[k]` for every candidate timestep. Mark this function `__attribute__((always_inline))` or keep it in the header so the compiler inlines it.
- **Early break on resource conflict:** if any single resource k exceeds capacity at time t, break immediately — don't check the remaining resources or remaining timesteps in that window.
- **Avoid recomputing predecessor finish times:** cache `earliest_start[activity] = max(finish_time[pred])` once per activity, not per candidate timestep.

## Genetic Algorithm Throughput

- **Avoid copying activity lists:** use index-based references into a flat population array `int population[P][N]`. Crossover writes directly into offspring buffer, no temporary vectors.
- **Fast PRNG:** use `std::mt19937` seeded once, or even a simpler xorshift64 for mutation/selection random numbers. Python's `random.random()` has significant per-call overhead; a C++ xorshift is a single multiply-shift.
- **Compile-time constants where possible:** if K is always <= 5, template the resource loop or unroll it. The compiler can vectorise a fixed-length inner loop far more aggressively.

## Compiler Flags

- Compile with `-O2 -march=native` for auto-vectorisation and architecture-specific instructions.
- Use `-flto` (link-time optimisation) to allow cross-function inlining.
- Profile-guided optimisation (`-fprofile-generate` / `-fprofile-use`) on the J10/J20 benchmarks can yield an additional 10-20% speedup on the hot SSGS path.

## Threading (std::thread)

- **Parallel population evaluation:** split the population across `std::thread` workers. Each thread decodes its assigned individuals via SSGS independently — no shared mutable state needed, just read-only problem data.
- **Thread pool, not thread-per-generation:** spawn threads once at startup and reuse them via a simple work queue to avoid thread creation overhead each generation.
- Unlike Python (GIL-limited), C++ threads achieve true parallelism. On a 4-core grading machine, this can ~4x the number of GA generations per second.

## Quantified Impact vs Python

| Optimisation | Estimated Speedup vs Python |
|---|---|
| Compiled native code (baseline) | ~50-100x |
| Cache-friendly flat arrays | +2-3x on top of baseline |
| Inlined SSGS hot loop | +1.5-2x (avoids function call overhead) |
| Fast PRNG (xorshift vs Python random) | ~10x per random call |
| True multi-threading (no GIL) | ~Nx on N cores |
| **Combined** | **~200-500x more GA generations in 30s** |

This means where Python might evaluate ~50,000 schedules in 30 seconds, C++ can evaluate 10-25 million — directly translating to better solutions on harder instances.
