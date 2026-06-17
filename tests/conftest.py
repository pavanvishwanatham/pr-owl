"""
Shared test fixtures.
"""
import pytest


# ── PR data fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_pr_data():
    return {
        "number":        42,
        "title":         "feat: add payment retry logic",
        "body":          "Adds retry logic for failed payments using exponential backoff.",
        "state":         "open",
        "author":        "dev-user",
        "base":          {"ref": "main"},
        "head":          {"ref": "feat/payment-retry", "sha": "abc1234"},
        "additions":     120,
        "deletions":     30,
        "changed_files": 5,
        "labels":        [],
    }


@pytest.fixture
def sample_files():
    return [
        {
            "filename":  "src/payment/retry.py",
            "status":    "added",
            "additions": 80,
            "deletions": 0,
            "changes":   80,
            "patch": (
                "@@ -0,0 +1,10 @@\n"
                "+import os\n"
                "+\n"
                "+API_KEY = 'ghp_REDACTED_TEST_TOKEN_NOT_REAL'\n"
                "+\n"
                "+def process_payment(amount):\n"
                "+    # TODO: add currency support\n"
                "+    print('Processing payment:', amount)\n"
                "+    for i in range(3):\n"
                "+        for j in range(3):\n"
                "+            for k in range(3):\n"
            ),
        },
        {
            "filename":  "src/payment/models.py",
            "status":    "modified",
            "additions": 20,
            "deletions": 5,
            "changes":   25,
            "patch": (
                "@@ -10,5 +10,8 @@\n"
                " class PaymentModel:\n"
                "-    def process(self, amount):\n"
                "+    def process(self, amount, currency, retry_count=3):\n"
                "+        pass\n"
            ),
        },
    ]


@pytest.fixture
def sample_diff(sample_files):
    parts = []
    for f in sample_files:
        parts.append(f"diff --git a/{f['filename']} b/{f['filename']}")
        parts.append(f.get("patch", ""))
    return "\n".join(parts)


@pytest.fixture
def clean_files():
    """Files with no issues."""
    return [
        {
            "filename":  "src/utils/helpers.py",
            "status":    "modified",
            "additions": 10,
            "deletions": 2,
            "changes":   12,
            "patch": (
                "@@ -1,5 +1,8 @@\n"
                " def calculate_total(items: list[float]) -> float:\n"
                "+    if not items:\n"
                "+        return 0.0\n"
                "     return sum(items)\n"
            ),
        }
    ]
