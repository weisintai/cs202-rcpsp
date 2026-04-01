#ifndef SSGS_H
#define SSGS_H

#include "types.h"
#include <vector>

// Serial Schedule Generation Scheme.
// Takes a precedence-feasible activity list (topological order of 0..n+1)
// and returns a feasible schedule with start times and makespan.
Schedule ssgs(const Problem& p, const std::vector<int>& activity_list);

#endif
