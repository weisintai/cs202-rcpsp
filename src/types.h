#ifndef TYPES_H
#define TYPES_H

#include <vector>

// ── Problem data ────────────────────────────────────────────────────────────
struct Problem {
    int n;  // number of real activities (excluding dummies 0 and n+1)
    int K;  // number of renewable resource types
    // Indexed 0..n+1 (0 = super-source, n+1 = super-sink)
    std::vector<int> duration;
    std::vector<std::vector<int>> resource;    // resource[i][k]
    std::vector<std::vector<int>> successors;  // successors[i] = list of j
    std::vector<std::vector<int>> predecessors;// predecessors[j] = list of i
    std::vector<int> capacity;                 // capacity[k]
};

// ── Schedule result ─────────────────────────────────────────────────────────
struct Schedule {
    std::vector<int> start_time;  // start_time[i] for activity i
    int makespan;                 // = start_time[n+1]
};

#endif
