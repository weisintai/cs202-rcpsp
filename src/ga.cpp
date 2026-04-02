#include "ga.h"
#include "ssgs.h"
#include "priority.h"
#include "improvement.h"
#include <algorithm>
#include <numeric>
#include <iostream>
#include <unordered_set>

static bool schedule_budget_exhausted(long long schedule_count, long long schedule_limit) {
    return schedule_limit > 0 && schedule_count >= schedule_limit;
}

static bool time_budget_exhausted(const std::chrono::steady_clock::time_point& start_time,
                                  double time_limit_seconds) {
    auto now = std::chrono::steady_clock::now();
    double elapsed = std::chrono::duration<double>(now - start_time).count();
    return elapsed >= time_limit_seconds;
}

static Schedule counted_ssgs(const Problem& p,
                             const std::vector<int>& activity_list,
                             long long& schedule_count) {
    schedule_count++;
    return ssgs(p, activity_list);
}

static uint64_t activity_list_fingerprint(const std::vector<int>& list) {
    uint64_t hash = 1469598103934665603ULL;  // FNV-1a offset basis
    for (int act : list) {
        hash ^= static_cast<uint64_t>(act + 1);
        hash *= 1099511628211ULL;
    }
    return hash;
}

// ── Validate that an activity list is precedence-feasible ───────────────────
static bool respects_precedence(const Problem& p, const std::vector<int>& list) {
    int total = (int)list.size();
    std::vector<int> pos(total, -1);
    for (int i = 0; i < total; i++) pos[list[i]] = i;

    for (int u = 0; u < total; u++) {
        for (int v : p.successors[u]) {
            if (pos[u] >= pos[v]) return false;
        }
    }
    return true;
}

// ── Valid insertion interval for one activity in a precedence-feasible list ─
// Returns [lo, hi] in the list after removing list[from].
static std::pair<int, int> insertion_bounds(const Problem& p,
                                            const std::vector<int>& list,
                                            int from) {
    int n = (int)list.size();
    int act = list[from];

    std::vector<int> pos(n, -1);
    for (int i = 0; i < n; i++) pos[list[i]] = i;

    int lo = 0;
    int hi = n - 1;

    for (int pred : p.predecessors[act]) {
        int pred_pos = pos[pred];
        if (pred_pos > from) pred_pos--;
        lo = std::max(lo, pred_pos + 1);
    }

    for (int succ : p.successors[act]) {
        int succ_pos = pos[succ];
        if (succ_pos > from) succ_pos--;
        hi = std::min(hi, succ_pos);
    }

    lo = std::max(lo, 1);
    hi = std::min(hi, n - 2);

    return {lo, hi};
}

// ── Extract activity order from a schedule ──────────────────────────────────
static std::vector<int> order_from_schedule(const Problem& p, const Schedule& sched) {
    int total = p.n + 2;
    std::vector<int> order(total);
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        if (sched.start_time[a] != sched.start_time[b]) {
            return sched.start_time[a] < sched.start_time[b];
        }
        return a < b;
    });
    return order;
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
        std::swap(list[i], list[i + 1]);
        if (respects_precedence(p, list)) {
            return;
        }
        std::swap(list[i], list[i + 1]);
    }
}

// ── Mutation: swap two non-adjacent activities if precedence allows ─────────
static void mutate_long_swap(const Problem& p, std::vector<int>& list, std::mt19937& rng) {
    int n = (int)list.size();
    if (n <= 4) return;

    std::uniform_int_distribution<int> dist(1, n - 2);  // keep dummy source/sink fixed
    for (int attempt = 0; attempt < 5; attempt++) {
        int i = dist(rng);
        int j = dist(rng);
        if (i == j) continue;
        if (i > j) std::swap(i, j);
        if (j == i + 1) continue;  // leave adjacent swaps to mutate_swap

        std::swap(list[i], list[j]);
        if (respects_precedence(p, list)) {
            return;
        }
        std::swap(list[i], list[j]);
    }
}

// ── Mutation: move an activity earlier or later within valid bounds ─────────
static void mutate_insert(const Problem& p, std::vector<int>& list, std::mt19937& rng) {
    int n = (int)list.size();
    if (n <= 2) return;

    std::uniform_int_distribution<int> dist(1, n - 2);  // skip dummies at ends
    for (int attempt = 0; attempt < 5; attempt++) {
        int from = dist(rng);
        auto [lo, hi] = insertion_bounds(p, list, from);
        if (lo > hi) continue;

        std::vector<int> targets;
        targets.reserve(hi - lo + 1);
        for (int to = lo; to <= hi; to++) {
            if (to != from) targets.push_back(to);
        }
        if (targets.empty()) continue;

        std::uniform_int_distribution<int> target_dist(0, (int)targets.size() - 1);
        int to = targets[target_dist(rng)];

        int act = list[from];
        list.erase(list.begin() + from);
        list.insert(list.begin() + to, act);
        if (respects_precedence(p, list)) return;
        list.erase(list.begin() + to);
        list.insert(list.begin() + from, act);
    }
}

// ── Apply one random neighborhood move ──────────────────────────────────────
static void perturb_once(const Problem& p, std::vector<int>& list, std::mt19937& rng) {
    std::uniform_real_distribution<double> prob(0.0, 1.0);
    double move = prob(rng);
    if (move < 1.0 / 3.0) {
        mutate_swap(p, list, rng);
    } else if (move < 2.0 / 3.0) {
        mutate_long_swap(p, list, rng);
    } else {
        mutate_insert(p, list, rng);
    }
}

static void build_population_keys(const std::vector<std::vector<int>>& population,
                                  std::unordered_set<uint64_t>& keys) {
    keys.clear();
    keys.reserve(population.size() * 2);
    for (const auto& individual : population) {
        keys.insert(activity_list_fingerprint(individual));
    }
}

static void add_unique_population_member(std::vector<std::vector<int>>& population,
                                         std::unordered_set<uint64_t>& keys,
                                         std::vector<int> candidate) {
    uint64_t key = activity_list_fingerprint(candidate);
    if (keys.insert(key).second) {
        population.push_back(std::move(candidate));
    }
}

// ── Refresh non-elite population members after long stagnation ──────────────
static void restart_population(const Problem& p,
                               std::vector<std::vector<int>>& population,
                               std::vector<Schedule>& schedules,
                               std::vector<int>& fitness,
                               const GAConfig& config,
                               std::mt19937& rng,
                               long long& schedule_count,
                               int& best_idx,
                               int& worst_idx) {
    int pop_size = (int)population.size();
    int elite_count = std::min(config.restart_elite_count, pop_size);
    std::unordered_set<uint64_t> keys;
    keys.reserve(pop_size * 2);

    std::vector<int> order(pop_size);
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        if (fitness[a] != fitness[b]) return fitness[a] < fitness[b];
        return a < b;
    });

    std::vector<std::vector<int>> new_population;
    std::vector<Schedule> new_schedules;
    std::vector<int> new_fitness;
    new_population.reserve(pop_size);
    new_schedules.reserve(pop_size);
    new_fitness.reserve(pop_size);

    for (int i = 0; i < elite_count; i++) {
        int idx = order[i];
        uint64_t key = activity_list_fingerprint(population[idx]);
        if (!keys.insert(key).second) continue;
        new_population.push_back(population[idx]);
        new_schedules.push_back(schedules[idx]);
        new_fitness.push_back(fitness[idx]);
    }

    auto fresh_seeds = generate_initial_solutions(p, 20, rng);
    int seed_idx = 0;
    while ((int)new_population.size() < pop_size) {
        std::vector<int> candidate;
        if (seed_idx < (int)fresh_seeds.size()) {
            candidate = fresh_seeds[seed_idx++];
        } else {
            candidate = random_sort(p, rng);
        }
        uint64_t key = activity_list_fingerprint(candidate);
        if (!keys.insert(key).second) continue;
        new_population.push_back(candidate);
        new_schedules.push_back(counted_ssgs(p, candidate, schedule_count));
        new_fitness.push_back(new_schedules.back().makespan);
    }

    population = std::move(new_population);
    schedules = std::move(new_schedules);
    fitness = std::move(new_fitness);

    best_idx = 0;
    worst_idx = 0;
    for (int i = 1; i < pop_size; i++) {
        if (fitness[i] < fitness[best_idx]) best_idx = i;
        if (fitness[i] > fitness[worst_idx]) worst_idx = i;
    }
}

// ── Run GA ──────────────────────────────────────────────────────────────────
Schedule run_ga(const Problem& p,
               const std::vector<std::vector<int>>& initial_solutions,
               const GAConfig& config,
               std::mt19937& rng,
               bool use_improvement) {
    auto start_time = std::chrono::steady_clock::now();
    long long schedule_count = 0;

    int pop_size = config.population_size;

    // Initialize population
    std::vector<std::vector<int>> population;
    population.reserve(pop_size);
    std::unordered_set<uint64_t> population_keys;
    population_keys.reserve(pop_size * 2);

    // Add initial solutions
    for (const auto& sol : initial_solutions) {
        if ((int)population.size() >= pop_size) break;
        add_unique_population_member(population, population_keys, sol);
    }

    // Fill remaining with random permutations
    while ((int)population.size() < pop_size) {
        add_unique_population_member(population, population_keys, random_sort(p, rng));
    }

    // Evaluate initial population
    std::vector<int> fitness(pop_size);
    std::vector<Schedule> schedules(pop_size);
    int best_idx = 0;

    for (int i = 0; i < pop_size; i++) {
        schedules[i] = counted_ssgs(p, population[i], schedule_count);
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
    int last_improve_gen = 0;  // track when we last applied forward-backward
    int restart_count = 0;

    // Main GA loop
    while (true) {
        // Check time budget
        if (time_budget_exhausted(start_time, config.time_limit_seconds)) break;
        if (schedule_budget_exhausted(schedule_count, config.schedule_limit)) break;

        if (config.restart_stagnation_generations > 0 &&
            generations - last_improve_gen >= config.restart_stagnation_generations) {
            restart_population(
                p, population, schedules, fitness, config, rng,
                schedule_count, best_idx, worst_idx);
            build_population_keys(population, population_keys);
            last_improve_gen = generations;
            restart_count++;
            if (schedule_budget_exhausted(schedule_count, config.schedule_limit)) break;
            if (time_budget_exhausted(start_time, config.time_limit_seconds)) break;
        }

        // Periodically apply forward-backward improvement to best individual
        if (use_improvement && generations - last_improve_gen >= 50000) {
            Schedule improved = forward_backward_improve(
                p, schedules[best_idx], &schedule_count, config.schedule_limit);
            if (improved.makespan < fitness[best_idx]) {
                schedules[best_idx] = improved;
                fitness[best_idx] = improved.makespan;
                // Update the activity list from the improved schedule
                std::vector<int> new_order = order_from_schedule(p, improved);
                population[best_idx] = std::move(new_order);

                // Re-find worst
                worst_idx = 0;
                for (int i = 1; i < pop_size; i++) {
                    if (fitness[i] > fitness[worst_idx]) worst_idx = i;
                }
                last_improve_gen = generations;
            }
        }

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
            perturb_once(p, offspring, rng);
        }

        uint64_t child_key = activity_list_fingerprint(offspring);
        if (population_keys.count(child_key)) {
            bool escaped_duplicate = false;
            for (int attempt = 0; attempt < 3; attempt++) {
                perturb_once(p, offspring, rng);
                child_key = activity_list_fingerprint(offspring);
                if (!population_keys.count(child_key)) {
                    escaped_duplicate = true;
                    break;
                }
            }
            if (!escaped_duplicate) {
                generations++;
                continue;
            }
        }

        // Evaluate offspring
        if (schedule_budget_exhausted(schedule_count, config.schedule_limit)) break;
        Schedule child_sched = counted_ssgs(p, offspring, schedule_count);
        int child_fitness = child_sched.makespan;

        // Replace worst if offspring is better
        if (child_fitness < fitness[worst_idx]) {
            population_keys.erase(activity_list_fingerprint(population[worst_idx]));
            population[worst_idx] = std::move(offspring);
            population_keys.insert(child_key);
            schedules[worst_idx] = std::move(child_sched);
            fitness[worst_idx] = child_fitness;

            // Update best
            if (child_fitness < fitness[best_idx]) {
                best_idx = worst_idx;
                last_improve_gen = generations;
            }

            // Find new worst
            worst_idx = 0;
            for (int i = 1; i < pop_size; i++) {
                if (fitness[i] > fitness[worst_idx]) worst_idx = i;
            }
        }

        generations++;
    }

    // Final forward-backward improvement on the best solution
    if (use_improvement && !schedule_budget_exhausted(schedule_count, config.schedule_limit)) {
        Schedule final_sched = forward_backward_improve(
            p, schedules[best_idx], &schedule_count, config.schedule_limit);
        if (final_sched.makespan < fitness[best_idx]) {
            schedules[best_idx] = final_sched;
            fitness[best_idx] = final_sched.makespan;
        }
    }

    std::cerr << "GA: " << generations << " generations, " << schedule_count
              << " schedules, " << restart_count
              << " restarts, best makespan: " << fitness[best_idx] << std::endl;

    return schedules[best_idx];
}
