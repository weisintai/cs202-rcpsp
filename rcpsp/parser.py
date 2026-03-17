from __future__ import annotations

from pathlib import Path

from .models import Edge, Instance


class ParseError(ValueError):
    pass


def _clean_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def parse_sch(path: str | Path) -> Instance:
    file_path = Path(path)
    lines = _clean_lines(file_path)
    if not lines:
        raise ParseError(f"{file_path} is empty")

    header = [int(token) for token in lines[0].split()]
    if len(header) < 2:
        raise ParseError(f"{file_path} has an invalid header: {lines[0]!r}")

    n_jobs = header[0]
    n_resources = header[1]
    n_activities = n_jobs + 2
    expected_lines = 2 * n_jobs + 6
    if len(lines) != expected_lines:
        raise ParseError(
            f"{file_path} should have {expected_lines} non-empty lines, found {len(lines)}"
        )

    successor_lines = lines[1 : 1 + n_activities]
    duration_lines = lines[1 + n_activities : 1 + 2 * n_activities]
    capacity_line = lines[-1]

    edges: list[Edge] = []
    for raw in successor_lines:
        tokens = raw.split()
        if len(tokens) < 3:
            raise ParseError(f"Malformed successor row in {file_path}: {raw!r}")
        activity = int(tokens[0])
        successor_count = int(tokens[2])
        expected = 3 + 2 * successor_count
        if len(tokens) != expected:
            raise ParseError(
                f"Malformed successor row in {file_path}: expected {expected} tokens, got {len(tokens)}"
            )
        successors = [int(token) for token in tokens[3 : 3 + successor_count]]
        lags = [int(token.strip("[]")) for token in tokens[3 + successor_count :]]
        for successor, lag in zip(successors, lags, strict=True):
            edges.append(Edge(source=activity, target=successor, lag=lag))

    durations = [0] * n_activities
    demands = [[0] * n_resources for _ in range(n_activities)]
    for raw in duration_lines:
        tokens = [int(token) for token in raw.split()]
        expected = 3 + n_resources
        if len(tokens) != expected:
            raise ParseError(
                f"Malformed duration row in {file_path}: expected {expected} integers, got {len(tokens)}"
            )
        activity = tokens[0]
        durations[activity] = tokens[2]
        demands[activity] = tokens[3:]

    capacities = tuple(int(token) for token in capacity_line.split())
    if len(capacities) != n_resources:
        raise ParseError(
            f"{file_path} should define {n_resources} resource capacities, found {len(capacities)}"
        )

    outgoing_lists: list[list[Edge]] = [[] for _ in range(n_activities)]
    incoming_lists: list[list[Edge]] = [[] for _ in range(n_activities)]
    for edge in edges:
        outgoing_lists[edge.source].append(edge)
        incoming_lists[edge.target].append(edge)

    return Instance(
        name=file_path.stem,
        path=file_path,
        n_jobs=n_jobs,
        n_resources=n_resources,
        durations=tuple(durations),
        demands=tuple(tuple(row) for row in demands),
        capacities=capacities,
        edges=tuple(edges),
        outgoing=tuple(tuple(row) for row in outgoing_lists),
        incoming=tuple(tuple(row) for row in incoming_lists),
    )
