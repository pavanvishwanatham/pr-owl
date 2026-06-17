"""
DependencyRiskAgent — analyses changes to dependency manifests.

Checks:
  - package.json, requirements.txt, pyproject.toml, pom.xml, build.gradle
  - Major version upgrades (high risk)
  - Lock file changes without manifest change (suspicious)
  - Known dangerous patterns (wildcard versions, git deps)
"""
import re
from agents.base_agent import BaseAgent, AgentResult, Finding, Severity
from parsers.diff_parser import get_added_lines, get_removed_lines


_DEP_FILES = {
    "package.json", "requirements.txt", "pyproject.toml",
    "pom.xml", "build.gradle", "go.mod", "Gemfile",
}
_LOCK_FILES = {
    "package-lock.json", "yarn.lock", "poetry.lock",
    "Pipfile.lock", "go.sum", "Gemfile.lock",
}

# package.json version pattern: "some-pkg": "^1.2.3"
_PKG_JSON_DEP = re.compile(r'"([\w@/-]+)"\s*:\s*"([^"]+)"')
# requirements.txt: pkg==1.2.3 or pkg>=1.0
_REQUIREMENTS  = re.compile(r"^([\w-]+)\s*([=><~!]+)\s*([\d.]+)")
# pom.xml: <version>1.2.3-SNAPSHOT</version>  (capture any version string)
_POM_VERSION   = re.compile(r"<version>([^<]+)</version>")


def _is_major_upgrade(old_ver: str, new_ver: str) -> bool:
    """Return True if the major version number increased."""
    try:
        old_major = int(old_ver.lstrip("^~>=").split(".")[0])
        new_major = int(new_ver.lstrip("^~>=").split(".")[0])
        return new_major > old_major
    except (ValueError, IndexError):
        return False


class DependencyRiskAgent(BaseAgent):
    name = "DependencyRiskAgent"

    async def analyze(self, pr_data: dict, diff: str, files: list[dict]) -> AgentResult:
        findings: list[Finding] = []
        changed_dep_files   = [f for f in files if f["filename"].split("/")[-1] in _DEP_FILES]
        changed_lock_files  = [f for f in files if f["filename"].split("/")[-1] in _LOCK_FILES]

        # Lock file changed without manifest? Could be a manual tamper.
        if changed_lock_files and not changed_dep_files:
            for lf in changed_lock_files:
                findings.append(Finding(
                    file=lf["filename"],
                    line=1,
                    issue_type="LockFileTampered",
                    severity=Severity.HIGH,
                    message="Lock file changed without corresponding manifest change — possible manual edit",
                    suggestion="Regenerate the lock file via npm install / pip-compile / poetry lock.",
                ))

        for file in changed_dep_files:
            filename = file["filename"]
            patch = file.get("patch", "")
            if not patch:
                continue

            added   = get_added_lines(patch)
            removed = get_removed_lines(patch)

            basename = filename.split("/")[-1]

            if basename == "package.json":
                findings.extend(self._check_package_json(filename, added, removed))
            elif basename == "requirements.txt":
                findings.extend(self._check_requirements(filename, added, removed))
            elif basename in ("pom.xml", "build.gradle"):
                findings.extend(self._check_jvm(filename, added))

        return AgentResult(agent_name=self.name, findings=findings)

    def _check_package_json(self, filename, added, removed) -> list[Finding]:
        findings = []
        added_deps   = {m.group(1): m.group(2) for _, l in added   for m in [_PKG_JSON_DEP.search(l)] if m}
        removed_deps = {m.group(1): m.group(2) for _, l in removed for m in [_PKG_JSON_DEP.search(l)] if m}

        for pkg, new_ver in added_deps.items():
            old_ver = removed_deps.get(pkg)

            # Wildcard version
            if new_ver in ("*", "latest", "x"):
                findings.append(Finding(
                    file=filename, line=1,
                    issue_type="WildcardDependency", severity=Severity.HIGH,
                    message=f"`{pkg}` pinned to `{new_ver}` — unpredictable builds",
                    suggestion=f"Pin to a specific version e.g. `^{new_ver}` → `1.2.3`",
                ))
            # Git dependency
            elif new_ver.startswith(("git+", "github:", "gitlab:")):
                findings.append(Finding(
                    file=filename, line=1,
                    issue_type="GitDependency", severity=Severity.MEDIUM,
                    message=f"`{pkg}` depends on a git URL — not reproducible",
                    suggestion="Publish the dependency to npm and reference by version.",
                ))
            # Major upgrade
            elif old_ver and _is_major_upgrade(old_ver, new_ver):
                findings.append(Finding(
                    file=filename, line=1,
                    issue_type="MajorVersionUpgrade", severity=Severity.MEDIUM,
                    message=f"`{pkg}` upgraded from `{old_ver}` → `{new_ver}` (major bump)",
                    suggestion="Review changelog for breaking changes. Run full test suite.",
                ))

        return findings

    def _check_requirements(self, filename, added, removed) -> list[Finding]:
        findings = []
        for line_no, line in added:
            m = _REQUIREMENTS.match(line.strip())
            if not m:
                continue
            pkg, op, new_ver = m.group(1), m.group(2), m.group(3)

            # Find old version in removed lines
            old_ver = None
            for _, rline in removed:
                rm = _REQUIREMENTS.match(rline.strip())
                if rm and rm.group(1) == pkg:
                    old_ver = rm.group(3)
                    break

            if old_ver and _is_major_upgrade(old_ver, new_ver):
                findings.append(Finding(
                    file=filename, line=line_no,
                    issue_type="MajorVersionUpgrade", severity=Severity.MEDIUM,
                    message=f"`{pkg}` upgraded {old_ver} → {new_ver} (major bump)",
                    suggestion="Review release notes and run full test suite.",
                ))

            if op in ("", ">=") and "==" not in line:
                findings.append(Finding(
                    file=filename, line=line_no,
                    issue_type="UnpinnedDependency", severity=Severity.LOW,
                    message=f"`{pkg}` is not pinned to an exact version",
                    suggestion=f"Pin to `{pkg}=={new_ver}` for reproducible builds.",
                ))

        return findings

    def _check_jvm(self, filename, added) -> list[Finding]:
        findings = []
        for line_no, line in added:
            m = _POM_VERSION.search(line)
            if m:
                ver = m.group(1)
                if ver.endswith("-SNAPSHOT"):
                    findings.append(Finding(
                        file=filename, line=line_no,
                        issue_type="SnapshotDependency", severity=Severity.MEDIUM,
                        message=f"SNAPSHOT dependency `{ver}` — not suitable for production",
                        suggestion="Use a released version instead of SNAPSHOT.",
                    ))
        return findings
