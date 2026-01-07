"""Shared test fixtures."""

import pytest
import respx


@pytest.fixture
def mock_github_api():
    """Fixture providing a respx mock router for GitHub API."""
    with respx.mock(base_url="https://api.github.com") as respx_mock:
        yield respx_mock


@pytest.fixture
def sample_pr_response():
    """Sample PR API response."""
    return {
        "number": 123,
        "title": "Test PR",
        "state": "open",
        "merged": False,
        "draft": False,
        "user": {"login": "testuser", "id": 1},
        "head": {"sha": "abc123def456"},
        "labels": [{"name": "bug", "color": "ff0000"}],
        "assignees": [{"login": "reviewer", "id": 2}],
        "comments": 5,
        "updated_at": "2025-01-07T12:00:00Z",
    }


@pytest.fixture
def sample_reviews_response():
    """Sample reviews API response."""
    return [
        {
            "id": 1,
            "user": {"login": "reviewer1"},
            "state": "APPROVED",
            "submitted_at": "2025-01-07T10:00:00Z",
        },
        {
            "id": 2,
            "user": {"login": "reviewer2"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2025-01-07T11:00:00Z",
        },
    ]


@pytest.fixture
def sample_commit_status_response():
    """Sample commit status API response."""
    return {
        "state": "pending",
        "statuses": [],
        "sha": "abc123def456",
        "total_count": 0,
    }


@pytest.fixture
def sample_check_runs_response():
    """Sample check runs API response."""
    return {
        "total_count": 2,
        "check_runs": [
            {
                "id": 1,
                "name": "build",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/owner/repo/runs/1",
            },
            {
                "id": 2,
                "name": "test",
                "status": "in_progress",
                "conclusion": None,
                "html_url": "https://github.com/owner/repo/runs/2",
            },
        ],
    }


@pytest.fixture
def sample_check_runs_complete_response():
    """Sample check runs API response with all checks complete."""
    return {
        "total_count": 2,
        "check_runs": [
            {
                "id": 1,
                "name": "build",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/owner/repo/runs/1",
            },
            {
                "id": 2,
                "name": "test",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/owner/repo/runs/2",
            },
        ],
    }


@pytest.fixture
def merged_pr_response(sample_pr_response):
    """Sample merged PR response."""
    return {
        **sample_pr_response,
        "state": "closed",
        "merged": True,
    }


@pytest.fixture
def closed_pr_response(sample_pr_response):
    """Sample closed (not merged) PR response."""
    return {
        **sample_pr_response,
        "state": "closed",
        "merged": False,
    }
