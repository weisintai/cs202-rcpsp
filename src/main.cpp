#include "parser.h"
#include "graph.h"
#include "ssgs.h"
#include "validator.h"
#include "priority.h"
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
    auto solutions = generate_initial_solutions(prob, 20, rng);

    // Decode each via SSGS and keep the best
    Schedule best_sched;
    best_sched.makespan = INT32_MAX;

    for (const auto& order : solutions) {
        Schedule sched = ssgs(prob, order);
        if (sched.makespan < best_sched.makespan) {
            best_sched = sched;
        }
    }

    validate(prob, best_sched);
    std::cerr << "Makespan: " << best_sched.makespan << std::endl;

    // Output start times for activities 1..n
    for (int i = 1; i <= prob.n; i++) {
        std::cout << best_sched.start_time[i] << "\n";
    }

    return 0;
}
