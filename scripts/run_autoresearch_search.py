from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rcpsp.config import HeuristicConfig
from scripts.autoresearch_lib import summarize_autoresearch
from scripts.guardrails_lib import run_guardrail_suite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded autoresearch-style search over solver configurations.")
    parser.add_argument("--backend", choices=("hybrid", "cp"), default="cp")
    parser.add_argument("--trials", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--main-preset", default="submission_quick")
    parser.add_argument("--main-datasets", nargs="*", default=None)
    parser.add_argument("--aux-preset", default="broad_generalization")
    parser.add_argument("--aux-datasets", nargs="*", default=["testset_ubo10", "testset_ubo100", "testset_ubo200"])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp" / "autoresearch-search")
    return parser.parse_args()


def sample_config(rng: random.Random) -> dict[str, float | int | None]:
    defaults = HeuristicConfig()
    max_restart_options: list[int | None] = [None, 4, 8, 12, 16, 24]
    return {
        "slack_weight": round(max(0.0, defaults.slack_weight + rng.uniform(-1.0, 1.0)), 3),
        "tail_weight": round(max(0.0, defaults.tail_weight + rng.uniform(-0.5, 0.5)), 3),
        "overload_weight": round(max(0.0, defaults.overload_weight + rng.uniform(-0.8, 0.8)), 3),
        "resource_weight": round(max(0.0, defaults.resource_weight + rng.uniform(-0.3, 0.3)), 3),
        "late_weight": round(max(0.0, defaults.late_weight + rng.uniform(-0.25, 0.25)), 3),
        "noise_weight": round(max(0.0, defaults.noise_weight + rng.uniform(-0.15, 0.15)), 3),
        "max_restarts": rng.choice(max_restart_options),
    }


def evaluate_trial(
    *,
    backend: str,
    trial_index: int,
    base_seed: int,
    config: dict[str, float | int | None],
    main_preset: str,
    main_datasets: list[str],
    aux_preset: str,
    aux_datasets: list[str],
    output_dir: Path,
) -> dict:
    trial_dir = output_dir / f"trial_{trial_index:02d}"
    trial_dir.mkdir(parents=True, exist_ok=True)
    heuristic_args = {key: value for key, value in config.items() if key != "max_restarts"}
    max_restarts = config["max_restarts"]

    main = run_guardrail_suite(
        backend=backend,
        preset=main_preset,
        datasets=main_datasets,
        seed=base_seed + trial_index * 97,
        max_restarts=max_restarts if isinstance(max_restarts, int) else None,
        heuristic_args=heuristic_args,
        output_dir=trial_dir / "main",
    )
    main_eval = summarize_autoresearch(main["summary"])

    aux = run_guardrail_suite(
        backend=backend,
        preset=aux_preset,
        datasets=aux_datasets,
        seed=base_seed + trial_index * 97,
        max_restarts=max_restarts if isinstance(max_restarts, int) else None,
        heuristic_args=heuristic_args,
        output_dir=trial_dir / "aux",
    )
    aux_runs = aux["summary"]["runs"]
    aux_exact = 0.0
    aux_unknown = 0.0
    aux_over_budget = 0.0
    aux_unknown_against_reference = 0.0
    aux_runtime_ratio_penalty = 0.0
    if aux_runs:
        aux_exact = sum(float(run["compare_summary"].get("exact_match_rate") or 0.0) for run in aux_runs) / len(aux_runs)
        aux_unknown = sum(float(run["benchmark_summary"].get("unknown") or 0.0) for run in aux_runs)
        aux_over_budget = sum(float(run["benchmark_summary"].get("over_budget") or 0.0) for run in aux_runs)
        aux_unknown_against_reference = sum(
            float(run["compare_summary"].get("unknown_against_known_reference") or 0.0) for run in aux_runs
        )
        for run in aux_runs:
            runtime = float(run["benchmark_summary"].get("avg_runtime_seconds") or 0.0)
            limit = float(run["time_limit"])
            aux_runtime_ratio_penalty += max(0.0, runtime / max(limit, 1e-9) - 1.0)

    combined_score = (
        float(main_eval["score"])
        + 40.0 * aux_exact
        - 2.0 * aux_unknown
        - 4.0 * aux_unknown_against_reference
        - 25.0 * aux_over_budget
        - 10.0 * aux_runtime_ratio_penalty
    )
    result = {
        "trial": trial_index,
        "backend": backend,
        "seed": base_seed + trial_index * 97,
        "config": config,
        "main_evaluation": main_eval,
        "aux_summary": {
            "datasets": aux_datasets,
            "avg_exact_match_rate": aux_exact,
            "unknown": aux_unknown,
            "over_budget": aux_over_budget,
            "unknown_against_known_reference": aux_unknown_against_reference,
            "runtime_ratio_penalty": aux_runtime_ratio_penalty,
        },
        "combined_score": combined_score,
        "main_output_dir": main["output_dir"],
        "aux_output_dir": aux["output_dir"],
    }
    (trial_dir / "search_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline = {
        "slack_weight": HeuristicConfig.slack_weight,
        "tail_weight": HeuristicConfig.tail_weight,
        "overload_weight": HeuristicConfig.overload_weight,
        "resource_weight": HeuristicConfig.resource_weight,
        "late_weight": HeuristicConfig.late_weight,
        "noise_weight": HeuristicConfig.noise_weight,
        "max_restarts": None,
    }
    candidates = [baseline]
    while len(candidates) < args.trials:
        candidates.append(sample_config(rng))

    results = []
    best: dict | None = None
    for index, config in enumerate(candidates, start=1):
        print(f"trial {index}/{len(candidates)} {config}", flush=True)
        result = evaluate_trial(
            backend=args.backend,
            trial_index=index,
            base_seed=args.seed,
            config=config,
            main_preset=args.main_preset,
            main_datasets=args.main_datasets,
            aux_preset=args.aux_preset,
            aux_datasets=args.aux_datasets,
            output_dir=args.output_dir,
        )
        results.append(result)
        if best is None or float(result["combined_score"]) > float(best["combined_score"]):
            best = result
        print(
            json.dumps(
                {
                    "trial": index,
                    "combined_score": result["combined_score"],
                    "main_score": result["main_evaluation"]["score"],
                    "aux_avg_exact_match_rate": result["aux_summary"]["avg_exact_match_rate"],
                    "config": config,
                }
            ),
            flush=True,
        )

    payload = {"best": best, "results": results}
    output_path = args.output_dir / "search_summary.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"best": best, "summary_path": str(output_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
