#include "ssgs.h"
#include <algorithm>

Schedule ssgs(const Problem& p, const std::vector<int>& activity_list) {
    int total = p.n + 2;

    // Upper bound on horizon: sum of all durations
    int horizon = 0;
    for (int i = 0; i < total; i++) horizon += p.duration[i];
    horizon = std::max(horizon, 1);

    // Resource usage profile: usage[t * K + k] = units of resource k used at time t
    std::vector<int> usage(horizon * p.K, 0);

    std::vector<int> start_time(total, 0);
    std::vector<int> finish_time(total, 0);

    for (int act : activity_list) {
        int dur = p.duration[act];

        // Earliest start from precedence: max of all predecessor finish times
        int es = 0;
        for (int pred : p.predecessors[act]) {
            es = std::max(es, finish_time[pred]);
        }

        if (dur == 0) {
            // Dummy activity or zero-duration — no resource check needed
            start_time[act] = es;
            finish_time[act] = es;
            continue;
        }

        // Find earliest feasible start time >= es where resources are available
        // for the entire duration [t, t + dur)
        int t = es;
        while (true) {
            bool feasible = true;
            for (int tau = t; tau < t + dur; tau++) {
                for (int k = 0; k < p.K; k++) {
                    if (usage[tau * p.K + k] + p.resource[act][k] > p.capacity[k]) {
                        feasible = false;
                        // Jump to tau+1 as the next candidate start
                        t = tau + 1;
                        break;
                    }
                }
                if (!feasible) break;
            }
            if (feasible) break;
        }

        // Schedule activity at time t
        start_time[act] = t;
        finish_time[act] = t + dur;

        // Update resource usage
        for (int tau = t; tau < t + dur; tau++) {
            for (int k = 0; k < p.K; k++) {
                usage[tau * p.K + k] += p.resource[act][k];
            }
        }
    }

    Schedule sched;
    sched.start_time = std::move(start_time);
    sched.makespan = sched.start_time[p.n + 1];
    return sched;
}
