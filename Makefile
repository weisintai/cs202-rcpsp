CXX = g++
CXXFLAGS = -std=c++17 -O2 -march=native -flto -Wall -Wextra
TARGET = solver

$(TARGET): solver.cpp
	$(CXX) $(CXXFLAGS) -o $(TARGET) solver.cpp

debug: solver.cpp
	$(CXX) -std=c++17 -g -O0 -Wall -Wextra -fsanitize=address -o solver_debug solver.cpp

clean:
	rm -f $(TARGET) solver_debug

.PHONY: clean debug
