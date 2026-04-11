CXX = g++
CXXFLAGS = -std=c++17 -O2 -march=native -flto -Wall -Wextra
TARGET = solver
SRCDIR = src

SRCS = $(SRCDIR)/main.cpp $(SRCDIR)/parser.cpp \
       $(SRCDIR)/ssgs.cpp $(SRCDIR)/validator.cpp $(SRCDIR)/priority.cpp \
       $(SRCDIR)/ga.cpp $(SRCDIR)/improvement.cpp

$(TARGET): $(SRCS) $(wildcard $(SRCDIR)/*.h)
	$(CXX) $(CXXFLAGS) -I$(SRCDIR) -o $(TARGET) $(SRCS)

debug: $(SRCS) $(wildcard $(SRCDIR)/*.h)
	$(CXX) -std=c++17 -g -O0 -Wall -Wextra -fsanitize=address -I$(SRCDIR) -o solver_debug $(SRCS)

clean:
	rm -f $(TARGET) $(TARGET).exe solver_debug

.PHONY: clean debug
