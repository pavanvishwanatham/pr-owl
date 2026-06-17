"""
Tests for security/semgrep_scanner.py

semgrep may or may not be installed in the test environment.
All tests must pass regardless — if semgrep is absent the scanner must
return an empty list (graceful fallback).
"""
import pytest
from unittest.mock import patch, MagicMock
from security.semgrep_scanner import (
    _reconstruct_content,
    _is_semgrep_available,
    _severity_from_semgrep,
    run_semgrep_on_file,
)


# ── _reconstruct_content ──────────────────────────────────────────────────────

def test_reconstruct_content_includes_added_lines():
    patch = "@@ -1,2 +1,3 @@\n context\n+added_line\n context2\n"
    content = _reconstruct_content(patch)
    assert "added_line" in content
    assert "context" in content


def test_reconstruct_content_excludes_removed_lines():
    patch = "@@ -1,2 +1,1 @@\n-removed_line\n context\n"
    content = _reconstruct_content(patch)
    assert "removed_line" not in content


def test_reconstruct_content_skips_hunk_headers():
    patch = "@@ -0,0 +1,2 @@\n+line_one\n+line_two\n"
    content = _reconstruct_content(patch)
    assert "@@" not in content
    assert "line_one" in content
    assert "line_two" in content


def test_reconstruct_empty_patch():
    assert _reconstruct_content("") == ""


def test_reconstruct_multiline_patch():
    patch = (
        "@@ -1,3 +1,4 @@\n"
        " def foo():\n"
        "-    old_impl()\n"
        "+    new_impl()\n"
        "+    extra_line()\n"
        " \n"
    )
    content = _reconstruct_content(patch)
    assert "new_impl" in content
    assert "extra_line" in content
    assert "old_impl" not in content


# ── _severity_from_semgrep ────────────────────────────────────────────────────

def test_severity_error_maps_to_critical():
    assert _severity_from_semgrep({"severity": "ERROR"}) == "CRITICAL"


def test_severity_warning_maps_to_high():
    assert _severity_from_semgrep({"severity": "WARNING"}) == "HIGH"


def test_severity_info_maps_to_medium():
    assert _severity_from_semgrep({"severity": "INFO"}) == "MEDIUM"


def test_severity_unknown_defaults_to_medium():
    assert _severity_from_semgrep({"severity": "UNKNOWN"}) == "MEDIUM"


def test_severity_missing_defaults_to_medium():
    assert _severity_from_semgrep({}) == "MEDIUM"


# ── run_semgrep_on_file — fallback when semgrep unavailable ──────────────────

def test_returns_empty_when_semgrep_not_installed():
    with patch("security.semgrep_scanner._is_semgrep_available", return_value=False):
        result = run_semgrep_on_file("src/test.py", "@@ -0,0 +1 @@\n+API_KEY='secret'\n")
    assert result == []


def test_returns_empty_for_unsupported_extension():
    with patch("security.semgrep_scanner._is_semgrep_available", return_value=True):
        result = run_semgrep_on_file("data.parquet", "@@ -0,0 +1 @@\n+binary\n")
    assert result == []


def test_returns_empty_for_empty_patch():
    with patch("security.semgrep_scanner._is_semgrep_available", return_value=True):
        result = run_semgrep_on_file("src/test.py", "")
    assert result == []


# ── run_semgrep_on_file — mocked subprocess ───────────────────────────────────

_MOCK_SEMGREP_OUTPUT = """{
  "results": [
    {
      "check_id": "python.lang.security.audit.hardcoded-password",
      "path": "/tmp/pr_review_test.py",
      "start": {"line": 3, "col": 1},
      "extra": {
        "severity": "ERROR",
        "message": "Hardcoded password detected",
        "fix": "Use os.environ.get('PASSWORD') instead"
      }
    }
  ]
}"""


def test_semgrep_findings_parsed_correctly():
    """When semgrep runs and returns findings, they are correctly parsed."""
    import subprocess
    mock_result = MagicMock()
    mock_result.returncode = 1   # 1 = findings found
    mock_result.stdout = _MOCK_SEMGREP_OUTPUT
    mock_result.stderr = ""

    with patch("security.semgrep_scanner._is_semgrep_available", return_value=True), \
         patch("subprocess.run", return_value=mock_result):
        results = run_semgrep_on_file(
            "src/config.py",
            "@@ -0,0 +1,3 @@\n+def foo():\n+    pass\n+    password='secret'\n"
        )

    assert len(results) >= 1
    finding = results[0]
    assert finding["line"] == 3
    assert finding["severity"] == "CRITICAL"   # ERROR → CRITICAL
    assert "Hardcoded password" in finding["message"]
    assert "os.environ" in finding["fix"]
    assert "rule_id" in finding


def test_semgrep_deduplicates_findings():
    """Same (line, rule_id) pair from multiple configs must appear only once."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = _MOCK_SEMGREP_OUTPUT
    mock_result.stderr = ""

    with patch("security.semgrep_scanner._is_semgrep_available", return_value=True), \
         patch("subprocess.run", return_value=mock_result):
        results = run_semgrep_on_file(
            "src/config.py",
            "@@ -0,0 +1 @@\n+password='secret'\n"
        )

    # Even though we run 2 configs, the same finding should appear once
    rule_ids = [(r["line"], r["rule_id"]) for r in results]
    assert len(rule_ids) == len(set(rule_ids))


def test_semgrep_timeout_returns_empty():
    """Timeout must not crash — return empty list."""
    import subprocess
    with patch("security.semgrep_scanner._is_semgrep_available", return_value=True), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired("semgrep", 60)):
        results = run_semgrep_on_file("src/config.py", "@@ -0,0 +1 @@\n+line\n")
    assert results == []


def test_semgrep_bad_json_returns_empty():
    """Malformed JSON from semgrep must not crash — return empty list."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "NOT VALID JSON {{{"
    mock_result.stderr = ""

    with patch("security.semgrep_scanner._is_semgrep_available", return_value=True), \
         patch("subprocess.run", return_value=mock_result):
        results = run_semgrep_on_file("src/config.py", "@@ -0,0 +1 @@\n+line\n")
    assert results == []
