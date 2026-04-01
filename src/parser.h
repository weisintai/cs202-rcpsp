#ifndef PARSER_H
#define PARSER_H

#include "types.h"
#include <string>

// Parse a PSPLIB instance file (auto-detects .sm vs .SCH format)
Problem parse(const std::string& filename);

#endif
