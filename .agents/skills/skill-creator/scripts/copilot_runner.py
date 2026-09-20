# SPDX-License-Identifier: Apache-2.0
"""Isolated Copilot CLI execution. No SDK or host-tool impersonation."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from scripts.utils import parse_skill_md

SCHEMA_VERSION = 2
MINIMUM_VERSION = (1, 0, 85)
RUNTIME_PROFILE = "isolated-cli-v1"
FALLBACK_MESSAGE = (
    "Copilot CLI is unavailable in this environment; using native subagents instead. "
    "The controlling agent must dispatch them; this Python process cannot."
)
COPY_EXCLUDES = {".git", ".venv", "__pycache__", "node_modules", "tests", "evals"}


class CopilotError(RuntimeError):
    def __init__(self, code: str, message: str, *, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.code = code
        self.stdout = stdout
        self.stderr = stderr

    def as_dict(self) -> dict:
        return {"code": self.code, "message": str(self)}


def _stop_windows_tree(process: subprocess.Popen, started: str) -> None:
    # Native Copilot launchers can stall inside an additional Windows Job.
    # Keep the parent's process handle alive and target only its PID descendants.
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise CopilotError("process_control", "PowerShell is required for owned-process cleanup on Windows.")
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$started=[datetime]::Parse('{started}').ToUniversalTime(); "
        "function Stop-Owned([int]$target) { "
        "if($target -eq $PID) { throw 'Refusing to terminate the cleanup process' }; "
        "try { $live=Get-Process -Id $target -ErrorAction Stop; $null=$live.Handle; "
        "Stop-Process -Id $target -Force; "
        "if(-not $live.WaitForExit(3000)) { throw 'Owned process did not exit' } "
        "} catch { if(Get-Process -Id $target -ErrorAction SilentlyContinue) { throw } } }; "
        "function Stop-Children([int]$parent) { "
        "$children=@(Get-CimInstance Win32_Process -Filter \"ParentProcessId=$parent\" | "
        "Where-Object { $_.CreationDate.ToUniversalTime() -ge $started }); "
        "foreach($child in $children) { Stop-Children $child.ProcessId; "
        "Stop-Owned $child.ProcessId } }; "
        f"Stop-Children {process.pid}; "
    )
    if process.poll() is None:
        script += f"Stop-Owned {process.pid}"
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8",
        errors="replace", timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise CopilotError("process_control",
                           f"Owned process cleanup failed ({result.returncode}): {redact(result.stderr or result.stdout)}")


def redact(text: str) -> str:
    for key in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "COPILOT_PROVIDER_API_KEY",
                "COPILOT_PROVIDER_BEARER_TOKEN"):
        value = os.environ.get(key)
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def capture(command: list[str], *, cwd: Path | None = None, env: dict | None = None,
            prompt: str | None = None, timeout: float = 30) -> tuple[int, str, str]:
    """communicate drains both pipes on Windows and POSIX without select()."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive")
    started = datetime.now(timezone.utc).isoformat()
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        try:
            stdout, stderr = process.communicate(
                prompt + "\n" if prompt is not None and not prompt.endswith("\n") else prompt,
                timeout=timeout,
            )
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            if os.name == "nt":
                _stop_windows_tree(process, started)
            else:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    _stop_windows_tree(process, started)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=5)
            code = "cancelled" if isinstance(exc, KeyboardInterrupt) else "timeout"
            raise CopilotError(code, f"Copilot {code}. {redact(stderr).strip()}",
                               stdout=redact(stdout), stderr=redact(stderr)) from exc
        return process.returncode, redact(stdout), redact(stderr)
    finally:
        try:
            if os.name == "nt":
                _stop_windows_tree(process, started)
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def preflight() -> dict:
    executable = shutil.which("copilot")
    if not executable:
        raise CopilotError("cli_unavailable", FALLBACK_MESSAGE)
    if Path(executable).suffix.lower() == ".ps1":
        raise CopilotError("cli_unavailable", "A native executable or command shim is required. " + FALLBACK_MESSAGE)
    try:
        code, output, error = capture([executable, "--no-auto-update", "--version"])
        match = re.search(r"GitHub Copilot CLI (\d+)\.(\d+)\.(\d+)", output)
        if code or not match:
            raise CopilotError("cli_preflight", f"Cannot identify Copilot CLI: {error or output}")
        version = tuple(map(int, match.groups()))
        if version < MINIMUM_VERSION or version[0] != 1:
            raise CopilotError("unsupported_cli", "This adapter requires Copilot CLI 1.x, at least 1.0.85.")
        code, help_text, error = capture([executable, "--no-auto-update", "--help"])
        required = ("--output-format", "--usage-output-file", "--no-custom-instructions", "--no-ask-user")
        if code or any(flag not in help_text for flag in required):
            raise CopilotError("unsupported_cli", f"Required Copilot CLI capabilities are missing. {error}")
    except OSError as exc:
        raise CopilotError("cli_preflight", f"Cannot execute Copilot CLI: {exc}") from exc
    return {"executable": executable, "cli_version": ".".join(match.groups()),
            "backend": "copilot-cli", "profile": RUNTIME_PROFILE}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@contextmanager
def temporary_workspace():
    directory = tempfile.TemporaryDirectory(prefix="skill-creator-")
    try:
        yield directory.name
    finally:
        for attempt in range(5):
            try:
                directory.cleanup()
                break
            except PermissionError as exc:
                if attempt == 4:
                    raise CopilotError("cleanup_error", f"Workspace remains locked: {directory.name}") from exc
                time.sleep(0.2 * (attempt + 1))


def _copy_tree(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        if any(part in COPY_EXCLUDES for part in path.relative_to(source).parts):
            continue
        if path.is_symlink():
            raise CopilotError("unsafe_input", f"Symlinks are not allowed in staged skill resources: {path}")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*COPY_EXCLUDES))


def skill_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file() and not any(part in COPY_EXCLUDES for part in item.relative_to(path).parts):
            digest.update(item.relative_to(path).as_posix().encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


def clean_events(stdout: str, *, allow_incomplete: bool = False) -> list[dict]:
    events = []
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line.lstrip("\ufeff"))
        except json.JSONDecodeError as exc:
            if allow_incomplete and index == len(lines) - 1:
                continue
            raise CopilotError("protocol_error", "CLI stdout is not valid JSONL.") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise CopilotError("protocol_error", "CLI event lacks a valid type.")
        if event["type"] in ("assistant.reasoning", "assistant.reasoning_delta"):
            continue
        data = event.get("data")
        if "data" in event and not isinstance(data, dict):
            raise CopilotError("protocol_error", "CLI event data must be an object.")
        if isinstance(data, dict):
            for key in ("reasoningOpaque", "reasoningText", "reasoning"):
                data.pop(key, None)
        events.append(event)
    return events


def summarize_events(events: list[dict], process_code: int) -> dict:
    results = [event for event in events if event["type"] == "result"]
    failures = [event for event in events if event["type"] in ("session.error", "abort")]
    if failures:
        raise CopilotError("runtime_error", json.dumps(failures[-1].get("data", {})))
    if process_code:
        raise CopilotError("process_error", f"Copilot exited with status {process_code}.")
    if len(results) != 1 or results[0].get("exitCode") != 0:
        raise CopilotError("protocol_error", "Missing or unsuccessful final CLI result record.")
    messages = [event["data"] for event in events if event["type"] == "assistant.message"
                and not event.get("agentId") and isinstance(event.get("data"), dict)]
    final = [message for message in messages if not message.get("toolRequests")
             and isinstance(message.get("content"), str) and message["content"]]
    if not final:
        raise CopilotError("protocol_error", "No completed assistant response in the CLI stream.")
    models = sorted({message["model"] for message in messages if message.get("model")})
    return {"response": final[-1]["content"],
            "model_actual": models[0] if len(models) == 1 else None,
            "models": models, "session_id": results[0].get("sessionId")}


def usage_metrics(usage: dict | None) -> dict:
    if not usage:
        return {"total_tokens": None, "metrics_source": None, "metrics_complete": False}
    details = usage.get("tokenDetails", {})
    names = ("input", "cache_read", "cache_write", "output")
    counts = [details.get(name, {}).get("tokenCount") for name in names]
    valid = all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in counts)
    return {
        "total_tokens": sum(counts) if valid else None,
        "token_details": details,
        "metrics_source": "copilot-usage-output-file",
        "metrics_complete": valid,
        "api_duration_ms": usage.get("totalApiDurationMs"),
    }


def natural_trigger(events: list[dict], name: str, query: str) -> bool:
    """CLI 1.0.85 omits skill.invoked; correlate model request/start/success."""
    if query.lstrip().startswith("/") or re.search(
        r"SKILL\.md|[.](?:agents|github)[/\\]skills|"
        rf"\b(?:use|invoke|load|run|consult)\s+(?:the\s+)?(?:skill\s+)?{re.escape(name)}\b", query, re.I
    ):
        raise CopilotError("forced_invocation", "Natural-trigger queries must not explicitly invoke or preload the skill.")
    requested, started, completed = set(), set(), set()
    for event in events:
        data = event.get("data", {})
        if event.get("agentId") or data.get("agentId") or data.get("parentToolCallId"):
            continue
        if event["type"] == "skill.invoked" and data.get("name") == name:
            if data.get("trigger") != "agent-invoked":
                raise CopilotError("unverified_trigger", "Skill was preloaded, explicitly invoked, or lacks provenance.")
        if event["type"] == "assistant.message":
            for request in data.get("toolRequests", []):
                if request.get("name") == "skill" and request.get("arguments", {}).get("skill") == name:
                    requested.add(request.get("toolCallId"))
        if event["type"] == "tool.execution_start" and data.get("toolName") == "skill":
            if data.get("arguments", {}).get("skill") == name:
                started.add(data.get("toolCallId"))
        if event["type"] == "tool.execution_complete" and data.get("toolCallId") in started:
            if not data.get("success"):
                raise CopilotError("skill_load_error", "The target skill invocation failed; this is not a negative trigger.")
            completed.add(data.get("toolCallId"))
    if requested != started or requested != completed:
        raise CopilotError("unverified_trigger", "Target invocation has no verified successful completion.")
    return bool((requested & started & completed) - {None})


def run_prompt(prompt: str, *, model: str | None = None, timeout: float = 120,
               skill_path: Path | None = None, skill_content: str | None = None,
               inputs: dict[str, Path] | None = None, profile: str = "text",
               allow_tools: list[str] | None = None, artifact_dir: Path | None = None,
               cli: dict | None = None) -> dict:
    cli = cli or preflight()
    if profile not in ("text", "trigger", "behavior", "grade"):
        raise ValueError(f"Unknown runner profile: {profile}")
    if artifact_dir and ((artifact_dir / "outputs").exists() or (artifact_dir / "run.json").exists()):
        raise ValueError("Run artifacts already exist; use a new run directory to avoid stale outputs.")
    if profile != "behavior" and allow_tools:
        raise ValueError("Additional tool approvals are only allowed for behavior runs.")
    if any(rule in ("shell", "write", "url", "*") for rule in allow_tools or []):
        raise ValueError("Use scoped tool permissions, not blanket shell/write/network approval.")
    record = {
        "schema_version": SCHEMA_VERSION, "backend": "copilot-cli",
        "cli_version": cli["cli_version"], "status": "error", "error": None,
        "model_requested": model or os.environ.get("COPILOT_MODEL"),
        "model_actual": None, "isolation": "verified", "profile": RUNTIME_PROFILE,
        "skill_hash": skill_hash(skill_path) if skill_path else None,
    }
    with temporary_workspace() as temporary:
        root = Path(temporary)
        work, home = root / "work", root / "profile"
        work.mkdir()
        home.mkdir()
        (work / "outputs").mkdir()
        git = shutil.which("git")
        if not git:
            raise CopilotError("missing_git", "Git is required to bound ancestor skill discovery.")
        code, _, error = capture([git, "init", "--quiet", str(work)])
        if code:
            raise CopilotError("workspace_error", f"Cannot initialize isolated workspace: {error}")
        target = None
        if skill_path:
            name, _, _ = parse_skill_md(skill_path)
            target = work / ".agents" / "skills" / name
            target.parent.mkdir(parents=True)
            _copy_tree(skill_path, target)
            if skill_content is not None:
                (target / "SKILL.md").write_text(skill_content, encoding="utf-8")
        for relative, source in (inputs or {}).items():
            destination = work / relative
            if Path(relative).is_absolute() or not destination.resolve().is_relative_to(work):
                raise CopilotError("unsafe_input", f"Input destination escapes workspace: {relative}")
            if source.is_symlink() or not source.is_file():
                raise CopilotError("unsafe_input", f"Input must be a regular file: {source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        env = os.environ.copy()
        for key in ("COPILOT_SKILLS_DIRS", "COPILOT_CUSTOM_INSTRUCTIONS_DIRS"):
            env.pop(key, None)
        env.update(COPILOT_HOME=str(home), COPILOT_ALLOW_ALL="false", COPILOT_AUTO_UPDATE="false")
        settings = {"disableAllHooks": True, "memory": False, "ide": {"autoConnect": False},
                    "customAgents": {"defaultLocalOnly": True}}
        write_json(home / "settings.json", settings)
        write_json(home / "config.json", {"trustedFolders": [str(work)]})
        command = [cli["executable"], "--no-auto-update", "-C", str(work)]

        def inventory() -> list[dict]:
            code, text, error = capture(command + ["skill", "list", "--json"], cwd=work, env=env)
            if code:
                raise CopilotError("discovery_error", f"Cannot list isolated skills: {error}")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise CopilotError("discovery_error", "Skill inventory is not JSON.") from exc
            if not isinstance(data, list):
                raise CopilotError("discovery_error", "Skill inventory has an unsupported schema.")
            return data

        discovered = inventory()
        settings["disabledSkills"] = [item["name"] for item in discovered
                                      if not target or Path(item.get("path", "")).resolve() != target.resolve()]
        write_json(home / "settings.json", settings)
        discovered = inventory()
        active = [item for item in discovered if item.get("enabled")]
        expected = {str(target.resolve())} if target else set()
        if {str(Path(item.get("path", "")).resolve()) for item in active} != expected or len(active) != len(expected):
            raise CopilotError("isolation_error", "Active skill inventory does not match the staged configuration.")
        record["skill_inventory"] = [{"name": item["name"], "source": item["source"],
                                      "enabled": item["enabled"]} for item in discovered]
        command += [
            "--output-format=json", "--stream=on", "--no-color", "--no-custom-instructions",
            "--no-ask-user", "--disable-builtin-mcps", "--disallow-temp-dir",
            "--deny-tool=url", "--usage-output-file", str(root / "usage.json"),
        ]
        if os.name == "nt":
            command += ["--no-eager-powershell-resolution"]
        if profile in ("trigger", "text"):
            command += ["--available-tools=skill", "--deny-tool=shell", "--deny-tool=write"]
        else:
            command += ["--available-tools=skill,view,create,edit,apply_patch,glob,rg"]
            command += ["--deny-tool=shell"]
            if profile == "behavior":
                # Path verification still confines writes to the disposable cwd.
                # write(directory) is an exact suffix match, not a directory grant.
                command += ["--allow-tool=write"]
            else:
                command += ["--deny-tool=write"]
        for rule in allow_tools or []:
            if rule.startswith("shell("):
                command = [arg for arg in command if arg != "--deny-tool=shell"]
                command = [arg for arg in command if not arg.startswith("--available-tools=")]
                command += ["--available-tools=skill,view,create,edit,apply_patch,glob,rg,powershell,bash"]
            command.append(f"--allow-tool={rule}")
        if model:
            command += ["--model", model]
        started = time.perf_counter()
        events, usage = [], None
        try:
            code, stdout, stderr = capture(command, cwd=work, env=env, prompt=prompt, timeout=timeout)
            if code:
                raise CopilotError("process_error", f"Copilot exited with status {code}: {stderr.strip()}",
                                   stdout=stdout, stderr=stderr)
            events = clean_events(stdout)
            record.update(summarize_events(events, code))
            record["stderr"] = stderr
            usage_path = root / "usage.json"
            if usage_path.exists():
                try:
                    usage = json.loads(usage_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise CopilotError("protocol_error", "Usage output is malformed JSON.") from exc
            record["status"] = "completed"
            denied = [event for event in events if event["type"] == "tool.execution_complete"
                      and event.get("data", {}).get("success") is False
                      and re.search(r"permission|denied", json.dumps(event["data"].get("error", {})), re.I)]
            if denied:
                raise CopilotError("permission_denied", "A required tool was denied; this run is not a valid evaluation.")
        except CopilotError as exc:
            if exc.stdout:
                events = clean_events(exc.stdout, allow_incomplete=True)
            record["stderr"] = exc.stderr
            record["status"] = "timeout" if exc.code == "timeout" else "error"
            record["error"] = exc.as_dict()
        duration = (time.perf_counter() - started) * 1000
        timing = {"schema_version": SCHEMA_VERSION, "duration_ms": duration,
                  "total_duration_seconds": duration / 1000,
                  "executor_duration_seconds": duration / 1000, **usage_metrics(usage)}
        record["metrics_source"] = timing["metrics_source"]
        record["events"] = events
        record["timing"] = timing
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            for output in (work / "outputs").rglob("*"):
                if output.is_symlink():
                    raise CopilotError("unsafe_output", "Refusing to export a symbolic link from task outputs.")
            shutil.copytree(work / "outputs", artifact_dir / "outputs", dirs_exist_ok=True)
            if record.get("response"):
                (artifact_dir / "outputs" / "response.txt").write_text(record["response"], encoding="utf-8")
    if artifact_dir:
        write_json(artifact_dir / "timing.json", timing)
        write_json(artifact_dir / "run.json", {k: v for k, v in record.items() if k not in ("events", "timing", "response")})
        (artifact_dir / "events.jsonl").write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")
        (artifact_dir / "transcript.md").write_text(
            f"## Eval Prompt\n\n{prompt}\n\n## Response\n\n{record.get('response', '')}\n\n"
            f"## Status\n\n{record['status']}\n\n{json.dumps(record.get('error'))}\n", encoding="utf-8")
    return record


def require_success(record: dict) -> str:
    if record["status"] != "completed":
        error = record.get("error") or {"code": "runtime_error", "message": "Run did not complete."}
        raise CopilotError(error["code"], error["message"])
    return record["response"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", help="Check CLI availability without making model calls")
    parser.add_argument("--prompt-file", type=Path, help="Run a self-contained role/task prompt through the CLI")
    parser.add_argument("--profile", choices=("text", "grade", "behavior"), default="text")
    parser.add_argument("--skill-path", type=Path, help="Stage this skill for an intentional behavior run")
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--input", action="append", default=[], help="Staged relative name=source file")
    parser.add_argument("--artifacts-dir", type=Path)
    parser.add_argument("--allow-tool", action="append", default=[])
    args = parser.parse_args()
    if args.preflight == bool(args.prompt_file):
        parser.error("Specify exactly one of --preflight or --prompt-file.")
    try:
        if args.preflight:
            print(json.dumps(preflight(), indent=2))
        else:
            inputs = {}
            for item in args.input:
                if "=" not in item:
                    raise ValueError("--input requires relative_name=source_file.")
                relative, source = item.split("=", 1)
                if relative in inputs:
                    raise ValueError(f"Duplicate input name: {relative}")
                inputs[relative] = Path(source)
            record = run_prompt(args.prompt_file.read_text(encoding="utf-8"), profile=args.profile,
                                model=args.model, timeout=args.timeout, inputs=inputs,
                                skill_path=args.skill_path,
                                artifact_dir=args.artifacts_dir, allow_tools=args.allow_tool)
            print(json.dumps({key: value for key, value in record.items() if key != "events"}, indent=2))
            if record["status"] != "completed":
                sys.exit(1)
    except (CopilotError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, CopilotError) else "input_error"
        error = exc.as_dict() if isinstance(exc, CopilotError) else {"code": code, "message": str(exc)}
        print(json.dumps({"status": "unavailable" if code == "cli_unavailable" else "error", "error": error}))
        print(str(exc), file=sys.stderr)
        sys.exit(2 if code == "cli_unavailable" else 1)


if __name__ == "__main__":
    main()
