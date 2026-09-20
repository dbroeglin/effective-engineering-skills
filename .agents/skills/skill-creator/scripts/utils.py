# Modified for GitHub Copilot; see ../NOTICE for upstream provenance.
"""Shared utilities for skill-creator scripts."""

from pathlib import Path

import yaml


def parse_skill_md(skill_path: Path) -> tuple[str, str, str]:
    """Parse SKILL.md, returning (name, description, unchanged UTF-8 content)."""
    with (skill_path / "SKILL.md").open(encoding="utf-8", newline="") as stream:
        content = stream.read()
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].lstrip("\ufeff").rstrip() != "---":
        raise ValueError("SKILL.md missing frontmatter (no opening ---)")
    end_index = next(
        (index for index, line in enumerate(lines[1:], 1) if line.rstrip() == "---"),
        None,
    )
    if end_index is None:
        raise ValueError("SKILL.md missing frontmatter (no closing ---)")
    try:
        frontmatter = yaml.safe_load("".join(lines[1:end_index]))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise ValueError("Frontmatter must be a YAML dictionary")
    for field in ("name", "description"):
        value = frontmatter.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"'{field}' must be a nonempty string")
    return frontmatter["name"], frontmatter["description"], content
