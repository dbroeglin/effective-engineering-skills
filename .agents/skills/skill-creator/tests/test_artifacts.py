# Modified for GitHub Copilot. Licensed under Apache-2.0; see ../LICENSE.txt.
"""Focused compatibility checks for the existing benchmark and review scripts."""

import errno
import importlib.util
import json
import re
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from scripts.aggregate_benchmark import calculate_stats, generate_benchmark, generate_markdown
from scripts.generate_report import generate_html as report_html

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("review", ROOT / "eval-viewer" / "generate_review.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / (".reporting-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def make_run(self, workspace, config, passed, nested=False):
        eval_dir = workspace / "eval-1-example"
        run = eval_dir / config / ("run-1" if nested else "")
        (run / "outputs").mkdir(parents=True)
        (eval_dir / "eval_metadata.json").write_text(
            json.dumps({"eval_id": 1, "prompt": "café </script>"}), encoding="utf-8")
        (run / "outputs" / "answer.txt").write_text("answer </script>", encoding="utf-8")
        (run / "grading.json").write_text(json.dumps({
            "summary": {"passed": int(passed), "failed": int(not passed), "total": 1, "pass_rate": int(passed)},
            "expectations": [{"text": "Correct", "passed": passed, "evidence": "Checked"}],
            "execution_metrics": {"output_chars": 9999},
        }), encoding="utf-8")
        return run

    def test_flat_nested_legacy_and_delta_direction(self):
        for layout in ("flat", "nested", "legacy"):
            workspace = self.root / layout
            base = workspace / "runs" if layout == "legacy" else workspace
            self.make_run(base, "old_skill", False, layout != "flat")
            self.make_run(base, "new_skill", True, layout != "flat")
            benchmark = generate_benchmark(workspace)
            self.assertEqual(benchmark["runs"][0]["configuration"], "new_skill")
            self.assertEqual(benchmark["run_summary"]["delta"]["pass_rate"], "+1.00")
            self.assertIsNone(benchmark["runs"][0]["result"]["tokens"])
            self.assertIsNone(benchmark["runs"][0]["result"]["tool_calls"])
            self.assertIsNone(benchmark["runs"][0]["result"]["errors"])
            self.assertIsNone(benchmark["metadata"]["executor_model"])
            self.assertEqual(benchmark["metadata"]["runs_per_configuration"], 1)
            self.assertIn("unavailable", generate_markdown(benchmark))

    def test_measured_zero_and_runtime_tokens_are_not_replaced(self):
        run = self.make_run(self.root, "with_skill", True)
        timing = {"total_tokens": 0, "duration_ms": 0, "metrics_complete": True}
        (run / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
        (run / "run.json").write_text('{"model_actual":"actual-model"}', encoding="utf-8")
        benchmark = generate_benchmark(self.root)
        self.assertEqual(benchmark["runs"][0]["result"]["tokens"], 0)
        self.assertEqual(benchmark["runs"][0]["result"]["time_seconds"], 0)
        self.assertEqual(benchmark["metadata"]["executor_model"], "actual-model")
        timing.update(total_tokens=30, duration_ms=2000, modelMetrics={"inputTokens": 18, "outputTokens": 12, "reasoningTokens": 7})
        (run / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
        self.assertEqual(generate_benchmark(self.root)["runs"][0]["result"]["tokens"], 30)
        self.assertEqual(calculate_stats([None, 0])["mean"], 0)
        self.assertIsNone(calculate_stats([None])["mean"])

    def test_review_metadata_static_embedding_and_previous_feedback(self):
        self.make_run(self.root, "with_skill", True, nested=True)
        runs = review.find_runs(self.root)
        self.assertEqual(runs[0]["prompt"], "café </script>")
        self.assertEqual(runs[0]["eval_id"], 1)
        previous = {runs[0]["id"]: {"feedback": "Keep this", "outputs": runs[0]["outputs"]}}
        benchmark = generate_benchmark(self.root)
        page = review.generate_html(runs, "skill", previous, benchmark)
        embedded = json.loads(re.search(r"const EMBEDDED_DATA = (.*?);\n", page).group(1))
        self.assertEqual(embedded["benchmark"], benchmark)
        self.assertEqual(embedded["previous_feedback"][runs[0]["id"]], "Keep this")
        self.assertNotIn("answer </script>", page)
        self.assertIn("Apache License", page)
        self.assertIn("Modified for GitHub Copilot", page)
        selected = self.root / "selected"
        (selected / "outputs").mkdir(parents=True)
        (self.root / "eval_metadata.json").write_text('{"prompt":"outside"}', encoding="utf-8")
        self.assertEqual(review.find_runs(selected)[0]["prompt"], "(No prompt found)")

    def test_empty_and_incomplete_reports_have_no_winner(self):
        cases = [
            {"history": [], "best_description": None},
            {"best_description": None, "best_score": "unavailable", "history": [{
                "iteration": 1, "status": "incomplete", "incomplete": 1,
                "train_results": [{"query": "negative", "should_trigger": False, "status": "incomplete",
                                   "pass": None, "runs": 0, "triggers": 0}], "test_results": None,
            }]},
        ]
        for data in cases:
            page = report_html(data)
            self.assertIn("unavailable", page)
            self.assertNotIn('<tr class="best-row">', page)
            self.assertNotIn(">0/0<", page)

    def test_busy_port_fallback_does_not_mask_other_errors(self):
        first = review.create_server(review.ReviewHandler, 0)
        self.addCleanup(first.server_close)
        second = review.create_server(review.ReviewHandler, first.server_address[1])
        self.addCleanup(second.server_close)
        self.assertEqual(second.server_address[0], "127.0.0.1")
        self.assertNotEqual(first.server_address[1], second.server_address[1])
        self.assertNotEqual(first.socket.fileno(), -1)
        with patch.object(review, "LoopbackReviewServer", side_effect=PermissionError(errno.EACCES, "denied")) as server:
            with self.assertRaises(PermissionError):
                review.create_server(review.ReviewHandler, 3117)
            self.assertEqual(server.call_count, 1)

    @unittest.skipUnless(shutil.which("node"), "Optional JavaScript rendering check")
    def test_viewer_null_metrics_render_without_errors(self):
        self.make_run(self.root, "with_skill", False)
        page = review.generate_html(review.find_runs(self.root), "skill", benchmark=generate_benchmark(self.root))
        script = re.findall(r"<script>([\s\S]*?)</script>", page)[0].split("// ---- Start ----")[0]
        harness = """
const elements = {};
global.document = {
  addEventListener() {},
  getElementById(id) { return elements[id] ||= {style: {}, innerHTML: ""}; },
  createElement() { return {set textContent(v) { this.innerHTML = String(v); }}; }
};
"""
        result = subprocess.run(["node", "-"], input=harness + script + """
renderBenchmark();
const html = elements["benchmark-content"].innerHTML;
if (!html.includes("Unavailable") || !html.includes("0% ± 0%") || html.includes("NaN")) throw Error("Bad metric rendering");
""", capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
