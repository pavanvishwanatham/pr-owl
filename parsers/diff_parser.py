"""
Diff parser — utilities for working with GitHub PR patch strings.

GitHub provides a `patch` field per file in the PR files API.
It looks like a standard unified diff hunk but without file headers.

Example patch:
  @@ -10,6 +10,8 @@
   context line
  -removed line
  +added line
   context line
"""
import re

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def get_added_lines(patch: str) -> list[tuple[int, str]]:
    """
    Return list of (new_line_number, line_content) for all added lines (+).
    Line content does NOT include the leading '+'.
    """
    result = []
    current_line = 0

    for raw_line in patch.splitlines():
        hunk = _HUNK_HEADER.match(raw_line)
        if hunk:
            current_line = int(hunk.group(2)) - 1  # will be incremented below
            continue

        if raw_line.startswith("+"):
            current_line += 1
            result.append((current_line, raw_line[1:]))
        elif raw_line.startswith("-"):
            pass  # removed line — don't advance new-file line counter
        else:
            current_line += 1  # context line

    return result


def get_removed_lines(patch: str) -> list[tuple[int, str]]:
    """
    Return list of (old_line_number, line_content) for all removed lines (-).
    Line content does NOT include the leading '-'.
    """
    result = []
    current_line = 0

    for raw_line in patch.splitlines():
        hunk = _HUNK_HEADER.match(raw_line)
        if hunk:
            current_line = int(hunk.group(1)) - 1
            continue

        if raw_line.startswith("-"):
            current_line += 1
            result.append((current_line, raw_line[1:]))
        elif raw_line.startswith("+"):
            pass
        else:
            current_line += 1

    return result


def get_context_lines(patch: str) -> list[tuple[int, str]]:
    """Return unchanged context lines (neither added nor removed)."""
    result = []
    current_new = 0
    for raw_line in patch.splitlines():
        hunk = _HUNK_HEADER.match(raw_line)
        if hunk:
            current_new = int(hunk.group(2)) - 1
            continue
        if raw_line.startswith(" "):
            current_new += 1
            result.append((current_new, raw_line[1:]))
        elif raw_line.startswith("+"):
            current_new += 1
    return result
