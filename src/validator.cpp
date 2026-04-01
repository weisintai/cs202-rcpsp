#include "validator.h"
#include <iostream>
#include <vector>

bool validate(const Problem& p, const Schedule& sched) {
    int total = p.n + 2;
    bool ok = true;

    // Check precedence
    for (int i = 0; i < total; i++) {
        for (int j : p.successors[i]) {
            if (sched.start_time[j] < sched.start_time[i] + p.duration[i]) {
                std::cerr << "PRECEDENCE VIOLATION: " << i << " -> " << j
                          << " (S[" << j << "]=" << sched.start_time[j]
                          << " < S[" << i << "]+" << p.duration[i]
                          << "=" << sched.start_time[i] + p.duration[i] << ")\n";
                ok = false;
            }
        }
    }

    // Check resource capacity at every timestep
    int horizon = sched.makespan;
    for (int t = 0; t < horizon; t++) {
        std::vector<int> used(p.K, 0);
        for (int i = 0; i < total; i++) {
            if (sched.start_time[i] <= t && t < sched.start_time[i] + p.duration[i]) {
                for (int k = 0; k < p.K; k++) {
                    used[k] += p.resource[i][k];
                }
            }
        }
        for (int k = 0; k < p.K; k++) {
            if (used[k] > p.capacity[k]) {
                std::cerr << "RESOURCE VIOLATION at t=" << t
                          << " resource " << k << ": " << used[k]
                          << " > " << p.capacity[k] << "\n";
                ok = false;
            }
        }
    }

    if (ok) std::cerr << "Schedule is FEASIBLE" << std::endl;
    return ok;
}
