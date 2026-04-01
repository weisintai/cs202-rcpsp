#include "parser.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <algorithm>

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
