"""
Formats the final PR comment from all agent results.
Produces a structured Markdown report.
"""
from agents.base_agent import AgentResult, Severity

SEVERITY_EMOJI = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH:     "🟠",
    Severity.MEDIUM:   "🟡",
    Severity.LOW:      "⚪",
}

RISK_EMOJI = {
    "LOW":    "🟢",
    "MEDIUM": "🟡",
    "HIGH":   "🔴",
}

MERGE_RECOMMENDATION = {
    "LOW":    "✅ **Safe to merge** — no critical issues found.",
    "MEDIUM": "⚠️ **Review suggested** — address medium-severity issues before merging.",
    "HIGH":   "🚫 **Do not merge** — critical or high-severity issues must be fixed first.",
}


def _section(title: str, content: str) -> str:
    return f"\n<details>\n<summary><b>{title}</b></summary>\n\n{content}\n</details>\n"


def _findings_table(findings) -> str:
    if not findings:
        return "_No issues found._\n"
    rows = ["| File | Line | Severity | Issue | Message |",
            "|------|------|----------|-------|---------|"]
    for f in sorted(findings, key=lambda x: (x.severity, x.file)):
        emoji = SEVERITY_EMOJI.get(f.severity, "")
        rows.append(
            f"| `{f.file}` | {f.line} | {emoji} {f.severity} "
            f"| {f.issue_type} | {f.message[:100]} |"
        )
    return "\n".join(rows) + "\n"


def format_pr_comment(
    results: dict[str, AgentResult],
    risk: dict,
    pr_data: dict,
) -> str:
    lines = []

    # ── Header ──────────────────────────────────────────────────────────────
    lines.append("## 🤖 AI PR Review Report\n")
    lines.append(f"> Analysed by PR Review Agent • PR #{pr_data.get('number')} — "
                 f"`{pr_data.get('head_branch', '')}` → `{pr_data.get('base_branch', '')}`\n")

    # ── PR Summary ──────────────────────────────────────────────────────────
    summary_result = results.get("SummaryAgent")
    if summary_result and not summary_result.error:
        lines.append(_section("📋 PR Summary", summary_result.summary or "_No summary generated._"))

    # ── Code Quality ────────────────────────────────────────────────────────
    cq = results.get("CodeQualityAgent")
    if cq:
        body = _findings_table(cq.findings)
        lines.append(_section(f"🔍 Code Quality Issues ({len(cq.findings)})", body))

    # ── Security ────────────────────────────────────────────────────────────
    sec = results.get("SecurityAgent")
    if sec:
        body = _findings_table(sec.findings)
        lines.append(_section(f"🔒 Security Risks ({len(sec.findings)})", body))

    # ── Naming ──────────────────────────────────────────────────────────────
    naming = results.get("NamingAgent")
    if naming:
        body = _findings_table(naming.findings)
        lines.append(_section(f"✏️ Naming Issues ({len(naming.findings)})", body))

    # ── Breaking Changes ────────────────────────────────────────────────────
    bc = results.get("BreakingChangeAgent")
    if bc:
        body = _findings_table(bc.findings)
        lines.append(_section(f"💥 Breaking Changes ({len(bc.findings)})", body))

    # ── Dependency Risk ─────────────────────────────────────────────────────
    dep = results.get("DependencyRiskAgent")
    if dep:
        body = _findings_table(dep.findings)
        lines.append(_section(f"📦 Dependency Risks ({len(dep.findings)})", body))

    # ── Docs ────────────────────────────────────────────────────────────────
    docs = results.get("DocsAgent")
    if docs:
        body = _findings_table(docs.findings)
        lines.append(_section(f"📝 Documentation Issues ({len(docs.findings)})", body))

    # ── AI Review ───────────────────────────────────────────────────────────
    ai = results.get("AIReviewAgent")
    if ai and not ai.error:
        body = ai.summary or _findings_table(ai.findings)
        lines.append(_section(f"🧠 AI Code Review ({len(ai.findings)} findings)", body))
    elif ai and ai.error:
        lines.append(_section("🧠 AI Code Review", f"⚠️ AI review skipped: {ai.error}"))

    # ── Auto-fix Suggestions ────────────────────────────────────────────────
    fix = results.get("AutoFixAgent")
    if fix and fix.summary:
        lines.append(_section("🔧 Suggested Fixes", fix.summary))

    # ── Risk Score ──────────────────────────────────────────────────────────
    risk_emoji = RISK_EMOJI.get(risk["level"], "")
    risk_body = (
        f"**Score:** {risk['score']}/100  \n"
        f"**Level:** {risk_emoji} {risk['level']}\n\n"
        "**Key reasons:**\n"
        + "\n".join(f"- {r}" for r in risk["reasons"])
    )
    lines.append(_section("📊 Risk Score", risk_body))

    # ── Merge Recommendation ────────────────────────────────────────────────
    lines.append(f"\n---\n\n{MERGE_RECOMMENDATION[risk['level']]}\n")
    lines.append("\n_🤖 This review was generated automatically. Always apply human judgment._")

    return "\n".join(lines)
