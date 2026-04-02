#include "improvement.h"
#include "ssgs.h"
#include <algorithm>
#include <numeric>

// ── Backward SSGS ──────────────────────────────────────────────────────────
// Schedules activities as late as possible while respecting precedence and
// resource constraints. Processes activities in reverse order of their start
// times (latest-scheduled first).
// Returns a schedule with latest-start times and the same makespan.
static Schedule backward_ssgs(const Problem& p, const Schedule& fwd) {
    int total = p.n + 2;
    int makespan = fwd.makespan;

    // Sort activities by start time descending (latest first)
    std::vector<int> order(total);
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        return fwd.start_time[a] > fwd.start_time[b];
    });

    // Resource usage profile
    int horizon = makespan + 1;
    std::vector<int> usage(horizon * p.K, 0);

    std::vector<int> start_time(total, 0);
    std::vector<int> finish_time(total, 0);

    for (int act : order) {
        int dur = p.duration[act];

        // Latest finish from successors: min of all successor start times
        int lf = makespan;
        for (int succ : p.successors[act]) {
            lf = std::min(lf, start_time[succ]);
        }

        if (dur == 0) {
            start_time[act] = lf;
            finish_time[act] = lf;
            continue;
        }

        // Latest start: lf - dur, then scan backwards for resource feasibility
        int ls = lf - dur;

        while (ls >= 0) {
            bool feasible = true;
            for (int tau = ls; tau < ls + dur; tau++) {
                for (int k = 0; k < p.K; k++) {
                    if (usage[tau * p.K + k] + p.resource[act][k] > p.capacity[k]) {
                        feasible = false;
                        ls = tau - dur;  // try earlier
                        break;
                    }
                }
                if (!feasible) break;
            }
            if (feasible) break;
        }

        // Clamp to 0
        if (ls < 0) ls = 0;

        start_time[act] = ls;
        finish_time[act] = ls + dur;

        // Update resource usage
        for (int tau = ls; tau < ls + dur; tau++) {
            for (int k = 0; k < p.K; k++) {
                usage[tau * p.K + k] += p.resource[act][k];
            }
        }
    }

    Schedule bwd;
    bwd.start_time = std::move(start_time);
    bwd.makespan = makespan;
    return bwd;
}

// ── Extract activity order from a schedule ──────────────────────────────────
// Sort activities by start time ascending — this gives a precedence-feasible
// order that can be fed back into forward SSGS.
static std::vector<int> order_from_schedule(const Problem& p, const Schedule& sched) {
    int total = p.n + 2;
    std::vector<int> order(total);
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        if (sched.start_time[a] != sched.start_time[b])
            return sched.start_time[a] < sched.start_time[b];
        return a < b;  // stable tie-break by activity id
    });
    return order;
}

// ── Public: forward-backward improvement ────────────────────────────────────
Schedule forward_backward_improve(const Problem& p, const Schedule& initial) {
    Schedule best = initial;

    for (int iter = 0; iter < 10; iter++) {
        // Backward pass: schedule as late as possible
        Schedule bwd = backward_ssgs(p, best);

        // Extract order from backward schedule (earliest start first)
        std::vector<int> new_order = order_from_schedule(p, bwd);

        // Forward pass: re-schedule with the new order
        Schedule fwd = ssgs(p, new_order);

        if (fwd.makespan < best.makespan) {
            best = fwd;
        } else {
            break;  // no improvement, stop
        }
    }

    return best;
}
