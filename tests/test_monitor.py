"""Integration tests for the monitor_pr tool."""

from datetime import UTC
from unittest.mock import AsyncMock, patch

import pytest
from httpx import Response

from main import monitor_pr_impl


class MockProgress:
    """Mock Progress dependency for testing."""

    def __init__(self):
        self.total = None
        self.messages = []
        self.progress = 0

    async def set_total(self, total: int) -> None:
        self.total = total

    async def set_message(self, message: str) -> None:
        self.messages.append(message)

    async def increment(self, amount: int = 1) -> None:
        self.progress += amount


@pytest.fixture
def mock_progress():
    """Fixture providing a mock Progress object."""
    return MockProgress()


@pytest.fixture
def complete_pr_mocks(
    sample_pr_response,
    sample_reviews_response,
    sample_commit_status_response,
    sample_check_runs_complete_response,
):
    """Fixture providing all mocked responses for a complete PR check."""
    return {
        "pr": sample_pr_response,
        "reviews": sample_reviews_response,
        "status": sample_commit_status_response,
        "checks": sample_check_runs_complete_response,
    }


class TestMonitorPRInvalidInput:
    """Tests for invalid input handling."""

    async def test_invalid_url(self, mock_progress):
        """Test handling of invalid URL."""
        result = await monitor_pr_impl(
            pr_url="https://gitlab.com/owner/repo/pull/123",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,
            progress=mock_progress,
        )

        assert result["success"] is False
        assert "error" in result
        assert "Not a GitHub URL" in result["error"]

    async def test_invalid_pr_path(self, mock_progress):
        """Test handling of invalid PR path."""
        result = await monitor_pr_impl(
            pr_url="https://github.com/owner/repo/issues/123",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,
            progress=mock_progress,
        )

        assert result["success"] is False
        assert "error" in result
        assert "Not a valid PR URL" in result["error"]


class TestMonitorPRMerged:
    """Tests for merged PR detection."""

    async def test_pr_merged(
        self,
        mock_github_api,
        mock_progress,
        merged_pr_response,
        sample_reviews_response,
        sample_commit_status_response,
        sample_check_runs_complete_response,
    ):
        """Test that merged PR is detected immediately."""
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(200, json=merged_pr_response)
        )
        mock_github_api.get("/repos/owner/repo/pulls/123/reviews").mock(
            return_value=Response(200, json=sample_reviews_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/status").mock(
            return_value=Response(200, json=sample_commit_status_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/check-runs").mock(
            return_value=Response(200, json=sample_check_runs_complete_response)
        )

        result = await monitor_pr_impl(
            pr_url="https://github.com/owner/repo/pull/123",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,
            progress=mock_progress,
        )

        assert result["success"] is True
        assert result["reason"] == "merged"
        assert result["poll_count"] == 1
        assert "final_status" in result


class TestMonitorPRClosed:
    """Tests for closed PR detection."""

    async def test_pr_closed(
        self,
        mock_github_api,
        mock_progress,
        closed_pr_response,
        sample_reviews_response,
        sample_commit_status_response,
        sample_check_runs_complete_response,
    ):
        """Test that closed (not merged) PR is detected."""
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(200, json=closed_pr_response)
        )
        mock_github_api.get("/repos/owner/repo/pulls/123/reviews").mock(
            return_value=Response(200, json=sample_reviews_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/status").mock(
            return_value=Response(200, json=sample_commit_status_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/check-runs").mock(
            return_value=Response(200, json=sample_check_runs_complete_response)
        )

        result = await monitor_pr_impl(
            pr_url="https://github.com/owner/repo/pull/123",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,
            progress=mock_progress,
        )

        assert result["success"] is True
        assert result["reason"] == "closed"


class TestMonitorPRChecksComplete:
    """Tests for checks completion detection."""

    async def test_checks_complete(
        self,
        mock_github_api,
        mock_progress,
        sample_pr_response,
        sample_reviews_response,
        sample_commit_status_response,
        sample_check_runs_complete_response,
    ):
        """Test that completed checks are detected."""
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
            return_value=Response(200, json=sample_check_runs_complete_response)
        )

        result = await monitor_pr_impl(
            pr_url="https://github.com/owner/repo/pull/123",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,
            progress=mock_progress,
        )

        assert result["success"] is True
        assert result["reason"] == "checks_complete"
        assert result["checks_passed"] is True


class TestMonitorPRTimeout:
    """Tests for timeout handling."""

    async def test_timeout(
        self,
        mock_github_api,
        mock_progress,
        sample_pr_response,
        sample_reviews_response,
        sample_commit_status_response,
        sample_check_runs_response,  # Has incomplete checks
    ):
        """Test timeout when checks don't complete."""
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

        # Patch sleep to avoid waiting and patch time to simulate timeout
        with patch("main.asyncio.sleep", new_callable=AsyncMock):
            # After first poll, simulate timeout by patching datetime
            with patch("main.datetime") as mock_datetime:
                from datetime import datetime, timedelta

                start_time = datetime.now(UTC)
                # First call returns start time, subsequent calls return past timeout
                mock_datetime.now.side_effect = [
                    start_time,  # Initial start time
                    start_time,  # First poll elapsed check
                    start_time + timedelta(seconds=120),  # Second poll - timeout
                ]
                mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)

                result = await monitor_pr_impl(
                    pr_url="https://github.com/owner/repo/pull/123",
                    poll_interval_seconds=5.0,
                    max_timeout_seconds=60.0,
                    progress=mock_progress,
                )

        assert result["success"] is False
        assert result["reason"] == "timeout"
        assert "final_status" in result


class TestMonitorPRAPIError:
    """Tests for API error handling."""

    async def test_api_error(self, mock_github_api, mock_progress):
        """Test API error handling."""
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(500, json={"message": "Internal Server Error"})
        )

        result = await monitor_pr_impl(
            pr_url="https://github.com/owner/repo/pull/123",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,
            progress=mock_progress,
        )

        assert result["success"] is False
        assert result["reason"] == "api_error"
        assert result["status_code"] == 500

    async def test_not_found_error(self, mock_github_api, mock_progress):
        """Test 404 error handling."""
        mock_github_api.get("/repos/owner/repo/pulls/999").mock(
            return_value=Response(404, json={"message": "Not Found"})
        )

        result = await monitor_pr_impl(
            pr_url="https://github.com/owner/repo/pull/999",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,
            progress=mock_progress,
        )

        assert result["success"] is False
        assert result["reason"] == "api_error"
        assert result["status_code"] == 404


class TestMonitorPRRateLimit:
    """Tests for rate limit handling."""

    async def test_rate_limit_timeout(self, mock_github_api, mock_progress):
        """Test rate limit when reset exceeds timeout."""
        from datetime import datetime

        # 2 hours from now
        future_reset = int(datetime.now(UTC).timestamp()) + 7200

        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            return_value=Response(
                403,
                headers={
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": str(future_reset),
                },
            )
        )

        result = await monitor_pr_impl(
            pr_url="https://github.com/owner/repo/pull/123",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,  # Timeout is less than rate limit reset
            progress=mock_progress,
        )

        assert result["success"] is False
        assert result["reason"] == "rate_limit_timeout"

    async def test_rate_limit_recovery(
        self,
        mock_github_api,
        mock_progress,
        sample_pr_response,
        sample_reviews_response,
        sample_commit_status_response,
        sample_check_runs_complete_response,
    ):
        """Test recovery from rate limit when reset is within timeout."""
        from datetime import datetime

        # Rate limit resets in 5 seconds (within our 60s timeout)
        near_reset = int(datetime.now(UTC).timestamp()) + 5

        # First call hits rate limit, second call succeeds
        mock_github_api.get("/repos/owner/repo/pulls/123").mock(
            side_effect=[
                Response(
                    403,
                    headers={
                        "x-ratelimit-remaining": "0",
                        "x-ratelimit-reset": str(near_reset),
                    },
                ),
                Response(200, json=sample_pr_response),
            ]
        )
        mock_github_api.get("/repos/owner/repo/pulls/123/reviews").mock(
            return_value=Response(200, json=sample_reviews_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/status").mock(
            return_value=Response(200, json=sample_commit_status_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/check-runs").mock(
            return_value=Response(200, json=sample_check_runs_complete_response)
        )

        with patch("main.asyncio.sleep", new_callable=AsyncMock):
            result = await monitor_pr_impl(
                pr_url="https://github.com/owner/repo/pull/123",
                poll_interval_seconds=5.0,
                max_timeout_seconds=60.0,
                progress=mock_progress,
            )

        assert result["success"] is True
        assert result["reason"] == "checks_complete"
        # Should have logged rate limit message
        assert any("Rate limited" in msg for msg in mock_progress.messages)


class TestMonitorPRNetworkError:
    """Tests for network error handling."""

    async def test_network_error_recovery(
        self,
        mock_github_api,
        mock_progress,
        sample_pr_response,
        sample_reviews_response,
        sample_commit_status_response,
        sample_check_runs_complete_response,
    ):
        """Test recovery from network error."""
        import httpx

        # First call raises network error, second succeeds
        pr_route = mock_github_api.get("/repos/owner/repo/pulls/123")
        pr_route.mock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                Response(200, json=sample_pr_response),
            ]
        )
        mock_github_api.get("/repos/owner/repo/pulls/123/reviews").mock(
            return_value=Response(200, json=sample_reviews_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/status").mock(
            return_value=Response(200, json=sample_commit_status_response)
        )
        mock_github_api.get("/repos/owner/repo/commits/abc123def456/check-runs").mock(
            return_value=Response(200, json=sample_check_runs_complete_response)
        )

        with patch("main.asyncio.sleep", new_callable=AsyncMock):
            result = await monitor_pr_impl(
                pr_url="https://github.com/owner/repo/pull/123",
                poll_interval_seconds=5.0,
                max_timeout_seconds=60.0,
                progress=mock_progress,
            )

        assert result["success"] is True
        assert result["reason"] == "checks_complete"
        # Should have logged network error
        assert any("Network error" in msg for msg in mock_progress.messages)


class TestMonitorPRProgress:
    """Tests for progress reporting."""

    async def test_progress_reporting(
        self,
        mock_github_api,
        mock_progress,
        sample_pr_response,
        sample_reviews_response,
        sample_commit_status_response,
        sample_check_runs_complete_response,
    ):
        """Test that progress is reported correctly."""
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
            return_value=Response(200, json=sample_check_runs_complete_response)
        )

        await monitor_pr_impl(
            pr_url="https://github.com/owner/repo/pull/123",
            poll_interval_seconds=5.0,
            max_timeout_seconds=60.0,
            progress=mock_progress,
        )

        # Check total was set
        assert mock_progress.total == 12  # 60 / 5

        # Check messages were sent
        assert any("Starting monitor" in msg for msg in mock_progress.messages)
        assert any("Connected" in msg for msg in mock_progress.messages)
        assert any("Poll #1" in msg for msg in mock_progress.messages)

        # Check progress was incremented
        assert mock_progress.progress >= 1
