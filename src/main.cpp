#include "parser.h"
#include "graph.h"
#include "ssgs.h"
#include "validator.h"
#include <iostream>

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: solver <instance_file>" << std::endl;
        return 1;
    }

    Problem prob = parse(argv[1]);

    // Generate a topological order, clean up any cycles, and decode via SSGS
    std::vector<int> order = topological_sort(prob);
    remove_back_edges(prob, order);
    Schedule sched = ssgs(prob, order);

    validate(prob, sched);
    std::cerr << "Makespan: " << sched.makespan << std::endl;

    // Output start times for activities 1..n
    for (int i = 1; i <= prob.n; i++) {
        std::cout << sched.start_time[i] << "\n";
    }

    return 0;
}
