CXX = g++
CXXFLAGS = -std=c++17 -O2 -march=native -flto -Wall -Wextra
TARGET = solver
PYTHON = python3

$(TARGET): solver.cpp
	$(CXX) $(CXXFLAGS) -o $(TARGET) solver.cpp

debug: solver.cpp
	$(CXX) -std=c++17 -g -O0 -Wall -Wextra -fsanitize=address -o solver_debug solver.cpp

bench-j10: $(TARGET)
	$(PYTHON) scripts/benchmark_rcpsp.py run --dataset j10 --solver ./solver --build-cmd "make"

bench-j20: $(TARGET)
	$(PYTHON) scripts/benchmark_rcpsp.py run --dataset j20 --solver ./solver --build-cmd "make"

bench-j30: $(TARGET)
	$(PYTHON) scripts/benchmark_rcpsp.py run --dataset j30 --solver ./solver --build-cmd "make"

bench-j60: $(TARGET)
	$(PYTHON) scripts/benchmark_rcpsp.py run --dataset j60 --solver ./solver --build-cmd "make"

bench-j90: $(TARGET)
	$(PYTHON) scripts/benchmark_rcpsp.py run --dataset j90 --solver ./solver --build-cmd "make"

bench-j120: $(TARGET)
	$(PYTHON) scripts/benchmark_rcpsp.py run --dataset j120 --solver ./solver --build-cmd "make"

clean:
	rm -f $(TARGET) solver_debug

.PHONY: clean debug bench-j10 bench-j20 bench-j30 bench-j60 bench-j90 bench-j120
