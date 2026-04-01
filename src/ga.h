#ifndef GA_H
#define GA_H

#include "types.h"
#include <vector>
#include <random>
#include <chrono>

struct GAConfig {
    int population_size = 100;
    int tournament_size = 5;
    double crossover_rate = 0.9;
    double mutation_rate = 0.3;
    double time_limit_seconds = 28.0;
};

// Run the genetic algorithm and return the best schedule found.
// initial_solutions: seed population from priority rules + random.
// use_improvement: if true, apply forward-backward improvement periodically and at the end.
Schedule run_ga(const Problem& p,
               const std::vector<std::vector<int>>& initial_solutions,
               const GAConfig& config,
               std::mt19937& rng,
               bool use_improvement = true);

#endif
