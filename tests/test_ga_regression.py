#!/usr/bin/env python3
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOLVER = ROOT / "solver"
INSTANCE = ROOT / "datasets/psplib/j30/instances/j305_1.sm"
GA_RE = re.compile(r"GA: (\d+) generations, (\d+) schedules, (\d+) restarts, best makespan: (\d+)")
MK_RE = re.compile(r"Makespan: (\d+)")


def run_solver(*args: str) -> tuple[int, int, int, int]:
    completed = subprocess.run(
        [str(SOLVER), str(INSTANCE), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    ga_match = GA_RE.search(completed.stderr)
    mk_match = MK_RE.search(completed.stderr)
    assert ga_match is not None, completed.stderr
    assert mk_match is not None, completed.stderr
    generations, schedules, restarts, best = map(int, ga_match.groups())
    makespan = int(mk_match.group(1))
    assert best == makespan, completed.stderr
    return generations, schedules, restarts, makespan


def main() -> None:
    run_a = run_solver("--schedules", "300000")
    run_b = run_solver("--schedules", "300000")
    run_c = run_solver("--schedules", "600000")

    assert run_a == run_b, f"fixed-budget run changed across repeats: {run_a} vs {run_b}"
    assert run_c[3] <= run_a[3], f"larger schedule budget regressed makespan: {run_a[3]} -> {run_c[3]}"

    print("repeat_300k:", run_a)
    print("repeat_300k_again:", run_b)
    print("budget_600k:", run_c)


if __name__ == "__main__":
    main()
