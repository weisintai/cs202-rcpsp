#include "priority.h"
#include <algorithm>
#include <queue>
#include <functional>
#include <numeric>
#include <string>

// ── Compute Latest Finish Time for each activity ────────────────────────────
// Backward pass from sink: LFT[sink] = CPM makespan, then work backwards.
// Activities with earlier LFT should be scheduled first (tighter deadline).
static std::vector<int> compute_lft(const Problem& p) {
    int total = p.n + 2;

    // Forward pass: compute earliest start/finish times
    std::vector<int> est(total, 0);
    std::vector<int> eft(total, 0);

    // Topological order via Kahn's for the forward pass
    std::vector<int> in_deg(total, 0);
    for (int i = 0; i < total; i++)
        in_deg[i] = (int)p.predecessors[i].size();

    std::queue<int> q;
    for (int i = 0; i < total; i++)
        if (in_deg[i] == 0) q.push(i);

    while (!q.empty()) {
        int u = q.front(); q.pop();
        eft[u] = est[u] + p.duration[u];
        for (int v : p.successors[u]) {
            est[v] = std::max(est[v], eft[u]);
            if (--in_deg[v] == 0) q.push(v);
        }
    }

    int cpm_makespan = eft[p.n + 1];

    // Backward pass: compute latest finish times
    std::vector<int> lft(total, cpm_makespan);

    // Reverse topological order via Kahn's on reversed graph
    std::vector<int> out_deg(total, 0);
    for (int i = 0; i < total; i++)
        out_deg[i] = (int)p.successors[i].size();

    for (int i = 0; i < total; i++)
        if (out_deg[i] == 0) q.push(i);

    while (!q.empty()) {
        int u = q.front(); q.pop();
        for (int v : p.predecessors[u]) {
            lft[v] = std::min(lft[v], lft[u] - p.duration[u]);
            if (--out_deg[v] == 0) q.push(v);
        }
    }

    return lft;
}

// ── Compute total number of transitive successors ───────────────────────────
// More successors = higher priority (should be scheduled earlier).
static std::vector<int> compute_total_successors(const Problem& p) {
    int total = p.n + 2;
    std::vector<int> count(total, 0);
    std::vector<bool> visited(total, false);

    // DFS from each node to count reachable successors
    // Use reverse topological order for efficiency (bottom-up DP)
    std::vector<int> out_deg(total, 0);
    for (int i = 0; i < total; i++)
        out_deg[i] = (int)p.successors[i].size();

    std::queue<int> q;
    for (int i = 0; i < total; i++)
        if (out_deg[i] == 0) q.push(i);

    std::vector<int> rev_order;
    rev_order.reserve(total);
    while (!q.empty()) {
        int u = q.front(); q.pop();
        rev_order.push_back(u);
        for (int v : p.predecessors[u]) {
            if (--out_deg[v] == 0) q.push(v);
        }
    }

    // Bottom-up: count[i] = sum(1 + count[j]) for all direct successors j
    // This counts direct successors + their transitive successors
    for (int u : rev_order) {
        count[u] = 0;
        for (int v : p.successors[u]) {
            count[u] += 1 + count[v];
        }
    }

    return count;
}

// ── Priority-biased topological sort ────────────────────────────────────────
// Modified Kahn's: among eligible activities (in-degree 0), pick the one
// with the lowest priority value first.
static std::vector<int> biased_topo_sort(const Problem& p, const std::vector<int>& priority) {
    int total = p.n + 2;
    std::vector<int> in_deg(total, 0);
    for (int i = 0; i < total; i++)
        in_deg[i] = (int)p.predecessors[i].size();

    // Min-heap on priority value
    auto cmp = [&](int a, int b) { return priority[a] > priority[b]; };
    std::priority_queue<int, std::vector<int>, decltype(cmp)> pq(cmp);

    for (int i = 0; i < total; i++)
        if (in_deg[i] == 0) pq.push(i);

    std::vector<int> order;
    order.reserve(total);

    while (!pq.empty()) {
        int u = pq.top(); pq.pop();
        order.push_back(u);
        for (int v : p.successors[u]) {
            if (--in_deg[v] == 0) {
                pq.push(v);
            }
        }
    }

    return order;
}

// ── Randomized priority-biased topological sort ─────────────────────────────
// At each step, sample uniformly from the best few eligible activities by the
// chosen priority rule instead of always taking the single best one.
static std::vector<int> randomized_biased_topo_sort(const Problem& p,
                                                    const std::vector<int>& priority,
                                                    int candidate_pool,
                                                    std::mt19937& rng) {
    int total = p.n + 2;
    std::vector<int> in_deg(total, 0);
    for (int i = 0; i < total; i++)
        in_deg[i] = (int)p.predecessors[i].size();

    std::vector<int> eligible;
    for (int i = 0; i < total; i++) {
        if (in_deg[i] == 0) eligible.push_back(i);
    }

    std::vector<int> order;
    order.reserve(total);

    while (!eligible.empty()) {
        std::sort(eligible.begin(), eligible.end(), [&](int a, int b) {
            if (priority[a] != priority[b]) return priority[a] < priority[b];
            return a < b;
        });

        int pool = std::min(candidate_pool, (int)eligible.size());
        std::uniform_int_distribution<int> dist(0, pool - 1);
        int idx = dist(rng);
        int u = eligible[idx];

        eligible[idx] = eligible.back();
        eligible.pop_back();

        order.push_back(u);
        for (int v : p.successors[u]) {
            if (--in_deg[v] == 0) {
                eligible.push_back(v);
            }
        }
    }

    return order;
}

// ── Priority values by rule name ────────────────────────────────────────────
static std::vector<int> compute_priority_values(const Problem& p, const std::string& rule) {
    int total = p.n + 2;
    std::vector<int> priority(total, 0);

    if (rule == "lft") {
        // Lower LFT = tighter deadline = schedule first
        priority = compute_lft(p);
    } else if (rule == "mts") {
        // More total successors = higher priority = lower value for min-heap
        auto counts = compute_total_successors(p);
        for (int i = 0; i < total; i++)
            priority[i] = -counts[i];  // negate so min-heap picks highest count
    } else if (rule == "grd") {
        // Greater total resource demand = higher priority
        for (int i = 0; i < total; i++) {
            int sum = 0;
            for (int k = 0; k < p.K; k++)
                sum += p.resource[i][k];
            priority[i] = -sum;  // negate for min-heap
        }
    } else if (rule == "spt") {
        // Shorter duration = higher priority
        for (int i = 0; i < total; i++)
            priority[i] = p.duration[i];
    }

    return priority;
}

// ── Public: priority-biased sort by rule name ───────────────────────────────
std::vector<int> priority_sort(const Problem& p, const std::string& rule) {
    return biased_topo_sort(p, compute_priority_values(p, rule));
}

// ── Public: random feasible topological order ───────────────────────────────
std::vector<int> random_sort(const Problem& p, std::mt19937& rng) {
    int total = p.n + 2;
    std::vector<int> in_deg(total, 0);
    for (int i = 0; i < total; i++)
        in_deg[i] = (int)p.predecessors[i].size();

    std::vector<int> eligible;
    for (int i = 0; i < total; i++)
        if (in_deg[i] == 0) eligible.push_back(i);

    std::vector<int> order;
    order.reserve(total);

    while (!eligible.empty()) {
        // Pick a random eligible activity
        std::uniform_int_distribution<int> dist(0, (int)eligible.size() - 1);
        int idx = dist(rng);
        int u = eligible[idx];

        // Remove from eligible (swap with last)
        eligible[idx] = eligible.back();
        eligible.pop_back();

        order.push_back(u);

        for (int v : p.successors[u]) {
            if (--in_deg[v] == 0) {
                eligible.push_back(v);
            }
        }
    }

    return order;
}

// ── Public: generate all initial solutions ──────────────────────────────────
std::vector<std::vector<int>> generate_initial_solutions(const Problem& p, int num_random, std::mt19937& rng) {
    std::vector<std::vector<int>> solutions;

    // One solution per priority rule
    for (const auto& rule : {"lft", "mts", "grd", "spt"}) {
        solutions.push_back(priority_sort(p, rule));
    }

    // Replace most pure-random seeds with randomized strong-rule variants.
    int num_lft = num_random / 2;
    int num_mts = num_random / 3;
    int num_pure_random = num_random - num_lft - num_mts;

    auto lft_priority = compute_priority_values(p, "lft");
    auto mts_priority = compute_priority_values(p, "mts");

    for (int i = 0; i < num_lft; i++) {
        solutions.push_back(randomized_biased_topo_sort(p, lft_priority, 3, rng));
    }

    for (int i = 0; i < num_mts; i++) {
        solutions.push_back(randomized_biased_topo_sort(p, mts_priority, 3, rng));
    }

    for (int i = 0; i < num_pure_random; i++) {
        solutions.push_back(random_sort(p, rng));
    }

    return solutions;
}
