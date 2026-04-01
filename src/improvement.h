#ifndef IMPROVEMENT_H
#define IMPROVEMENT_H

#include "types.h"
#include <vector>

// Forward-backward improvement (double justification).
// Takes a schedule and repeatedly applies backward + forward SSGS passes
// until no improvement is found. Returns the improved schedule.
Schedule forward_backward_improve(const Problem& p, const Schedule& initial);

#endif
