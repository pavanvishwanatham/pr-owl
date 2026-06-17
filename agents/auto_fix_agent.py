"""
AutoFixAgent — generates patch-style fix suggestions for issues found in the diff.
Uses the LLM to produce unified-diff-style suggestions.
"""
from agents.base_agent import BaseAgent, AgentResult
from ai.llm_client import call_llm
from ai.prompts import AUTO_FIX_SYSTEM, build_auto_fix_prompt


class AutoFixAgent(BaseAgent):
    name = "AutoFixAgent"

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        # Only generate fixes for small-to-medium PRs (avoid huge context)
        changed_files = pr_data.get("changed_files", len(files))
        if changed_files > 20:
            return AgentResult(
                agent_name=self.name,
                summary="_Auto-fix suggestions skipped for large PRs (>20 files)._",
            )

        relevant = [
            f for f in files
            if f.get("patch") and f.get("additions", 0) > 0
        ][:10]  # cap at 10 files

        if not relevant:
            return AgentResult(agent_name=self.name, summary="_No fixable changes found._")

        user_prompt = build_auto_fix_prompt(pr_data, relevant)

        try:
            suggestions = await call_llm(system=AUTO_FIX_SYSTEM, user=user_prompt)
        except Exception as exc:
            return AgentResult(agent_name=self.name, error=str(exc))

        return AgentResult(agent_name=self.name, summary=suggestions)
