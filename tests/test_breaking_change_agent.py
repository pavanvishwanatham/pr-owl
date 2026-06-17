"""Tests for agents/breaking_change_agent.py"""
import asyncio
import pytest
from agents.breaking_change_agent import BreakingChangeAgent
from agents.base_agent import Severity


@pytest.fixture
def agent():
    return BreakingChangeAgent()


def run(coro):
    return asyncio.run(coro)


def test_detects_removed_function(agent, sample_pr_data):
    files = [{
        "filename": "src/api.py",
        "status":   "modified",
        "additions": 0, "deletions": 3,
        "patch": (
            "@@ -5,5 +5,2 @@\n"
            " class API:\n"
            "-    def get_user(self, user_id):\n"
            "-        pass\n"
            " \n"
        ),
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    removed = [f for f in result.findings if f.issue_type == "FunctionRemoved"]
    assert len(removed) == 1
    assert "get_user" in removed[0].message
    assert removed[0].severity == Severity.HIGH


def test_detects_js_export_removed(agent, sample_pr_data):
    files = [{
        "filename": "src/utils.js",
        "status":   "modified",
        "additions": 0, "deletions": 1,
        "patch": (
            "@@ -1,3 +1,2 @@\n"
            " // utils\n"
            "-export function formatDate(date) { return date.toISOString(); }\n"
            " \n"
        ),
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    removed = [f for f in result.findings if f.issue_type in ("FunctionRemoved", "ExportRemoved")]
    assert len(removed) >= 1


def test_detects_signature_change(agent, sample_pr_data):
    files = [{
        "filename": "src/service.py",
        "status":   "modified",
        "additions": 1, "deletions": 1,
        "patch": (
            "@@ -3,4 +3,4 @@\n"
            " class Service:\n"
            "-    def process(self, amount):\n"
            "+    def process(self, amount, currency, retry=3):\n"
            "         pass\n"
        ),
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    sig_changes = [f for f in result.findings if f.issue_type == "SignatureChange"]
    assert len(sig_changes) >= 1
    assert "process" in sig_changes[0].message


def test_no_findings_for_added_function(agent, sample_pr_data):
    """Adding a new function should not trigger breaking change."""
    files = [{
        "filename": "src/api.py",
        "status":   "modified",
        "additions": 3, "deletions": 0,
        "patch": (
            "@@ -5,2 +5,5 @@\n"
            " class API:\n"
            "+    def new_endpoint(self):\n"
            "+        pass\n"
            " \n"
        ),
    }]
    result = run(agent.analyze(sample_pr_data, "", files))
    assert result.findings == []


def test_no_findings_for_empty_patch(agent, sample_pr_data):
    files = [{"filename": "README.md", "status": "modified",
              "additions": 1, "deletions": 0, "patch": ""}]
    result = run(agent.analyze(sample_pr_data, "", files))
    assert result.findings == []
