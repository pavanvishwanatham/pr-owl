"""
SecretScanner — detects secrets, tokens, and credentials in source lines.

Two detection strategies:
  1. Pattern matching — fast regex patterns for known credential formats
  2. Entropy analysis — flags high-entropy strings that look like random secrets
"""
import re
import math
from typing import Optional


# (pattern, type, high_confidence)
_PATTERNS: list[tuple[re.Pattern, str, bool]] = [
    # GitHub
    (re.compile(r"ghp_[0-9A-Za-z]{36}"),           "GitHubToken",     True),
    (re.compile(r"github_pat_[0-9A-Za-z_]{82}"),   "GitHubFineToken", True),
    # AWS
    (re.compile(r"AKIA[0-9A-Z]{16}"),              "AWSAccessKey",    True),
    (re.compile(r"(?i)aws[_\-]secret[_\-]access[_\-]key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})"),
                                                     "AWSSecretKey",    True),
    # Stripe keys  (must be before generic APIKey to avoid early-exit on api_key match)
    (re.compile(r"sk_live_[0-9A-Za-z]{24}"),        "StripeSecretKey", True),
    # Slack tokens
    (re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"), "SlackToken",      True),
    # Private keys
    (re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
                                                     "PrivateKey",      True),
    # Passwords in code
    (re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]([^'\"]{6,})['\"]"),
                                                     "HardcodedPassword", True),
    # Generic API keys / tokens
    (re.compile(r"(?i)(api[_\-]?key|apikey)\s*[=:]\s*['\"]([A-Za-z0-9_\-]{20,})['\"]?"),
                                                     "APIKey",          False),
    (re.compile(r"(?i)(access[_\-]?token|auth[_\-]?token)\s*[=:]\s*['\"]([A-Za-z0-9_.\-]{20,})['\"]?"),
                                                     "AccessToken",     False),
    # URLs with credentials
    (re.compile(r"[a-z]+://[^:@\s]+:[^@\s]{4,}@[a-zA-Z0-9.\-]+"),
                                                     "URLWithCredentials", True),
    # JWT tokens
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
                                                     "JWTToken",        False),
]

# Characters used in secret entropy analysis
_B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
_HEX_CHARS = "0123456789abcdefABCDEF"

# Strings to skip — common false positives
_SKIP_VALUES = {
    "example", "placeholder", "your_token_here", "changeme",
    "password", "secret", "mypassword", "test", "demo",
}

_STRING_RE = re.compile(r"""['"]([\w.+/=\-]{20,})['"]]?""")


def _entropy(s: str, charset: str) -> float:
    """Shannon entropy of string s over the given charset."""
    count = {c: 0 for c in charset}
    for c in s:
        if c in count:
            count[c] += 1
    length = sum(count.values())
    if length == 0:
        return 0.0
    return -sum(
        (n / length) * math.log2(n / length)
        for n in count.values()
        if n > 0
    )


def _is_high_entropy(value: str) -> Optional[str]:
    """Return the charset type if the value has suspiciously high entropy."""
    if len(value) < 20:
        return None
    if value.lower() in _SKIP_VALUES:
        return None

    b64_ent = _entropy(value, _B64_CHARS)
    hex_ent = _entropy(value, _HEX_CHARS)

    if b64_ent > 4.5 and all(c in _B64_CHARS for c in value):
        return "Base64"
    if hex_ent > 3.5 and all(c in _HEX_CHARS for c in value):
        return "Hex"
    return None


class SecretScanner:
    def scan_line(self, line: str) -> list[dict]:
        """
        Scan a single source line for secrets.
        Returns list of: {"type", "message", "high_confidence"}
        """
        hits = []

        # Pattern-based detection
        for pattern, secret_type, high_conf in _PATTERNS:
            if pattern.search(line):
                hits.append({
                    "type": secret_type,
                    "message": f"Possible {secret_type} detected in code",
                    "high_confidence": high_conf,
                })
                break  # one hit per line per scan pass

        # Entropy-based detection (only if no pattern match)
        if not hits:
            for m in _STRING_RE.finditer(line):
                value = m.group(1)
                charset = _is_high_entropy(value)
                if charset:
                    hits.append({
                        "type": "HighEntropySecret",
                        "message": f"High-entropy {charset} string detected — possible secret",
                        "high_confidence": False,
                    })
                    break

        return hits
