"""
GitHub API client — thin wrapper over httpx for PR operations.
Targets GitHub Enterprise (configurable via GITHUB_API_BASE).
"""
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings

log = structlog.get_logger()


def _headers() -> dict:
    settings = get_settings()
    return {
        "Authorization": f"token {settings.github_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }


def _base() -> str:
    return get_settings().github_api_base.rstrip("/")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_pr(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch PR metadata."""
    url = f"{_base()}/repos/{owner}/{repo}/pulls/{pr_number}"
    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_pr_files(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Fetch all files changed in the PR (paginated)."""
    url = f"{_base()}/repos/{owner}/{repo}/pulls/{pr_number}/files"
    results = []
    page = 1
    async with httpx.AsyncClient(verify=True) as client:
        while True:
            resp = await client.get(
                url, headers=_headers(), params={"per_page": 100, "page": page}
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            results.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return results


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_pr_diff(owner: str, repo: str, pr_number: int) -> str:
    """Fetch the full unified diff of the PR."""
    url = f"{_base()}/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {**_headers(), "Accept": "application/vnd.github.v3.diff"}
    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_file_content(owner: str, repo: str, path: str, ref: str) -> str:
    """Fetch a file's content at a specific ref."""
    import base64
    url = f"{_base()}/repos/{owner}/{repo}/contents/{path}"
    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.get(url, headers=_headers(), params={"ref": ref})
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        data = resp.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return data.get("content", "")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def post_pr_comment(owner: str, repo: str, pr_number: int, body: str) -> dict:
    """Post a top-level comment on the PR."""
    url = f"{_base()}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.post(url, headers=_headers(), json={"body": body})
        resp.raise_for_status()
        log.info("github.comment_posted", pr=pr_number, url=resp.json().get("html_url"))
        return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def post_pr_review(
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    inline_comments: list[dict],
    event: str = "COMMENT",
) -> dict:
    """
    Submit a PR review with optional inline comments.

    inline_comments format:
        [{"path": "src/Foo.java", "line": 42, "side": "RIGHT", "body": "..."}]
    """
    url = f"{_base()}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    headers = {**_headers(), "Accept": "application/vnd.github+json"}
    payload = {"body": body, "event": event, "comments": inline_comments}
    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        log.info("github.review_posted", pr=pr_number, comments=len(inline_comments))
        return resp.json()
