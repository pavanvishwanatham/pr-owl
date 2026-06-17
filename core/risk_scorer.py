"""
Risk scorer — aggregates agent findings into a single LOW / MEDIUM / HIGH score.
"""
from agents.base_agent import AgentResult, Severity


WEIGHTS = {
    # (agent_name, severity) -> score contribution
    ("SecurityAgent",        Severity.CRITICAL): 40,
    ("SecurityAgent",        Severity.HIGH):     25,
    ("SecurityAgent",        Severity.MEDIUM):   10,
    ("BreakingChangeAgent",  Severity.HIGH):     20,
    ("BreakingChangeAgent",  Severity.MEDIUM):   10,
    ("DependencyRiskAgent",  Severity.HIGH):     15,
    ("DependencyRiskAgent",  Severity.MEDIUM):    8,
    ("CodeQualityAgent",     Severity.HIGH):      8,
    ("CodeQualityAgent",     Severity.MEDIUM):    4,
    ("AIReviewAgent",        Severity.CRITICAL): 30,
    ("AIReviewAgent",        Severity.HIGH):     15,
    ("AIReviewAgent",        Severity.MEDIUM):    5,
}

# Flat bonuses for structural PR characteristics
def _structural_score(pr_data: dict, files: list[dict]) -> int:
    score = 0
    changed_files = pr_data.get("changed_files", 0)
    additions = pr_data.get("additions", 0)

    if changed_files > 30:
        score += 10   # very large PR
    elif changed_files > 15:
        score += 5

    if additions > 1000:
        score += 10   # large diff

    # No test files in PR?
    has_tests = any(
        "test" in f["filename"].lower() or "spec" in f["filename"].lower()
        for f in files
    )
    if not has_tests and additions > 50:
        score += 10   # new code with no tests

    # Core / sensitive file changes
    sensitive_paths = ("auth", "security", "payment", "credential", "secret", "config/prod")
    if any(
        any(p in f["filename"].lower() for p in sensitive_paths)
        for f in files
    ):
        score += 15

    return score


def compute_risk(
    results: dict[str, AgentResult],
    pr_data: dict,
    files: list[dict],
) -> dict:
    """
    Returns:
        {
            "score": int,        # 0–100
            "level": "LOW" | "MEDIUM" | "HIGH",
            "reasons": [str],    # human-readable reasons
        }
    """
    score = _structural_score(pr_data, files)
    reasons = []

    for agent_name, result in results.items():
        for finding in result.findings:
            weight = WEIGHTS.get((agent_name, finding.severity), 0)
            # Default small weight for any unmatched finding
            if weight == 0 and finding.severity in (Severity.HIGH, Severity.CRITICAL):
                weight = 5
            score += weight

    # Cap at 100
    score = min(score, 100)

    # Build reasons list from top contributing findings
    all_findings = []
    for result in results.values():
        all_findings.extend(result.findings)

    critical_high = [f for f in all_findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
    for f in critical_high[:5]:  # top 5
        reasons.append(f"[{f.severity}] {f.issue_type}: {f.message[:80]}")

    if not reasons:
        reasons.append("No critical or high-severity issues detected.")

    level = "LOW" if score < 30 else "HIGH" if score >= 60 else "MEDIUM"

    return {"score": score, "level": level, "reasons": reasons}
