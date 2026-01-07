"""URL parsing utilities for GitHub PR URLs."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Regex pattern for GitHub PR URLs
GITHUB_PR_PATTERN = re.compile(
    r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?$"
)


@dataclass(frozen=True)
class PRReference:
    """Immutable reference to a GitHub PR."""

    owner: str
    repo: str
    number: int

    @property
    def api_base(self) -> str:
        """Return the base API URL for this PR's repository."""
        return f"https://api.github.com/repos/{self.owner}/{self.repo}"


def parse_pr_url(url: str) -> PRReference:
    """
    Parse a GitHub PR URL into its components.

    Args:
        url: A GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)

    Returns:
        PRReference with owner, repo, and PR number

    Raises:
        ValueError: If URL is not a valid GitHub PR URL
    """
    parsed = urlparse(url)

    # Validate host
    if parsed.netloc not in ("github.com", "www.github.com"):
        raise ValueError(f"Not a GitHub URL: {url}")

    # Match path pattern
    match = GITHUB_PR_PATTERN.match(parsed.path)
    if not match:
        raise ValueError(f"Not a valid PR URL format: {url}")

    return PRReference(
        owner=match.group("owner"),
        repo=match.group("repo"),
        number=int(match.group("number")),
    )
