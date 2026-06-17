"""
DocsAgent — warns when new public APIs, exported functions, or config changes
are introduced without updating README, docs/, or Swagger/OpenAPI specs.
"""
import re
from agents.base_agent import BaseAgent, AgentResult, Finding, Severity
from parsers.diff_parser import get_added_lines


# Patterns that suggest a new public API / export was added
_NEW_API_PATTERNS = [
    re.compile(r"^\+\s*@(app|router)\.(get|post|put|delete|patch)\s*\("),  # FastAPI/Flask routes
    re.compile(r"^\+\s*public\s+(static\s+)?\w+\s+\w+\s*\("),              # Java public methods
    re.compile(r"^\+\s*export\s+(function|const|class|default)\s+"),        # JS/TS exports
    re.compile(r"^\+\s*def\s+[a-z]\w+\s*\(.*\)\s*->"),                     # Python typed public functions
]

# Patterns suggesting config schema changes
_CONFIG_PATTERNS = [
    re.compile(r"application\.(yml|yaml|properties)$"),
    re.compile(r"config\.(py|js|ts|json|yaml|yml)$"),
    re.compile(r"settings\.(py|js|ts)$"),
]

# What we consider "docs updated"
_DOC_FILES = {"readme", "changelog", "swagger", "openapi", "docs/", "api-docs"}


def _has_doc_update(files: list[dict]) -> bool:
    for f in files:
        name = f["filename"].lower()
        if any(d in name for d in _DOC_FILES):
            return True
    return False


class DocsAgent(BaseAgent):
    name = "DocsAgent"

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        findings: list[Finding] = []
        has_docs = _has_doc_update(files)

        new_apis = []
        config_changes = []

        for file in files:
            filename = file["filename"]
            patch = file.get("patch", "")
            if not patch:
                continue

            added = get_added_lines(patch)

            for line_no, line in added:
                raw = "+" + line
                for pattern in _NEW_API_PATTERNS:
                    if pattern.match(raw):
                        new_apis.append((filename, line_no, line.strip()))
                        break

            # Config file changes
            for pattern in _CONFIG_PATTERNS:
                if pattern.search(filename):
                    config_changes.append(filename)
                    break

        if new_apis and not has_docs:
            for filename, line_no, line in new_apis[:5]:  # cap findings
                findings.append(Finding(
                    file=filename,
                    line=line_no,
                    issue_type="MissingDocUpdate",
                    severity=Severity.MEDIUM,
                    message=f"New public API/export added but no README/docs/Swagger update found",
                    suggestion="Update README.md, docs/, or the OpenAPI/Swagger spec to document this endpoint or export.",
                ))

        if config_changes and not has_docs:
            for cfg in config_changes[:3]:
                findings.append(Finding(
                    file=cfg,
                    line=1,
                    issue_type="ConfigChangedNoDoc",
                    severity=Severity.LOW,
                    message="Config file changed — ensure documentation reflects the new config options",
                    suggestion="Update README or docs/ to document any new or changed configuration keys.",
                ))

        return AgentResult(agent_name=self.name, findings=findings)
