# SPDX-License-Identifier: Apache-2.0
"""Focused offline checks for parsing and portable ZIP distribution."""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from uuid import uuid4

from scripts.package_skill import package_skill
from scripts.quick_validate import validate_skill
from scripts.utils import parse_skill_md

SKILL_ROOT = Path(__file__).resolve().parents[1]


class SkillPackagingTests(unittest.TestCase):
    def setUp(self):
        self.workspace = SKILL_ROOT.parents[2] / f".packaging-{uuid4().hex}"
        self.skill = self.workspace / "scope Ω" / "sample-skill"
        self.skill.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.workspace)
        self.content = (
            "---\r\nname: sample-skill\r\ndescription: >-\r\n"
            "  Handle café inputs\r\n  and quoted text.\r\n"
            "metadata:\r\n  version: '1.0'\r\nuser-invocable: false\r\n---\r\n# Body\r\n"
        ).encode("utf-8")
        (self.skill / "SKILL.md").write_bytes(self.content)

    def package(self, output=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return package_skill(self.skill, output or self.workspace / "archives")

    def test_yaml_and_utf8_content_are_preserved(self):
        name, description, content = parse_skill_md(self.skill)
        self.assertEqual(name, "sample-skill")
        self.assertEqual(description, "Handle café inputs and quoted text.")
        self.assertEqual(content.encode("utf-8"), self.content)
        self.assertTrue(validate_skill(self.skill)[0])
        (self.skill / "SKILL.md").write_text(
            "---\nname: sample-skill\ndescription: 'Don''t remove \"quotes\".'\n---\n",
            encoding="utf-8",
        )
        self.assertEqual(parse_skill_md(self.skill)[1], "Don't remove \"quotes\".")

    def test_missing_malformed_and_empty_frontmatter_fail(self):
        for content in ("No header", "---\nname: [\n---\n", "---\nname: ''\ndescription: ''\n---\n"):
            with self.subTest(content=content):
                (self.skill / "SKILL.md").write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    parse_skill_md(self.skill)
                self.assertFalse(validate_skill(self.skill)[0])
                self.assertIsNone(self.package())

    def test_zip_keeps_resources_and_own_legal_files_but_not_generated_data(self):
        included = ["scripts/run.py", "assets/template.bin", "references/guide.md",
                    "eval-viewer/generate_review.py", "LICENSE.txt", "NOTICE"]
        excluded = ["evals/evals.json", "tests/test_case.py", ".git/config",
                    ".venv/config", ".env", "outputs/result.txt"]
        for relative in included + excluded:
            path = self.skill / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"Input skill's own content")
        result = self.package()
        self.assertIsNotNone(result)
        self.assertEqual(result.suffix, ".zip")
        with zipfile.ZipFile(result) as archive:
            self.assertEqual(archive.read("sample-skill/SKILL.md"), self.content)
            for relative in included:
                self.assertEqual(archive.read(f"sample-skill/{relative}"), b"Input skill's own content")
            for relative in excluded:
                self.assertNotIn(f"sample-skill/{relative}", archive.namelist())
            archive.extractall(self.workspace / "installed")
        self.assertTrue(validate_skill(self.workspace / "installed" / "sample-skill")[0])

    def test_destination_inside_source_is_rejected(self):
        self.assertIsNone(self.package(self.skill))
        self.assertIsNone(self.package(self.skill / "new-output"))
        self.assertFalse((self.skill / "new-output").exists())

    def test_symlink_escape_is_rejected(self):
        outside = self.workspace / "outside.txt"
        outside.write_text("Do not package", encoding="utf-8")
        try:
            (self.skill / "linked.txt").symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"Symlink privilege unavailable: {exc}")
        self.assertIsNone(self.package())
        self.assertFalse((self.workspace / "archives").exists())

    def test_direct_and_module_entrypoints_work_from_another_directory(self):
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("PYTHONPATH", None)
        for script in ("quick_validate", "package_skill"):
            for module in (False, True):
                with self.subTest(script=script, module=module):
                    command = (["-m", f"scripts.{script}"] if module
                               else [str(SKILL_ROOT / "scripts" / f"{script}.py")])
                    args = [str(self.skill)]
                    if script == "package_skill":
                        args.append(str(self.workspace / "archives"))
                    completed = subprocess.run(
                        [sys.executable, *command, *args], cwd=self.workspace,
                        env={**env, **({"PYTHONPATH": str(SKILL_ROOT)} if module else {})},
                        capture_output=True, text=True, encoding="utf-8", timeout=30,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
