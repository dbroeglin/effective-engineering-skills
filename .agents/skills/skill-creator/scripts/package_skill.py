#!/usr/bin/env python3
# Modified for GitHub Copilot; see ../NOTICE for upstream provenance.
"""Create an ordinary ZIP containing a skill and its own resources/legal files.

Run ``python -m scripts.package_skill <skill> [output-directory]`` from the
creator's root, or run this script by absolute path from another directory.
Output defaults to the current directory, outside the skill. Extract the ZIP
into a persistent Copilot skill root; this is not a native installer.
Known generated/credential paths are excluded, but review contents before sharing.
"""

import argparse
import fnmatch
import os
import stat
import sys
import zipfile
from pathlib import Path

if __package__:
    from .quick_validate import validate_skill
else:
    from quick_validate import validate_skill

EXCLUDE_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv",
    ".copilot", ".ssh", ".aws", ".azure", "credentials", "secrets",
}
EXCLUDE_GLOBS = {
    "*.pyc", ".env", ".env.*", "*.key", "*.pem", "credentials.*", "secrets.*",
}
EXCLUDE_FILES = {".ds_store", ".git-credentials", ".netrc", ".npmrc"}
ROOT_EXCLUDE_DIRS = {
    "evals", "tests", "outputs", "artifacts", "profiles", "runtime", "runtime-profiles", "dist",
}


def should_exclude(rel_path: Path) -> bool:
    """Check a path relative to the skill's parent (first part is its name)."""
    parts = [part.lower() for part in rel_path.parts[1:]]
    if not parts:
        return False
    if any(part in EXCLUDE_DIRS for part in parts) or parts[0] in ROOT_EXCLUDE_DIRS:
        return True
    return parts[-1] in EXCLUDE_FILES or any(
        fnmatch.fnmatchcase(parts[-1], pattern) for pattern in EXCLUDE_GLOBS)


def _reject_link(path: Path) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or (
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise ValueError(f"Symbolic links/reparse points are not supported: {path}")


def _walk_error(error):
    raise error


def package_skill(skill_path, output_dir=None):
    """Return the created ZIP path, or None with a diagnostic on failure."""
    try:
        skill_path = Path(skill_path).expanduser().absolute()
        _reject_link(skill_path)
        skill_path = skill_path.resolve(strict=True)
        if not skill_path.is_dir():
            raise ValueError(f"Not a skill directory: {skill_path}")
        _reject_link(skill_path / "SKILL.md")
        valid, message = validate_skill(skill_path)
        if not valid:
            raise ValueError(f"Validation failed: {message}")
        output_path = Path(output_dir if output_dir is not None else Path.cwd()).expanduser().resolve()
        if output_path.is_relative_to(skill_path):
            raise ValueError("Output directory must be outside the skill directory (no self-inclusion)")
        destination = output_path / f"{skill_path.name}.zip"
        if destination.exists() or destination.is_symlink():
            _reject_link(destination)

        files = []
        for directory, subdirs, names in os.walk(skill_path, onerror=_walk_error, followlinks=False):
            directory = Path(directory)
            subdirs[:] = [name for name in subdirs
                          if not should_exclude((directory / name).relative_to(skill_path.parent))]
            for name in subdirs + names:
                path = directory / name
                if should_exclude(path.relative_to(skill_path.parent)):
                    continue
                _reject_link(path)
                if path.is_file():
                    files.append(path)
        if destination.exists() and any(path.samefile(destination) for path in files):
            raise ValueError("Destination archive aliases a source file")
        output_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(files):
                _reject_link(path)
                archive.write(path, path.relative_to(skill_path.parent).as_posix())
        print(f"Packaged skill to: {destination}")
        return destination
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"Error packaging skill: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", type=Path)
    parser.add_argument("output_directory", nargs="?", type=Path)
    args = parser.parse_args(argv)
    result = package_skill(args.skill_path, args.output_directory)
    return 0 if result is not None else 1


if __name__ == "__main__":
    sys.exit(main())
