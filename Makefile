CXX = g++
CXXFLAGS = -std=c++17 -O2 -march=native -flto -Wall -Wextra
TARGET = solver
PYTHON = python3
SRCDIR = src

SRCS = $(SRCDIR)/main.cpp $(SRCDIR)/parser.cpp \
       $(SRCDIR)/ssgs.cpp $(SRCDIR)/validator.cpp $(SRCDIR)/priority.cpp \
       $(SRCDIR)/ga.cpp $(SRCDIR)/improvement.cpp

$(TARGET): $(SRCS) $(wildcard $(SRCDIR)/*.h)
	$(CXX) $(CXXFLAGS) -I$(SRCDIR) -o $(TARGET) $(SRCS)

debug: $(SRCS) $(wildcard $(SRCDIR)/*.h)
	$(CXX) -std=c++17 -g -O0 -Wall -Wextra -fsanitize=address -I$(SRCDIR) -o solver_debug $(SRCS)

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

report-harness: $(TARGET)
	$(PYTHON) scripts/run_report_harness.py --solver ./$(TARGET)

clean:
	rm -f $(TARGET) $(TARGET).exe solver_debug

.PHONY: clean debug bench-j10 bench-j20 bench-j30 bench-j60 bench-j90 bench-j120 report-harness
