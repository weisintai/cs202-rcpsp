#include "parser.h"
#include "ssgs.h"
#include "validator.h"
#include "priority.h"
#include "improvement.h"
#include "ga.h"
#include <iostream>
#include <random>
#include <cstring>
#include <cstdlib>
#include <string>

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: solver <instance_file> [--time <seconds>] [--schedules <count>] "
                  << "[--restart-stagnation <gens>] [--restart-elites <count>] "
                  << "[--mutation-rate <rate>] [--mode baseline|priority|ga|full] "
                  << "[--rule lft|mts|grd|spt|random]" << std::endl;
        return 1;
    }

    // Parse command-line arguments
    double time_limit = 28.0;
    long long schedule_limit = 0;
    int restart_stagnation = 100000;
    int restart_elites = 10;
    double mutation_rate = 0.3;
    std::string mode = "full";
    std::string rule = "";
    for (int i = 2; i < argc; i++) {
        if (std::strcmp(argv[i], "--time") == 0 && i + 1 < argc) {
            time_limit = std::atof(argv[i + 1]);
            i++;
        } else if (std::strcmp(argv[i], "--schedules") == 0 && i + 1 < argc) {
            schedule_limit = std::atoll(argv[i + 1]);
            i++;
        } else if (std::strcmp(argv[i], "--restart-stagnation") == 0 && i + 1 < argc) {
            restart_stagnation = std::atoi(argv[i + 1]);
            i++;
        } else if (std::strcmp(argv[i], "--restart-elites") == 0 && i + 1 < argc) {
            restart_elites = std::atoi(argv[i + 1]);
            i++;
        } else if (std::strcmp(argv[i], "--mutation-rate") == 0 && i + 1 < argc) {
            mutation_rate = std::atof(argv[i + 1]);
            i++;
        } else if (std::strcmp(argv[i], "--mode") == 0 && i + 1 < argc) {
            mode = argv[i + 1];
            i++;
        } else if (std::strcmp(argv[i], "--rule") == 0 && i + 1 < argc) {
            rule = argv[i + 1];
            i++;
        }
    }

    Problem prob = parse(argv[1]);

    std::mt19937 rng(42);
    Schedule best;

    if (!rule.empty()) {
        // Single priority rule mode: one biased topo sort + SSGS
        std::vector<int> order;
        if (rule == "random") {
            order = random_sort(prob, rng);
        } else {
            order = priority_sort(prob, rule);
        }
        best = ssgs(prob, order);

    } else if (mode == "baseline") {
        // Random topological order + SSGS, no priority rules, no GA, no improvement
        auto order = random_sort(prob, rng);
        best = ssgs(prob, order);

    } else if (mode == "priority") {
        // Best of priority rules + random permutations, no GA, no improvement
        auto initial = generate_initial_solutions(prob, 20, rng);
        best = ssgs(prob, initial[0]);
        for (size_t i = 1; i < initial.size(); i++) {
            Schedule s = ssgs(prob, initial[i]);
            if (s.makespan < best.makespan) best = s;
        }

    } else if (mode == "ga") {
        // Random initial population + GA, no forward-backward improvement
        // Seed with random permutations only (no priority rules)
        std::vector<std::vector<int>> initial;
        for (int i = 0; i < 20; i++) {
            initial.push_back(random_sort(prob, rng));
        }
        GAConfig config;
        config.time_limit_seconds = time_limit;
        config.schedule_limit = schedule_limit;
        config.restart_stagnation_generations = restart_stagnation;
        config.restart_elite_count = restart_elites;
        config.mutation_rate = mutation_rate;
        best = run_ga(prob, initial, config, rng, false);

    } else {
        // Full pipeline: priority rules + GA + forward-backward improvement
        auto initial = generate_initial_solutions(prob, 20, rng);
        GAConfig config;
        config.time_limit_seconds = time_limit;
        config.schedule_limit = schedule_limit;
        config.restart_stagnation_generations = restart_stagnation;
        config.restart_elite_count = restart_elites;
        config.mutation_rate = mutation_rate;
        best = run_ga(prob, initial, config, rng, true);
    }

    validate(prob, best);
    std::cerr << "Makespan: " << best.makespan << std::endl;

    // Output start times for activities 1..n
    for (int i = 1; i <= prob.n; i++) {
        std::cout << best.start_time[i] << "\n";
    }

    return 0;
}
