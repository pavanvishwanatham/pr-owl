"""
Base classes shared by all agents.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):  # str mixin makes it behave like StrEnum on Python 3.9
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"


@dataclass
class Finding:
    file:       str
    line:       int
    issue_type: str
    severity:   Severity
    message:    str
    suggestion: str = ""


@dataclass
class AgentResult:
    agent_name: str
    findings:   list[Finding] = field(default_factory=list)
    summary:    str = ""       # free-form markdown (used by AI agents)
    error:      str = ""       # non-empty if the agent failed


class BaseAgent(ABC):
    name: str = "BaseAgent"

    @abstractmethod
    async def analyze(
        self,
        pr_data: dict,
        diff: str,
        files: list[dict],
    ) -> AgentResult:
        """
        Analyse the PR and return findings.

        Args:
            pr_data: PR metadata dict from GitHub API
            diff:    Full unified diff string
            files:   List of file dicts with keys: filename, status, patch, additions, deletions
        """
        ...
