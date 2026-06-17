"""Tests for agents/naming_agent.py"""
import asyncio
import pytest
from agents.naming_agent import NamingAgent


@pytest.fixture
def agent():
    return NamingAgent()


def run(coro):
    return asyncio.run(coro)


def make_file(filename, patch_lines):
    patch = "@@ -0,0 +1," + str(len(patch_lines)) + " @@\n"
    patch += "\n".join("+" + l for l in patch_lines) + "\n"
    return {"filename": filename, "status": "added",
            "additions": len(patch_lines), "deletions": 0, "patch": patch}


# ── Python ────────────────────────────────────────────────────────────────────

def test_python_snake_case_ok(agent, sample_pr_data):
    f = make_file("src/utils.py", ["def calculate_total(items):"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    naming = [x for x in result.findings if x.issue_type == "FunctionNaming"]
    assert naming == []


def test_python_camel_case_function_flagged(agent, sample_pr_data):
    f = make_file("src/utils.py", ["def calculateTotal(items):"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    naming = [x for x in result.findings if x.issue_type == "FunctionNaming"]
    assert len(naming) == 1
    assert "snake_case" in naming[0].message


def test_python_pascal_case_class_ok(agent, sample_pr_data):
    f = make_file("src/models.py", ["class PaymentService:"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    naming = [x for x in result.findings if x.issue_type == "ClassNaming"]
    assert naming == []


def test_python_lowercase_class_flagged(agent, sample_pr_data):
    f = make_file("src/models.py", ["class paymentService:"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    naming = [x for x in result.findings if x.issue_type == "ClassNaming"]
    assert len(naming) == 1


# ── JavaScript ────────────────────────────────────────────────────────────────

def test_js_camel_case_function_ok(agent, sample_pr_data):
    f = make_file("src/api.js", ["function processPayment(amount) {"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    naming = [x for x in result.findings if x.issue_type == "FunctionNaming"]
    assert naming == []


def test_js_snake_case_function_flagged(agent, sample_pr_data):
    f = make_file("src/api.js", ["function process_payment(amount) {"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    naming = [x for x in result.findings if x.issue_type == "FunctionNaming"]
    assert len(naming) == 1
    assert "camelCase" in naming[0].message


def test_js_pascal_class_ok(agent, sample_pr_data):
    f = make_file("src/PaymentService.js", ["class PaymentService {"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    naming = [x for x in result.findings if x.issue_type == "ClassNaming"]
    assert naming == []


# ── Unsupported file type skipped ─────────────────────────────────────────────

def test_yaml_file_skipped(agent, sample_pr_data):
    f = make_file("config.yaml", ["api_key: value"])
    result = run(agent.analyze(sample_pr_data, "", [f]))
    assert result.findings == []
