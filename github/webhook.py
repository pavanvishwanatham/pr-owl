"""
GitHub webhook receiver.
Verifies HMAC-SHA256 signature, filters PR events, runs review in background.
"""
import hashlib
import hmac
import structlog
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from core.config import get_settings
from workers.pr_worker import _review_pr_async

log = structlog.get_logger()
router = APIRouter()


def _verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub's X-Hub-Signature-256 header."""
    secret = get_settings().github_webhook_secret
    if not secret:
        log.warning("webhook.no_secret_configured")
        return True  # allow in dev; enforce in prod

    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    payload_bytes = await request.body()

    if not _verify_signature(payload_bytes, x_hub_signature_256):
        log.warning("webhook.invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Only handle pull_request events
    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    payload = await request.json()
    action = payload.get("action", "")

    # Trigger on open or push (synchronize)
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    owner = repo.get("owner", {}).get("login", "")
    repo_name = repo.get("name", "")
    pr_number = pr.get("number")

    if not all([owner, repo_name, pr_number]):
        raise HTTPException(status_code=400, detail="Malformed payload")

    log.info("webhook.pr_received", owner=owner, repo=repo_name, pr=pr_number, action=action)

    # Run review as a FastAPI background task (no Redis/Dramatiq needed)
    background_tasks.add_task(_review_pr_async, owner=owner, repo=repo_name, pr_number=pr_number)

    return {"status": "queued", "pr": pr_number}
