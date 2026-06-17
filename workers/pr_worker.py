"""
Dramatiq worker — runs the full PR review pipeline asynchronously.

Flow:
  1. Fetch PR metadata, files, and diff from GitHub
  2. Run all agents concurrently
  3. Compute risk score
  4. Format comment
  5. Post comment to GitHub
  6. Persist results to PostgreSQL
"""
import asyncio
import structlog
import dramatiq
from dramatiq.brokers.redis import RedisBroker

from core.config import get_settings
from core.analyzer import PRAnalyzer
from core.risk_scorer import compute_risk
from core.comment_formatter import format_pr_comment
from github import client as gh
from db.database import get_session_factory
from db.models import PRReview, PRFinding

log = structlog.get_logger()

# Connect Dramatiq to Redis
broker = RedisBroker(url=get_settings().redis_url)
dramatiq.set_broker(broker)

_analyzer = PRAnalyzer()


@dramatiq.actor(max_retries=2, time_limit=300_000)  # 5 min timeout
def review_pr_task(owner: str, repo: str, pr_number: int):
    """Entry point called by the webhook handler. Runs the async pipeline."""
    asyncio.run(_review_pr_async(owner=owner, repo=repo, pr_number=pr_number))


async def _review_pr_async(owner: str, repo: str, pr_number: int):
    log.info("worker.start", owner=owner, repo=repo, pr=pr_number)

    try:
        # ── 1. Fetch PR data ──────────────────────────────────────────────
        pr_data, files, diff = await asyncio.gather(
            gh.get_pr(owner, repo, pr_number),
            gh.get_pr_files(owner, repo, pr_number),
            gh.get_pr_diff(owner, repo, pr_number),
        )

        # ── 2. Decide whether to run AI agents ────────────────────────────
        settings = get_settings()
        run_ai = not (
            settings.skip_ai_for_large_prs
            and pr_data.get("changed_files", 0) > settings.large_pr_file_threshold
        )

        # Truncate diff if too large
        max_bytes = settings.max_diff_size_kb * 1024
        if len(diff.encode()) > max_bytes:
            diff = diff[:max_bytes] + "\n[... diff truncated ...]"

        # ── 3. Run all agents ─────────────────────────────────────────────
        results = await _analyzer.analyze(
            pr_data=pr_data, diff=diff, files=files, run_ai=run_ai
        )

        # ── 4. Compute risk score ─────────────────────────────────────────
        risk = compute_risk(results, pr_data, files)
        log.info("worker.risk", pr=pr_number, level=risk["level"], score=risk["score"])

        # ── 5. Format comment ─────────────────────────────────────────────
        pr_meta = {
            "number":      pr_data.get("number"),
            "head_branch": pr_data.get("head", {}).get("ref", ""),
            "base_branch": pr_data.get("base", {}).get("ref", ""),
        }
        comment_body = format_pr_comment(results, risk, pr_meta)

        # ── 6. Post to GitHub ─────────────────────────────────────────────
        posted = await gh.post_pr_comment(owner, repo, pr_number, comment_body)
        comment_url = posted.get("html_url", "")
        log.info("worker.comment_posted", pr=pr_number, url=comment_url)

        # ── 7. Persist results ────────────────────────────────────────────
        await _save_results(
            owner=owner, repo=repo, pr_number=pr_number,
            risk=risk, results=results, comment_url=comment_url,
        )

    except Exception as exc:
        log.error("worker.error", owner=owner, repo=repo, pr=pr_number, error=str(exc))
        raise  # let Dramatiq retry


async def _save_results(owner, repo, pr_number, risk, results, comment_url):
    factory = get_session_factory()
    async with factory() as session:
        # Serialize results for storage
        serialized = {
            name: {
                "error": r.error,
                "summary": r.summary,
                "findings": [
                    {
                        "file": f.file, "line": f.line,
                        "issue_type": f.issue_type, "severity": str(f.severity),
                        "message": f.message,
                    }
                    for f in r.findings
                ],
            }
            for name, r in results.items()
        }

        review = PRReview(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            risk_level=risk["level"],
            risk_score=risk["score"],
            comment_url=comment_url,
            agent_results=serialized,
        )
        session.add(review)
        await session.flush()  # get the review.id

        for agent_name, result in results.items():
            for finding in result.findings:
                session.add(PRFinding(
                    review_id=review.id,
                    agent=agent_name,
                    file=finding.file,
                    line=finding.line,
                    issue_type=finding.issue_type,
                    severity=str(finding.severity),
                    message=finding.message,
                    suggestion=finding.suggestion,
                ))

        await session.commit()
        log.info("worker.db_saved", review_id=review.id)
