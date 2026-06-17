"""Tests for parsers/diff_parser.py"""
import pytest
from parsers.diff_parser import get_added_lines, get_removed_lines, get_context_lines

SAMPLE_PATCH = """\
@@ -10,6 +10,9 @@
 context line one
-removed line
+added line A
+added line B
 context line two
+added line C
"""


def test_get_added_lines_returns_correct_lines():
    lines = get_added_lines(SAMPLE_PATCH)
    contents = [l for _, l in lines]
    assert "added line A" in contents
    assert "added line B" in contents
    assert "added line C" in contents
    assert "removed line" not in contents
    assert "context line one" not in contents


def test_get_added_lines_correct_line_numbers():
    lines = get_added_lines(SAMPLE_PATCH)
    # new file starts at line 10; context=line10, removed doesn't advance new counter
    # line 10: context, line 11: added A, line 12: added B, line 13: context, line 14: added C
    line_numbers = [n for n, _ in lines]
    assert 11 in line_numbers
    assert 12 in line_numbers
    assert 14 in line_numbers


def test_get_removed_lines():
    lines = get_removed_lines(SAMPLE_PATCH)
    contents = [l for _, l in lines]
    assert "removed line" in contents
    assert "added line A" not in contents


def test_get_context_lines():
    lines = get_context_lines(SAMPLE_PATCH)
    contents = [l for _, l in lines]
    assert "context line one" in contents
    assert "context line two" in contents
    assert "added line A" not in contents


def test_empty_patch_returns_empty():
    assert get_added_lines("") == []
    assert get_removed_lines("") == []


def test_added_only_patch():
    patch = "@@ -0,0 +1,3 @@\n+line one\n+line two\n+line three\n"
    lines = get_added_lines(patch)
    assert len(lines) == 3
    assert lines[0] == (1, "line one")
    assert lines[2] == (3, "line three")


def test_multiple_hunks():
    patch = (
        "@@ -1,3 +1,3 @@\n"
        " ctx\n"
        "-old\n"
        "+new\n"
        "@@ -10,3 +10,4 @@\n"
        " ctx2\n"
        "+extra\n"
        " ctx3\n"
    )
    added = get_added_lines(patch)
    contents = [l for _, l in added]
    assert "new" in contents
    assert "extra" in contents
    assert len(added) == 2
