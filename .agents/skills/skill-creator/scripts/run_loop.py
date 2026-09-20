#!/usr/bin/env python3
# Modified for GitHub Copilot from Anthropic's skill-creator. See ../NOTICE.
"""Evaluate and improve Copilot skill descriptions with blinded held-out validation."""

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

from scripts.copilot_runner import CopilotError, preflight, write_json
from scripts.generate_report import generate_html
from scripts.improve_description import improve_description
from scripts.run_eval import run_eval, validate_eval_set
from scripts.utils import parse_skill_md


def split_eval_set(eval_set: list[dict], holdout: float, seed: int = 42) -> tuple[list[dict], list[dict]]:
    if not 0 < holdout < 1:
        raise ValueError("holdout must be between 0 and 1 when splitting.")
    cases = validate_eval_set(eval_set)
    rng = random.Random(seed)
    train, validation = [], []
    for label in (True, False):
        group = [case for case in cases if case["should_trigger"] is label]
        if len(group) < 2:
            raise ValueError("Held-out validation needs at least two cases of each class; use --holdout 0 otherwise.")
        rng.shuffle(group)
        count = min(len(group) - 1, max(1, int(len(group) * holdout)))
        validation.extend(group[:count])
        train.extend(group[count:])
    return train, validation


def _summary(results: list[dict]) -> dict:
    return {"total": len(results), "passed": sum(item["pass"] is True for item in results),
            "failed": sum(item["pass"] is False for item in results),
            "incomplete": sum(item["pass"] is None for item in results)}


def run_loop(eval_set: list[dict], skill_path: Path, description_override: str | None,
             num_workers: int, timeout: float, max_iterations: int,
             runs_per_query: int, trigger_threshold: float, holdout: float,
             model: str | None, verbose: bool, live_report_path: Path | None = None,
             log_dir: Path | None = None) -> dict:
    cases = validate_eval_set(eval_set)
    if max_iterations < 1 or not 0 <= holdout < 1:
        raise ValueError("max_iterations must be positive and holdout must be in [0, 1).")
    name, original, content = parse_skill_md(skill_path)
    current = original if description_override is None else description_override
    train, validation = split_eval_set(cases, holdout) if holdout else (cases, [])
    train_ids = {str(case["id"]) for case in train}
    history = []
    exit_reason = "max_iterations"
    for iteration in range(1, max_iterations + 1):
        if verbose:
            print(f"Iteration {iteration}/{max_iterations}", file=sys.stderr)
        evaluation = run_eval(
            train + validation, name, current, num_workers, timeout,
            runs_per_query=runs_per_query, trigger_threshold=trigger_threshold,
            model=model, skill_path=skill_path,
            log_dir=log_dir / f"iteration-{iteration}" if log_dir else None,
        )
        train_results = [result for result in evaluation["results"] if str(result["id"]) in train_ids]
        test_results = [result for result in evaluation["results"] if str(result["id"]) not in train_ids]
        training, testing = _summary(train_results), _summary(test_results)
        entry = {
            "iteration": iteration, "description": current, "status": evaluation["status"],
            "incomplete": evaluation["summary"]["incomplete"],
            "train_results": train_results, "test_results": test_results or None,
            "results": train_results, **training,
        }
        entry.update({f"train_{key}": value for key, value in training.items()})
        entry.update({f"test_{key}": value if validation else None for key, value in testing.items()})
        history.append(entry)
        if evaluation["status"] != "completed":
            exit_reason = "incomplete_evaluation"
            break
        if live_report_path:
            live_report_path.write_text(generate_html({
                "original_description": original, "best_description": current,
                "best_score": "in progress", "iterations_run": len(history),
                "holdout": holdout, "train_size": len(train), "test_size": len(validation),
                "history": history,
            }, auto_refresh=True, skill_name=name), encoding="utf-8")
        if not training["failed"]:
            exit_reason = "all_train_passed"
            break
        if iteration < max_iterations:
            current = improve_description(
                name, content, current, {"results": train_results, "summary": training},
                [{key: value for key, value in previous.items() if not key.startswith("test_")}
                 for previous in history],
                model, log_dir=log_dir, iteration=iteration,
            )
    eligible = [entry for entry in history if entry["status"] == "completed"]
    score_prefix = "test" if validation else "train"
    best = max(eligible, key=lambda entry: entry[f"{score_prefix}_passed"]) if eligible else None
    output = {
        "schema_version": 2, "status": "incomplete" if exit_reason == "incomplete_evaluation" else "completed",
        "exit_reason": exit_reason, "original_description": original,
        "best_description": best["description"] if best else None,
        "best_score": f"{best[f'{score_prefix}_passed']}/{best[f'{score_prefix}_total']}" if best else "unavailable",
        "best_train_score": f"{best['train_passed']}/{best['train_total']}" if best else None,
        "best_test_score": f"{best['test_passed']}/{best['test_total']}" if best and validation else None,
        "final_description": current, "iterations_run": len(history), "holdout": holdout,
        "train_size": len(train), "test_size": len(validation), "history": history,
    }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-set", required=True, type=Path)
    parser.add_argument("--skill-path", required=True, type=Path)
    parser.add_argument("--description")
    parser.add_argument("--num-workers", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--runs-per-query", type=int, default=3)
    parser.add_argument("--trigger-threshold", type=float, default=0.5)
    parser.add_argument("--holdout", type=float, default=0.4)
    parser.add_argument("--model")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--report", default="auto", help="HTML path, auto, or none; does not launch a browser")
    parser.add_argument("--results-dir", type=Path)
    args = parser.parse_args()
    cases = validate_eval_set(json.loads(args.eval_set.read_text(encoding="utf-8")))
    preflight()
    results_dir = args.results_dir or Path(tempfile.mkdtemp(prefix="skill-optimization-results-"))
    results_dir.mkdir(parents=True, exist_ok=True)
    if (results_dir / "results.json").exists():
        raise ValueError("Results already exist; choose a fresh results directory.")
    report = None if args.report == "none" else (
        results_dir / "report.html" if args.report == "auto" else Path(args.report))
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
    print(f"Maximum trigger calls: {len(cases) * args.runs_per_query * args.max_iterations}; "
          f"additional optimizer calls may be needed. Results: {results_dir}", file=sys.stderr)
    output = run_loop(
        cases, args.skill_path, args.description, args.num_workers, args.timeout,
        args.max_iterations, args.runs_per_query, args.trigger_threshold,
        args.holdout, args.model, args.verbose, report, results_dir / "logs",
    )
    write_json(results_dir / "results.json", output)
    if report:
        name, _, _ = parse_skill_md(args.skill_path)
        report.write_text(generate_html(output, skill_name=name), encoding="utf-8")
    print(json.dumps(output, indent=2))
    if output["status"] != "completed":
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (CopilotError, ValueError, OSError) as exc:
        error = exc.as_dict() if isinstance(exc, CopilotError) else {"code": "input_error", "message": str(exc)}
        print(json.dumps({"status": "error", "error": error}))
        print(str(exc), file=sys.stderr)
        sys.exit(2 if error["code"] == "cli_unavailable" else 1)
