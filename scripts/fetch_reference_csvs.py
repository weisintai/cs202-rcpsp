from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rcpsp.reference import REFERENCE_URLS, local_reference_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache public reference optimum CSVs under benchmarks/data.")
    parser.add_argument(
        "--datasets",
        nargs="*",
        choices=tuple(sorted(REFERENCE_URLS)),
        default=("sm_j10", "sm_j20"),
        help="datasets to cache locally; defaults to the missing public exact-reference sets",
    )
    parser.add_argument("--force", action="store_true", help="overwrite an existing local optimum.csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for dataset in args.datasets:
        path = local_reference_path(dataset)
        if path.exists() and not args.force:
            print(f"skip {dataset}: {path} already exists")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"download {dataset}: {REFERENCE_URLS[dataset]}")
        path.write_bytes(urlopen(REFERENCE_URLS[dataset]).read())
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
