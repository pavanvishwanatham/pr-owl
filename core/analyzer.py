"""
PRAnalyzer — orchestrates all agents concurrently and merges results.
"""
import asyncio
import structlog
from typing import Any

from agents.code_quality_agent import CodeQualityAgent
from agents.security_agent import SecurityAgent
from agents.naming_agent import NamingAgent
from agents.ai_review_agent import AIReviewAgent
from agents.summary_agent import SummaryAgent
from agents.auto_fix_agent import AutoFixAgent
from agents.docs_agent import DocsAgent
from agents.breaking_change_agent import BreakingChangeAgent
from agents.dependency_risk_agent import DependencyRiskAgent
from agents.base_agent import AgentResult

log = structlog.get_logger()


class PRAnalyzer:
    """
    Runs all agents concurrently and returns merged results.

    Usage:
        analyzer = PRAnalyzer()
        results = await analyzer.analyze(pr_data, diff, files)
    """

    def __init__(self):
        # Agents that run on pure diff/regex — fast, no LLM call
        self.static_agents = [
            CodeQualityAgent(),
            SecurityAgent(),
            NamingAgent(),
            DocsAgent(),
            BreakingChangeAgent(),
            DependencyRiskAgent(),
        ]
        # Agents that call the LLM — slower, run after static
        self.ai_agents = [
            SummaryAgent(),
            AIReviewAgent(),
            AutoFixAgent(),
        ]

    async def analyze(
        self,
        pr_data: dict,
        diff: str,
        files: list[dict],
        run_ai: bool = True,
    ) -> dict[str, AgentResult]:
        """
        Run all agents concurrently. Returns a dict keyed by agent name.

        Args:
            pr_data: PR metadata dict (from GitHub API)
            diff:    Full unified diff string
            files:   List of file objects with filename, status, patch, additions, deletions
            run_ai:  Set False to skip LLM agents (e.g. for very large PRs)
        """
        agents_to_run = self.static_agents + (self.ai_agents if run_ai else [])

        log.info("pr_analyzer.start", pr=pr_data.get("number"), agents=len(agents_to_run))

        tasks = [self._safe_run(agent, pr_data, diff, files) for agent in agents_to_run]
        results_list: list[AgentResult] = await asyncio.gather(*tasks)

        results = {r.agent_name: r for r in results_list}
        log.info(
            "pr_analyzer.done",
            pr=pr_data.get("number"),
            total_findings=sum(len(r.findings) for r in results.values()),
        )
        return results

    async def _safe_run(self, agent, pr_data, diff, files) -> AgentResult:
        """Run a single agent, catching exceptions so one failure doesn't abort all."""
        try:
            log.debug("agent.start", agent=agent.name)
            result = await agent.analyze(pr_data, diff, files)
            log.debug("agent.done", agent=agent.name, findings=len(result.findings))
            return result
        except Exception as exc:
            log.error("agent.error", agent=agent.name, error=str(exc))
            from agents.base_agent import AgentResult
            return AgentResult(agent_name=agent.name, error=str(exc))
