#include "parser.h"
#include "graph.h"
#include "ssgs.h"
#include "validator.h"
#include "priority.h"
#include "ga.h"
#include <iostream>
#include <random>

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: solver <instance_file>" << std::endl;
        return 1;
    }

    Problem prob = parse(argv[1]);

    // Clean up any cycles in the precedence graph (.SCH files only)
    std::vector<int> topo = topological_sort(prob);
    remove_back_edges(prob, topo);

    // Generate initial solutions using priority rules + random permutations
    std::mt19937 rng(42);
    auto initial = generate_initial_solutions(prob, 20, rng);

    // Run genetic algorithm
    GAConfig config;
    Schedule best = run_ga(prob, initial, config, rng);

    validate(prob, best);
    std::cerr << "Makespan: " << best.makespan << std::endl;

    // Output start times for activities 1..n
    for (int i = 1; i <= prob.n; i++) {
        std::cout << best.start_time[i] << "\n";
    }

    return 0;
}
