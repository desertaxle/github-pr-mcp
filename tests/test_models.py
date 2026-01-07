"""Tests for Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from github_pr_mcp.models import (
    CheckConclusion,
    CheckRun,
    CheckStatus,
    CombinedStatus,
    Label,
    MonitoringConfig,
    PRState,
    PRStatus,
    Review,
    ReviewState,
    User,
)


class TestEnums:
    """Tests for enum types."""

    def test_pr_state_values(self):
        """Test PRState enum values."""
        assert PRState.OPEN.value == "open"
        assert PRState.CLOSED.value == "closed"

    def test_review_state_values(self):
        """Test ReviewState enum values."""
        assert ReviewState.APPROVED.value == "APPROVED"
        assert ReviewState.CHANGES_REQUESTED.value == "CHANGES_REQUESTED"

    def test_check_status_values(self):
        """Test CheckStatus enum values."""
        assert CheckStatus.COMPLETED.value == "completed"
        assert CheckStatus.IN_PROGRESS.value == "in_progress"

    def test_check_conclusion_values(self):
        """Test CheckConclusion enum values."""
        assert CheckConclusion.SUCCESS.value == "success"
        assert CheckConclusion.FAILURE.value == "failure"

    def test_combined_status_values(self):
        """Test CombinedStatus enum values."""
        assert CombinedStatus.SUCCESS.value == "success"
        assert CombinedStatus.PENDING.value == "pending"
        assert CombinedStatus.FAILURE.value == "failure"


class TestCheckRun:
    """Tests for CheckRun model."""

    def test_basic_check_run(self):
        """Test creating a basic check run."""
        check = CheckRun(id=1, name="build", status=CheckStatus.COMPLETED)
        assert check.id == 1
        assert check.name == "build"
        assert check.status == CheckStatus.COMPLETED
        assert check.conclusion is None
        assert check.html_url is None

    def test_completed_check_run(self):
        """Test check run with conclusion."""
        check = CheckRun(
            id=1,
            name="test",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
            html_url="https://github.com/owner/repo/runs/1",
        )
        assert check.conclusion == CheckConclusion.SUCCESS
        assert check.html_url == "https://github.com/owner/repo/runs/1"


class TestReview:
    """Tests for Review model."""

    def test_basic_review(self):
        """Test creating a basic review."""
        review = Review(id=1, user_login="reviewer", state=ReviewState.APPROVED)
        assert review.id == 1
        assert review.user_login == "reviewer"
        assert review.state == ReviewState.APPROVED
        assert review.submitted_at is None

    def test_review_with_timestamp(self):
        """Test review with submitted_at timestamp."""
        now = datetime.now(UTC)
        review = Review(
            id=1, user_login="reviewer", state=ReviewState.APPROVED, submitted_at=now
        )
        assert review.submitted_at == now


class TestLabel:
    """Tests for Label model."""

    def test_basic_label(self):
        """Test creating a basic label."""
        label = Label(name="bug")
        assert label.name == "bug"
        assert label.color is None

    def test_label_with_color(self):
        """Test label with color."""
        label = Label(name="enhancement", color="00ff00")
        assert label.color == "00ff00"


class TestUser:
    """Tests for User model."""

    def test_user(self):
        """Test creating a user."""
        user = User(login="testuser", id=123)
        assert user.login == "testuser"
        assert user.id == 123


class TestPRStatus:
    """Tests for PRStatus model."""

    @pytest.fixture
    def sample_pr_status(self):
        """Sample PR status for testing."""
        return PRStatus(
            number=123,
            title="Test PR",
            author=User(login="author", id=1),
            state=PRState.OPEN,
            is_merged=False,
            is_draft=False,
            combined_commit_status=CombinedStatus.PENDING,
            check_runs=[],
            all_checks_complete=False,
            checks_passing=False,
            reviews=[],
            review_decision=None,
            labels=[],
            assignees=[],
            comment_count=5,
            updated_at=datetime.now(UTC),
        )

    def test_is_terminal_when_merged(self, sample_pr_status):
        """Test is_terminal returns True when merged."""
        sample_pr_status.is_merged = True
        assert sample_pr_status.is_terminal is True

    def test_is_terminal_when_closed(self, sample_pr_status):
        """Test is_terminal returns True when closed."""
        sample_pr_status.state = PRState.CLOSED
        assert sample_pr_status.is_terminal is True

    def test_is_terminal_when_checks_complete(self, sample_pr_status):
        """Test is_terminal returns True when all checks complete."""
        sample_pr_status.all_checks_complete = True
        assert sample_pr_status.is_terminal is True

    def test_is_terminal_false_when_open_with_pending_checks(self, sample_pr_status):
        """Test is_terminal returns False when PR is open with pending checks."""
        assert sample_pr_status.is_terminal is False


class TestMonitoringConfig:
    """Tests for MonitoringConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = MonitoringConfig()
        assert config.poll_interval_seconds == 30.0
        assert config.max_timeout_seconds == 3600.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = MonitoringConfig(
            poll_interval_seconds=60.0, max_timeout_seconds=7200.0
        )
        assert config.poll_interval_seconds == 60.0
        assert config.max_timeout_seconds == 7200.0

    def test_poll_interval_min_validation(self):
        """Test poll_interval_seconds minimum validation."""
        with pytest.raises(ValidationError):
            MonitoringConfig(poll_interval_seconds=4.0)  # Below 5.0

    def test_poll_interval_max_validation(self):
        """Test poll_interval_seconds maximum validation."""
        with pytest.raises(ValidationError):
            MonitoringConfig(poll_interval_seconds=301.0)  # Above 300.0

    def test_max_timeout_min_validation(self):
        """Test max_timeout_seconds minimum validation."""
        with pytest.raises(ValidationError):
            MonitoringConfig(max_timeout_seconds=59.0)  # Below 60.0

    def test_max_timeout_max_validation(self):
        """Test max_timeout_seconds maximum validation."""
        with pytest.raises(ValidationError):
            MonitoringConfig(max_timeout_seconds=86401.0)  # Above 86400.0
