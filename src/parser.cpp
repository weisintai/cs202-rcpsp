#include "parser.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <stdexcept>

// ── Trim whitespace ─────────────────────────────────────────────────────────
static std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

static std::vector<std::string> split_ws(const std::string& s) {
    std::istringstream iss(s);
    std::vector<std::string> tokens;
    std::string token;
    while (iss >> token) tokens.push_back(token);
    return tokens;
}

// ── Detect format ───────────────────────────────────────────────────────────
// .sm files start with a line of asterisks; .SCH files start with integers.
static bool is_sm_format(const std::string& first_line) {
    std::string t = trim(first_line);
    return !t.empty() && t[0] == '*';
}

static Problem finalize_problem(Problem p) {
    p.horizon = 0;
    for (int dur : p.duration) {
        p.horizon += dur;
    }
    p.horizon = std::max(p.horizon, 1);

    for (int act = 0; act < p.n + 2; act++) {
        for (int k = 0; k < p.K; k++) {
            if (p.resource[act][k] > p.capacity[k]) {
                throw std::runtime_error(
                    "INFEASIBLE: activity " + std::to_string(act) +
                    " requires " + std::to_string(p.resource[act][k]) +
                    " units of resource " + std::to_string(k) +
                    " but capacity is only " + std::to_string(p.capacity[k]));
            }
        }
    }

    return p;
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
    // .sm jobs are 1-indexed; we map to 0-indexed (job 1 -> 0, job N -> n+1)
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

    return finalize_problem(std::move(p));
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

    // Precedence section: one line per activity 0..n+1.
    //
    // Old format:
    //   activity_id  1  num_successors  succ1 succ2 ... [lag1] [lag2] ...
    //
    // Updated assignment format:
    //   activity_id  num_successors  succ1 succ2 ...
    //
    // Negative lags are maximal time lags (backward constraints) — skip for RCPSP.
    for (int i = 0; i < total; i++) {
        std::string line;
        if (!std::getline(fin, line)) break;
        auto tokens = split_ws(line);
        if (tokens.empty()) continue;

        int act_id = std::stoi(tokens[0]);
        bool has_bracket_lag = false;
        for (const auto& token : tokens) {
            if (token.size() >= 2 && token.front() == '[' && token.back() == ']') {
                has_bracket_lag = true;
                break;
            }
        }

        int nsuc = 0;
        int succ_start = 0;
        if (has_bracket_lag) {
            nsuc = std::stoi(tokens[2]);
            succ_start = 3;
        } else if ((int)tokens.size() == 2 + std::stoi(tokens[1])) {
            // New compact format: act_id nsuc succ...
            nsuc = std::stoi(tokens[1]);
            succ_start = 2;
        } else if ((int)tokens.size() == 3 + std::stoi(tokens[2])) {
            // Old format without explicit lag tokens.
            nsuc = std::stoi(tokens[2]);
            succ_start = 3;
        } else if (tokens.size() >= 3 && std::stoi(tokens[1]) == 1) {
            // Ambiguous short lines like "11 1 0" should still be treated as old.
            nsuc = std::stoi(tokens[2]);
            succ_start = 3;
        } else {
            std::cerr << "Error: unrecognised .SCH precedence line: " << line << std::endl;
            std::exit(1);
        }

        std::vector<int> succs(nsuc);
        for (int s = 0; s < nsuc; s++) {
            succs[s] = std::stoi(tokens[succ_start + s]);
        }

        if (!has_bracket_lag) {
            for (int succ : succs) {
                p.successors[act_id].push_back(succ);
                p.predecessors[succ].push_back(act_id);
            }
            continue;
        }

        // Old lag-bearing format: only keep edges with lag >= 0.
        int lag_start = succ_start + nsuc;
        for (int s = 0; s < nsuc; s++) {
            int lag = 0;
            if (lag_start + s < (int)tokens.size()) {
                const std::string& token = tokens[lag_start + s];
                if (token.size() >= 2 && token.front() == '[' && token.back() == ']') {
                    lag = std::stoi(token.substr(1, token.size() - 2));
                }
            }
            if (lag >= 0) {
                p.successors[act_id].push_back(succs[s]);
                p.predecessors[succs[s]].push_back(act_id);
            }
        }
    }

    // Duration/resource section: one line per activity 0..n+1.
    //
    // Old format:
    //   activity_id  1  duration  r1 r2 ... rK
    //
    // Updated assignment format:
    //   activity_id  duration  r1 r2 ... rK
    for (int i = 0; i < total; i++) {
        std::string line;
        if (!std::getline(fin, line)) break;
        auto tokens = split_ws(line);
        if (tokens.empty()) continue;

        int act_id = std::stoi(tokens[0]);
        int dur_idx = -1;
        int res_start = -1;
        if ((int)tokens.size() == p.K + 2) {
            dur_idx = 1;
            res_start = 2;
        } else if ((int)tokens.size() == p.K + 3) {
            dur_idx = 2;
            res_start = 3;
        } else {
            std::cerr << "Error: unrecognised .SCH duration/resource line: " << line << std::endl;
            std::exit(1);
        }

        p.duration[act_id] = std::stoi(tokens[dur_idx]);
        for (int k = 0; k < p.K; k++) {
            p.resource[act_id][k] = std::stoi(tokens[res_start + k]);
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

    return finalize_problem(std::move(p));
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
