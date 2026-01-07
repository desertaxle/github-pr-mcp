"""Async GitHub API client for PR monitoring."""

import asyncio
import os
from typing import Any

import httpx

from .models import (
    CheckConclusion,
    CheckRun,
    CheckStatus,
    CombinedStatus,
    Label,
    PRState,
    PRStatus,
    Review,
    ReviewState,
    User,
)
from .parser import PRReference


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(GitHubAPIError):
    """Raised when GitHub rate limit is exceeded."""

    def __init__(self, reset_time: int):
        super().__init__(f"Rate limit exceeded. Resets at {reset_time}", 403)
        self.reset_time = reset_time


class GitHubClient:
    """Async client for GitHub REST API."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self._client: httpx.AsyncClient | None = None

    @property
    def headers(self) -> dict[str, str]:
        """Return headers for API requests."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @property
    def is_authenticated(self) -> bool:
        """Check if client has authentication token."""
        return self.token is not None

    async def __aenter__(self) -> GitHubClient:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=self.headers,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an API request with error handling."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        response = await self._client.request(method, path, **kwargs)

        # Handle rate limiting
        if response.status_code == 403:
            remaining = response.headers.get("x-ratelimit-remaining", "0")
            if remaining == "0":
                reset_time = int(response.headers.get("x-ratelimit-reset", "0"))
                raise RateLimitError(reset_time)

        if response.status_code == 404:
            raise GitHubAPIError(f"Resource not found: {path}", 404)

        if response.status_code >= 400:
            raise GitHubAPIError(f"API error: {response.text}", response.status_code)

        return response.json()

    async def get_pr(self, ref: PRReference) -> dict[str, Any]:
        """Get pull request details."""
        return await self._request(
            "GET", f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"
        )

    async def get_reviews(self, ref: PRReference) -> list[dict[str, Any]]:
        """Get all reviews for a PR (handles pagination)."""
        reviews: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._request(
                "GET",
                f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/reviews",
                params={"per_page": 100, "page": page},
            )
            if not data:
                break
            reviews.extend(data)
            if len(data) < 100:
                break
            page += 1
        return reviews

    async def get_commit_status(self, ref: PRReference, sha: str) -> dict[str, Any]:
        """Get combined commit status for a SHA."""
        return await self._request(
            "GET", f"/repos/{ref.owner}/{ref.repo}/commits/{sha}/status"
        )

    async def get_check_runs(self, ref: PRReference, sha: str) -> list[dict[str, Any]]:
        """Get all check runs for a commit (handles pagination)."""
        check_runs: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._request(
                "GET",
                f"/repos/{ref.owner}/{ref.repo}/commits/{sha}/check-runs",
                params={"per_page": 100, "page": page},
            )
            runs = data.get("check_runs", [])
            check_runs.extend(runs)
            if len(runs) < 100:
                break
            page += 1
        return check_runs

    async def get_pr_status(self, ref: PRReference) -> PRStatus:
        """Fetch complete PR status by aggregating multiple API calls."""
        # Get PR details first (needed for head SHA)
        pr_data = await self.get_pr(ref)
        head_sha = pr_data["head"]["sha"]

        # Fetch additional data in parallel
        reviews_data, status_data, check_runs_data = await asyncio.gather(
            self.get_reviews(ref),
            self.get_commit_status(ref, head_sha),
            self.get_check_runs(ref, head_sha),
        )

        # Parse reviews
        reviews = [
            Review(
                id=r["id"],
                user_login=r["user"]["login"],
                state=ReviewState(r["state"]),
                submitted_at=r.get("submitted_at"),
            )
            for r in reviews_data
        ]

        # Determine review decision (most recent non-comment review per user)
        review_decision = self._compute_review_decision(reviews)

        # Parse check runs
        check_runs = [
            CheckRun(
                id=c["id"],
                name=c["name"],
                status=CheckStatus(c["status"]),
                conclusion=(
                    CheckConclusion(c["conclusion"]) if c.get("conclusion") else None
                ),
                html_url=c.get("html_url"),
            )
            for c in check_runs_data
        ]

        # Compute check status
        all_checks_complete = (
            all(cr.status == CheckStatus.COMPLETED for cr in check_runs)
            if check_runs
            else True
        )

        checks_passing = (
            all_checks_complete
            and all(
                cr.conclusion
                in (
                    CheckConclusion.SUCCESS,
                    CheckConclusion.SKIPPED,
                    CheckConclusion.NEUTRAL,
                )
                for cr in check_runs
            )
            if check_runs
            else True
        )

        # Combined status from legacy API
        combined_status = CombinedStatus(status_data.get("state", "pending"))

        return PRStatus(
            number=ref.number,
            title=pr_data["title"],
            author=User(login=pr_data["user"]["login"], id=pr_data["user"]["id"]),
            state=PRState(pr_data["state"]),
            is_merged=pr_data.get("merged", False),
            is_draft=pr_data.get("draft", False),
            combined_commit_status=combined_status,
            check_runs=check_runs,
            all_checks_complete=all_checks_complete,
            checks_passing=checks_passing,
            reviews=reviews,
            review_decision=review_decision,
            labels=[
                Label(name=label["name"], color=label.get("color"))
                for label in pr_data.get("labels", [])
            ],
            assignees=[
                User(login=a["login"], id=a["id"]) for a in pr_data.get("assignees", [])
            ],
            comment_count=pr_data.get("comments", 0),
            updated_at=pr_data["updated_at"],
        )

    def _compute_review_decision(self, reviews: list[Review]) -> str | None:
        """Compute overall review decision from individual reviews."""
        # Get most recent review per user (excluding COMMENTED and PENDING)
        user_reviews: dict[str, Review] = {}
        for review in reviews:
            if review.state in (ReviewState.APPROVED, ReviewState.CHANGES_REQUESTED):
                existing = user_reviews.get(review.user_login)
                if not existing or (
                    review.submitted_at
                    and existing.submitted_at
                    and review.submitted_at > existing.submitted_at
                ):
                    user_reviews[review.user_login] = review

        if not user_reviews:
            return None

        # If any reviewer requested changes, that takes precedence
        if any(r.state == ReviewState.CHANGES_REQUESTED for r in user_reviews.values()):
            return "CHANGES_REQUESTED"

        # All reviewers approved
        # (since user_reviews only contains APPROVED or CHANGES_REQUESTED)
        return "APPROVED"
