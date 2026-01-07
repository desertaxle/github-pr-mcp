"""Pydantic data models for GitHub PR status."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PRState(str, Enum):
    """Pull request state."""

    OPEN = "open"
    CLOSED = "closed"


class ReviewState(str, Enum):
    """Pull request review state."""

    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    PENDING = "PENDING"
    DISMISSED = "DISMISSED"


class CheckStatus(str, Enum):
    """GitHub check run status."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAITING = "waiting"
    PENDING = "pending"
    REQUESTED = "requested"


class CheckConclusion(str, Enum):
    """GitHub check run conclusion."""

    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    STALE = "stale"


class CombinedStatus(str, Enum):
    """Combined status from commit statuses API."""

    SUCCESS = "success"
    PENDING = "pending"
    FAILURE = "failure"


class CheckRun(BaseModel):
    """Individual check run from GitHub."""

    id: int
    name: str
    status: CheckStatus
    conclusion: CheckConclusion | None = None
    html_url: str | None = None


class Review(BaseModel):
    """Pull request review."""

    id: int
    user_login: str
    state: ReviewState
    submitted_at: datetime | None = None


class Label(BaseModel):
    """PR label."""

    name: str
    color: str | None = None


class User(BaseModel):
    """GitHub user."""

    login: str
    id: int


class PRStatus(BaseModel):
    """Complete status snapshot of a pull request."""

    # Basic info
    number: int
    title: str
    author: User
    state: PRState
    is_merged: bool
    is_draft: bool

    # CI/CD status
    combined_commit_status: CombinedStatus
    check_runs: list[CheckRun] = Field(default_factory=list)
    all_checks_complete: bool
    checks_passing: bool

    # Review status
    reviews: list[Review] = Field(default_factory=list)
    review_decision: str | None = None  # "APPROVED", "CHANGES_REQUESTED", or None

    # Metadata
    labels: list[Label] = Field(default_factory=list)
    assignees: list[User] = Field(default_factory=list)
    comment_count: int
    updated_at: datetime

    @property
    def is_terminal(self) -> bool:
        """Check if PR has reached a terminal state for monitoring."""
        return (
            self.is_merged or self.state == PRState.CLOSED or self.all_checks_complete
        )


class MonitoringConfig(BaseModel):
    """Configuration for PR monitoring."""

    poll_interval_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    max_timeout_seconds: float = Field(
        default=3600.0, ge=60.0, le=86400.0
    )  # 1 hour default, max 24 hours
