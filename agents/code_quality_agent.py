"""
CodeQualityAgent — static rule-based checks on added lines.

Detects:
  - console.log / print / System.out.println  (debug statements)
  - TODO / FIXME / HACK / XXX                 (todo comments)
  - Large functions (>50 added lines)
  - Commented-out code blocks
  - Nested loops (depth > 2)
  - Unused imports                             (NEW — per language, regex-based)
  - Duplicate code blocks                      (NEW — rolling MD5 hash across files)
"""
import hashlib
import re
from agents.base_agent import BaseAgent, AgentResult, Finding, Severity
from parsers.diff_parser import get_added_lines


# ── Per-language import extraction ───────────────────────────────────────────

# Python:  import os  /  import os as operating_system  /  from os import path, getcwd
_PY_IMPORT      = re.compile(r"^import\s+([\w.]+)(?:\s+as\s+(\w+))?$")
_PY_FROM_IMPORT = re.compile(r"^from\s+[\w.]+\s+import\s+(.+)$")

# JS/TS:  import { a, b } from 'x'  /  import x from 'x'  /  const x = require('x')
_JS_IMPORT      = re.compile(r"^import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+['\"]")
_JS_REQUIRE     = re.compile(r"(?:const|let|var)\s+(?:\{([^}]+)\}|(\w+))\s*=\s*require\s*\(")

# Java:  import com.example.Foo;
_JAVA_IMPORT    = re.compile(r"^import\s+[\w.]+\.(\w+)\s*;$")

# Go:    import "fmt"  /  import f "fmt"  (inside import block detected by simple heuristic)
_GO_IMPORT      = re.compile(r'^\s*(?:(\w+)\s+)?"[\w/.]+"')

# Duplicate code settings
_DUP_BLOCK_SIZE = 6          # consecutive added lines to form a block
_DUP_MIN_CHARS  = 80         # minimum total characters to avoid flagging tiny blocks


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _extract_imported_names(line: str, ext: str) -> list[str]:
    """Return the local binding names introduced by an import statement."""
    names: list[str] = []
    stripped = line.strip()

    if ext == "py":
        m = _PY_IMPORT.match(stripped)
        if m:
            # "import os.path as p" → local name is "p" (or "path")
            names.append(m.group(2) or m.group(1).split(".")[-1])
            return names
        m = _PY_FROM_IMPORT.match(stripped)
        if m:
            raw = m.group(1).strip()
            if raw == "*":
                return []   # star-import — can't check
            for part in raw.split(","):
                part = part.strip()
                alias = part.split(" as ")
                names.append(alias[-1].strip())
            return names

    elif ext in ("js", "ts", "jsx", "tsx"):
        m = _JS_IMPORT.match(stripped)
        if m:
            if m.group(1):   # named imports: { a, b as c }
                for part in m.group(1).split(","):
                    alias = part.strip().split(" as ")
                    names.append(alias[-1].strip())
            elif m.group(2):
                names.append(m.group(2))
            return names
        m = _JS_REQUIRE.match(stripped)
        if m:
            if m.group(1):
                for part in m.group(1).split(","):
                    alias = part.strip().split(":")
                    names.append(alias[0].strip())
            elif m.group(2):
                names.append(m.group(2))
            return names

    elif ext == "java":
        m = _JAVA_IMPORT.match(stripped)
        if m:
            names.append(m.group(1))
            return names

    return names


def _is_import_line(line: str, ext: str) -> bool:
    stripped = line.strip()
    if ext == "py":
        return stripped.startswith("import ") or stripped.startswith("from ")
    if ext in ("js", "ts", "jsx", "tsx"):
        return stripped.startswith("import ") or bool(_JS_REQUIRE.match(stripped))
    if ext == "java":
        return stripped.startswith("import ")
    return False


class CodeQualityAgent(BaseAgent):
    name = "CodeQualityAgent"

    # (pattern, issue_type, severity, message)
    _LINE_RULES: list[tuple] = [
        (
            re.compile(r"\bconsole\.(log|warn|error|debug)\b"),
            "DebugStatement", Severity.MEDIUM,
            "console.log left in code — remove before merging",
        ),
        (
            re.compile(r"\bprint\s*\("),
            "DebugStatement", Severity.LOW,
            "print() statement — use a logger instead",
        ),
        (
            re.compile(r"System\.out\.(print|println)\b"),
            "DebugStatement", Severity.MEDIUM,
            "System.out.println — use a logger instead",
        ),
        (
            re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE),
            "TodoComment", Severity.LOW,
            "TODO/FIXME comment — track in JIRA instead of leaving in code",
        ),
        (
            re.compile(r"//\s*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE),
            "TodoComment", Severity.LOW,
            "TODO/FIXME comment — track in JIRA instead of leaving in code",
        ),
        (
            re.compile(r"^\s*//\s+[a-zA-Z].*[;{}]\s*$"),
            "CommentedCode", Severity.LOW,
            "Commented-out code detected — remove dead code",
        ),
        (
            re.compile(r"^\s*#\s+[a-zA-Z].*[=:(]\s*$"),
            "CommentedCode", Severity.LOW,
            "Commented-out code detected — remove dead code",
        ),
    ]

    # ── Public entry point ────────────────────────────────────────────────────

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        findings: list[Finding] = []

        for file in files:
            filename = file["filename"]
            patch = file.get("patch", "")
            if not patch:
                continue

            added = get_added_lines(patch)

            # Per-line rule checks
            for line_no, line in added:
                for pattern, issue_type, severity, message in self._LINE_RULES:
                    if pattern.search(line):
                        findings.append(Finding(
                            file=filename,
                            line=line_no,
                            issue_type=issue_type,
                            severity=severity,
                            message=message,
                        ))
                        break  # one finding per line

            findings.extend(self._check_nested_loops(filename, added))
            findings.extend(self._check_large_functions(filename, added))
            findings.extend(self._check_unused_imports(filename, added))

        # Duplicate code runs across all files together
        findings.extend(self._check_duplicate_code(files))

        return AgentResult(agent_name=self.name, findings=findings)

    # ── Nested loops ──────────────────────────────────────────────────────────

    def _check_nested_loops(self, filename: str, added: list) -> list[Finding]:
        findings = []
        loop_kw  = re.compile(r"\b(for|while)\b")
        indent_re = re.compile(r"^(\s*)")
        depth = 0
        prev_indent = 0

        for line_no, line in added:
            indent = len(indent_re.match(line).group(1))
            if indent > prev_indent and loop_kw.search(line):
                depth += 1
            elif indent < prev_indent:
                depth = max(0, depth - 1)
            prev_indent = indent

            if depth >= 3:
                findings.append(Finding(
                    file=filename, line=line_no,
                    issue_type="NestedLoop", severity=Severity.MEDIUM,
                    message="Triple-nested loop — extract inner logic into a helper function",
                ))
                depth = 0

        return findings

    # ── Large functions ───────────────────────────────────────────────────────

    def _check_large_functions(self, filename: str, added: list) -> list[Finding]:
        findings = []
        func_re = re.compile(
            r"\b(def |public |private |protected |async def |function |fun )\w+"
        )
        func_start = None
        func_count = 0

        for line_no, line in added:
            if func_re.search(line):
                if func_start and func_count > 50:
                    findings.append(Finding(
                        file=filename, line=func_start,
                        issue_type="LargeFunction", severity=Severity.MEDIUM,
                        message=f"Function spans ~{func_count} added lines — consider breaking it up",
                    ))
                func_start = line_no
                func_count = 0
            elif func_start:
                func_count += 1

        # Check final function
        if func_start and func_count > 50:
            findings.append(Finding(
                file=filename, line=func_start,
                issue_type="LargeFunction", severity=Severity.MEDIUM,
                message=f"Function spans ~{func_count} added lines — consider breaking it up",
            ))

        return findings

    # ── Unused imports ────────────────────────────────────────────────────────

    def _check_unused_imports(self, filename: str, added: list) -> list[Finding]:
        """
        Flag imports that are added in this PR but whose local name never appears
        in any other added line of the same file.

        Scope: only checks NEWLY ADDED imports against NEWLY ADDED code.
        This avoids false positives for imports used in pre-existing lines.
        """
        ext = _ext(filename)
        if ext not in ("py", "js", "ts", "jsx", "tsx", "java"):
            return []

        import_lines: list[tuple[int, list[str]]] = []  # (line_no, [local_names])
        other_code_lines: list[str] = []

        for line_no, line in added:
            if _is_import_line(line, ext):
                names = _extract_imported_names(line, ext)
                if names:
                    import_lines.append((line_no, names))
            else:
                other_code_lines.append(line)

        if not import_lines or not other_code_lines:
            return []

        other_code = "\n".join(other_code_lines)
        findings = []

        for line_no, names in import_lines:
            unused = [n for n in names if n and re.search(r"\b" + re.escape(n) + r"\b", other_code) is None]
            if unused:
                names_str = ", ".join(f"'{n}'" for n in unused)
                findings.append(Finding(
                    file=filename,
                    line=line_no,
                    issue_type="UnusedImport",
                    severity=Severity.LOW,
                    message=f"Newly imported {names_str} not used in this PR's added lines",
                    suggestion=(
                        f"Remove the import if {names_str} is not needed, "
                        "or ensure it is used in the new code."
                    ),
                ))

        return findings

    # ── Duplicate code ────────────────────────────────────────────────────────

    def _check_duplicate_code(self, files: list[dict]) -> list[Finding]:
        """
        Detect blocks of identical code added in multiple files within the same PR.

        Strategy:
          - Extract _DUP_BLOCK_SIZE consecutive added, non-empty, non-comment lines per file
          - Normalise each line (strip whitespace) and hash the block with MD5
          - Report any hash that appears in 2+ different files
        """
        # hash → list of (filename, start_line_no)
        block_index: dict[str, list[tuple[str, int]]] = {}

        for file in files:
            filename = file["filename"]
            patch = file.get("patch", "")
            if not patch:
                continue

            added = get_added_lines(patch)

            # Filter to non-trivial, non-comment lines
            meaningful = [
                (ln, line.strip())
                for ln, line in added
                if line.strip()
                and not line.strip().startswith(("#", "//", "*", "/*", "*/", '"""', "'''"))
            ]

            if len(meaningful) < _DUP_BLOCK_SIZE:
                continue

            for i in range(len(meaningful) - _DUP_BLOCK_SIZE + 1):
                block = meaningful[i: i + _DUP_BLOCK_SIZE]
                block_text = "\n".join(line for _, line in block)

                # Skip trivially short blocks
                if len(block_text) < _DUP_MIN_CHARS:
                    continue

                block_hash = hashlib.md5(block_text.encode()).hexdigest()
                start_line = block[0][0]

                if block_hash not in block_index:
                    block_index[block_hash] = []
                block_index[block_hash].append((filename, start_line))

        # Report duplicates — only flag each (file, line) once
        findings: list[Finding] = []
        reported: set[tuple[str, int]] = set()

        for block_hash, locations in block_index.items():
            if len(locations) < 2:
                continue

            # Deduplicate locations by filename first (same file, sliding window)
            by_file: dict[str, int] = {}
            for fname, lineno in locations:
                if fname not in by_file:
                    by_file[fname] = lineno  # keep first occurrence per file

            if len(by_file) < 2:
                continue  # duplicate only within same file — skip

            for fname, lineno in by_file.items():
                key = (fname, lineno)
                if key in reported:
                    continue
                reported.add(key)

                other_files = [f for f in by_file if f != fname]
                findings.append(Finding(
                    file=fname,
                    line=lineno,
                    issue_type="DuplicateCode",
                    severity=Severity.MEDIUM,
                    message=(
                        f"Duplicate code block ({_DUP_BLOCK_SIZE}+ lines) also found in: "
                        + ", ".join(f"`{f}`" for f in other_files[:3])
                    ),
                    suggestion=(
                        "Extract the duplicated logic into a shared function, "
                        "utility module, or base class."
                    ),
                ))

        return findings
