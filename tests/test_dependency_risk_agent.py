"""Tests for agents/dependency_risk_agent.py"""
import asyncio
import pytest
from agents.dependency_risk_agent import DependencyRiskAgent
from agents.base_agent import Severity


@pytest.fixture
def agent():
    return DependencyRiskAgent()


def run(coro):
    return asyncio.run(coro)


def make_dep_file(filename, added_lines, removed_lines=None):
    patch = "@@ -1,5 +1,5 @@\n"
    for line in (removed_lines or []):
        patch += f"-{line}\n"
    for line in added_lines:
        patch += f"+{line}\n"
    return {
        "filename": filename, "status": "modified",
        "additions": len(added_lines),
        "deletions": len(removed_lines or []),
        "patch": patch,
    }


# ── package.json ──────────────────────────────────────────────────────────────

def test_detects_major_version_upgrade_package_json(agent, sample_pr_data):
    f = make_dep_file(
        "package.json",
        added_lines=['"react": "18.0.0"'],
        removed_lines=['"react": "17.0.2"'],
    )
    result = run(agent.analyze(sample_pr_data, "", [f]))
    major = [x for x in result.findings if x.issue_type == "MajorVersionUpgrade"]
    assert len(major) == 1
    assert "react" in major[0].message


def test_detects_wildcard_dependency(agent, sample_pr_data):
    f = make_dep_file("package.json", added_lines=['"lodash": "*"'])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    wild = [x for x in result.findings if x.issue_type == "WildcardDependency"]
    assert len(wild) == 1
    assert wild[0].severity == Severity.HIGH


def test_detects_git_dependency(agent, sample_pr_data):
    f = make_dep_file("package.json", added_lines=['"mylib": "git+https://github.com/org/mylib.git"'])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    git_dep = [x for x in result.findings if x.issue_type == "GitDependency"]
    assert len(git_dep) == 1


# ── requirements.txt ──────────────────────────────────────────────────────────

def test_detects_major_upgrade_requirements(agent, sample_pr_data):
    f = make_dep_file(
        "requirements.txt",
        added_lines=["django==4.0.0"],
        removed_lines=["django==3.2.0"],
    )
    result = run(agent.analyze(sample_pr_data, "", [f]))
    major = [x for x in result.findings if x.issue_type == "MajorVersionUpgrade"]
    assert len(major) == 1


def test_detects_unpinned_requirement(agent, sample_pr_data):
    f = make_dep_file("requirements.txt", added_lines=["requests>=2.0"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    unpinned = [x for x in result.findings if x.issue_type == "UnpinnedDependency"]
    assert len(unpinned) == 1


# ── Lock file tampered ────────────────────────────────────────────────────────

def test_lock_file_without_manifest_change(agent, sample_pr_data):
    files = [{
        "filename": "package-lock.json", "status": "modified",
        "additions": 10, "deletions": 5,
        "patch": "@@ -1,5 +1,10 @@\n+some change\n",
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    tampered = [x for x in result.findings if x.issue_type == "LockFileTampered"]
    assert len(tampered) == 1
    assert tampered[0].severity == Severity.HIGH


# ── pom.xml ───────────────────────────────────────────────────────────────────

def test_detects_snapshot_dependency(agent, sample_pr_data):
    f = make_dep_file("pom.xml", added_lines=["    <version>1.0.0-SNAPSHOT</version>"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    snap = [x for x in result.findings if x.issue_type == "SnapshotDependency"]
    assert len(snap) == 1


def test_minor_upgrade_not_flagged(agent, sample_pr_data):
    f = make_dep_file(
        "package.json",
        added_lines=['"axios": "1.7.0"'],
        removed_lines=['"axios": "1.6.0"'],
    )
    result = run(agent.analyze(sample_pr_data, "", [f]))
    major = [x for x in result.findings if x.issue_type == "MajorVersionUpgrade"]
    assert major == []
