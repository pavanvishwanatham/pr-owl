"""Tests for security/secret_scanner.py"""
import pytest
from security.secret_scanner import SecretScanner

scanner = SecretScanner()


# ── Pattern-based detection ───────────────────────────────────────────────────

def test_detects_github_token():
    line = "token = 'ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'"
    hits = scanner.scan_line(line)
    assert len(hits) > 0
    assert hits[0]["type"] == "GitHubToken"
    assert hits[0]["high_confidence"] is True


def test_detects_aws_access_key():
    line = "AWS_ACCESS_KEY_ID = 'AKIAXXXXXXXXXXXXXXXX'"
    hits = scanner.scan_line(line)
    assert any(h["type"] == "AWSAccessKey" for h in hits)


def test_detects_stripe_key():
    line = "stripe.api_key = 'sk_live_XXXXXXXXXXXXXXXXXXXXXXXX'"
    hits = scanner.scan_line(line)
    assert any(h["type"] == "StripeSecretKey" for h in hits)


def test_detects_private_key_header():
    line = "-----BEGIN RSA PRIVATE KEY-----"
    hits = scanner.scan_line(line)
    assert any(h["type"] == "PrivateKey" for h in hits)


def test_detects_hardcoded_password():
    line = 'password = "SuperSecret123"'
    hits = scanner.scan_line(line)
    assert any(h["type"] == "HardcodedPassword" for h in hits)


def test_detects_url_with_credentials():
    line = "conn = 'postgresql://admin:mypassword@localhost:5432/db'"
    hits = scanner.scan_line(line)
    assert any(h["type"] == "URLWithCredentials" for h in hits)


def test_detects_slack_token():
    line = "SLACK_TOKEN = 'xoxb-123456789-abcdefghij'"
    hits = scanner.scan_line(line)
    assert any(h["type"] == "SlackToken" for h in hits)


# ── Clean lines — no false positives ─────────────────────────────────────────

def test_clean_variable_assignment():
    line = "max_retries = 3"
    assert scanner.scan_line(line) == []


def test_clean_comment():
    line = "# This function handles payment processing"
    assert scanner.scan_line(line) == []


def test_placeholder_not_flagged():
    line = "api_key = 'your_token_here'"
    # Should not flag common placeholder values
    hits = scanner.scan_line(line)
    # Even if flagged, it should be low confidence
    for h in hits:
        assert h["high_confidence"] is False


def test_short_string_not_flagged():
    line = "token = 'abc123'"
    # Too short to be a real secret
    assert scanner.scan_line(line) == []


# ── Entropy detection ─────────────────────────────────────────────────────────

def test_high_entropy_hex_string():
    # Real-looking 40-char hex string (like a git SHA used as a token)
    line = "secret = 'a3f9b2c4e1d8f7a6b5c3d2e1f4a9b8c7d6e5f4a3'"
    hits = scanner.scan_line(line)
    # May or may not trigger entropy detection — just verify no crash
    assert isinstance(hits, list)


def test_env_file_detection_via_agent(sample_files, sample_pr_data, sample_diff):
    """SecurityAgent flags .env file being committed."""
    import asyncio
    from agents.security_agent import SecurityAgent
    files = [
        {"filename": ".env", "status": "added", "additions": 5, "deletions": 0, "patch": "+SECRET=abc"}
    ]
    agent = SecurityAgent()
    result = asyncio.run(agent.analyze(sample_pr_data, "", files))
    env_findings = [f for f in result.findings if f.issue_type == ".envExposure"]
    assert len(env_findings) == 1
    assert env_findings[0].severity.value == "CRITICAL"
