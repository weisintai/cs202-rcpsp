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

static bool time_budget_exhausted(const std::chrono::steady_clock::time_point& deadline) {
    return std::chrono::steady_clock::now() >= deadline;
}

static std::chrono::steady_clock::time_point effective_deadline(const GAConfig& config) {
    if (config.deadline != std::chrono::steady_clock::time_point::max()) {
        return config.deadline;
    }

    auto now = std::chrono::steady_clock::now();
    auto budget = std::chrono::duration<double>(std::max(0.0, config.time_limit_seconds));
    return now + std::chrono::duration_cast<std::chrono::steady_clock::duration>(budget);
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

static double effective_mutation_rate(const GAConfig& config, int generations_since_improve) {
    if (config.max_mutation_rate <= config.mutation_rate ||
        config.restart_stagnation_generations <= 0 ||
        generations_since_improve <= 0) {
        return config.mutation_rate;
    }

    double progress = std::min(
        1.0,
        static_cast<double>(generations_since_improve) / config.restart_stagnation_generations);
    return config.mutation_rate + (config.max_mutation_rate - config.mutation_rate) * progress;
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

static std::vector<int> crossover_one_point(const std::vector<int>& parent1,
                                            const std::vector<int>& parent2,
                                            std::mt19937& rng) {
    int n = (int)parent1.size();
    std::uniform_int_distribution<int> dist(1, n - 2);
    int cut = dist(rng);

    std::vector<int> child;
    child.reserve(n);
    std::vector<bool> in_child(n, false);

    for (int i = 0; i < cut; i++) {
        child.push_back(parent1[i]);
        in_child[parent1[i]] = true;
    }
    for (int act : parent2) {
        if (!in_child[act]) child.push_back(act);
    }
    return child;
}

// ── Precedence-aware merge crossover ───────────────────────────────────────
static std::vector<int> crossover_merge(const Problem& p,
                                        const std::vector<int>& parent1,
                                        const std::vector<int>& parent2,
                                        std::mt19937& rng) {
    int total = (int)parent1.size();
    std::vector<int> pos1(total, 0);
    std::vector<int> pos2(total, 0);
    for (int i = 0; i < total; i++) {
        pos1[parent1[i]] = i;
        pos2[parent2[i]] = i;
    }

    std::vector<int> remaining_preds(total, 0);
    for (int act = 0; act < total; act++) {
        remaining_preds[act] = (int)p.predecessors[act].size();
    }

    std::vector<int> eligible;
    eligible.reserve(total);
    for (int act = 0; act < total; act++) {
        if (remaining_preds[act] == 0) eligible.push_back(act);
    }

    std::vector<int> child;
    child.reserve(total);
    std::vector<bool> scheduled(total, false);
    std::uniform_real_distribution<double> pick_parent(0.0, 1.0);

    while (!eligible.empty()) {
        std::sort(eligible.begin(), eligible.end(), [&](int a, int b) {
            int sum_a = pos1[a] + pos2[a];
            int sum_b = pos1[b] + pos2[b];
            if (sum_a != sum_b) return sum_a < sum_b;

            int spread_a = std::abs(pos1[a] - pos2[a]);
            int spread_b = std::abs(pos1[b] - pos2[b]);
            if (spread_a != spread_b) return spread_a < spread_b;

            if (pos1[a] != pos1[b]) return pos1[a] < pos1[b];
            if (pos2[a] != pos2[b]) return pos2[a] < pos2[b];
            return a < b;
        });

        int pool = std::min(3, (int)eligible.size());
        int chosen_idx = 0;
        if (pool > 1) {
            bool prefer_parent1 = pick_parent(rng) < 0.5;
            for (int i = 1; i < pool; i++) {
                int current = eligible[chosen_idx];
                int candidate = eligible[i];
                int current_rank = prefer_parent1 ? pos1[current] : pos2[current];
                int candidate_rank = prefer_parent1 ? pos1[candidate] : pos2[candidate];
                if (candidate_rank < current_rank ||
                    (candidate_rank == current_rank &&
                     pos1[candidate] + pos2[candidate] < pos1[current] + pos2[current])) {
                    chosen_idx = i;
                }
            }
        }

        int act = eligible[chosen_idx];
        eligible[chosen_idx] = eligible.back();
        eligible.pop_back();
        scheduled[act] = true;
        child.push_back(act);

        for (int succ : p.successors[act]) {
            remaining_preds[succ]--;
            if (remaining_preds[succ] == 0 && !scheduled[succ]) {
                eligible.push_back(succ);
            }
        }
    }

    return child;
}

static std::vector<int> crossover(const Problem& p,
                                  const std::vector<int>& parent1,
                                  const std::vector<int>& parent2,
                                  const GAConfig& config,
                                  int generations_since_improve,
                                  std::mt19937& rng) {
    std::uniform_real_distribution<double> prob(0.0, 1.0);
    bool prefer_merge = false;
    if (config.restart_stagnation_generations > 0) {
        prefer_merge = generations_since_improve >= config.restart_stagnation_generations / 4;
    }

    if (!prefer_merge && prob(rng) < 0.25) {
        prefer_merge = true;
    }

    if (prefer_merge) {
        return crossover_merge(p, parent1, parent2, rng);
    }
    return crossover_one_point(parent1, parent2, rng);
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
                               const std::chrono::steady_clock::time_point& deadline,
                               int& best_idx,
                               int& worst_idx) {
    int pop_size = (int)population.size();
    int elite_count = std::max(1, std::min(config.restart_elite_count, pop_size));
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
        if (time_budget_exhausted(deadline) ||
            schedule_budget_exhausted(schedule_count, config.schedule_limit)) {
            break;
        }

        std::vector<int> candidate;
        if (seed_idx < (int)fresh_seeds.size()) {
            candidate = fresh_seeds[seed_idx++];
        } else {
            candidate = random_sort(p, rng);
        }
        uint64_t key = activity_list_fingerprint(candidate);
        if (!keys.insert(key).second) continue;
        Schedule schedule = counted_ssgs(p, candidate, schedule_count);
        new_population.push_back(std::move(candidate));
        new_schedules.push_back(std::move(schedule));
        new_fitness.push_back(new_schedules.back().makespan);
    }

    population = std::move(new_population);
    schedules = std::move(new_schedules);
    fitness = std::move(new_fitness);

    best_idx = 0;
    worst_idx = 0;
    for (int i = 1; i < (int)fitness.size(); i++) {
        if (fitness[i] < fitness[best_idx]) best_idx = i;
        if (fitness[i] > fitness[worst_idx]) worst_idx = i;
    }
}

static bool should_polish_offspring(const Problem& p,
                                    int child_fitness,
                                    int best_fitness,
                                    int parent1_fitness,
                                    int parent2_fitness) {
    int better_parent = std::min(parent1_fitness, parent2_fitness);
    if (child_fitness >= better_parent) return false;

    int slack = std::max(1, p.n / 30);
    return child_fitness <= best_fitness + slack;
}

// ── Run GA ──────────────────────────────────────────────────────────────────
Schedule run_ga(const Problem& p,
                const std::vector<std::vector<int>>& initial_solutions,
                const GAConfig& config,
                std::mt19937& rng,
                bool use_improvement) {
    long long schedule_count = 0;
    const auto deadline = effective_deadline(config);

    int target_pop_size = config.population_size;

    // Initialize population
    std::vector<std::vector<int>> seed_population;
    seed_population.reserve(target_pop_size);
    std::unordered_set<uint64_t> population_keys;
    population_keys.reserve(target_pop_size * 2);

    // Add initial solutions
    for (const auto& sol : initial_solutions) {
        if ((int)seed_population.size() >= target_pop_size) break;
        add_unique_population_member(seed_population, population_keys, sol);
    }

    // Fill remaining with random permutations
    while ((int)seed_population.size() < target_pop_size) {
        add_unique_population_member(seed_population, population_keys, random_sort(p, rng));
    }

    // Evaluate initial population
    std::vector<std::vector<int>> population;
    population.reserve(seed_population.size());
    population_keys.clear();
    population_keys.reserve(seed_population.size() * 2);
    std::vector<int> fitness;
    fitness.reserve(seed_population.size());
    std::vector<Schedule> schedules;
    schedules.reserve(seed_population.size());
    int best_idx = 0;

    for (size_t i = 0; i < seed_population.size(); i++) {
        if (!population.empty()) {
            if (time_budget_exhausted(deadline)) break;
            if (schedule_budget_exhausted(schedule_count, config.schedule_limit)) break;
        }

        Schedule schedule = counted_ssgs(p, seed_population[i], schedule_count);
        population.push_back(seed_population[i]);
        schedules.push_back(std::move(schedule));
        fitness.push_back(schedules.back().makespan);
        population_keys.insert(activity_list_fingerprint(population.back()));
        if (fitness.back() < fitness[best_idx]) {
            best_idx = (int)fitness.size() - 1;
        }
    }

    if (population.empty()) {
        Schedule schedule = counted_ssgs(p, seed_population.front(), schedule_count);
        population.push_back(seed_population.front());
        schedules.push_back(std::move(schedule));
        fitness.push_back(schedules.back().makespan);
        population_keys.insert(activity_list_fingerprint(population.back()));
    }

    Schedule best_schedule = schedules[best_idx];
    int best_fitness = fitness[best_idx];

    // Find worst individual
    int worst_idx = 0;
    for (int i = 1; i < (int)population.size(); i++) {
        if (fitness[i] > fitness[worst_idx]) worst_idx = i;
    }

    int generations = 0;
    int last_improve_gen = 0;  // track when we last applied forward-backward
    int restart_count = 0;

    // Main GA loop
    while (true) {
        if (population.size() < 2) break;

        // Check time budget
        if (time_budget_exhausted(deadline)) break;
        if (schedule_budget_exhausted(schedule_count, config.schedule_limit)) break;

        if (config.restart_stagnation_generations > 0 &&
            generations - last_improve_gen >= config.restart_stagnation_generations) {
            restart_population(
                p, population, schedules, fitness, config, rng,
                schedule_count, deadline, best_idx, worst_idx);
            build_population_keys(population, population_keys);
            last_improve_gen = generations;
            restart_count++;
            if (schedule_budget_exhausted(schedule_count, config.schedule_limit)) break;
            if (time_budget_exhausted(deadline)) break;
            if (population.size() < 2) break;

            if (fitness[best_idx] < best_fitness) {
                best_schedule = schedules[best_idx];
                best_fitness = fitness[best_idx];
            }
        }

        // Periodically apply forward-backward improvement to best individual
        if (use_improvement &&
            generations - last_improve_gen >= 50000 &&
            !time_budget_exhausted(deadline)) {
            Schedule improved = forward_backward_improve(
                p, schedules[best_idx], &schedule_count, config.schedule_limit, deadline);
            if (improved.makespan < fitness[best_idx]) {
                schedules[best_idx] = improved;
                fitness[best_idx] = improved.makespan;
                // Update the activity list from the improved schedule
                std::vector<int> new_order = order_from_schedule(p, improved);
                population[best_idx] = std::move(new_order);
                build_population_keys(population, population_keys);

                // Re-find worst
                worst_idx = 0;
                for (int i = 1; i < (int)population.size(); i++) {
                    if (fitness[i] > fitness[worst_idx]) worst_idx = i;
                }
                last_improve_gen = generations;
            }
            if (fitness[best_idx] < best_fitness) {
                best_schedule = schedules[best_idx];
                best_fitness = fitness[best_idx];
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
            offspring = crossover(
                p, population[p1], population[p2], config,
                generations - last_improve_gen, rng);
        } else {
            offspring = population[p1];  // copy better parent
        }

        // Mutation
        double mutation_rate = effective_mutation_rate(config, generations - last_improve_gen);
        if (prob(rng) < mutation_rate) {
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
        if (time_budget_exhausted(deadline)) break;
        if (schedule_budget_exhausted(schedule_count, config.schedule_limit)) break;
        Schedule child_sched = counted_ssgs(p, offspring, schedule_count);
        int child_fitness = child_sched.makespan;

        if (use_improvement &&
            should_polish_offspring(p, child_fitness, fitness[best_idx], fitness[p1], fitness[p2]) &&
            !schedule_budget_exhausted(schedule_count, config.schedule_limit) &&
            !time_budget_exhausted(deadline)) {
            Schedule polished = forward_backward_improve(
                p, child_sched, &schedule_count, config.schedule_limit, deadline);
            if (polished.makespan < child_fitness) {
                std::vector<int> polished_order = order_from_schedule(p, polished);
                uint64_t polished_key = activity_list_fingerprint(polished_order);
                if (polished_key == child_key || !population_keys.count(polished_key)) {
                    offspring = std::move(polished_order);
                    child_sched = std::move(polished);
                    child_fitness = child_sched.makespan;
                    child_key = polished_key;
                }
            }
        }

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

            if (child_fitness < best_fitness) {
                best_schedule = schedules[best_idx];
                best_fitness = child_fitness;
            }

            // Find new worst
            worst_idx = 0;
            for (int i = 1; i < (int)population.size(); i++) {
                if (fitness[i] > fitness[worst_idx]) worst_idx = i;
            }
        }

        generations++;
    }

    // Final forward-backward improvement on the best solution
    if (use_improvement &&
        !schedule_budget_exhausted(schedule_count, config.schedule_limit) &&
        !time_budget_exhausted(deadline)) {
        Schedule final_sched = forward_backward_improve(
            p, best_schedule, &schedule_count, config.schedule_limit, deadline);
        if (final_sched.makespan < best_fitness) {
            schedules[best_idx] = final_sched;
            fitness[best_idx] = final_sched.makespan;
            best_schedule = final_sched;
            best_fitness = final_sched.makespan;
        }
    }

    std::cerr << "GA: " << generations << " generations, " << schedule_count
              << " schedules, " << restart_count
              << " restarts, best makespan: " << best_fitness << std::endl;

    return best_schedule;
}
