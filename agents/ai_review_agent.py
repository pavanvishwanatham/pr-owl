"""
AIReviewAgent — sends the PR diff to an LLM and returns structured findings.
"""
import json
import structlog
from agents.base_agent import BaseAgent, AgentResult, Finding, Severity
from ai.llm_client import call_llm
from ai.prompts import AI_REVIEW_SYSTEM, build_ai_review_prompt

log = structlog.get_logger()


class AIReviewAgent(BaseAgent):
    name = "AIReviewAgent"

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        # Build a focused diff (only files with real changes, skip generated/lock files)
        relevant = [
            f for f in files
            if f.get("patch")
            and not any(f["filename"].endswith(ext) for ext in (
                ".lock", ".min.js", ".min.css", ".pb.go", ".generated.",
                "package-lock.json", "yarn.lock", "poetry.lock",
            ))
        ]

        if not relevant:
            return AgentResult(agent_name=self.name, summary="No reviewable files found.")

        user_prompt = build_ai_review_prompt(pr_data, relevant)

        try:
            response = await call_llm(
                system=AI_REVIEW_SYSTEM,
                user=user_prompt,
                response_format="json",
            )
            data = json.loads(response)
        except Exception as exc:
            log.error("ai_review.parse_error", error=str(exc))
            # Fallback: return raw response as summary
            return AgentResult(agent_name=self.name, summary=str(response), error=str(exc))

        findings = []
        for item in data.get("findings", []):
            try:
                sev = Severity(item.get("severity", "MEDIUM").upper())
            except ValueError:
                sev = Severity.MEDIUM

            findings.append(Finding(
                file=item.get("file", "unknown"),
                line=int(item.get("line", 0)),
                issue_type=item.get("type", "AIFinding"),
                severity=sev,
                message=item.get("message", ""),
                suggestion=item.get("suggestion", ""),
            ))

        summary_md = data.get("overall_summary", "")

        return AgentResult(agent_name=self.name, findings=findings, summary=summary_md)
