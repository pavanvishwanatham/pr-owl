"""Tests for agents/docs_agent.py"""
import asyncio
import pytest
from agents.docs_agent import DocsAgent


@pytest.fixture
def agent():
    return DocsAgent()


def run(coro):
    return asyncio.run(coro)


def make_file(filename, patch_lines, status="modified"):
    patch = "@@ -0,0 +1," + str(len(patch_lines)) + " @@\n"
    patch += "\n".join("+" + l for l in patch_lines) + "\n"
    return {"filename": filename, "status": status,
            "additions": len(patch_lines), "deletions": 0, "patch": patch}


def test_new_fastapi_route_without_docs_flagged(agent, sample_pr_data):
    files = [
        make_file("src/api.py", ['@app.get("/users/{user_id}")']),
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "MissingDocUpdate"]
    assert len(issues) >= 1


def test_new_route_with_readme_update_not_flagged(agent, sample_pr_data):
    files = [
        make_file("src/api.py", ['@app.post("/payments")']),
        make_file("README.md", ["## New endpoint: POST /payments"]),
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "MissingDocUpdate"]
    assert issues == []


def test_new_js_export_without_docs_flagged(agent, sample_pr_data):
    files = [
        make_file("src/utils.js", ["export function formatCurrency(amount, currency) {"]),
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "MissingDocUpdate"]
    assert len(issues) >= 1


def test_config_change_without_docs_flagged(agent, sample_pr_data):
    files = [
        make_file("config.py", ["NEW_FEATURE_FLAG = True"]),
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "ConfigChangedNoDoc"]
    assert len(issues) >= 1


def test_no_issues_for_internal_functions(agent, sample_pr_data):
    """Private/internal functions shouldn't require doc updates."""
    files = [
        make_file("src/internal.py", ["def _private_helper(x):  pass"]),
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    assert result.findings == []


def test_swagger_update_clears_missing_doc(agent, sample_pr_data):
    files = [
        make_file("src/api.py", ['@router.get("/items")']),
        make_file("docs/swagger.yaml", ["  /items:", "    get:"]),
    ]
    result = run(agent.analyze(sample_pr_data, "", files))
    issues = [f for f in result.findings if f.issue_type == "MissingDocUpdate"]
    assert issues == []
