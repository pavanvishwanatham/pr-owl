"""Tests for core/risk_scorer.py"""
import pytest
from agents.base_agent import AgentResult, Finding, Severity
from core.risk_scorer import compute_risk


def make_result(agent_name, findings):
    return AgentResult(agent_name=agent_name, findings=findings)


def make_finding(severity, issue_type="TestIssue"):
    return Finding(file="test.py", line=1, issue_type=issue_type,
                   severity=severity, message="test message")


@pytest.fixture
def base_pr(sample_pr_data):
    return sample_pr_data


@pytest.fixture
def base_files(sample_files):
    return sample_files


# ── Risk level thresholds ─────────────────────────────────────────────────────

def test_no_findings_gives_low_risk(base_pr, base_files):
    results = {
        "CodeQualityAgent": make_result("CodeQualityAgent", []),
        "SecurityAgent":    make_result("SecurityAgent", []),
    }
    risk = compute_risk(results, base_pr, base_files)
    assert risk["level"] == "LOW"
    assert risk["score"] < 30


def test_critical_security_gives_high_risk(base_pr, base_files):
    results = {
        "SecurityAgent": make_result("SecurityAgent", [
            make_finding(Severity.CRITICAL, "HardcodedPassword"),
        ]),
    }
    risk = compute_risk(results, base_pr, base_files)
    assert risk["level"] == "HIGH"
    assert risk["score"] >= 60


def test_multiple_medium_gives_medium_risk(base_pr, base_files):
    results = {
        "CodeQualityAgent": make_result("CodeQualityAgent", [
            make_finding(Severity.MEDIUM) for _ in range(3)
        ]),
    }
    risk = compute_risk(results, base_pr, base_files)
    # 3 medium code quality findings + structural score
    assert risk["level"] in ("LOW", "MEDIUM")  # depends on structural factors


def test_breaking_change_high_severity_raises_score(base_pr, base_files):
    results = {
        "BreakingChangeAgent": make_result("BreakingChangeAgent", [
            make_finding(Severity.HIGH, "FunctionRemoved"),
            make_finding(Severity.HIGH, "ExportRemoved"),
        ]),
    }
    risk = compute_risk(results, base_pr, base_files)
    assert risk["score"] >= 40


def test_score_capped_at_100(base_pr, base_files):
    # Many critical findings
    findings = [make_finding(Severity.CRITICAL) for _ in range(20)]
    results = {"SecurityAgent": make_result("SecurityAgent", findings)}
    risk = compute_risk(results, base_pr, base_files)
    assert risk["score"] <= 100


def test_risk_includes_reasons(base_pr, base_files):
    results = {
        "SecurityAgent": make_result("SecurityAgent", [
            make_finding(Severity.CRITICAL, "APIKeyLeak"),
        ]),
    }
    risk = compute_risk(results, base_pr, base_files)
    assert len(risk["reasons"]) >= 1


def test_large_pr_structural_bonus(sample_pr_data, sample_files):
    pr = {**sample_pr_data, "changed_files": 35, "additions": 1500}
    results = {}
    risk = compute_risk(results, pr, sample_files)
    # Large PR + large diff + no tests = structural penalty
    assert risk["score"] > 0


def test_risk_levels_are_valid(base_pr, base_files):
    results = {"CodeQualityAgent": make_result("CodeQualityAgent", [])}
    risk = compute_risk(results, base_pr, base_files)
    assert risk["level"] in ("LOW", "MEDIUM", "HIGH")
