#ifndef GRAPH_H
#define GRAPH_H

#include "types.h"
#include <vector>

// Topological sort using Kahn's algorithm (cycle-resilient).
// If cycles exist (possible in .SCH files), breaks them by forcing
// the lowest in-degree node into the queue when it stalls.
std::vector<int> topological_sort(const Problem& p);

// Remove edges that violate topological order (cycle-breaking cleanup).
// After topological sort with forced cycle breaks, some edges go "backwards".
// This removes them and rebuilds predecessor lists.
void remove_back_edges(Problem& p, const std::vector<int>& order);

#endif
