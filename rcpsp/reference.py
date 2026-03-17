from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from urllib.request import urlopen


REFERENCE_URLS = {
    "sm_j10": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/sm_j10/optimum/optimum.csv",
    "sm_j20": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/sm_j20/optimum/optimum.csv",
    "sm_j30": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/sm_j30/optimum/optimum.csv",
    "testset_ubo20": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo20/optimum/optimum.csv",
    "testset_ubo50": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo50/optimum/optimum.csv",
}


@dataclass(frozen=True)
class ReferenceValue:
    kind: str
    lower: int | None = None
    upper: int | None = None


def normalize_instance_name(name: str) -> str:
    lowered = name.strip().lower()
    if lowered.endswith(".sch"):
        return lowered[:-4]
    return lowered


def parse_reference_value(raw: str) -> ReferenceValue:
    value = raw.strip()
    if value == "unsat":
        return ReferenceValue(kind="unsat")
    if ".." in value:
        lower_text, upper_text = value.split("..", maxsplit=1)
        return ReferenceValue(kind="bounded", lower=int(lower_text), upper=int(upper_text))
    return ReferenceValue(kind="exact", lower=int(value), upper=int(value))


def fetch_reference_values(dataset: str) -> dict[str, ReferenceValue]:
    if dataset not in REFERENCE_URLS:
        available = ", ".join(sorted(REFERENCE_URLS))
        raise ValueError(f"unknown dataset {dataset!r}; expected one of: {available}")

    text = urlopen(REFERENCE_URLS[dataset]).read().decode()
    rows = csv.DictReader(StringIO(text))
    values: dict[str, ReferenceValue] = {}
    for row in rows:
        name = normalize_instance_name(row["problem"])
        values[name] = parse_reference_value(row["optimum"])
    return values
