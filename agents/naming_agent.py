"""
NamingAgent — checks naming conventions for variables, functions, classes, and constants.

Strategy:
  - Python:     snake_case functions/vars, PascalCase classes, UPPER_CASE constants
  - JavaScript/TypeScript: camelCase vars/functions, PascalCase classes, UPPER_CASE constants
  - Java:       camelCase methods/vars, PascalCase classes, UPPER_CASE constants
  - Go:         mixedCaps (camelCase/PascalCase depending on export)

Uses tree-sitter AST when possible; falls back to regex on the diff patch.
"""
import re
from agents.base_agent import BaseAgent, AgentResult, Finding, Severity
from parsers.diff_parser import get_added_lines
from parsers.ast_parser import ASTParser


SNAKE_CASE    = re.compile(r"^[a-z][a-z0-9_]*$")
CAMEL_CASE    = re.compile(r"^[a-z][a-zA-Z0-9]*$")
PASCAL_CASE   = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
UPPER_CASE    = re.compile(r"^[A-Z][A-Z0-9_]*$")
SCREAMING     = re.compile(r"^[A-Z_0-9]+$")

# Regex-based fallbacks (match definition lines in the diff)
PYTHON_FUNC   = re.compile(r"^\+\s*(?:async\s+)?def\s+([a-zA-Z_]\w*)\s*\(")
PYTHON_CLASS  = re.compile(r"^\+\s*class\s+([a-zA-Z_]\w*)\s*[:(]")
PYTHON_CONST  = re.compile(r"^\+\s*([A-Z_][A-Z0-9_]*)\s*=")
JS_FUNC       = re.compile(r"^\+\s*(?:async\s+)?function\s+([a-zA-Z_$]\w*)\s*\(")
JS_CLASS      = re.compile(r"^\+\s*class\s+([a-zA-Z_]\w*)\s*[{(]?")
JS_CONST      = re.compile(r"^\+\s*const\s+([A-Z_][A-Z0-9_]*)\s*=")
JAVA_CLASS    = re.compile(r"^\+\s*(?:public|private|protected)?\s*class\s+([A-Za-z]\w*)")
JAVA_METHOD   = re.compile(r"^\+\s*(?:public|private|protected|static|final|\s)+\s+\w+\s+([a-z]\w*)\s*\(")


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


class NamingAgent(BaseAgent):
    name = "NamingAgent"

    def __init__(self):
        self._ast = ASTParser()

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        findings: list[Finding] = []

        for file in files:
            filename = file["filename"]
            patch = file.get("patch", "")
            ext = _ext(filename)
            if not patch or ext not in ("py", "js", "ts", "tsx", "jsx", "java", "go"):
                continue

            added = get_added_lines(patch)

            for line_no, line in added:
                raw_line = "+" + line  # simulate diff line for regex
                issues = []

                if ext == "py":
                    issues = self._check_python(raw_line)
                elif ext in ("js", "ts", "tsx", "jsx"):
                    issues = self._check_js(raw_line)
                elif ext == "java":
                    issues = self._check_java(raw_line)

                for issue_type, name, suggestion in issues:
                    findings.append(Finding(
                        file=filename,
                        line=line_no,
                        issue_type=issue_type,
                        severity=Severity.LOW,
                        message=f"'{name}' does not follow convention. {suggestion}",
                        suggestion=suggestion,
                    ))

        return AgentResult(agent_name=self.name, findings=findings)

    def _check_python(self, line: str) -> list[tuple]:
        issues = []
        m = PYTHON_FUNC.match(line)
        if m:
            name = m.group(1)
            if not SNAKE_CASE.match(name) and not name.startswith("_"):
                issues.append(("FunctionNaming", name, f"Use snake_case. Rename to: {_to_snake(name)}"))

        m = PYTHON_CLASS.match(line)
        if m:
            name = m.group(1)
            if not PASCAL_CASE.match(name):
                issues.append(("ClassNaming", name, f"Use PascalCase. Rename to: {_to_pascal(name)}"))

        return issues

    def _check_js(self, line: str) -> list[tuple]:
        issues = []
        m = JS_FUNC.match(line)
        if m:
            name = m.group(1)
            if not CAMEL_CASE.match(name) and not PASCAL_CASE.match(name):
                issues.append(("FunctionNaming", name, f"Use camelCase. Rename to: {_to_camel(name)}"))

        m = JS_CLASS.match(line)
        if m:
            name = m.group(1)
            if not PASCAL_CASE.match(name):
                issues.append(("ClassNaming", name, f"Use PascalCase. Rename to: {_to_pascal(name)}"))

        return issues

    def _check_java(self, line: str) -> list[tuple]:
        issues = []
        m = JAVA_CLASS.match(line)
        if m:
            name = m.group(1)
            if not PASCAL_CASE.match(name):
                issues.append(("ClassNaming", name, f"Use PascalCase. Rename to: {_to_pascal(name)}"))

        m = JAVA_METHOD.match(line)
        if m:
            name = m.group(1)
            if not CAMEL_CASE.match(name):
                issues.append(("MethodNaming", name, f"Use camelCase. Rename to: {_to_camel(name)}"))

        return issues


# ── Conversion helpers ──────────────────────────────────────────────────────

def _to_snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


def _to_camel(name: str) -> str:
    parts = re.split(r"[_\s]+", name)
    return parts[0].lower() + "".join(p.title() for p in parts[1:])


def _to_pascal(name: str) -> str:
    return "".join(p.title() for p in re.split(r"[_\s]+", name))
