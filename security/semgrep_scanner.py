"""
SemgrepScanner — runs semgrep as a subprocess on PR file content.

Uses the `p/secrets` ruleset by default (no internet needed after first download).
Falls back gracefully if semgrep is not installed.

Flow per changed file:
  1. Reconstruct "new" file content from the patch (added + context lines)
  2. Write to a temp file with the correct extension
  3. Run: semgrep --config=p/secrets --json --quiet <tempfile>
  4. Parse JSON output and map line numbers back to original PR positions
  5. Return structured findings
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger()

# Semgrep rulesets to run (can be extended)
_SEMGREP_CONFIGS = [
    "p/secrets",       # leaked credentials, tokens, keys
    "p/security-audit", # broad security audit
]

# Extensions semgrep handles well
_SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rb", ".php", ".cs",
    ".yaml", ".yml", ".json", ".env",
}

_semgrep_available: Optional[bool] = None  # cached check


def _is_semgrep_available() -> bool:
    """Check once whether semgrep binary is on PATH."""
    global _semgrep_available
    if _semgrep_available is None:
        try:
            result = subprocess.run(
                ["semgrep", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            _semgrep_available = result.returncode == 0
            if _semgrep_available:
                log.info("semgrep.available", version=result.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            _semgrep_available = False
            log.warning("semgrep.not_found", hint="Install with: pip install semgrep")
    return _semgrep_available


def _reconstruct_content(patch: str) -> str:
    """
    Rebuild the new file content from a unified diff patch.
    Includes both context lines and added lines; skips removed lines.
    """
    lines = []
    for raw in patch.splitlines():
        if raw.startswith("@@"):
            continue          # hunk header
        elif raw.startswith("+"):
            lines.append(raw[1:])  # added line
        elif raw.startswith("-"):
            pass               # removed — not in new file
        else:
            lines.append(raw[1:] if raw.startswith(" ") else raw)  # context
    return "\n".join(lines)


def _severity_from_semgrep(extra: dict) -> str:
    """Map semgrep severity strings to our scale."""
    sev = extra.get("severity", "").upper()  # empty string → falls through to default
    return {
        "ERROR":   "CRITICAL",
        "WARNING": "HIGH",
        "INFO":    "MEDIUM",
    }.get(sev, "MEDIUM")


def run_semgrep_on_file(filename: str, patch: str) -> list[dict]:
    """
    Run semgrep on the reconstructed content of a single changed file.

    Returns a list of dicts:
        {
          "line":       int,
          "rule_id":    str,
          "message":    str,
          "severity":   str,   # CRITICAL / HIGH / MEDIUM / LOW
          "fix":        str,   # suggested fix (if provided by rule)
        }
    """
    if not _is_semgrep_available():
        return []

    ext = Path(filename).suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        return []

    content = _reconstruct_content(patch)
    if not content.strip():
        return []

    findings = []

    # Write content to a named temp file with the right extension
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=ext,
        prefix="pr_review_",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        for config in _SEMGREP_CONFIGS:
            try:
                result = subprocess.run(
                    [
                        "semgrep",
                        f"--config={config}",
                        "--json",
                        "--quiet",
                        "--no-git-ignore",
                        "--disable-version-check",
                        tmp_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                # semgrep returns 0 (no findings) or 1 (findings found)
                if result.returncode not in (0, 1):
                    log.warning(
                        "semgrep.nonzero_exit",
                        config=config, code=result.returncode,
                        stderr=result.stderr[:200],
                    )
                    continue

                if not result.stdout.strip():
                    continue

                data = json.loads(result.stdout)

                for item in data.get("results", []):
                    start = item.get("start", {})
                    extra = item.get("extra", {})
                    fix_text = extra.get("fix", "") or ""

                    findings.append({
                        "line":     start.get("line", 0),
                        "rule_id":  item.get("check_id", "semgrep"),
                        "message":  extra.get("message", "Security issue detected by semgrep"),
                        "severity": _severity_from_semgrep(extra),
                        "fix":      fix_text[:300] if fix_text else "",
                    })

            except json.JSONDecodeError as exc:
                log.warning("semgrep.json_parse_error", config=config, error=str(exc))
            except subprocess.TimeoutExpired:
                log.warning("semgrep.timeout", config=config, file=filename)

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Deduplicate by (line, rule_id)
    seen = set()
    deduped = []
    for f in findings:
        key = (f["line"], f["rule_id"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    log.debug("semgrep.done", file=filename, findings=len(deduped))
    return deduped
