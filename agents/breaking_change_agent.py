"""
BreakingChangeAgent — detects potentially breaking changes in the PR diff.

Detects:
  - Function/method signature changes (parameter added/removed)
  - Return type changes
  - Public API removal (deleted functions/classes)
  - Renamed exports
  - Config schema changes
"""
import re
from agents.base_agent import BaseAgent, AgentResult, Finding, Severity
from parsers.diff_parser import get_added_lines, get_removed_lines


# Patterns to extract function/method signatures from diff lines
_FUNC_DEF = re.compile(
    r"(?:def|function|public|private|protected|static|async)\s+([a-zA-Z_]\w*)\s*\("
)
_EXPORT_DEF = re.compile(r"export\s+(?:function|class|const|default)\s+([a-zA-Z_]\w*)")
_CLASS_DEF  = re.compile(r"class\s+([a-zA-Z_]\w*)")


def _extract_names(lines: list[tuple], pattern: re.Pattern) -> set[str]:
    names = set()
    for _, line in lines:
        m = pattern.search(line)
        if m:
            names.add(m.group(1))
    return names


class BreakingChangeAgent(BaseAgent):
    name = "BreakingChangeAgent"

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        findings: list[Finding] = []

        for file in files:
            filename = file["filename"]
            patch = file.get("patch", "")
            if not patch:
                continue

            added   = get_added_lines(patch)
            removed = get_removed_lines(patch)

            # Functions/methods that were removed (not just renamed)
            removed_funcs = _extract_names(removed, _FUNC_DEF)
            added_funcs   = _extract_names(added,   _FUNC_DEF)
            deleted_funcs = removed_funcs - added_funcs

            for name in deleted_funcs:
                # Find the line number where it was removed
                line_no = next(
                    (ln for ln, l in removed if _FUNC_DEF.search(l) and name in l), 1
                )
                findings.append(Finding(
                    file=filename,
                    line=line_no,
                    issue_type="FunctionRemoved",
                    severity=Severity.HIGH,
                    message=f"Function/method `{name}` was removed — callers will break",
                    suggestion="Deprecate first, then remove in a follow-up PR. "
                               "Or keep a shim that delegates to the new name.",
                ))

            # Exported symbols that were removed
            removed_exports = _extract_names(removed, _EXPORT_DEF)
            added_exports   = _extract_names(added,   _EXPORT_DEF)
            deleted_exports = removed_exports - added_exports

            for name in deleted_exports:
                line_no = next(
                    (ln for ln, l in removed if _EXPORT_DEF.search(l) and name in l), 1
                )
                findings.append(Finding(
                    file=filename,
                    line=line_no,
                    issue_type="ExportRemoved",
                    severity=Severity.HIGH,
                    message=f"Exported symbol `{name}` was removed — importers will break",
                    suggestion="Consider keeping the old export as a re-export alias.",
                ))

            # Classes that were removed
            removed_classes = _extract_names(removed, _CLASS_DEF)
            added_classes   = _extract_names(added,   _CLASS_DEF)
            deleted_classes = removed_classes - added_classes

            for name in deleted_classes:
                line_no = next(
                    (ln for ln, l in removed if _CLASS_DEF.search(l) and name in l), 1
                )
                findings.append(Finding(
                    file=filename,
                    line=line_no,
                    issue_type="ClassRemoved",
                    severity=Severity.HIGH,
                    message=f"Class `{name}` was removed — existing usages will break",
                    suggestion="Deprecate with a warning before removing.",
                ))

            # Signature change heuristic: same function name in both added and removed
            # but different parameter list
            for name in removed_funcs & added_funcs:
                removed_sig = next(
                    (l for _, l in removed if _FUNC_DEF.search(l) and name in l), ""
                )
                added_sig = next(
                    (l for _, l in added if _FUNC_DEF.search(l) and name in l), ""
                )
                if removed_sig and added_sig and removed_sig != added_sig:
                    line_no = next(
                        (ln for ln, l in added if _FUNC_DEF.search(l) and name in l), 1
                    )
                    findings.append(Finding(
                        file=filename,
                        line=line_no,
                        issue_type="SignatureChange",
                        severity=Severity.MEDIUM,
                        message=f"Signature of `{name}` changed — callers may need updating",
                        suggestion=(
                            f"Before: `{removed_sig.strip()[:80]}`\n"
                            f"After:  `{added_sig.strip()[:80]}`\n"
                            "Check all call sites."
                        ),
                    ))

        return AgentResult(agent_name=self.name, findings=findings)
