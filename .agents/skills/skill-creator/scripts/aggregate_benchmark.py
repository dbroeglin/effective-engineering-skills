#!/usr/bin/env python3
# Modified for GitHub Copilot. See ../NOTICE and ../LICENSE.txt.
"""
Aggregate individual run results into benchmark summary statistics.

Reads grading.json files from run directories and produces:
- run_summary with mean, stddev, min, max for each metric
- delta between with_skill and without_skill configurations

Usage:
    python aggregate_benchmark.py <benchmark_dir>

Example:
    python aggregate_benchmark.py benchmarks/2026-01-15T10-30-00/

The script supports flat eval-N/with_skill/grading.json and these repeated layouts:

    Workspace layout (from skill-creator iterations):
    <benchmark_dir>/
    └── eval-N/
        ├── with_skill/
        │   ├── run-1/grading.json
        │   └── run-2/grading.json
        └── without_skill/
            ├── run-1/grading.json
            └── run-2/grading.json

    Legacy layout (with runs/ subdirectory):
    <benchmark_dir>/
    └── runs/
        └── eval-N/
            ├── with_skill/
            │   └── run-1/grading.json
            └── without_skill/
                └── run-1/grading.json
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def calculate_stats(values: list[float]) -> dict:
    """Calculate mean, stddev, min, max for available measurements."""
    values = [value for value in values if value is not None]
    if not values:
        return {"mean": None, "stddev": None, "min": None, "max": None}

    n = len(values)
    mean = sum(values) / n

    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0

    return {
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4)
    }


def ordered_configs(results: dict) -> list[str]:
    """Put the primary before its baseline, independent of directory order."""
    names = [name for name in results if name != "delta"]
    primary = next((name for name in ("with_skill", "new_skill") if name in names), None)
    baseline = next((name for name in ("without_skill", "old_skill") if name in names), None)
    return list(dict.fromkeys(name for name in (primary, baseline, *names) if name is not None))


def load_run_results(benchmark_dir: Path) -> dict:
    """
    Load all run results from a benchmark directory.

    Returns dict keyed by config name (e.g. "with_skill"/"without_skill",
    or "new_skill"/"old_skill"), each containing a list of run results.
    """
    runs_dir = benchmark_dir / "runs"
    if runs_dir.exists():
        search_dir = runs_dir
    elif list(benchmark_dir.glob("eval-*")):
        search_dir = benchmark_dir
    else:
        print(f"No eval directories found in {benchmark_dir} or {benchmark_dir / 'runs'}")
        return {}

    results: dict[str, list] = {}

    for eval_idx, eval_dir in enumerate(sorted(search_dir.glob("eval-*"))):
        metadata_path = eval_dir / "eval_metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, encoding="utf-8") as mf:
                    eval_id = json.load(mf).get("eval_id", eval_idx)
            except (json.JSONDecodeError, OSError):
                eval_id = eval_idx
        else:
            try:
                eval_id = int(eval_dir.name.split("-")[1])
            except ValueError:
                eval_id = eval_idx

        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir():
                continue
            run_dirs = sorted(config_dir.glob("run-*"))
            if (config_dir / "grading.json").is_file():
                run_dirs = [config_dir]
            if not run_dirs:
                continue
            config = config_dir.name
            results.setdefault(config, [])

            for run_dir in run_dirs:
                run_number = 1 if run_dir == config_dir else int(run_dir.name.split("-")[1])
                grading_file = run_dir / "grading.json"
                if not grading_file.exists():
                    print(f"Warning: grading.json not found in {run_dir}")
                    continue
                try:
                    with open(grading_file, encoding="utf-8") as f:
                        grading = json.load(f)
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON in {grading_file}: {e}")
                    continue

                result = {
                    "eval_id": eval_id,
                    "run_number": run_number,
                    "pass_rate": grading.get("summary", {}).get("pass_rate"),
                    "passed": grading.get("summary", {}).get("passed", 0),
                    "failed": grading.get("summary", {}).get("failed", 0),
                    "total": grading.get("summary", {}).get("total", 0),
                }

                timing = {}
                timing_file = run_dir / "timing.json"
                if timing_file.exists():
                    try:
                        with open(timing_file, encoding="utf-8") as tf:
                            timing = json.load(tf)
                    except json.JSONDecodeError:
                        pass
                embedded_timing = grading.get("timing") or {}
                result["time_seconds"] = None
                for source in (timing, embedded_timing):
                    seconds = source.get("executor_duration_seconds")
                    if seconds is None and source.get("duration_ms") is not None:
                        seconds = source["duration_ms"] / 1000
                    if seconds is None:
                        seconds = source.get("total_duration_seconds")
                    if seconds is not None:
                        result["time_seconds"] = seconds
                        break
                result["tokens"] = timing.get("total_tokens", embedded_timing.get("total_tokens"))
                if timing.get("metrics_complete") is False:
                    result["tokens"] = None

                metrics = grading.get("execution_metrics", {})
                result["tool_calls"] = metrics.get("total_tool_calls")
                result["errors"] = metrics.get("errors_encountered")

                result["model_actual"] = None
                manifest_path = run_dir / "run.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, encoding="utf-8") as mf:
                            result["model_actual"] = json.load(mf).get("model_actual")
                    except (json.JSONDecodeError, OSError):
                        pass

                raw_expectations = grading.get("expectations", [])
                for exp in raw_expectations:
                    if "text" not in exp or "passed" not in exp:
                        print(f"Warning: expectation in {grading_file} missing required fields (text, passed, evidence): {exp}")
                result["expectations"] = raw_expectations

                notes_summary = grading.get("user_notes_summary", {})
                notes = []
                notes.extend(notes_summary.get("uncertainties", []))
                notes.extend(notes_summary.get("needs_review", []))
                notes.extend(notes_summary.get("workarounds", []))
                result["notes"] = notes
                results[config].append(result)

    return results


def aggregate_results(results: dict) -> dict:
    """Aggregate run results into summary statistics and primary-minus-baseline deltas."""
    run_summary = {}
    configs = ordered_configs(results)
    for config in configs:
        runs = results.get(config, [])
        run_summary[config] = {
            "pass_rate": calculate_stats([r.get("pass_rate") for r in runs]),
            "time_seconds": calculate_stats([r.get("time_seconds") for r in runs]),
            "tokens": calculate_stats([r.get("tokens") for r in runs])
        }

    primary = run_summary.get(configs[0], {}) if configs else {}
    baseline = run_summary.get(configs[1], {}) if len(configs) > 1 else {}
    run_summary["delta"] = {}
    for metric, precision in (("pass_rate", 2), ("time_seconds", 1), ("tokens", 0)):
        a = primary.get(metric, {}).get("mean")
        b = baseline.get(metric, {}).get("mean")
        run_summary["delta"][metric] = f"{a - b:+.{precision}f}" if a is not None and b is not None else None
    return run_summary


def generate_benchmark(benchmark_dir: Path, skill_name: str = "", skill_path: str = "") -> dict:
    """Generate complete benchmark.json from run results."""
    results = load_run_results(benchmark_dir)
    run_summary = aggregate_results(results)

    runs = []
    for config in ordered_configs(results):
        for result in results[config]:
            runs.append({
                "eval_id": result["eval_id"],
                "configuration": config,
                "run_number": result["run_number"],
                "result": {
                    "pass_rate": result["pass_rate"],
                    "passed": result["passed"],
                    "failed": result["failed"],
                    "total": result["total"],
                    "time_seconds": result["time_seconds"],
                    "tokens": result["tokens"],
                    "tool_calls": result["tool_calls"],
                    "errors": result["errors"]
                },
                "expectations": result["expectations"],
                "notes": result["notes"]
            })

    eval_ids = sorted(set(r["eval_id"] for config in results.values() for r in config))
    models = {r.get("model_actual") for config in results.values() for r in config}
    repeats = {sum(r["eval_id"] == eval_id for r in config) for config in results.values() for eval_id in eval_ids}
    benchmark = {
        "metadata": {
            "skill_name": skill_name or "<skill-name>",
            "skill_path": skill_path or "<path/to/skill>",
            "executor_model": next(iter(models)) if len(models) == 1 else None,
            "analyzer_model": None,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "evals_run": eval_ids,
            "runs_per_configuration": next(iter(repeats)) if len(repeats) == 1 else None
        },
        "runs": runs,
        "run_summary": run_summary,
        "notes": []
    }
    return benchmark


def generate_markdown(benchmark: dict) -> str:
    """Generate human-readable benchmark.md from benchmark data."""
    metadata = benchmark["metadata"]
    run_summary = benchmark["run_summary"]
    configs = ordered_configs(run_summary)
    config_a = configs[0] if len(configs) >= 1 else "config_a"
    config_b = configs[1] if len(configs) >= 2 else "config_b"
    label_a = config_a.replace("_", " ").title()
    label_b = config_b.replace("_", " ").title()

    lines = [
        f"# Skill Benchmark: {metadata['skill_name']}",
        "",
        f"**Model**: {metadata['executor_model'] or 'unavailable'}",
        f"**Date**: {metadata['timestamp']}",
        f"**Evals**: {', '.join(map(str, metadata['evals_run']))} ({metadata['runs_per_configuration'] if metadata['runs_per_configuration'] is not None else 'variable'} runs each per configuration)",
        "",
        "## Summary",
        "",
        f"| Metric | {label_a} | {label_b} | Delta |",
        "|--------|------------|---------------|-------|",
    ]
    a_summary = run_summary.get(config_a, {})
    b_summary = run_summary.get(config_b, {})
    delta = run_summary.get("delta", {})

    def format_stat(stat, scale=1, precision=0, suffix=""):
        if stat.get("mean") is None:
            return "unavailable"
        return f"{stat['mean'] * scale:.{precision}f}{suffix} ± {stat['stddev'] * scale:.{precision}f}{suffix}"

    for metric, label, scale, precision, suffix in (
        ("pass_rate", "Pass Rate", 100, 0, "%"),
        ("time_seconds", "Time", 1, 1, "s"),
        ("tokens", "Tokens", 1, 0, ""),
    ):
        a = format_stat(a_summary.get(metric, {}), scale, precision, suffix)
        b = format_stat(b_summary.get(metric, {}), scale, precision, suffix)
        lines.append(f"| {label} | {a} | {b} | {delta.get(metric) if delta.get(metric) is not None else 'unavailable'} |")

    if benchmark.get("notes"):
        lines.extend(["", "## Notes", ""])
        for note in benchmark["notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate benchmark run results into summary statistics"
    )
    parser.add_argument(
        "benchmark_dir",
        type=Path,
        help="Path to the benchmark directory"
    )
    parser.add_argument(
        "--skill-name",
        default="",
        help="Name of the skill being benchmarked"
    )
    parser.add_argument(
        "--skill-path",
        default="",
        help="Path to the skill being benchmarked"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output path for benchmark.json (default: <benchmark_dir>/benchmark.json)"
    )

    args = parser.parse_args()

    if not args.benchmark_dir.exists():
        print(f"Directory not found: {args.benchmark_dir}")
        sys.exit(1)

    # Generate benchmark
    benchmark = generate_benchmark(args.benchmark_dir, args.skill_name, args.skill_path)

    # Determine output paths
    output_json = args.output or (args.benchmark_dir / "benchmark.json")
    output_md = output_json.with_suffix(".md")

    # Write benchmark.json
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(benchmark, f, indent=2)
    print(f"Generated: {output_json}")

    # Write benchmark.md
    markdown = generate_markdown(benchmark)
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"Generated: {output_md}")

    # Print summary
    run_summary = benchmark["run_summary"]
    configs = ordered_configs(run_summary)
    delta = run_summary.get("delta", {})

    print(f"\nSummary:")
    for config in configs:
        pr = run_summary[config]["pass_rate"]["mean"]
        label = config.replace("_", " ").title()
        score = f"{pr * 100:.1f}%" if pr is not None else "unavailable"
        print(f"  {label}: {score} pass rate")
    print(f"  Delta:         {delta.get('pass_rate', '—')}")


if __name__ == "__main__":
    main()
