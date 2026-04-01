#include "ga.h"
#include "ssgs.h"
#include "priority.h"
#include <algorithm>
#include <numeric>
#include <iostream>

// ── Check if activity list respects precedence at position i ────────────────
// Returns true if swapping positions i and i+1 would preserve precedence.
static bool can_swap(const Problem& p, const std::vector<int>& list, int i) {
    int a = list[i];
    int b = list[i + 1];
    // Can't swap if a is a predecessor of b (b depends on a)
    for (int pred : p.predecessors[b]) {
        if (pred == a) return false;
    }
    // Can't swap if b is a predecessor of a (a depends on b)
    for (int pred : p.predecessors[a]) {
        if (pred == b) return false;
    }
    return true;
}

// ── Tournament selection ────────────────────────────────────────────────────
static int tournament_select(const std::vector<int>& fitness,
                            int tournament_size, std::mt19937& rng) {
    int pop_size = (int)fitness.size();
    std::uniform_int_distribution<int> dist(0, pop_size - 1);

    int best = dist(rng);
    for (int i = 1; i < tournament_size; i++) {
        int candidate = dist(rng);
        if (fitness[candidate] < fitness[best]) {
            best = candidate;
        }
    }
    return best;
}

// ── One-point crossover ────────────────────────────────────────────────────
// Take prefix from parent1 up to crossover point, fill remaining from parent2
// in the order they appear. Result is always a valid permutation.
// Precedence feasibility: since parent2 is precedence-feasible, the relative
// order of activities taken from parent2 preserves precedence.
static std::vector<int> crossover(const std::vector<int>& parent1,
                                  const std::vector<int>& parent2,
                                  std::mt19937& rng) {
    int n = (int)parent1.size();
    std::uniform_int_distribution<int> dist(1, n - 2);  // avoid trivial cuts
    int cut = dist(rng);

    std::vector<int> child;
    child.reserve(n);

    // Take prefix from parent1
    std::vector<bool> in_child(n + 2, false);  // indexed by activity id
    for (int i = 0; i < cut; i++) {
        child.push_back(parent1[i]);
        in_child[parent1[i]] = true;
    }

    // Fill remaining from parent2, preserving parent2's order
    for (int i = 0; i < n; i++) {
        if (!in_child[parent2[i]]) {
            child.push_back(parent2[i]);
        }
    }

    return child;
}

// ── Mutation: swap two adjacent activities if precedence allows ─────────────
static void mutate_swap(const Problem& p, std::vector<int>& list, std::mt19937& rng) {
    int n = (int)list.size();
    if (n <= 2) return;

    // Try a few random positions
    std::uniform_int_distribution<int> dist(0, n - 2);
    for (int attempt = 0; attempt < 3; attempt++) {
        int i = dist(rng);
        if (can_swap(p, list, i)) {
            std::swap(list[i], list[i + 1]);
            return;
        }
    }
}

// ── Mutation: shift an activity to an earlier valid position ────────────────
static void mutate_shift(const Problem& p, std::vector<int>& list, std::mt19937& rng) {
    int n = (int)list.size();
    if (n <= 2) return;

    std::uniform_int_distribution<int> dist(1, n - 2);  // skip dummies at ends
    int from = dist(rng);
    int act = list[from];

    // Find the latest position of any predecessor of act in the list
    int earliest_pos = 0;
    for (int pred : p.predecessors[act]) {
        for (int j = 0; j < from; j++) {
            if (list[j] == pred && j + 1 > earliest_pos) {
                earliest_pos = j + 1;
            }
        }
    }

    if (earliest_pos >= from) return;  // can't move earlier

    // Pick a random position between earliest_pos and from-1
    std::uniform_int_distribution<int> pos_dist(earliest_pos, from - 1);
    int to = pos_dist(rng);

    // Shift: remove from 'from', insert at 'to'
    int val = list[from];
    list.erase(list.begin() + from);
    list.insert(list.begin() + to, val);
}

// ── Run GA ──────────────────────────────────────────────────────────────────
Schedule run_ga(const Problem& p,
               const std::vector<std::vector<int>>& initial_solutions,
               const GAConfig& config,
               std::mt19937& rng) {
    auto start_time = std::chrono::steady_clock::now();

    int pop_size = config.population_size;

    // Initialize population
    std::vector<std::vector<int>> population;
    population.reserve(pop_size);

    // Add initial solutions
    for (const auto& sol : initial_solutions) {
        if ((int)population.size() >= pop_size) break;
        population.push_back(sol);
    }

    // Fill remaining with random permutations
    while ((int)population.size() < pop_size) {
        population.push_back(random_sort(p, rng));
    }

    // Evaluate initial population
    std::vector<int> fitness(pop_size);
    std::vector<Schedule> schedules(pop_size);
    int best_idx = 0;

    for (int i = 0; i < pop_size; i++) {
        schedules[i] = ssgs(p, population[i]);
        fitness[i] = schedules[i].makespan;
        if (fitness[i] < fitness[best_idx]) {
            best_idx = i;
        }
    }

    // Find worst individual
    int worst_idx = 0;
    for (int i = 1; i < pop_size; i++) {
        if (fitness[i] > fitness[worst_idx]) worst_idx = i;
    }

    int generations = 0;

    // Main GA loop
    while (true) {
        // Check time budget
        auto now = std::chrono::steady_clock::now();
        double elapsed = std::chrono::duration<double>(now - start_time).count();
        if (elapsed >= config.time_limit_seconds) break;

        // Select two parents
        int p1 = tournament_select(fitness, config.tournament_size, rng);
        int p2 = tournament_select(fitness, config.tournament_size, rng);
        while (p2 == p1) {
            p2 = tournament_select(fitness, config.tournament_size, rng);
        }

        // Crossover
        std::vector<int> offspring;
        std::uniform_real_distribution<double> prob(0.0, 1.0);
        if (prob(rng) < config.crossover_rate) {
            offspring = crossover(population[p1], population[p2], rng);
        } else {
            offspring = population[p1];  // copy better parent
        }

        // Mutation
        if (prob(rng) < config.mutation_rate) {
            if (prob(rng) < 0.5) {
                mutate_swap(p, offspring, rng);
            } else {
                mutate_shift(p, offspring, rng);
            }
        }

        // Evaluate offspring
        Schedule child_sched = ssgs(p, offspring);
        int child_fitness = child_sched.makespan;

        // Replace worst if offspring is better
        if (child_fitness < fitness[worst_idx]) {
            population[worst_idx] = std::move(offspring);
            schedules[worst_idx] = std::move(child_sched);
            fitness[worst_idx] = child_fitness;

            // Update best
            if (child_fitness < fitness[best_idx]) {
                best_idx = worst_idx;
            }

            // Find new worst
            worst_idx = 0;
            for (int i = 1; i < pop_size; i++) {
                if (fitness[i] > fitness[worst_idx]) worst_idx = i;
            }
        }

        generations++;
    }

    std::cerr << "GA: " << generations << " generations, best makespan: "
              << fitness[best_idx] << std::endl;

    return schedules[best_idx];
}
