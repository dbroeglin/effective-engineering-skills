#!/usr/bin/env python3
# Modified for GitHub Copilot. See ../NOTICE and ../LICENSE.txt.
"""Generate an HTML report from run_loop.py output.

Takes the JSON output from run_loop.py and generates a visual HTML report
showing each description attempt with check/x for each test case.
Distinguishes between train and test queries.
"""

import argparse
import html
import json
import sys
from pathlib import Path

def generate_html(data: dict, auto_refresh: bool = False, skill_name: str = "") -> str:
    """Generate HTML report from loop output data. If auto_refresh is True, adds a meta refresh tag."""
    history = data.get("history", []) or []
    title_prefix = html.escape(skill_name + " \u2014 ") if skill_name else ""

    # Get all unique queries from train and test sets, with should_trigger info
    train_queries: list[dict] = []
    test_queries: list[dict] = []
    if history:
        for r in history[0].get("train_results", history[0].get("results", [])) or []:
            train_queries.append({"query": r["query"], "should_trigger": r.get("should_trigger", True)})
        for r in history[0].get("test_results", []) or []:
            test_queries.append({"query": r["query"], "should_trigger": r.get("should_trigger", True)})

    refresh_tag = '    <meta http-equiv="refresh" content="5">\n' if auto_refresh else ""
    skill_root = Path(__file__).resolve().parents[1]
    license_text = (skill_root / "LICENSE.txt").read_text(encoding="utf-8")
    notice = (skill_root / "NOTICE").read_text(encoding="utf-8") if (skill_root / "NOTICE").exists() else ""
    attribution = "<!-- Modified for GitHub Copilot. Template license only; user outputs retain their own licenses.\n" + notice + license_text + "\n-->"

    html_parts = ["""<!DOCTYPE html>
""" + attribution + """
<html>
<head>
    <meta charset="utf-8">
""" + refresh_tag + """    <title>""" + title_prefix + """Skill Description Optimization</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@500;600&family=Lora:wght@400;500&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Lora', Georgia, serif;
            max-width: 100%;
            margin: 0 auto;
            padding: 20px;
            background: #faf9f5;
            color: #141413;
        }
        h1 { font-family: 'Poppins', sans-serif; color: #141413; }
        .explainer {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #e8e6dc;
            color: #b0aea5;
            font-size: 0.875rem;
            line-height: 1.6;
        }
        .summary {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #e8e6dc;
        }
        .summary p { margin: 5px 0; }
        .best { color: #788c5d; font-weight: bold; }
        .table-container {
            overflow-x: auto;
            width: 100%;
        }
        table {
            border-collapse: collapse;
            background: white;
            border: 1px solid #e8e6dc;
            border-radius: 6px;
            font-size: 12px;
            min-width: 100%;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border: 1px solid #e8e6dc;
            white-space: normal;
            word-wrap: break-word;
        }
        th {
            font-family: 'Poppins', sans-serif;
            background: #141413;
            color: #faf9f5;
            font-weight: 500;
        }
        th.test-col {
            background: #6a9bcc;
        }
        th.query-col { min-width: 200px; }
        td.description {
            font-family: monospace;
            font-size: 11px;
            word-wrap: break-word;
            max-width: 400px;
        }
        td.result {
            text-align: center;
            font-size: 16px;
            min-width: 40px;
        }
        td.test-result {
            background: #f0f6fc;
        }
        .pass { color: #788c5d; }
        .fail { color: #c44; }
        .rate {
            font-size: 9px;
            color: #b0aea5;
            display: block;
        }
        tr:hover { background: #faf9f5; }
        .score {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 11px;
        }
        .score-good { background: #eef2e8; color: #788c5d; }
        .score-ok { background: #fef3c7; color: #d97706; }
        .score-bad { background: #fceaea; color: #c44; }
        .train-label { color: #b0aea5; font-size: 10px; }
        .test-label { color: #6a9bcc; font-size: 10px; font-weight: bold; }
        .best-row { background: #f5f8f2; }
        th.positive-col { border-bottom: 3px solid #788c5d; }
        th.negative-col { border-bottom: 3px solid #c44; }
        th.test-col.positive-col { border-bottom: 3px solid #788c5d; }
        th.test-col.negative-col { border-bottom: 3px solid #c44; }
        .legend { font-family: 'Poppins', sans-serif; display: flex; gap: 20px; margin-bottom: 10px; font-size: 13px; align-items: center; }
        .legend-item { display: flex; align-items: center; gap: 6px; }
        .legend-swatch { width: 16px; height: 16px; border-radius: 3px; display: inline-block; }
        .swatch-positive { background: #141413; border-bottom: 3px solid #788c5d; }
        .swatch-negative { background: #141413; border-bottom: 3px solid #c44; }
        .swatch-test { background: #6a9bcc; }
        .swatch-train { background: #141413; }
    </style>
</head>
<body>
    <h1>""" + title_prefix + """Skill Description Optimization</h1>
    <div class="explainer">
        <strong>Optimizing your skill's description.</strong> Each row is a description attempt evaluated through GitHub Copilot. Green checkmarks mean the skill triggered correctly (or correctly didn't trigger), red crosses mean a valid evaluation got it wrong, and dashes mean the result is unavailable or incomplete. Failed execution is never a successful non-trigger. "Train" shows queries used to improve the description; "Test" shows held-out queries. Review the proposed best description before applying it to your skill.
    </div>
"""]

    # Summary section
    best_test_score = data.get('best_test_score')
    html_parts.append(f"""
    <div class="summary">
        <p><strong>Original:</strong> {html.escape(data.get('original_description') or 'N/A')}</p>
        <p class="best"><strong>Best:</strong> {html.escape(data.get('best_description') or 'unavailable')}</p>
        <p><strong>Best Score:</strong> {data.get('best_score', 'unavailable')} {'(test)' if test_queries or best_test_score is not None else '(train)'}</p>
        <p><strong>Iterations:</strong> {data.get('iterations_run', 0)} | <strong>Train:</strong> {data.get('train_size', '?')} | <strong>Test:</strong> {data.get('test_size', '?')}</p>
    </div>
""")

    # Legend
    html_parts.append("""
    <div class="legend">
        <span style="font-weight:600">Query columns:</span>
        <span class="legend-item"><span class="legend-swatch swatch-positive"></span> Should trigger</span>
        <span class="legend-item"><span class="legend-swatch swatch-negative"></span> Should NOT trigger</span>
        <span class="legend-item"><span class="legend-swatch swatch-train"></span> Train</span>
        <span class="legend-item"><span class="legend-swatch swatch-test"></span> Test</span>
    </div>
""")

    # Table header
    html_parts.append("""
    <div class="table-container">
    <table>
        <thead>
            <tr>
                <th>Iter</th>
                <th>Train</th>
                <th>Test</th>
                <th class="query-col">Description</th>
""")

    # Add column headers for train queries
    for qinfo in train_queries:
        polarity = "positive-col" if qinfo["should_trigger"] else "negative-col"
        html_parts.append(f'                <th class="{polarity}">{html.escape(qinfo["query"])}</th>\n')

    # Add column headers for test queries (different color)
    for qinfo in test_queries:
        polarity = "positive-col" if qinfo["should_trigger"] else "negative-col"
        html_parts.append(f'                <th class="test-col {polarity}">{html.escape(qinfo["query"])}</th>\n')

    html_parts.append("""            </tr>
        </thead>
        <tbody>
""")

    # Find best iteration for highlighting
    eligible = [h for h in history if h.get("status", "completed") == "completed" and not h.get("incomplete")]
    if test_queries:
        best_iter = max(eligible, key=lambda h: h.get("test_passed") or 0, default={}).get("iteration")
    else:
        best_iter = max(eligible, key=lambda h: h.get("train_passed", h.get("passed")) or 0, default={}).get("iteration")

    # Add rows for each iteration
    for h in history:
        iteration = h.get("iteration", "?")
        description = h.get("description") or ""
        train_results = h.get("train_results", h.get("results", [])) or []
        test_results = h.get("test_results", []) or []

        # Create lookups for results by query
        train_by_query = {r["query"]: r for r in train_results}
        test_by_query = {r["query"]: r for r in test_results}

        def aggregate_runs(results: list[dict]) -> tuple[int, int]:
            correct = total = 0
            for r in results:
                if r.get("status", "completed") != "completed" or r.get("pass") is None:
                    continue
                runs, triggers = r.get("runs", 0), r.get("triggers", 0)
                total += runs
                correct += triggers if r.get("should_trigger", True) else runs - triggers
            return correct, total

        train_correct, train_runs = aggregate_runs(train_results)
        test_correct, test_runs = aggregate_runs(test_results)

        def score_class(correct: int, total: int) -> str:
            if not total:
                return ""
            return "score-good" if correct / total >= 0.8 else "score-ok" if correct / total >= 0.5 else "score-bad"

        row_class = "best-row" if best_iter is not None and iteration == best_iter else ""

        html_parts.append(f"""            <tr class="{row_class}">
                <td>{iteration}</td>
                <td><span class="score {score_class(train_correct, train_runs)}">{f'{train_correct}/{train_runs}' if train_runs else 'unavailable'}</span></td>
                <td><span class="score {score_class(test_correct, test_runs)}">{f'{test_correct}/{test_runs}' if test_runs else 'unavailable'}</span></td>
                <td class="description">{html.escape(description)}</td>
""")

        # Add result for each train query
        for qinfo in train_queries:
            r = train_by_query.get(qinfo["query"], {})
            did_pass = r.get("pass") if r.get("status", "completed") == "completed" else None
            icon = "—" if did_pass is None else "✓" if did_pass else "✗"
            css_class = "" if did_pass is None else "pass" if did_pass else "fail"
            rate = f"{r.get('triggers', 0)}/{r.get('runs', 0)}" if did_pass is not None else "unavailable"
            html_parts.append(f'                <td class="result {css_class}">{icon}<span class="rate">{rate}</span></td>\n')

        # Add result for each test query (with different background)
        for qinfo in test_queries:
            r = test_by_query.get(qinfo["query"], {})
            did_pass = r.get("pass") if r.get("status", "completed") == "completed" else None
            icon = "—" if did_pass is None else "✓" if did_pass else "✗"
            css_class = "" if did_pass is None else "pass" if did_pass else "fail"
            rate = f"{r.get('triggers', 0)}/{r.get('runs', 0)}" if did_pass is not None else "unavailable"
            html_parts.append(f'                <td class="result test-result {css_class}">{icon}<span class="rate">{rate}</span></td>\n')

        html_parts.append("            </tr>\n")

    html_parts.append("""        </tbody>
    </table>
    </div>
""")

    html_parts.append("""
</body>
</html>
""")

    return "".join(html_parts)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Generate HTML report from run_loop output")
    parser.add_argument("input", help="Path to JSON output from run_loop.py (or - for stdin)")
    parser.add_argument("-o", "--output", default=None, help="Output HTML file (default: stdout)")
    parser.add_argument("--skill-name", default="", help="Skill name to include in the report title")
    args = parser.parse_args()

    if args.input == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    html_output = generate_html(data, skill_name=args.skill_name)

    if args.output:
        Path(args.output).write_text(html_output, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(html_output)


if __name__ == "__main__":
    main()
