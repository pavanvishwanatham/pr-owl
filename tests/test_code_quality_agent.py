"""Tests for agents/code_quality_agent.py"""
import asyncio
import pytest
from agents.code_quality_agent import CodeQualityAgent
from agents.base_agent import Severity


@pytest.fixture
def agent():
    return CodeQualityAgent()


def run(coro):
    return asyncio.run(coro)


# ── console.log / print detection ────────────────────────────────────────────

def test_detects_console_log(agent, sample_pr_data):
    files = [{
        "filename": "src/app.js", "status": "modified",
        "additions": 1, "deletions": 0,
        "patch": "@@ -1,1 +1,2 @@\n context\n+  console.log('debug', result)\n",
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "DebugStatement"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.MEDIUM


def test_detects_print_statement(agent, sample_pr_data):
    files = [{
        "filename": "src/utils.py", "status": "modified",
        "additions": 1, "deletions": 0,
        "patch": "@@ -1,1 +1,2 @@\n def foo():\n+    print('hello world')\n",
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "DebugStatement"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.LOW


def test_detects_system_out_println(agent, sample_pr_data):
    files = [{
        "filename": "Foo.java", "status": "modified",
        "additions": 1, "deletions": 0,
        "patch": "@@ -1,1 +1,2 @@\n // comment\n+    System.out.println(\"debug\");\n",
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "DebugStatement"]
    assert len(issues) >= 1


# ── TODO / FIXME detection ────────────────────────────────────────────────────

def test_detects_todo_comment_python(agent, sample_pr_data):
    files = [{
        "filename": "src/payment.py", "status": "modified",
        "additions": 1, "deletions": 0,
        "patch": "@@ -1,1 +1,2 @@\n def pay():\n+    # TODO: handle refunds\n",
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "TodoComment"]
    assert len(issues) == 1


def test_detects_fixme_comment_js(agent, sample_pr_data):
    files = [{
        "filename": "app.js", "status": "modified",
        "additions": 1, "deletions": 0,
        "patch": "@@ -1,1 +1,2 @@\n // code\n+// FIXME: this crashes on null\n",
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "TodoComment"]
    assert len(issues) == 1


# ── Nested loop detection ─────────────────────────────────────────────────────

def test_detects_triple_nested_loop(agent, sample_pr_data):
    patch = (
        "@@ -1,1 +1,10 @@\n"
        "+def process():\n"
        "+    for i in range(10):\n"
        "+        for j in range(10):\n"
        "+            for k in range(10):\n"
        "+                pass\n"
    )
    files = [{
        "filename": "src/heavy.py", "status": "added",
        "additions": 5, "deletions": 0, "patch": patch,
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "NestedLoop"]
    assert len(issues) >= 1


# ── Clean file — no false positives ──────────────────────────────────────────

def test_clean_file_no_findings(agent, sample_pr_data, clean_files):
    result = run(agent.analyze(sample_pr_data, "", clean_files))
    assert result.findings == []


def test_no_patch_file_skipped(agent, sample_pr_data):
    files = [{"filename": "README.md", "status": "modified",
              "additions": 1, "deletions": 0, "patch": ""}]
    result = run(agent.analyze(sample_pr_data, "", files))
    assert result.findings == []


# ── Unused imports ────────────────────────────────────────────────────────────

def test_detects_unused_python_import(agent, sample_pr_data):
    files = [{
        "filename": "src/service.py", "status": "modified",
        "additions": 3, "deletions": 0,
        "patch": (
            "@@ -1,1 +1,4 @@\n"
            " def foo():\n"
            "+import os\n"
            "+import json\n"
            "+    result = json.loads('{}')\n"   # json IS used, os is NOT
        ),
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    unused = [f for f in result.findings if f.issue_type == "UnusedImport"]
    assert len(unused) == 1
    assert "os" in unused[0].message


def test_detects_unused_js_import(agent, sample_pr_data):
    files = [{
        "filename": "src/app.js", "status": "modified",
        "additions": 3, "deletions": 0,
        "patch": (
            "@@ -1,1 +1,4 @@\n"
            " // module\n"
            "+import { useState, useEffect } from 'react'\n"
            "+function App() {\n"
            "+  const [x] = useState(0)\n"   # useState used, useEffect NOT used
        ),
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    unused = [f for f in result.findings if f.issue_type == "UnusedImport"]
    assert len(unused) == 1
    assert "useEffect" in unused[0].message


def test_used_python_import_not_flagged(agent, sample_pr_data):
    files = [{
        "filename": "src/utils.py", "status": "modified",
        "additions": 2, "deletions": 0,
        "patch": (
            "@@ -1,1 +1,3 @@\n"
            " # utils\n"
            "+import os\n"
            "+path = os.path.join('a', 'b')\n"
        ),
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    unused = [f for f in result.findings if f.issue_type == "UnusedImport"]
    assert unused == []


def test_star_import_not_flagged(agent, sample_pr_data):
    """Star imports can't be checked — should not raise false positives."""
    files = [{
        "filename": "src/models.py", "status": "modified",
        "additions": 1, "deletions": 0,
        "patch": "@@ -1,1 +1,2 @@\n # models\n+from sqlalchemy import *\n",
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    unused = [f for f in result.findings if f.issue_type == "UnusedImport"]
    assert unused == []


def test_from_import_with_alias_used(agent, sample_pr_data):
    files = [{
        "filename": "src/api.py", "status": "modified",
        "additions": 2, "deletions": 0,
        "patch": (
            "@@ -1,1 +1,3 @@\n"
            " # api\n"
            "+from datetime import datetime as dt\n"
            "+now = dt.now()\n"
        ),
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    unused = [f for f in result.findings if f.issue_type == "UnusedImport"]
    assert unused == []


# ── Duplicate code ────────────────────────────────────────────────────────────

def _dup_block():
    """A 6-line block of non-trivial code that will hash-match."""
    return [
        "    if value is None:",
        "        raise ValueError('value cannot be None')",
        "    processed = str(value).strip().lower()",
        "    if len(processed) == 0:",
        "        raise ValueError('value cannot be empty')",
        "    return processed",
    ]


def _make_dup_file(filename, extra_lines=None):
    block = _dup_block()
    all_lines = block + (extra_lines or [])
    patch = f"@@ -0,0 +1,{len(all_lines)} @@\n"
    patch += "\n".join("+" + l for l in all_lines) + "\n"
    return {
        "filename": filename, "status": "added",
        "additions": len(all_lines), "deletions": 0, "patch": patch,
    }


def test_detects_duplicate_code_across_files(agent, sample_pr_data):
    files = [
        _make_dup_file("src/payment/validator.py", ["extra = 'payment'"]),
        _make_dup_file("src/order/validator.py",   ["extra = 'order'"]),
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    dups = [f for f in result.findings if f.issue_type == "DuplicateCode"]
    assert len(dups) >= 1
    # Both files should be mentioned
    all_messages = " ".join(f.message for f in dups)
    assert "validator.py" in all_messages


def test_no_duplicate_within_single_file(agent, sample_pr_data):
    """Duplicate within the same file (sliding window) should NOT be reported."""
    block = _dup_block()
    all_lines = block + ["    pass"] + block  # same block twice in one file
    patch = f"@@ -0,0 +1,{len(all_lines)} @@\n"
    patch += "\n".join("+" + l for l in all_lines) + "\n"
    files = [{
        "filename": "src/single.py", "status": "added",
        "additions": len(all_lines), "deletions": 0, "patch": patch,
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    dups = [f for f in result.findings if f.issue_type == "DuplicateCode"]
    assert dups == []


def test_short_blocks_not_flagged_as_duplicate(agent, sample_pr_data):
    """Blocks that are too short (< _DUP_MIN_CHARS) should not be flagged."""
    tiny = ["pass", "return", "x = 1", "y = 2", "z = 3", "w = 4"]
    files = [
        {"filename": "a.py", "status": "added", "additions": 6, "deletions": 0,
         "patch": "@@ -0,0 +1,6 @@\n" + "\n".join("+" + l for l in tiny)},
        {"filename": "b.py", "status": "added", "additions": 6, "deletions": 0,
         "patch": "@@ -0,0 +1,6 @@\n" + "\n".join("+" + l for l in tiny)},
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    dups = [f for f in result.findings if f.issue_type == "DuplicateCode"]
    assert dups == []


def test_unique_code_blocks_not_flagged(agent, sample_pr_data):
    files = [
        _make_dup_file("src/a.py", ["unique_a = True", "something_else_a()"]),
        {
            "filename": "src/b.py", "status": "added",
            "additions": 6, "deletions": 0,
            "patch": (
                "@@ -0,0 +1,6 @@\n"
                "+def completely_different():\n"
                "+    x = fetch_data()\n"
                "+    y = process(x)\n"
                "+    z = transform(y)\n"
                "+    result = finalise(z)\n"
                "+    return result\n"
            ),
        },
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    dups = [f for f in result.findings if f.issue_type == "DuplicateCode"]
    assert dups == []
