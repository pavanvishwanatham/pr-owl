"""
SecurityAgent — detects secrets, API keys, tokens, and other sensitive data.

Two-layer scanning:
  Layer 1 — SecretScanner (regex + Shannon entropy):  fast, always runs
  Layer 2 — SemgrepScanner (subprocess):              deep, runs when semgrep is installed

Both layers run per changed file. Results are deduplicated by (line, type).
"""
from agents.base_agent import BaseAgent, AgentResult, Finding, Severity
from parsers.diff_parser import get_added_lines
from security.secret_scanner import SecretScanner
from security.semgrep_scanner import run_semgrep_on_file

import structlog
log = structlog.get_logger()

_SKIP_EXTENSIONS = (".lock", ".min.js", ".min.css", ".map", ".svg", ".png", ".jpg")


class SecurityAgent(BaseAgent):
    name = "SecurityAgent"

    def __init__(self):
        self._scanner = SecretScanner()

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        findings: list[Finding] = []
        # Track (file, line, type) to avoid duplicate findings from both layers
        seen: set[tuple] = set()

        for file in files:
            filename = file["filename"]
            patch = file.get("patch", "")
            if not patch:
                continue

            if any(filename.endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue

            added = get_added_lines(patch)

            # ── Layer 1: regex + entropy (SecretScanner) ──────────────────
            for line_no, line in added:
                hits = self._scanner.scan_line(line)
                for hit in hits:
                    key = (filename, line_no, hit["type"])
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(Finding(
                        file=filename,
                        line=line_no,
                        issue_type=hit["type"],
                        severity=Severity.CRITICAL if hit["high_confidence"] else Severity.HIGH,
                        message=hit["message"],
                        suggestion=(
                            "Remove from code immediately. Rotate the credential. "
                            "Use environment variables or a secrets manager (e.g. Vault, AWS Secrets Manager)."
                        ),
                    ))

            # ── Layer 2: semgrep subprocess ───────────────────────────────
            semgrep_hits = run_semgrep_on_file(filename, patch)
            for hit in semgrep_hits:
                line_no = hit["line"]
                key = (filename, line_no, hit["rule_id"])
                if key in seen:
                    continue
                seen.add(key)

                sev_map = {
                    "CRITICAL": Severity.CRITICAL,
                    "HIGH":     Severity.HIGH,
                    "MEDIUM":   Severity.MEDIUM,
                    "LOW":      Severity.LOW,
                }
                sev = sev_map.get(hit["severity"], Severity.HIGH)
                suggestion = hit["fix"] or "Review and remove the flagged value."

                findings.append(Finding(
                    file=filename,
                    line=line_no,
                    issue_type=f"semgrep:{hit['rule_id'].split('.')[-1]}",
                    severity=sev,
                    message=f"[semgrep] {hit['message']}",
                    suggestion=suggestion,
                ))

            # ── .env file committed ───────────────────────────────────────
            if filename.endswith(".env") and file.get("status") == "added":
                key = (filename, 1, ".envExposure")
                if key not in seen:
                    seen.add(key)
                    findings.append(Finding(
                        file=filename,
                        line=1,
                        issue_type=".envExposure",
                        severity=Severity.CRITICAL,
                        message=".env file committed to the repository",
                        suggestion="Add .env to .gitignore immediately. Rotate every credential inside.",
                    ))

        log.debug("security_agent.done", files=len(files), findings=len(findings))
        return AgentResult(agent_name=self.name, findings=findings)
