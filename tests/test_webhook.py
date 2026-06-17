"""
Integration tests for the GitHub webhook endpoint.
Uses FastAPI TestClient — no real GitHub or Redis connection needed.
"""
import hashlib
import hmac
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# Mock settings and dramatiq before importing the app
import os
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")


def _sign(payload: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _pr_payload(action="opened", pr_number=42):
    return {
        "action": action,
        "pull_request": {
            "number": pr_number,
            "title":  "Test PR",
            "body":   "Test body",
        },
        "repository": {
            "name":  "my-repo",
            "owner": {"login": "Flipkart"},
        },
    }


@pytest.fixture
def client():
    """TestClient with mocked DB init and Dramatiq broker."""
    with patch("db.database.init_db", return_value=None), \
         patch("dramatiq.set_broker"), \
         patch("workers.pr_worker.review_pr_task") as mock_task:

        # Patch the send method
        mock_task.send = MagicMock()

        from server import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, mock_task


# ── Health check ──────────────────────────────────────────────────────────────

def test_health_check(client):
    c, _ = client
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Webhook — valid PR opened ─────────────────────────────────────────────────

def test_webhook_pr_opened_queues_job(client):
    c, mock_task = client
    payload = json.dumps(_pr_payload("opened")).encode()
    sig = _sign(payload)

    resp = c.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event":      "pull_request",
            "X-Hub-Signature-256": sig,
            "Content-Type":        "application/json",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["pr"] == 42


def test_webhook_pr_synchronize_queues_job(client):
    c, mock_task = client
    payload = json.dumps(_pr_payload("synchronize", 99)).encode()
    sig = _sign(payload)

    resp = c.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event":      "pull_request",
            "X-Hub-Signature-256": sig,
            "Content-Type":        "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


# ── Webhook — ignored events ──────────────────────────────────────────────────

def test_non_pr_event_ignored(client):
    c, _ = client
    payload = json.dumps({"action": "created"}).encode()
    sig = _sign(payload)

    resp = c.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event":      "push",
            "X-Hub-Signature-256": sig,
            "Content-Type":        "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_pr_closed_action_ignored(client):
    c, _ = client
    payload = json.dumps(_pr_payload("closed")).encode()
    sig = _sign(payload)

    resp = c.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event":      "pull_request",
            "X-Hub-Signature-256": sig,
            "Content-Type":        "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── Webhook — invalid signature ───────────────────────────────────────────────

def test_invalid_signature_rejected(client):
    c, _ = client
    payload = json.dumps(_pr_payload()).encode()

    resp = c.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-GitHub-Event":      "pull_request",
            "X-Hub-Signature-256": "sha256=invalidsignature",
            "Content-Type":        "application/json",
        },
    )
    assert resp.status_code == 401
