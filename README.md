# Effective engineering skills

A repository-maintained Copilot port of
[`skill-creator`](.agents/skills/skill-creator/SKILL.md), retaining its name and
`.agents\skills\skill-creator` location.

## Skills in this repository

- **[`skill-creator`](.agents/skills/skill-creator/SKILL.md)** — the maintained
  Copilot port of Anthropic's skill, described below.
- **[`effective-writing`](.agents/skills/effective-writing/SKILL.md)** — an
  independently-authored skill for writing clear, effective documentation,
  corporate/business documents, and LinkedIn or other social posts. Its guidance is
  an original synthesis of public-domain and openly-licensed writing standards; see
  its [`references/sources.md`](.agents/skills/effective-writing/references/sources.md)
  for attributions. Apache-2.0; not part of the upstream `skill-creator` port.

## Prerequisites and use

- **Python 3.10+**, **PyYAML** from the skill's `requirements.txt`, and **Git** on
  `PATH` for isolated evaluation repository boundaries.
- An authenticated **GitHub Copilot CLI** for preferred execution. **No SDK**.
- If CLI or shell execution is unavailable, explicitly announce:
  **“Copilot CLI is unavailable in this environment; using native subagents instead.”**
  Use independent host subagents, disclosing isolation/telemetry limitations.
  Other CLI errors are not missing-CLI fallback or valid negative scores.

The host coordinates paired cases, grading, and review through a small CLI
bridge. See the [workflow](.agents/skills/skill-creator/SKILL.md) and
[commands/conformance limits](.agents/skills/skill-creator/references/copilot-runtime.md).

## Install and develop

Use this checkout, or copy the **complete** skill directory/unpack its ordinary ZIP
into `<project>\.agents\skills`, yielding `skill-creator\SKILL.md`. Retain scripts,
references, assets, role documents, viewer, requirements, `LICENSE.txt`, and
`NOTICE`; resources resolve relative to the installed skill. A registered
`copilot skill add <directory>` location must remain available—it is not copied.

From the skill directory:

```powershell
python -m pip install -r requirements.txt
python -m scripts.copilot_runner --preflight
python -m unittest discover -s tests
```

## Ownership and license

The APM manifest/lock no longer own or deploy `anthropics/skills`; apply both
updates together. Do not adopt this fork with `apm uninstall`, including dry-run.
APM 0.28.0 install/update/prune preserved the fork in isolated checks. Pruning the
last cached dependency can remove the empty lockfile: rerun `apm lock` before
frozen installs. Both APM pack formats omit this first-party skill, so use the
complete directory/ZIP route instead.

Upstream: `anthropics/skills`, `skills/skill-creator`, commit
`41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f`. The
[unchanged Apache-2.0 license](.agents/skills/skill-creator/LICENSE.txt) retains
`Copyright 2026 Anthropic, PBC.` Our modifications use Apache-2.0 too; see the
repository-added [NOTICE](.agents/skills/skill-creator/NOTICE), not an upstream
notice or endorsement. This scope does not license the entire repository or
independently authored output skills. Preserve applicable legal material in
distributions and mark modified imported files **“Modified for GitHub Copilot”**.
