#!/usr/bin/env python3
# Modified for GitHub Copilot from Anthropic's skill-creator. See ../NOTICE.
"""Evaluate natural skill triggering through isolated Copilot CLI sessions."""

import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from scripts.copilot_runner import (
    CopilotError, natural_trigger, preflight, require_success, run_prompt, write_json,
)
from scripts.utils import parse_skill_md


def validate_eval_set(eval_set: list[dict]) -> list[dict]:
    if not isinstance(eval_set, list) or not eval_set:
        raise ValueError("The trigger eval set must be a nonempty JSON array.")
    normalized, ids, queries = [], set(), set()
    for index, item in enumerate(eval_set):
        if not isinstance(item, dict) or not isinstance(item.get("query"), str) or not item["query"].strip():
            raise ValueError(f"Case {index + 1} needs a nonempty query.")
        if not isinstance(item.get("should_trigger"), bool):
            raise ValueError(f"Case {index + 1} needs a boolean should_trigger.")
        case_id = item.get("id", index + 1)
        if isinstance(case_id, bool) or not isinstance(case_id, (int, str)):
            raise ValueError("Case IDs must be integers or strings.")
        query_key = " ".join(item["query"].split()).casefold()
        if str(case_id) in ids or query_key in queries:
            raise ValueError("Case IDs and normalized queries must be unique; use runs-per-query for repeats.")
        ids.add(str(case_id))
        queries.add(query_key)
        normalized.append({**item, "id": case_id})
    return normalized


def run_single_query(query: str, skill_path: Path, description: str, timeout: float,
                     model: str | None = None, artifact_dir: Path | None = None,
                     cli: dict | None = None) -> dict:
    name, _, _ = parse_skill_md(skill_path)
    natural_trigger([], name, query)  # Reject explicitly forced queries before paying for a call.
    fixture = "---\n" + yaml.safe_dump({"name": name, "description": description}, sort_keys=False)
    fixture += "---\n\nThis is a trigger-only evaluation fixture. After loading, briefly acknowledge the request.\n"
    try:
        record = run_prompt(query, model=model, timeout=timeout, skill_path=skill_path,
                            skill_content=fixture, profile="trigger", artifact_dir=artifact_dir, cli=cli)
        require_success(record)
        triggered = natural_trigger(record["events"], name, query)
        result = {"status": "triggered" if triggered else "not_triggered", "triggered": triggered,
                  "error": None, "model_actual": record["model_actual"], "timing": record["timing"]}
    except (CopilotError, OSError, ValueError) as exc:
        error = exc.as_dict() if isinstance(exc, CopilotError) else {"code": "input_error", "message": str(exc)}
        result = {"status": "error", "triggered": None, "error": error}
    if artifact_dir:
        write_json(artifact_dir / "trigger.json", result)
    return result


def run_eval(eval_set: list[dict], skill_name: str, description: str,
             num_workers: int, timeout: float, project_root: Path | None = None,
             runs_per_query: int = 1, trigger_threshold: float = 0.5,
             model: str | None = None, *, skill_path: Path,
             log_dir: Path | None = None) -> dict:
    del project_root  # Legacy parameter; evaluation never stages into the caller's repository.
    cases = validate_eval_set(eval_set)
    if num_workers < 1 or runs_per_query < 1 or timeout <= 0 or not 0 < trigger_threshold <= 1:
        raise ValueError("Workers, repeats, and timeout must be positive; threshold must be in (0, 1].")
    if not description.strip() or len(description) > 1024:
        raise ValueError("Description must contain 1 to 1024 characters.")
    actual_name, _, _ = parse_skill_md(skill_path)
    if actual_name != skill_name:
        raise ValueError("skill_name does not match the staged skill.")
    for case in cases:
        natural_trigger([], skill_name, case["query"])
    cli = preflight()
    samples = {str(case["id"]): [] for case in cases}
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {}
        for index, case in enumerate(cases):
            for repetition in range(1, runs_per_query + 1):
                folder = log_dir / f"query-{index + 1}" / f"run-{repetition}" if log_dir else None
                future = pool.submit(run_single_query, case["query"], skill_path, description,
                                     timeout, model, folder, cli)
                futures[future] = (str(case["id"]), repetition)
        for future in as_completed(futures):
            case_id, repetition = futures[future]
            samples[case_id].append({"run_number": repetition, **future.result()})
    results = []
    for case in cases:
        runs = sorted(samples[str(case["id"])], key=lambda result: result["run_number"])
        valid = [run for run in runs if run["triggered"] is not None]
        complete = len(valid) == runs_per_query
        triggers = sum(run["triggered"] for run in valid)
        rate = triggers / len(valid) if valid else None
        models = {run.get("model_actual") for run in valid}
        if len(models) > 1 or None in models:
            complete = False
        passed = ((rate >= trigger_threshold) if case["should_trigger"] else (rate < trigger_threshold)) if complete else None
        results.append({**case, "trigger_rate": rate, "triggers": triggers, "runs": len(valid),
                        "planned_runs": runs_per_query, "invalid_runs": runs_per_query - len(valid),
                        "status": "completed" if complete else "incomplete",
                        "model_actual": next(iter(models)) if len(models) == 1 else None,
                        "pass": passed, "samples": runs})
    models = {result["model_actual"] for result in results if result["status"] == "completed"}
    if len(models) > 1:
        for result in results:
            result.update(status="incomplete", **{"pass": None})
    passed = sum(result["pass"] is True for result in results)
    failed = sum(result["pass"] is False for result in results)
    incomplete = len(results) - passed - failed
    return {
        "schema_version": 2, "skill_name": skill_name, "description": description,
        "backend": "copilot-cli", "cli_version": cli["cli_version"],
        "status": "incomplete" if incomplete else "completed", "results": results,
        "summary": {"total": len(results), "passed": passed, "failed": failed,
                    "incomplete": incomplete},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-set", required=True)
    parser.add_argument("--skill-path", type=Path, required=True)
    parser.add_argument("--description")
    parser.add_argument("--num-workers", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--runs-per-query", type=int, default=3)
    parser.add_argument("--trigger-threshold", type=float, default=0.5)
    parser.add_argument("--model")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    try:
        cases = validate_eval_set(json.loads(Path(args.eval_set).read_text(encoding="utf-8")))
        name, description, _ = parse_skill_md(args.skill_path)
        preflight()
        directory = args.results_dir or Path(tempfile.mkdtemp(prefix="skill-trigger-results-"))
        if (directory / "results.json").exists():
            raise ValueError("Results already exist; use a new results directory.")
        print(f"Trigger calls planned: {len(cases) * args.runs_per_query}; results: {directory}", file=sys.stderr)
        output = run_eval(cases, name, args.description if args.description is not None else description,
                          args.num_workers, args.timeout, runs_per_query=args.runs_per_query,
                          trigger_threshold=args.trigger_threshold, model=args.model,
                          skill_path=args.skill_path, log_dir=directory)
        write_json(directory / "results.json", output)
        print(json.dumps(output, indent=2))
        if output["status"] != "completed":
            sys.exit(1)
    except (CopilotError, ValueError, OSError) as exc:
        error = exc.as_dict() if isinstance(exc, CopilotError) else {"code": "input_error", "message": str(exc)}
        print(json.dumps({"status": "error", "error": error}))
        print(str(exc), file=sys.stderr)
        sys.exit(2 if error["code"] == "cli_unavailable" else 1)


if __name__ == "__main__":
    main()
