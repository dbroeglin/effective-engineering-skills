# SPDX-License-Identifier: Apache-2.0
"""Focused regression checks for the Copilot transport and existing eval loop."""

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from scripts.copilot_runner import (
    CopilotError, _copy_tree, capture, clean_events, natural_trigger, preflight, run_prompt, summarize_events, usage_metrics,
)
from scripts.improve_description import extract_description, improve_description
from scripts.run_eval import run_eval, validate_eval_set
from scripts.run_loop import run_loop, split_eval_set


def activation(name="sample", *, success=True):
    return [
        {"type": "assistant.message", "data": {"content": "", "model": "test-model",
         "toolRequests": [{"toolCallId": "call-1", "name": "skill", "arguments": {"skill": name}}]}},
        {"type": "tool.execution_start", "data": {"toolCallId": "call-1", "toolName": "skill",
                                                "arguments": {"skill": name}}},
        {"type": "tool.execution_complete", "data": {"toolCallId": "call-1", "success": success}},
    ]


def completion():
    return [
        {"type": "assistant.message", "data": {"content": "done", "model": "test-model", "toolRequests": []}},
        {"type": "result", "exitCode": 0, "sessionId": "test-session"},
    ]


class TransportTests(unittest.TestCase):
    def test_observed_cli_contract(self):
        events = activation() + completion()
        self.assertTrue(natural_trigger(events, "sample", "A relevant task"))
        self.assertEqual(summarize_events(events, 0)["response"], "done")
        self.assertFalse(natural_trigger(completion(), "sample", "An unrelated task"))
        self.assertFalse(natural_trigger(activation("sample-extra"), "sample", "A task"))

    def test_forced_preloaded_failed_and_uncorrelated_calls_are_not_negatives(self):
        for query in ("/sample request", "Use the skill sample", "Read SKILL.md"):
            with self.assertRaises(CopilotError):
                natural_trigger(activation(), "sample", query)
        for events in (
            activation(success=False), activation()[1:], activation()[:-1],
            [{"type": "skill.invoked", "data": {"name": "sample", "trigger": "context-load"}}],
        ):
            with self.assertRaises(CopilotError):
                natural_trigger(events, "sample", "A relevant task")
        nested = [{**event, "agentId": "child"} for event in activation()]
        self.assertFalse(natural_trigger(nested, "sample", "A task"))

    def test_protocol_requires_final_success(self):
        for events, code in ((completion()[:-1], 0), (completion(), 1),
                             (completion() + [{"type": "session.error", "data": {"message": "auth"}}], 0)):
            with self.assertRaises(CopilotError):
                summarize_events(events, code)
        for text in ("not json", '{"type":"assistant.message","data":[]}'):
            with self.assertRaises(CopilotError):
                clean_events(text)

    def test_reasoning_is_not_persisted(self):
        stream = json.dumps({"type": "assistant.reasoning_delta", "data": {"deltaContent": "private"}})
        stream += "\n" + json.dumps({"type": "assistant.message", "data": {"content": "answer", "reasoningOpaque": "private"}})
        events = clean_events(stream)
        self.assertEqual(len(events), 1)
        self.assertNotIn("reasoningOpaque", events[0]["data"])

    def test_missing_usage_is_not_zero_and_caches_are_not_double_counted(self):
        self.assertIsNone(usage_metrics(None)["total_tokens"])
        self.assertIsNone(usage_metrics({"tokenDetails": {"output": {"tokenCount": 5}}})["total_tokens"])
        data = {"tokenDetails": {name: {"tokenCount": count} for name, count in
                (("input", 4), ("cache_read", 4269), ("cache_write", 4541), ("output", 104))},
                "modelMetrics": {"x": {"usage": {"inputTokens": 8814, "reasoningTokens": 36}}}}
        self.assertEqual(usage_metrics(data)["total_tokens"], 8918)

    def test_missing_cli_has_explicit_fallback(self):
        with patch("scripts.copilot_runner.shutil.which", return_value=None):
            with self.assertRaises(CopilotError) as caught:
                preflight()
        self.assertEqual(caught.exception.code, "cli_unavailable")
        self.assertIn("native subagents", str(caught.exception))

    def test_staging_ignores_environment_links_but_rejects_resource_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            (source / ".venv").mkdir(parents=True)
            (source / "SKILL.md").write_text("skill", encoding="utf-8")
            try:
                (source / ".venv" / "python").symlink_to(sys.executable)
            except OSError:
                self.skipTest("Creating symlinks requires privileges on this platform.")
            _copy_tree(source, root / "staged")
            self.assertTrue((root / "staged" / "SKILL.md").is_file())
            self.assertFalse((root / "staged" / ".venv").exists())
            (source / "resource").symlink_to(sys.executable)
            with self.assertRaises(CopilotError):
                _copy_tree(source, root / "rejected")

    def test_cleanup_failure_cannot_publish_completed_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workspace, artifacts = root / "workspace", root / "artifacts"
            workspace.mkdir()

            @contextmanager
            def locked_workspace():
                yield str(workspace)
                raise CopilotError("cleanup_error", "Workspace remains locked.")

            stream = "\n".join(json.dumps(event) for event in completion())
            with patch("scripts.copilot_runner.temporary_workspace", locked_workspace), patch(
                "scripts.copilot_runner.capture",
                side_effect=[(0, "", ""), (0, "[]", ""), (0, "[]", ""), (0, stream, "")],
            ), patch("scripts.copilot_runner.shutil.which", return_value="git"):
                with self.assertRaises(CopilotError):
                    run_prompt("A task", artifact_dir=artifacts,
                               cli={"executable": "copilot", "cli_version": "test"})
            self.assertFalse((artifacts / "run.json").exists())

    def test_portable_capture_and_timeout(self):
        code, text, error = capture([sys.executable, "-c", "import sys; print(sys.stdin.read())"], prompt="hello")
        self.assertEqual(code, 0)
        self.assertEqual(text.strip(), "hello")
        self.assertEqual(error, "")
        with self.assertRaises(CopilotError) as caught:
            capture([sys.executable, "-c", "import time; print('started', flush=True); time.sleep(30)"], timeout=0.3)
        self.assertEqual(caught.exception.code, "timeout", str(caught.exception))
        self.assertIn("started", caught.exception.stdout)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.skill = Path(self.temp.name) / "sample"
        self.skill.mkdir()
        (self.skill / "SKILL.md").write_text("---\nname: sample\ndescription: A sample skill.\n---\nBody\n", encoding="utf-8")
        self.cases = [{"id": index, "query": f"task {index}", "should_trigger": index < 2} for index in range(4)]

    def tearDown(self):
        self.temp.cleanup()

    def test_split_and_invalid_cases(self):
        self.assertEqual(split_eval_set(self.cases, 0.4), split_eval_set(self.cases, 0.4))
        train, heldout = split_eval_set(self.cases, 0.4)
        self.assertFalse({item["id"] for item in train} & {item["id"] for item in heldout})
        for cases in ([], self.cases + [self.cases[0]], [{"query": "x", "should_trigger": "true"}]):
            with self.assertRaises(ValueError):
                validate_eval_set(cases)
        with self.assertRaises(ValueError):
            split_eval_set(self.cases[:2], 0.4)

    def test_execution_errors_do_not_pass_negative_queries(self):
        with patch("scripts.run_eval.preflight", return_value={"cli_version": "test"}), patch(
            "scripts.run_eval.run_single_query", return_value={"status": "error", "triggered": None,
                                                             "error": {"code": "auth", "message": "login required"}}
        ):
            result = run_eval(self.cases, "sample", "A sample skill.", 1, 10,
                              runs_per_query=1, skill_path=self.skill)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["summary"]["passed"], 0)
        self.assertTrue(all(item["pass"] is None for item in result["results"]))

    def test_incomplete_candidates_cannot_win(self):
        incomplete = {"status": "incomplete", "summary": {"incomplete": 4}, "results": [
            {**item, "pass": None, "triggers": 0, "runs": 0} for item in self.cases
        ]}
        with patch("scripts.run_loop.run_eval", return_value=incomplete), patch(
            "scripts.run_loop.improve_description"
        ) as improve:
            result = run_loop(self.cases, self.skill, None, 1, 10, 2, 1, 0.5, 0.4, None, False)
        self.assertIsNone(result["best_description"])
        self.assertEqual(result["status"], "incomplete")
        improve.assert_not_called()

    def test_description_parser_and_blinded_history(self):
        for response in ("", "plain text", "<new_description></new_description>",
                         "<new_description>a</new_description><new_description>b</new_description>"):
            with self.assertRaises(ValueError):
                extract_description(response)
        with patch("scripts.improve_description._call_copilot", return_value="<new_description>Better description.</new_description>") as call:
            description = improve_description(
                "sample", "body", "old", {"results": [{"query": "train", "pass": False}]},
                [{"description": "old", "test_results": ["HELD_OUT_SECRET"]}], None,
                test_results={"secret": "HELD_OUT_SECRET"},
            )
        self.assertEqual(description, "Better description.")
        self.assertNotIn("HELD_OUT_SECRET", call.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
