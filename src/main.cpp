#include "parser.h"
#include "ssgs.h"
#include "validator.h"
#include "priority.h"
#include "ga.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <random>

namespace {

constexpr double kDefaultTimeLimitSeconds = 28.0;
constexpr double kHardSubmissionTimeLimitSeconds = 29.0;

void print_usage() {
    std::cerr << "Usage: solver <instance_file> [--time <seconds>]" << std::endl;
}

double clamp_time_limit(double requested_seconds) {
    if (!std::isfinite(requested_seconds) || requested_seconds < 0.0) {
        return 0.0;
    }
    return std::min(requested_seconds, kHardSubmissionTimeLimitSeconds);
}

Schedule best_priority_seed_schedule(const Problem& prob,
                                     const std::vector<std::vector<int>>& initial) {
    Schedule fallback = ssgs(prob, initial.front());
    size_t deterministic_seed_count = std::min<size_t>(4, initial.size());
    for (size_t i = 1; i < deterministic_seed_count; i++) {
        Schedule candidate = ssgs(prob, initial[i]);
        if (candidate.makespan < fallback.makespan) {
            fallback = std::move(candidate);
        }
    }
    return fallback;
}

}  // namespace

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage();
        return 1;
    }

    const auto wall_start = std::chrono::steady_clock::now();

    double time_limit = kDefaultTimeLimitSeconds;
    long long schedule_limit = 0;
    int restart_stagnation = 100000;
    int restart_elites = 10;
    double mutation_rate = 0.3;

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
            if (std::strcmp(argv[i + 1], "full") != 0) {
                std::cerr << "Error: submission build only supports the full solver pipeline"
                          << std::endl;
                return 1;
            }
            i++;
        } else if (std::strcmp(argv[i], "--rule") == 0) {
            std::cerr << "Error: submission build does not expose single-rule solver modes"
                      << std::endl;
            return 1;
        } else {
            std::cerr << "Error: unrecognised argument '" << argv[i] << "'" << std::endl;
            print_usage();
            return 1;
        }
    }

    Problem prob = parse(argv[1]);

    std::mt19937 rng(42);
    auto initial = generate_initial_solutions(prob, 20, rng);
    Schedule fallback = best_priority_seed_schedule(prob, initial);

    GAConfig config;
    config.time_limit_seconds = clamp_time_limit(time_limit);
    config.deadline = wall_start + std::chrono::duration_cast<std::chrono::steady_clock::duration>(
        std::chrono::duration<double>(config.time_limit_seconds));
    config.schedule_limit = schedule_limit;
    config.restart_stagnation_generations = restart_stagnation;
    config.restart_elite_count = restart_elites;
    config.mutation_rate = mutation_rate;

    Schedule best = run_ga(prob, initial, config, rng, true);

    if (!validate(prob, best)) {
        std::cerr << "Falling back to deterministic priority-seed schedule" << std::endl;
        best = std::move(fallback);
        if (!validate(prob, best)) {
            return 1;
        }
    }
    std::cerr << "Makespan: " << best.makespan << std::endl;

    for (int i = 1; i <= prob.n; i++) {
        std::cout << best.start_time[i] << "\n";
    }

    return 0;
}
