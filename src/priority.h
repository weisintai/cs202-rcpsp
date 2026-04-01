#ifndef PRIORITY_H
#define PRIORITY_H

#include "types.h"
#include <vector>
#include <random>

// Generate a topological order biased by a priority rule.
// Lower priority value = scheduled earlier.
// rule: "lft", "mts", "grd", "spt"
std::vector<int> priority_sort(const Problem& p, const std::string& rule);

// Generate a random feasible topological order (random tie-breaking).
std::vector<int> random_sort(const Problem& p, std::mt19937& rng);

// Generate multiple initial solutions using all priority rules + random.
// Returns a vector of activity lists (topological orders).
std::vector<std::vector<int>> generate_initial_solutions(const Problem& p, int num_random, std::mt19937& rng);

#endif
