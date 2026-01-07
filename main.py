"""FastMCP server for GitHub PR monitoring."""

import asyncio
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import Progress

from github_pr_mcp.client import GitHubAPIError, GitHubClient, RateLimitError
from github_pr_mcp.models import MonitoringConfig, PRStatus
from github_pr_mcp.parser import parse_pr_url

mcp = FastMCP("GitHub PR Monitor")


class ProgressReporter(Protocol):
    """Protocol for progress reporting."""

    async def set_total(self, total: int) -> None: ...
    async def set_message(self, message: str) -> None: ...
    async def increment(self, amount: int = 1) -> None: ...


async def monitor_pr_impl(
    pr_url: str,
    poll_interval_seconds: float,
    max_timeout_seconds: float,
    progress: ProgressReporter,
) -> dict[str, Any]:
    """
    Monitor a GitHub PR until it reaches a terminal state.

    Terminal states:
    - PR is merged
    - PR is closed
    - All CI checks complete (passed or failed)

    Args:
        pr_url: GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)
        poll_interval_seconds: Seconds between status checks (default: 30, min: 5)
        max_timeout_seconds: Maximum monitoring duration (default: 3600 = 1 hour)

    Returns:
        Final PR status including state, checks, reviews, and metadata.
    """
    # Validate configuration
    config = MonitoringConfig(
        poll_interval_seconds=max(5.0, poll_interval_seconds),
        max_timeout_seconds=max(60.0, max_timeout_seconds),
    )

    # Parse URL
    try:
        pr_ref = parse_pr_url(pr_url)
    except ValueError as e:
        return {"error": str(e), "success": False}

    # Setup progress reporting
    # Estimate max polls based on timeout
    estimated_polls = int(config.max_timeout_seconds / config.poll_interval_seconds)
    await progress.set_total(estimated_polls)
    await progress.set_message(
        f"Starting monitor for {pr_ref.owner}/{pr_ref.repo}#{pr_ref.number}"
    )

    start_time = datetime.now(UTC)
    poll_count = 0
    last_status: PRStatus | None = None

    async with GitHubClient() as client:
        # Log authentication status
        auth_status = "authenticated" if client.is_authenticated else "unauthenticated"
        await progress.set_message(f"Connected ({auth_status})")

        while True:
            poll_count += 1
            elapsed = (datetime.now(UTC) - start_time).total_seconds()

            # Check timeout
            if elapsed >= config.max_timeout_seconds:
                await progress.set_message("Timeout reached")
                return {
                    "success": False,
                    "reason": "timeout",
                    "elapsed_seconds": elapsed,
                    "poll_count": poll_count,
                    "final_status": last_status.model_dump() if last_status else None,
                }

            try:
                # Fetch current status
                status = await client.get_pr_status(pr_ref)
                last_status = status

                # Update progress
                await progress.increment()
                checks_status = "complete" if status.all_checks_complete else "pending"
                review_status = status.review_decision or "none"
                await progress.set_message(
                    f"Poll #{poll_count}: {status.state.value} | "
                    f"Checks: {checks_status} | "
                    f"Reviews: {review_status}"
                )

                # Check termination conditions
                if status.is_merged:
                    return {
                        "success": True,
                        "reason": "merged",
                        "elapsed_seconds": elapsed,
                        "poll_count": poll_count,
                        "final_status": status.model_dump(),
                    }

                if status.state.value == "closed":
                    return {
                        "success": True,
                        "reason": "closed",
                        "elapsed_seconds": elapsed,
                        "poll_count": poll_count,
                        "final_status": status.model_dump(),
                    }

                if status.all_checks_complete:
                    return {
                        "success": True,
                        "reason": "checks_complete",
                        "checks_passed": status.checks_passing,
                        "elapsed_seconds": elapsed,
                        "poll_count": poll_count,
                        "final_status": status.model_dump(),
                    }

            except RateLimitError as e:
                # Calculate wait time until reset
                wait_seconds = max(0, e.reset_time - int(datetime.now(UTC).timestamp()))
                await progress.set_message(f"Rate limited. Waiting {wait_seconds}s...")

                if wait_seconds > config.max_timeout_seconds - elapsed:
                    return {
                        "success": False,
                        "reason": "rate_limit_timeout",
                        "message": "Rate limit reset exceeds remaining timeout",
                        "final_status": (
                            last_status.model_dump() if last_status else None
                        ),
                    }

                await asyncio.sleep(min(wait_seconds + 1, 60))  # Cap at 60s increments
                continue

            except GitHubAPIError as e:
                return {
                    "success": False,
                    "reason": "api_error",
                    "error": str(e),
                    "status_code": e.status_code,
                    "final_status": last_status.model_dump() if last_status else None,
                }

            except httpx.RequestError as e:
                # Network error - retry after interval
                await progress.set_message(f"Network error: {e}. Retrying...")
                # Don't return, just wait and retry

            # Wait before next poll
            await asyncio.sleep(config.poll_interval_seconds)


@mcp.tool(task=True)
async def monitor_pr(
    pr_url: str,
    poll_interval_seconds: float = 30.0,
    max_timeout_seconds: float = 3600.0,
    progress: Progress = Progress(),
) -> dict[str, Any]:  # pragma: no cover
    """
    Monitor a GitHub PR until it reaches a terminal state.

    Terminal states:
    - PR is merged
    - PR is closed
    - All CI checks complete (passed or failed)

    Args:
        pr_url: GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)
        poll_interval_seconds: Seconds between status checks (default: 30, min: 5)
        max_timeout_seconds: Maximum monitoring duration (default: 3600 = 1 hour)

    Returns:
        Final PR status including state, checks, reviews, and metadata.
    """
    return await monitor_pr_impl(
        pr_url=pr_url,
        poll_interval_seconds=poll_interval_seconds,
        max_timeout_seconds=max_timeout_seconds,
        progress=progress,
    )


if __name__ == "__main__":
    mcp.run()
