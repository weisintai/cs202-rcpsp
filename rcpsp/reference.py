from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from urllib.request import urlopen


REFERENCE_URLS = {
    "sm_j10": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/sm_j10/optimum/optimum.csv",
    "sm_j20": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/sm_j20/optimum/optimum.csv",
    "sm_j30": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/sm_j30/optimum/optimum.csv",
    "testset_ubo10": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo10/optimum/optimum.csv",
    "testset_ubo20": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo20/optimum/optimum.csv",
    "testset_ubo50": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo50/optimum/optimum.csv",
    "testset_ubo100": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo100/optimum/optimum.csv",
    "testset_ubo200": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo200/optimum/optimum.csv",
    "testset_ubo500": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo500/optimum/optimum.csv",
    "testset_ubo1000": "https://raw.githubusercontent.com/ptal/kobe-scheduling/master/data/rcpsp-max/testset_ubo1000/optimum/optimum.csv",
}
ROOT = Path(__file__).resolve().parent.parent
LOCAL_REFERENCE_ROOT = ROOT / "benchmarks" / "data"


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


def local_reference_path(dataset: str) -> Path:
    return LOCAL_REFERENCE_ROOT / dataset / "optimum" / "optimum.csv"


def parse_reference_csv(text: str) -> dict[str, ReferenceValue]:
    rows = csv.DictReader(StringIO(text))
    values: dict[str, ReferenceValue] = {}
    for row in rows:
        name = normalize_instance_name(row["problem"])
        values[name] = parse_reference_value(row["optimum"])
    return values


def fetch_reference_values(dataset: str) -> dict[str, ReferenceValue]:
    if dataset not in REFERENCE_URLS:
        available = ", ".join(sorted(REFERENCE_URLS))
        raise ValueError(f"unknown dataset {dataset!r}; expected one of: {available}")

    path = local_reference_path(dataset)
    if path.exists():
        return parse_reference_csv(path.read_text(encoding="utf-8"))

    try:
        text = urlopen(REFERENCE_URLS[dataset]).read().decode()
    except Exception as exc:
        raise RuntimeError(
            (
                f"reference data for {dataset!r} was not found locally at {path} "
                f"and could not be fetched from {REFERENCE_URLS[dataset]}: {exc}. "
                f"Run `python scripts/fetch_reference_csvs.py --datasets {dataset}` "
                "to cache it under benchmarks/data."
            )
        ) from exc
    return parse_reference_csv(text)
