"""Tests for core/comment_formatter.py"""
import pytest
from agents.base_agent import AgentResult, Finding, Severity
from core.comment_formatter import format_pr_comment


def make_result(agent_name, findings=None, summary=""):
    return AgentResult(agent_name=agent_name, findings=findings or [], summary=summary)


def make_finding(severity=Severity.HIGH, issue_type="TestIssue", file="src/test.py", line=10):
    return Finding(file=file, line=line, issue_type=issue_type,
                   severity=severity, message="Test message for " + issue_type)


@pytest.fixture
def pr_meta():
    return {"number": 42, "head_branch": "feat/test", "base_branch": "main"}


@pytest.fixture
def basic_results():
    return {
        "CodeQualityAgent":  make_result("CodeQualityAgent",  [make_finding(Severity.MEDIUM, "DebugStatement")]),
        "SecurityAgent":     make_result("SecurityAgent",     [make_finding(Severity.CRITICAL, "APIKeyLeak")]),
        "NamingAgent":       make_result("NamingAgent",       []),
        "BreakingChangeAgent": make_result("BreakingChangeAgent", []),
        "DependencyRiskAgent": make_result("DependencyRiskAgent", []),
        "DocsAgent":         make_result("DocsAgent",         []),
        "SummaryAgent":      make_result("SummaryAgent",      summary="This PR adds retry logic."),
        "AIReviewAgent":     make_result("AIReviewAgent",     summary="Looks mostly good. One security issue."),
        "AutoFixAgent":      make_result("AutoFixAgent",      summary="### Fix: Remove hardcoded key\n```diff\n-API_KEY='sk_live_XXXX...'\n+API_KEY=os.getenv('API_KEY')\n```"),
    }


@pytest.fixture
def risk_high():
    return {"score": 75, "level": "HIGH", "reasons": ["[CRITICAL] APIKeyLeak: hardcoded stripe key"]}


@pytest.fixture
def risk_low():
    return {"score": 10, "level": "LOW", "reasons": ["No critical issues detected."]}


# ── Structure ─────────────────────────────────────────────────────────────────

def test_comment_contains_header(basic_results, risk_high, pr_meta):
    comment = format_pr_comment(basic_results, risk_high, pr_meta)
    assert "AI PR Review Report" in comment


def test_comment_contains_pr_number(basic_results, risk_high, pr_meta):
    comment = format_pr_comment(basic_results, risk_high, pr_meta)
    assert "PR #42" in comment


def test_comment_contains_branch_info(basic_results, risk_high, pr_meta):
    comment = format_pr_comment(basic_results, risk_high, pr_meta)
    assert "feat/test" in comment
    assert "main" in comment


def test_comment_contains_risk_score(basic_results, risk_high, pr_meta):
    comment = format_pr_comment(basic_results, risk_high, pr_meta)
    assert "75" in comment
    assert "HIGH" in comment


def test_comment_contains_merge_recommendation_high(basic_results, risk_high, pr_meta):
    comment = format_pr_comment(basic_results, risk_high, pr_meta)
    assert "Do not merge" in comment


def test_comment_contains_merge_recommendation_low(basic_results, risk_low, pr_meta):
    comment = format_pr_comment(basic_results, risk_low, pr_meta)
    assert "Safe to merge" in comment


def test_comment_contains_security_section(basic_results, risk_high, pr_meta):
    comment = format_pr_comment(basic_results, risk_high, pr_meta)
    assert "Security" in comment


def test_comment_contains_summary(basic_results, risk_high, pr_meta):
    comment = format_pr_comment(basic_results, risk_high, pr_meta)
    assert "retry logic" in comment  # from SummaryAgent summary


def test_comment_contains_fix_suggestions(basic_results, risk_high, pr_meta):
    comment = format_pr_comment(basic_results, risk_high, pr_meta)
    assert "Suggested Fix" in comment


def test_ai_agent_error_shown_gracefully(pr_meta, risk_low):
    results = {
        "AIReviewAgent": AgentResult(agent_name="AIReviewAgent", error="timeout"),
        "SummaryAgent":  make_result("SummaryAgent"),
    }
    comment = format_pr_comment(results, risk_low, pr_meta)
    assert "skipped" in comment.lower() or "timeout" in comment


def test_empty_results_doesnt_crash(pr_meta, risk_low):
    comment = format_pr_comment({}, risk_low, pr_meta)
    assert "AI PR Review Report" in comment
    assert isinstance(comment, str)
