#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <algorithm>
#include <cstring>

// ── Problem data ────────────────────────────────────────────────────────────
struct Problem {
    int n;  // number of real activities (excluding dummies 0 and n+1)
    int K;  // number of renewable resource types
    // Indexed 0..n+1 (0 = super-source, n+1 = super-sink)
    std::vector<int> duration;
    std::vector<std::vector<int>> resource;    // resource[i][k]
    std::vector<std::vector<int>> successors;  // successors[i] = list of j
    std::vector<std::vector<int>> predecessors;// predecessors[j] = list of i
    std::vector<int> capacity;                 // capacity[k]
};

// ── Trim whitespace ─────────────────────────────────────────────────────────
static std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

// ── Detect format ───────────────────────────────────────────────────────────
// .sm files start with a line of asterisks; .SCH files start with integers.
static bool is_sm_format(const std::string& first_line) {
    std::string t = trim(first_line);
    return !t.empty() && t[0] == '*';
}

// ── Parse standard PSPLIB .sm format ────────────────────────────────────────
static Problem parse_sm(std::ifstream& fin, const std::string& first_line) {
    Problem p;
    (void)first_line;  // already consumed the first *** line

    // Read all remaining lines
    std::vector<std::string> lines;
    lines.push_back(first_line);
    std::string line;
    while (std::getline(fin, line)) {
        lines.push_back(line);
    }

    int total_jobs = 0;
    int num_renewable = 0;
    int prec_start = -1;
    int req_start = -1;
    int avail_start = -1;

    for (int i = 0; i < (int)lines.size(); i++) {
        const std::string& l = lines[i];

        // Extract total jobs (includes super-source and super-sink)
        if (l.find("jobs (incl. supersource/sink )") != std::string::npos) {
            // format: "jobs (incl. supersource/sink ):  32"
            size_t pos = l.find(':');
            total_jobs = std::stoi(trim(l.substr(pos + 1)));
        }
        // Extract number of renewable resources
        if (l.find("- renewable") != std::string::npos &&
            l.find("nonrenewable") == std::string::npos) {
            size_t pos = l.find(':');
            std::string rhs = trim(l.substr(pos + 1));
            std::istringstream iss(rhs);
            iss >> num_renewable;
        }
        // Find section starts
        if (l.find("PRECEDENCE RELATIONS:") != std::string::npos) {
            prec_start = i + 2;  // skip header line
        }
        if (l.find("REQUESTS/DURATIONS:") != std::string::npos) {
            req_start = i + 3;  // skip header + separator line
        }
        if (l.find("RESOURCEAVAILABILITIES:") != std::string::npos) {
            avail_start = i + 2;  // skip header line
        }
    }

    p.n = total_jobs - 2;  // exclude super-source (job 1) and super-sink (job total_jobs)
    p.K = num_renewable;

    int total = p.n + 2;  // 0..n+1
    p.duration.resize(total, 0);
    p.resource.resize(total, std::vector<int>(p.K, 0));
    p.successors.resize(total);
    p.predecessors.resize(total);
    p.capacity.resize(p.K, 0);

    // Parse precedence relations
    // .sm jobs are 1-indexed; we map to 0-indexed (job 1 → 0, job N → n+1)
    for (int i = prec_start; i < (int)lines.size(); i++) {
        std::string t = trim(lines[i]);
        if (t.empty() || t[0] == '*') break;
        std::istringstream iss(t);
        int jobnr, modes, nsuc;
        iss >> jobnr >> modes >> nsuc;
        int src = jobnr - 1;  // convert to 0-indexed
        for (int s = 0; s < nsuc; s++) {
            int suc;
            iss >> suc;
            suc -= 1;  // convert to 0-indexed
            p.successors[src].push_back(suc);
            p.predecessors[suc].push_back(src);
        }
    }

    // Parse requests/durations
    for (int i = req_start; i < (int)lines.size(); i++) {
        std::string t = trim(lines[i]);
        if (t.empty() || t[0] == '*') break;
        std::istringstream iss(t);
        int jobnr, mode, dur;
        iss >> jobnr >> mode >> dur;
        int idx = jobnr - 1;  // convert to 0-indexed
        p.duration[idx] = dur;
        for (int k = 0; k < p.K; k++) {
            iss >> p.resource[idx][k];
        }
    }

    // Parse resource availabilities
    {
        std::string t = trim(lines[avail_start]);
        std::istringstream iss(t);
        for (int k = 0; k < p.K; k++) {
            iss >> p.capacity[k];
        }
    }

    return p;
}

// ── Parse ProGenMax .SCH format ─────────────────────────────────────────────
static Problem parse_sch(std::ifstream& fin, const std::string& first_line) {
    Problem p;

    // First line: n  K  0  0
    {
        std::istringstream iss(first_line);
        iss >> p.n >> p.K;
    }

    int total = p.n + 2;  // activities 0..n+1
    p.duration.resize(total, 0);
    p.resource.resize(total, std::vector<int>(p.K, 0));
    p.successors.resize(total);
    p.predecessors.resize(total);
    p.capacity.resize(p.K, 0);

    // Precedence section: one line per activity 0..n+1
    // Format: activity_id  1  num_successors  succ1 succ2 ...  [lag1] [lag2] ...
    // Negative lags are maximal time lags (backward constraints) — skip for RCPSP.
    for (int i = 0; i < total; i++) {
        std::string line;
        if (!std::getline(fin, line)) break;
        std::istringstream iss(line);
        int act_id, modes, nsuc;
        iss >> act_id >> modes >> nsuc;
        std::vector<int> succs(nsuc);
        for (int s = 0; s < nsuc; s++) {
            iss >> succs[s];
        }
        // Read time lags in [value] format — only keep edges with lag >= 0
        for (int s = 0; s < nsuc; s++) {
            std::string token;
            if (!(iss >> token)) {
                // No lag info — treat as standard precedence
                p.successors[act_id].push_back(succs[s]);
                p.predecessors[succs[s]].push_back(act_id);
                continue;
            }
            // Parse "[value]"
            int lag = 0;
            if (token.front() == '[' && token.back() == ']') {
                lag = std::stoi(token.substr(1, token.size() - 2));
            }
            if (lag >= 0) {
                p.successors[act_id].push_back(succs[s]);
                p.predecessors[succs[s]].push_back(act_id);
            }
        }
    }

    // Duration/resource section: one line per activity 0..n+1
    // Format: activity_id  1  duration  r1 r2 ... rK
    for (int i = 0; i < total; i++) {
        std::string line;
        if (!std::getline(fin, line)) break;
        std::istringstream iss(line);
        int act_id, modes;
        iss >> act_id >> modes;
        iss >> p.duration[act_id];
        for (int k = 0; k < p.K; k++) {
            iss >> p.resource[act_id][k];
        }
    }

    // Last data line: resource capacities
    {
        std::string line;
        if (std::getline(fin, line)) {
            std::istringstream iss(line);
            for (int k = 0; k < p.K; k++) {
                iss >> p.capacity[k];
            }
        }
    }

    return p;
}

// ── Unified parse entry point ───────────────────────────────────────────────
Problem parse(const std::string& filename) {
    std::ifstream fin(filename);
    if (!fin.is_open()) {
        std::cerr << "Error: cannot open " << filename << std::endl;
        std::exit(1);
    }

    std::string first_line;
    std::getline(fin, first_line);

    if (is_sm_format(first_line)) {
        return parse_sm(fin, first_line);
    } else {
        return parse_sch(fin, first_line);
    }
}

// ── Topological sort (Kahn's algorithm, cycle-resilient) ────────────────────
// Returns a precedence-feasible ordering of activities 0..n+1.
// If cycles exist (possible in .SCH files), breaks them by forcing the
// lowest in-degree node into the queue when it stalls.
std::vector<int> topological_sort(const Problem& p) {
    int total = p.n + 2;
    std::vector<int> in_degree(total, 0);
    for (int i = 0; i < total; i++) {
        in_degree[i] = (int)p.predecessors[i].size();
    }

    std::vector<bool> processed(total, false);
    std::vector<int> queue;
    for (int i = 0; i < total; i++) {
        if (in_degree[i] == 0) queue.push_back(i);
    }

    std::vector<int> order;
    order.reserve(total);
    int head = 0;
    while ((int)order.size() < total) {
        // Process everything currently in the queue
        while (head < (int)queue.size()) {
            int u = queue[head++];
            if (processed[u]) continue;
            processed[u] = true;
            order.push_back(u);
            for (int v : p.successors[u]) {
                if (!processed[v] && --in_degree[v] == 0) {
                    queue.push_back(v);
                }
            }
        }

        if ((int)order.size() >= total) break;

        // Cycle detected — force the unprocessed node with lowest in-degree
        int best = -1;
        for (int i = 0; i < total; i++) {
            if (!processed[i]) {
                if (best == -1 || in_degree[i] < in_degree[best]) {
                    best = i;
                }
            }
        }
        if (best != -1) {
            in_degree[best] = 0;
            queue.push_back(best);
        }
    }
    return order;
}

// ── Remove edges that violate topological order (cycle-breaking cleanup) ────
// After topological sort with forced cycle breaks, some edges go "backwards".
// Remove them from the predecessor/successor lists so SSGS sees a clean DAG.
void remove_back_edges(Problem& p, const std::vector<int>& order) {
    int total = p.n + 2;
    std::vector<int> pos(total);  // position of each activity in the order
    for (int i = 0; i < total; i++) {
        pos[order[i]] = i;
    }

    for (int u = 0; u < total; u++) {
        // Remove successors that appear before u in the order
        auto& succ = p.successors[u];
        succ.erase(std::remove_if(succ.begin(), succ.end(),
            [&](int v) { return pos[v] <= pos[u]; }), succ.end());
    }

    // Rebuild predecessors from clean successors
    for (int i = 0; i < total; i++) p.predecessors[i].clear();
    for (int u = 0; u < total; u++) {
        for (int v : p.successors[u]) {
            p.predecessors[v].push_back(u);
        }
    }
}

// ── Serial Schedule Generation Scheme (SSGS) ───────────────────────────────
// Takes a precedence-feasible activity list and returns start times + makespan.
// activity_list must contain all activities 0..n+1 in a topological order.
struct Schedule {
    std::vector<int> start_time;  // start_time[i] for activity i
    int makespan;                 // = start_time[n+1]
};

Schedule ssgs(const Problem& p, const std::vector<int>& activity_list) {
    int total = p.n + 2;

    // Upper bound on horizon: sum of all durations
    int horizon = 0;
    for (int i = 0; i < total; i++) horizon += p.duration[i];
    horizon = std::max(horizon, 1);

    // Resource usage profile: usage[t * K + k] = units of resource k used at time t
    std::vector<int> usage(horizon * p.K, 0);

    std::vector<int> start_time(total, 0);
    std::vector<int> finish_time(total, 0);

    for (int act : activity_list) {
        int dur = p.duration[act];

        // Earliest start from precedence: max of all predecessor finish times
        int es = 0;
        for (int pred : p.predecessors[act]) {
            es = std::max(es, finish_time[pred]);
        }

        if (dur == 0) {
            // Dummy activity or zero-duration — no resource check needed
            start_time[act] = es;
            finish_time[act] = es;
            continue;
        }

        // Find earliest feasible start time >= es where resources are available
        // for the entire duration [t, t + dur)
        int t = es;
        while (true) {
            bool feasible = true;
            for (int tau = t; tau < t + dur; tau++) {
                for (int k = 0; k < p.K; k++) {
                    if (usage[tau * p.K + k] + p.resource[act][k] > p.capacity[k]) {
                        feasible = false;
                        // Jump to tau+1 as the next candidate start
                        t = tau + 1;
                        break;
                    }
                }
                if (!feasible) break;
            }
            if (feasible) break;
        }

        // Schedule activity at time t
        start_time[act] = t;
        finish_time[act] = t + dur;

        // Update resource usage
        for (int tau = t; tau < t + dur; tau++) {
            for (int k = 0; k < p.K; k++) {
                usage[tau * p.K + k] += p.resource[act][k];
            }
        }
    }

    Schedule sched;
    sched.start_time = std::move(start_time);
    sched.makespan = sched.start_time[p.n + 1];
    return sched;
}

// ── Feasibility validator ───────────────────────────────────────────────────
bool validate(const Problem& p, const Schedule& sched) {
    int total = p.n + 2;
    bool ok = true;

    // Check precedence
    for (int i = 0; i < total; i++) {
        for (int j : p.successors[i]) {
            if (sched.start_time[j] < sched.start_time[i] + p.duration[i]) {
                std::cerr << "PRECEDENCE VIOLATION: " << i << " -> " << j
                          << " (S[" << j << "]=" << sched.start_time[j]
                          << " < S[" << i << "]+" << p.duration[i]
                          << "=" << sched.start_time[i] + p.duration[i] << ")\n";
                ok = false;
            }
        }
    }

    // Check resource capacity at every timestep
    int horizon = sched.makespan;
    for (int t = 0; t < horizon; t++) {
        std::vector<int> used(p.K, 0);
        for (int i = 0; i < total; i++) {
            if (sched.start_time[i] <= t && t < sched.start_time[i] + p.duration[i]) {
                for (int k = 0; k < p.K; k++) {
                    used[k] += p.resource[i][k];
                }
            }
        }
        for (int k = 0; k < p.K; k++) {
            if (used[k] > p.capacity[k]) {
                std::cerr << "RESOURCE VIOLATION at t=" << t
                          << " resource " << k << ": " << used[k]
                          << " > " << p.capacity[k] << "\n";
                ok = false;
            }
        }
    }

    if (ok) std::cerr << "Schedule is FEASIBLE" << std::endl;
    return ok;
}

// ── Debug print ─────────────────────────────────────────────────────────────
void print_problem(const Problem& p) {
    std::cerr << "n=" << p.n << " K=" << p.K << std::endl;
    std::cerr << "Capacities:";
    for (int k = 0; k < p.K; k++) std::cerr << " " << p.capacity[k];
    std::cerr << std::endl;

    for (int i = 0; i <= p.n + 1; i++) {
        std::cerr << "Activity " << i
                  << ": dur=" << p.duration[i]
                  << " res=[";
        for (int k = 0; k < p.K; k++) {
            if (k) std::cerr << ",";
            std::cerr << p.resource[i][k];
        }
        std::cerr << "] succ={";
        for (int j = 0; j < (int)p.successors[i].size(); j++) {
            if (j) std::cerr << ",";
            std::cerr << p.successors[i][j];
        }
        std::cerr << "} pred={";
        for (int j = 0; j < (int)p.predecessors[i].size(); j++) {
            if (j) std::cerr << ",";
            std::cerr << p.predecessors[i][j];
        }
        std::cerr << "}" << std::endl;
    }
}

// ── Main ────────────────────────────────────────────────────────────────────
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
