"""Tests for GitHub API client."""

import os
from datetime import UTC
from unittest.mock import patch

import pytest
from httpx import Response

from github_pr_mcp.client import (
    GitHubAPIError,
    GitHubClient,
    RateLimitError,
)
from github_pr_mcp.models import CombinedStatus, PRState, ReviewState
from github_pr_mcp.parser import PRReference


class TestGitHubClientInit:
    """Tests for GitHubClient initialization."""

    def test_init_with_token(self):
        """Test client initialization with explicit token."""
        client = GitHubClient(token="test-token")
        assert client.token == "test-token"
        assert client.is_authenticated is True

    def test_init_from_env(self):
        """Test client initialization from environment variable."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}):
            client = GitHubClient()
            assert client.token == "env-token"
            assert client.is_authenticated is True

    def test_init_no_token(self):
        """Test client initialization without token."""
        with patch.dict(os.environ, {}, clear=True):
            # Make sure GITHUB_TOKEN is not in env
            os.environ.pop("GITHUB_TOKEN", None)
            client = GitHubClient(token=None)
            assert client.token is None
            assert client.is_authenticated is False

    def test_headers_with_auth(self):
        """Test headers include authorization when token present."""
        client = GitHubClient(token="test-token")
        assert "Authorization" in client.headers
        assert client.headers["Authorization"] == "Bearer test-token"

    def test_headers_without_auth(self):
        """Test headers without authorization when no token."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GITHUB_TOKEN", None)
            client = GitHubClient(token=None)
            assert "Authorization" not in client.headers


class TestGitHubClientContextManager:
    """Tests for GitHubClient async context manager."""

    async def test_context_manager(self, mock_github_api):
        """Test async context manager properly initializes and closes client."""
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(200, json={"number": 123})
        )

        async with GitHubClient(token="test") as client:
            assert client._client is not None
            result = await client.get_pr(PRReference("owner", "repo", 123))
            assert result["number"] == 123

    async def test_request_without_context_manager(self):
        """Test that request fails if client not initialized."""
        client = GitHubClient(token="test")
        with pytest.raises(RuntimeError, match="Client not initialized"):
            await client._request("GET", "/test")


class TestGitHubClientGetPR:
    """Tests for get_pr method."""

    async def test_get_pr_success(self, mock_github_api, sample_pr_response):
        """Test successful PR fetch."""
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(200, json=sample_pr_response)
        )

        async with GitHubClient(token="test") as client:
            result = await client.get_pr(PRReference("owner", "repo", 123))

        assert result["number"] == 123
        assert result["title"] == "Test PR"

    async def test_get_pr_not_found(self, mock_github_api):
        """Test 404 error handling."""
        mock_github_api.get("/repos/owner/repo/pulls/999").mock(
            return_value=Response(404, json={"message": "Not Found"})
        )

        async with GitHubClient(token="test") as client:
            with pytest.raises(GitHubAPIError) as exc_info:
                await client.get_pr(PRReference("owner", "repo", 999))

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value).lower()


class TestGitHubClientRateLimit:
    """Tests for rate limit handling."""

    async def test_rate_limit_error(self, mock_github_api):
        """Test rate limit error is raised with reset time."""
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(
                403,
                headers={
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": "1704672000",
                },
            )
        )

        async with GitHubClient(token="test") as client:
            with pytest.raises(RateLimitError) as exc_info:
                await client.get_pr(PRReference("owner", "repo", 123))

        assert exc_info.value.reset_time == 1704672000
        assert exc_info.value.status_code == 403

    async def test_403_not_rate_limit(self, mock_github_api):
        """Test 403 without rate limit headers raises generic error."""
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(
                403,
                headers={"x-ratelimit-remaining": "100"},
                json={"message": "Forbidden"},
            )
        )

        async with GitHubClient(token="test") as client:
            with pytest.raises(GitHubAPIError) as exc_info:
                await client.get_pr(PRReference("owner", "repo", 123))

        assert exc_info.value.status_code == 403
        # Should not be RateLimitError
        assert not isinstance(exc_info.value, RateLimitError)


class TestGitHubClientGetReviews:
    """Tests for get_reviews method."""

    async def test_get_reviews_success(self, mock_github_api, sample_reviews_response):
        """Test successful reviews fetch."""
        mock_github_api.get("/repos/owner/repo/pulls/123/reviews").mock(
            return_value=Response(200, json=sample_reviews_response)
        )

        async with GitHubClient(token="test") as client:
            result = await client.get_reviews(PRReference("owner", "repo", 123))

        assert len(result) == 2
        assert result[0]["state"] == "APPROVED"

    async def test_get_reviews_pagination(self, mock_github_api):
        """Test reviews pagination."""
        # First page: 100 reviews
        page1 = [
            {"id": i, "user": {"login": f"user{i}"}, "state": "APPROVED"}
            for i in range(100)
        ]
        # Second page: 50 reviews
        page2 = [
            {"id": i + 100, "user": {"login": f"user{i + 100}"}, "state": "APPROVED"}
            for i in range(50)
        ]

        mock_github_api.get("/repos/owner/repo/pulls/123/reviews").mock(
            side_effect=[
                Response(200, json=page1),
                Response(200, json=page2),
            ]
        )

        async with GitHubClient(token="test") as client:
            result = await client.get_reviews(PRReference("owner", "repo", 123))

        assert len(result) == 150

    async def test_get_reviews_empty(self, mock_github_api):
        """Test empty reviews response."""
        mock_github_api.get("/repos/owner/repo/pulls/123/reviews").mock(
            return_value=Response(200, json=[])
        )

        async with GitHubClient(token="test") as client:
            result = await client.get_reviews(PRReference("owner", "repo", 123))

        assert result == []


class TestGitHubClientGetCommitStatus:
    """Tests for get_commit_status method."""

    async def test_get_commit_status_success(
        self, mock_github_api, sample_commit_status_response
    ):
        """Test successful commit status fetch."""
        mock_github_api.get("/repos/owner/repo/commits/abc123/status").mock(
            return_value=Response(200, json=sample_commit_status_response)
        )

        async with GitHubClient(token="test") as client:
            result = await client.get_commit_status(
                PRReference("owner", "repo", 123), "abc123"
            )

        assert result["state"] == "pending"


class TestGitHubClientGetCheckRuns:
    """Tests for get_check_runs method."""

    async def test_get_check_runs_success(
        self, mock_github_api, sample_check_runs_response
    ):
        """Test successful check runs fetch."""
        mock_github_api.get("/repos/owner/repo/commits/abc123/check-runs").mock(
            return_value=Response(200, json=sample_check_runs_response)
        )

        async with GitHubClient(token="test") as client:
            result = await client.get_check_runs(
                PRReference("owner", "repo", 123), "abc123"
            )

        assert len(result) == 2
        assert result[0]["name"] == "build"

    async def test_get_check_runs_pagination(self, mock_github_api):
        """Test check runs pagination."""
        page1 = {
            "total_count": 150,
            "check_runs": [
                {
                    "id": i,
                    "name": f"check{i}",
                    "status": "completed",
                    "conclusion": "success",
                }
                for i in range(100)
            ],
        }
        page2 = {
            "total_count": 150,
            "check_runs": [
                {
                    "id": i + 100,
                    "name": f"check{i + 100}",
                    "status": "completed",
                    "conclusion": "success",
                }
                for i in range(50)
            ],
        }

        mock_github_api.get("/repos/owner/repo/commits/abc123/check-runs").mock(
            side_effect=[
                Response(200, json=page1),
                Response(200, json=page2),
            ]
        )

        async with GitHubClient(token="test") as client:
            result = await client.get_check_runs(
                PRReference("owner", "repo", 123), "abc123"
            )

        assert len(result) == 150


class TestGitHubClientGetPRStatus:
    """Tests for get_pr_status method."""

    async def test_get_pr_status_success(
        self,
        mock_github_api,
        sample_pr_response,
        sample_reviews_response,
        sample_commit_status_response,
        sample_check_runs_response,
    ):
        """Test successful PR status aggregation."""
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(200, json=sample_pr_response)
        )
        mock_github_api.get("/repos/owner/repo/pulls/123/reviews").mock(
            return_value=Response(200, json=sample_reviews_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/status").mock(
            return_value=Response(200, json=sample_commit_status_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/check-runs").mock(
            return_value=Response(200, json=sample_check_runs_response)
        )

        async with GitHubClient(token="test") as client:
            status = await client.get_pr_status(PRReference("owner", "repo", 123))

        assert status.number == 123
        assert status.title == "Test PR"
        assert status.author.login == "testuser"
        assert status.state == PRState.OPEN
        assert status.is_merged is False
        assert status.combined_commit_status == CombinedStatus.PENDING
        assert len(status.check_runs) == 2
        assert status.all_checks_complete is False  # One check is in_progress
        assert len(status.reviews) == 2
        assert status.review_decision == "CHANGES_REQUESTED"
        assert len(status.labels) == 1
        assert status.labels[0].name == "bug"
        assert len(status.assignees) == 1
        assert status.comment_count == 5


class TestComputeReviewDecision:
    """Tests for _compute_review_decision method."""

    def test_no_reviews(self):
        """Test no review decision when no reviews."""
        client = GitHubClient(token="test")
        result = client._compute_review_decision([])
        assert result is None

    def test_all_approved(self):
        """Test approved when all reviewers approved."""
        from datetime import datetime

        from github_pr_mcp.models import Review

        client = GitHubClient(token="test")
        reviews = [
            Review(
                id=1,
                user_login="reviewer1",
                state=ReviewState.APPROVED,
                submitted_at=datetime.now(UTC),
            ),
            Review(
                id=2,
                user_login="reviewer2",
                state=ReviewState.APPROVED,
                submitted_at=datetime.now(UTC),
            ),
        ]
        result = client._compute_review_decision(reviews)
        assert result == "APPROVED"

    def test_changes_requested_takes_precedence(self):
        """Test changes requested takes precedence over approvals."""
        from datetime import datetime

        from github_pr_mcp.models import Review

        client = GitHubClient(token="test")
        reviews = [
            Review(
                id=1,
                user_login="reviewer1",
                state=ReviewState.APPROVED,
                submitted_at=datetime.now(UTC),
            ),
            Review(
                id=2,
                user_login="reviewer2",
                state=ReviewState.CHANGES_REQUESTED,
                submitted_at=datetime.now(UTC),
            ),
        ]
        result = client._compute_review_decision(reviews)
        assert result == "CHANGES_REQUESTED"

    def test_only_comments_ignored(self):
        """Test that comment-only reviews are ignored."""
        from datetime import datetime

        from github_pr_mcp.models import Review

        client = GitHubClient(token="test")
        reviews = [
            Review(
                id=1,
                user_login="reviewer1",
                state=ReviewState.COMMENTED,
                submitted_at=datetime.now(UTC),
            ),
        ]
        result = client._compute_review_decision(reviews)
        assert result is None

    def test_latest_review_wins(self):
        """Test that latest review per user wins."""
        from datetime import datetime, timedelta

        from github_pr_mcp.models import Review

        client = GitHubClient(token="test")
        now = datetime.now(UTC)
        reviews = [
            Review(
                id=1,
                user_login="reviewer1",
                state=ReviewState.CHANGES_REQUESTED,
                submitted_at=now - timedelta(hours=1),
            ),
            Review(
                id=2,
                user_login="reviewer1",
                state=ReviewState.APPROVED,
                submitted_at=now,  # Later review
            ),
        ]
        result = client._compute_review_decision(reviews)
        assert result == "APPROVED"

    def test_review_without_timestamp(self):
        """Test handling reviews without submitted_at timestamp."""
        from github_pr_mcp.models import Review

        client = GitHubClient(token="test")
        reviews = [
            Review(
                id=1,
                user_login="reviewer1",
                state=ReviewState.APPROVED,
                submitted_at=None,
            ),
        ]
        result = client._compute_review_decision(reviews)
        assert result == "APPROVED"

    def test_mixed_review_states_returns_none(self):
        """Test mixed review states (e.g. one approved, one only commented)."""
        from datetime import datetime

        from github_pr_mcp.models import Review

        client = GitHubClient(token="test")
        # One approved, one pending
        # (no APPROVED or CHANGES_REQUESTED from second reviewer)
        reviews = [
            Review(
                id=1,
                user_login="reviewer1",
                state=ReviewState.APPROVED,
                submitted_at=datetime.now(UTC),
            ),
            Review(
                id=2,
                user_login="reviewer2",
                state=ReviewState.PENDING,  # Pending review - not counted
                submitted_at=datetime.now(UTC),
            ),
        ]
        # Should still return APPROVED since pending reviews are ignored
        result = client._compute_review_decision(reviews)
        assert result == "APPROVED"

    def test_dismissed_review_ignored(self):
        """Test that dismissed reviews are ignored in decision."""
        from datetime import datetime

        from github_pr_mcp.models import Review

        client = GitHubClient(token="test")
        reviews = [
            Review(
                id=1,
                user_login="reviewer1",
                state=ReviewState.DISMISSED,
                submitted_at=datetime.now(UTC),
            ),
        ]
        result = client._compute_review_decision(reviews)
        assert result is None
