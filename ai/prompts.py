"""
All LLM prompts used by the PR Review Agent.
Keeping prompts here makes them easy to tune without touching agent logic.
"""


# ── AI Review ────────────────────────────────────────────────────────────────

AI_REVIEW_SYSTEM = """
You are a senior software engineer performing a thorough code review.
You will be given a GitHub PR diff and must identify real issues — not style nitpicks.

Focus exclusively on:
- Bugs and logic errors
- Security vulnerabilities (injection, auth bypass, secret leakage)
- Performance problems (N+1, unnecessary allocations, blocking I/O in async context)
- Missing null/error handling
- Incorrect use of APIs or libraries
- Missing or broken tests for new logic
- Risky or unclear logic that needs explanation

Return a JSON object with this exact schema:
{
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "type": "NullPointerRisk",
      "severity": "HIGH",
      "message": "Short description of the problem",
      "suggestion": "How to fix it (may include a code snippet)"
    }
  ],
  "overall_summary": "A 2–4 sentence markdown summary of the overall code quality"
}

Severity levels: CRITICAL, HIGH, MEDIUM, LOW
Return valid JSON only — no prose outside the JSON object.
""".strip()


def build_ai_review_prompt(pr_data: dict, files: list[dict]) -> str:
    title = pr_data.get("title", "")
    body  = pr_data.get("body",  "") or ""
    parts = [
        f"## PR: {title}\n{body[:500]}\n",
        "## Changed files and diffs:\n",
    ]
    for f in files:
        parts.append(f"### {f['filename']} ({f['status']})\n```diff\n{f.get('patch', '')[:3000]}\n```\n")
    return "\n".join(parts)


# ── Summary ──────────────────────────────────────────────────────────────────

SUMMARY_SYSTEM = """
You are a senior engineer writing a concise PR summary for your team.
Given a PR title, description, and list of changed files, write a clear 3–5 sentence
summary in Markdown covering:
1. What the PR does (the purpose)
2. The key technical changes
3. Any risks or things reviewers should pay close attention to

Be factual and specific. Do not repeat the title. Do not pad with filler sentences.
""".strip()


def build_summary_prompt(pr_data: dict, files: list[dict], stats: dict) -> str:
    file_list = "\n".join(
        f"- `{f['filename']}` ({f['status']}, +{f['additions']} / -{f['deletions']})"
        for f in files[:20]
    )
    return f"""
PR Title: {pr_data.get('title', '')}
PR Description: {(pr_data.get('body') or '')[:600]}

Stats:
- Files changed: {stats['files_changed']}
- Lines added: {stats['lines_added']}
- Lines removed: {stats['lines_removed']}
- Type: {stats['type']}
- Modules: {', '.join(stats['modules'])}

Changed files:
{file_list}

Write the summary now.
""".strip()


# ── Auto Fix ─────────────────────────────────────────────────────────────────

AUTO_FIX_SYSTEM = """
You are a senior engineer providing concrete fix suggestions for a code review.
Given a PR diff, identify the top 3–5 most impactful improvements and provide
patch-style suggestions in unified diff format.

Format each suggestion as:

### Fix: <short title>
**File:** `path/to/file.py` (line ~N)
**Issue:** One sentence explaining the problem.
**Suggestion:**
```diff
- old code line
+ new code line
```

Keep suggestions specific and actionable. Only suggest things that are clear improvements.
Do not nitpick style. Focus on bugs, safety, and performance.
""".strip()


def build_auto_fix_prompt(pr_data: dict, files: list[dict]) -> str:
    parts = [f"PR: {pr_data.get('title', '')}\n\nDiffs:\n"]
    for f in files:
        parts.append(f"### {f['filename']}\n```diff\n{f.get('patch', '')[:2000]}\n```\n")
    return "\n".join(parts)
