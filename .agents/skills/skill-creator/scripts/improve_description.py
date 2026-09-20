#!/usr/bin/env python3
# Modified for GitHub Copilot from Anthropic's skill-creator. See ../NOTICE.
"""Propose a skill description from complete training results using Copilot CLI."""

import argparse
import json
import re
import sys
from pathlib import Path

from scripts.copilot_runner import CopilotError, require_success, run_prompt, write_json
from scripts.utils import parse_skill_md


def _call_copilot(prompt: str, model: str | None, timeout: int = 300) -> str:
    return require_success(run_prompt(prompt, model=model, timeout=timeout, profile="text"))


def extract_description(text: str) -> str:
    match = re.fullmatch(r"\s*<new_description>(.*?)</new_description>\s*", text, re.DOTALL)
    if (not match or not match.group(1).strip()
            or text.count("<new_description>") != 1 or text.count("</new_description>") != 1):
        raise ValueError("Copilot must return exactly one nonempty <new_description> element.")
    return match.group(1).strip()


def improve_description(skill_name: str, skill_content: str, current_description: str,
                        eval_results: dict, history: list[dict], model: str | None,
                        test_results: dict | None = None, log_dir: Path | None = None,
                        iteration: int | None = None) -> str:
    del test_results  # Held-out results must never enter the improvement prompt.
    results = eval_results["results"]
    if not results or any(result.get("pass") is None for result in results):
        raise ValueError("Cannot optimize from incomplete or empty training results.")
    training_history = [
        {key: item[key] for key in ("description", "train_passed", "train_total", "train_results")
         if key in item}
        for item in history
    ]
    prompt = f"""Improve the description of the Copilot skill "{skill_name}".
Copilot discovers skill metadata, then may invoke the skill to load its instructions.
These results measure natural selection in a controlled Copilot CLI profile, not
explicit invocation and not a guarantee about every Copilot host.

Current description:
{current_description}

Training results (including relevant requests and near misses):
{json.dumps(results, ensure_ascii=False)}

Previous training attempts:
{json.dumps(training_history, ensure_ascii=False)}

Skill instructions for context:
<skill_content>
{skill_content}
</skill_content>

Generalize failures into categories of user intent. Do not enumerate the test
queries or overfit to their wording. Explain when the skill is useful and the
outcome it provides; prefer clear, distinctive wording over repeated MUSTs.
Include enough trigger context to distinguish adjacent tasks, while keeping the
description concise. Do not claim that all simple tasks never trigger skills.
Avoid repeating unsuccessful descriptions. The hard limit is 1024 characters.

Return only the proposed description in <new_description>...</new_description>.
Do not call tools, edit any files, or apply the description yourself."""
    response = _call_copilot(prompt, model)
    description = extract_description(response)
    transcript = {"iteration": iteration, "prompt": prompt, "response": response}
    if len(description) > 1024:
        response = _call_copilot(
            f"{prompt}\n\nThe previous candidate was too long ({len(description)} characters):\n"
            f"{description}\nRewrite it below 1025 characters, retaining its general intent.",
            model,
        )
        transcript["rewrite_response"] = response
        description = extract_description(response)
    if len(description) > 1024 or any(char in description for char in "<>"):
        raise ValueError("The proposed description must be at most 1024 characters and contain no angle brackets.")
    transcript.update(final_description=description, char_count=len(description))
    if log_dir:
        write_json(log_dir / f"improve_iter_{iteration or 'standalone'}.json", transcript)
    return description


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-results", required=True, type=Path)
    parser.add_argument("--skill-path", required=True, type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--model", help="Copilot model; otherwise the isolated CLI default")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    results = json.loads(args.eval_results.read_text(encoding="utf-8"))
    history = json.loads(args.history.read_text(encoding="utf-8")) if args.history else []
    name, _, content = parse_skill_md(args.skill_path)
    candidate = improve_description(name, content, results["description"], results, history, args.model)
    print(json.dumps({"description": candidate, "history": history + [{
        "description": results["description"], **results["summary"], "results": results["results"],
    }]}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (CopilotError, ValueError, OSError) as exc:
        error = exc.as_dict() if isinstance(exc, CopilotError) else {"code": "input_error", "message": str(exc)}
        print(json.dumps({"status": "error", "error": error}))
        print(str(exc), file=sys.stderr)
        sys.exit(2 if error["code"] == "cli_unavailable" else 1)
