#ifndef VALIDATOR_H
#define VALIDATOR_H

#include "types.h"

// Validate a schedule against precedence and resource constraints.
// Prints violations to stderr. Returns true if feasible.
bool validate(const Problem& p, const Schedule& sched);

#endif
