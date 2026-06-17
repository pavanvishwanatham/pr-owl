"""
Tests for core/analyzer.py — the orchestrator that runs all agents concurrently.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from agents.base_agent import AgentResult, Finding, Severity
from core.analyzer import PRAnalyzer


@pytest.fixture
def analyzer():
    return PRAnalyzer()


def run(coro):
    return asyncio.run(coro)


def test_analyzer_returns_results_for_all_agents(analyzer, sample_pr_data, sample_files, sample_diff):
    """All static agents should return results (even if empty)."""
    results = run(analyzer.analyze(sample_pr_data, sample_diff, sample_files, run_ai=False))

    expected_agents = {
        "CodeQualityAgent", "SecurityAgent", "NamingAgent",
        "DocsAgent", "BreakingChangeAgent", "DependencyRiskAgent",
    }
    assert expected_agents.issubset(set(results.keys()))


def test_analyzer_ai_agents_skipped_when_run_ai_false(analyzer, sample_pr_data, sample_files, sample_diff):
    results = run(analyzer.analyze(sample_pr_data, sample_diff, sample_files, run_ai=False))
    ai_agents = {"AIReviewAgent", "SummaryAgent", "AutoFixAgent"}
    assert not ai_agents.intersection(results.keys())


def test_analyzer_handles_agent_error_gracefully(sample_pr_data, sample_files, sample_diff):
    """If one agent crashes, others should still complete."""
    from agents.code_quality_agent import CodeQualityAgent

    original = CodeQualityAgent.analyze

    async def crashing_analyze(self, *args, **kwargs):
        raise RuntimeError("Simulated crash")

    analyzer = PRAnalyzer()

    with patch.object(CodeQualityAgent, "analyze", crashing_analyze):
        results = run(analyzer.analyze(sample_pr_data, sample_diff, sample_files, run_ai=False))

    # CodeQualityAgent should have an error result, not missing
    cq = results.get("CodeQualityAgent")
    assert cq is not None
    assert cq.error != ""

    # Other agents should still have results
    assert "SecurityAgent" in results
    assert results["SecurityAgent"].error == ""


def test_analyzer_finds_security_issue_in_sample_files(analyzer, sample_pr_data, sample_files, sample_diff):
    """The sample files fixture contains a hardcoded API key — SecurityAgent should find it."""
    results = run(analyzer.analyze(sample_pr_data, sample_diff, sample_files, run_ai=False))
    sec = results.get("SecurityAgent")
    assert sec is not None
    # sample_files has 'sk_live_XXXXXXXXXXXXXXXXXXXXXXXX' — should be flagged
    assert len(sec.findings) >= 1


def test_analyzer_finds_debug_statement_in_sample_files(analyzer, sample_pr_data, sample_files, sample_diff):
    """The sample files fixture contains print() — CodeQualityAgent should find it."""
    results = run(analyzer.analyze(sample_pr_data, sample_diff, sample_files, run_ai=False))
    cq = results.get("CodeQualityAgent")
    assert cq is not None
    debug = [f for f in cq.findings if f.issue_type == "DebugStatement"]
    assert len(debug) >= 1


def test_clean_files_produce_fewer_findings(analyzer, sample_pr_data, clean_files):
    results = run(analyzer.analyze(sample_pr_data, "", clean_files, run_ai=False))
    total = sum(len(r.findings) for r in results.values())
    assert total == 0
