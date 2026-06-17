"""
SummaryAgent — generates a human-readable PR summary using the LLM.
Also computes basic stats (type, modules, lines, files).
"""
import re
from agents.base_agent import BaseAgent, AgentResult
from ai.llm_client import call_llm
from ai.prompts import SUMMARY_SYSTEM, build_summary_prompt


def _detect_pr_type(pr_data: dict, files: list[dict]) -> str:
    title = (pr_data.get("title") or "").lower()
    body  = (pr_data.get("body")  or "").lower()
    text  = title + " " + body

    if any(k in text for k in ("fix", "bug", "patch", "hotfix", "resolve")):
        return "bug-fix"
    if any(k in text for k in ("refactor", "cleanup", "clean up", "restructure")):
        return "refactor"
    if any(k in text for k in ("feat", "feature", "add", "new", "implement")):
        return "feature"
    if any(k in text for k in ("test", "spec", "coverage")):
        return "test"
    if any(k in text for k in ("chore", "bump", "upgrade", "update dep")):
        return "chore"
    return "unknown"


def _affected_modules(files: list[dict]) -> list[str]:
    """Extract top-level directories from changed file paths."""
    modules = set()
    for f in files:
        parts = f["filename"].split("/")
        if len(parts) > 1:
            modules.add(parts[0])
        else:
            modules.add("root")
    return sorted(modules)


class SummaryAgent(BaseAgent):
    name = "SummaryAgent"

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        pr_type = _detect_pr_type(pr_data, files)
        modules = _affected_modules(files)

        stats = {
            "files_changed": pr_data.get("changed_files", len(files)),
            "lines_added":   pr_data.get("additions", 0),
            "lines_removed": pr_data.get("deletions", 0),
            "type":          pr_type,
            "modules":       modules,
        }

        user_prompt = build_summary_prompt(pr_data, files, stats)

        try:
            ai_summary = await call_llm(system=SUMMARY_SYSTEM, user=user_prompt)
        except Exception as exc:
            ai_summary = f"_(AI summary unavailable: {exc})_"

        summary_md = f"""
**Type:** `{pr_type}`
**Files changed:** {stats['files_changed']} (+{stats['lines_added']} / -{stats['lines_removed']} lines)
**Modules affected:** {', '.join(f'`{m}`' for m in modules)}

{ai_summary}
""".strip()

        return AgentResult(agent_name=self.name, summary=summary_md)
