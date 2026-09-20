<!-- SPDX-License-Identifier: Apache-2.0 -->
# Copilot CLI bridge

Use Python 3.10+, PyYAML from `requirements.txt`, Git on `PATH`, and an
authenticated Copilot CLI. Run Python modules from the skill directory.
Examples use Windows separators; adapt paths to your operating system.

```text
python -m scripts.copilot_runner --preflight
```

Preflight checks local availability/capabilities, not successful authentication or
model execution. If CLI or shell execution is unavailable, the **host** announces
the native-subagent fallback in `SKILL.md`. Other failures remain errors; do not
automatically install software, copy credentials, change models, or widen access.
Python cannot call the host's native subagent tools. No SDK is required.

## Worker calls

The host schedules paired workers and handles grading/review; the bridge runs one
self-contained prompt in a fresh CLI context. For example:

```text
python -m scripts.copilot_runner --prompt-file "<task.txt>" --profile behavior --skill-path "<skill>" --artifacts-dir "<run-dir>" --input "inputs\sample.txt=<source-file>"
python -m scripts.copilot_runner --prompt-file "<grader.txt>" --profile grade --artifacts-dir "<grader-dir>" --input "inputs\answer.txt=<run-dir>\outputs\answer.txt"
```

- Task prompts refer to staged input paths and save deliverables under `outputs/`.
  Use `with_skill/run-1`, `without_skill/run-1`, or `old_skill/run-1` as run folders.
  Omit `--skill-path` and the loading instruction for a no-skill baseline.
- Repeat `--input relative=source` for each required **regular file**, including
  transcripts. Input directories are not accepted. Prompts must not depend on
  access to the original repository or unstaged paths.
- Include `agents/grader.md`, `agents/comparator.md`, or `agents/analyzer.md` in the
  appropriate self-contained role prompt. Give blind comparisons neutral A/B
  labels. `grade` is read-only; the host saves its answer as `grading.json` beside
  the executor's artifacts, keeping grader artifacts separate.
- `--profile text` is for text-only work such as description improvement.
  Add `--model <id>` only for an explicit supported choice; otherwise record the
  CLI's actual default, which may differ from the host's model.
- Behavior can read/write its isolated working directory; shell and URL access
  are denied by default. Use scoped `--allow-tool <rule>` only for approved tasks
  needing extra capabilities. Do not use blanket permission/path bypasses.

Check the returned status before using results. The bridge exports outputs,
transcript, timing, and diagnostics to `--artifacts-dir`; it does not aggregate
cases or decide whether to revise the skill. Native fallback follows the same
host-led workflow, but labels prompt-controlled baselines and missing telemetry.

## Isolation

Each CLI working directory gets a real `git init --quiet` boundary and a fresh
`COPILOT_HOME`. A fresh home alone did **not** prevent ancestor skill discovery.
Run-local `settings.json` disables unwanted built-ins/hooks/memory; `config.json`
holds managed trust state. The enabled inventory must match the staged target
(or be empty for a baseline). User settings are not rewritten.

An existing `GH_TOKEN` authenticated the isolated probe without copying credentials;
this does not prove every file-backed login works with a fresh home. The runtime
package cache remains shared. Copied workspaces and CLI permissions are not an
OS sandbox, and organizational policy still applies.

## Conformance limits

The observed contract is **Copilot CLI 1.0.85 on Windows**. A matching or newer
version alone is not proof of protocol compatibility; see the checks in
[`copilot_runner.py`](../scripts/copilot_runner.py).

- Prompts use stdin without `-p`; with both present, the tested CLI ignored stdin.
  JSONL uses `--output-format=json --stream=on`. Narrow tool permissions worked
  without `--allow-all-tools`; trigger/text runs expose only `skill` and deny
  shell, writes, and URL access.
- Trigger scoring correlates `assistant.message.data.toolRequests`, exact target
  arguments, and successful `tool.execution_start`/`tool.execution_complete`.
  A valid negative also needs normal completion (`type: result`, `exitCode: 0`).
- Trigger fixtures retain name/description with a harmless body. They measure
  description-led selection, not other metadata or permissions; these scores do
  not establish auto-invocation for a skill configured to disable it.
- `session.skills_loaded`, `skill.invoked`, and `assistant.usage` were **not**
  forwarded. Explicit slash invocation can produce the same tool events: only
  controlled, unforced queries with verified inventory support natural-trigger
  inference. Ambiguous provenance, timeouts, malformed streams, and load failures
  are unavailable/invalid measurements, not valid negatives.
- Actual model identity comes from `assistant.message.data.model` when present.
  Final `--usage-output-file` data can supply usage. In this version, `tokenDetails`
  input/cache-read/cache-write/output buckets are disjoint; `modelMetrics` input
  already includes cached input, so adding both double-counts. Missing values are
  `null`, not zero, character-count estimates, or dollars. Keep executor and grader
  durations separate.

`scripts.run_eval` measures triggering; `scripts.run_loop` improves descriptions
using training failures and held-out validation. These are separate from forced
with-skill behavior tests. Without verified discovery and activation evidence,
retain qualitative description review rather than fabricating trigger scores.
