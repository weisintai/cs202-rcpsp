#include "graph.h"
#include <algorithm>

std::vector<int> topological_sort(const Problem& p) {
    int total = p.n + 2;
    std::vector<int> in_degree(total, 0);
    for (int i = 0; i < total; i++) {
        in_degree[i] = (int)p.predecessors[i].size();
    }

    std::vector<bool> processed(total, false);
    std::vector<int> queue;
    for (int i = 0; i < total; i++) {
        if (in_degree[i] == 0) queue.push_back(i);
    }

    std::vector<int> order;
    order.reserve(total);
    int head = 0;
    while ((int)order.size() < total) {
        // Process everything currently in the queue
        while (head < (int)queue.size()) {
            int u = queue[head++];
            if (processed[u]) continue;
            processed[u] = true;
            order.push_back(u);
            for (int v : p.successors[u]) {
                if (!processed[v] && --in_degree[v] == 0) {
                    queue.push_back(v);
                }
            }
        }

        if ((int)order.size() >= total) break;

        // Cycle detected — force the unprocessed node with lowest in-degree
        int best = -1;
        for (int i = 0; i < total; i++) {
            if (!processed[i]) {
                if (best == -1 || in_degree[i] < in_degree[best]) {
                    best = i;
                }
            }
        }
        if (best != -1) {
            in_degree[best] = 0;
            queue.push_back(best);
        }
    }
    return order;
}

void remove_back_edges(Problem& p, const std::vector<int>& order) {
    int total = p.n + 2;
    std::vector<int> pos(total);  // position of each activity in the order
    for (int i = 0; i < total; i++) {
        pos[order[i]] = i;
    }

    for (int u = 0; u < total; u++) {
        // Remove successors that appear before u in the order
        auto& succ = p.successors[u];
        succ.erase(std::remove_if(succ.begin(), succ.end(),
            [&](int v) { return pos[v] <= pos[u]; }), succ.end());
    }

    // Rebuild predecessors from clean successors
    for (int i = 0; i < total; i++) p.predecessors[i].clear();
    for (int u = 0; u < total; u++) {
        for (int v : p.successors[u]) {
            p.predecessors[v].push_back(u);
        }
    }
}
