#ifndef IMPROVEMENT_H
#define IMPROVEMENT_H

#include "types.h"
#include <chrono>
#include <vector>

// Forward-backward improvement (double justification).
// Takes a schedule and repeatedly applies backward + forward SSGS passes
// until no improvement is found. Returns the improved schedule.
Schedule forward_backward_improve(const Problem& p,
                                  const Schedule& initial,
                                  long long* schedule_counter = nullptr,
                                  long long schedule_limit = 0,
                                  std::chrono::steady_clock::time_point deadline =
                                      std::chrono::steady_clock::time_point::max());

#endif
