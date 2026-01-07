"""Tests for URL parser."""

import pytest

from github_pr_mcp.parser import PRReference, parse_pr_url


class TestParseUrl:
    """Tests for parse_pr_url function."""

    def test_valid_url(self):
        """Test parsing a valid GitHub PR URL."""
        result = parse_pr_url("https://github.com/owner/repo/pull/123")
        assert result == PRReference(owner="owner", repo="repo", number=123)

    def test_url_with_trailing_slash(self):
        """Test parsing URL with trailing slash."""
        result = parse_pr_url("https://github.com/owner/repo/pull/123/")
        assert result.number == 123
        assert result.owner == "owner"
        assert result.repo == "repo"

    def test_url_with_www(self):
        """Test parsing URL with www prefix."""
        result = parse_pr_url("https://www.github.com/owner/repo/pull/456")
        assert result == PRReference(owner="owner", repo="repo", number=456)

    def test_complex_owner_repo_names(self):
        """Test parsing URL with complex owner/repo names."""
        result = parse_pr_url("https://github.com/my-org/my-repo-name/pull/789")
        assert result.owner == "my-org"
        assert result.repo == "my-repo-name"
        assert result.number == 789

    def test_invalid_host(self):
        """Test that non-GitHub URLs are rejected."""
        with pytest.raises(ValueError, match="Not a GitHub URL"):
            parse_pr_url("https://gitlab.com/owner/repo/pull/123")

    def test_invalid_host_typo(self):
        """Test that typos in GitHub URL are rejected."""
        with pytest.raises(ValueError, match="Not a GitHub URL"):
            parse_pr_url("https://gitbuh.com/owner/repo/pull/123")

    def test_invalid_path_issues(self):
        """Test that issue URLs are rejected."""
        with pytest.raises(ValueError, match="Not a valid PR URL"):
            parse_pr_url("https://github.com/owner/repo/issues/123")

    def test_invalid_path_no_number(self):
        """Test that URLs without PR number are rejected."""
        with pytest.raises(ValueError, match="Not a valid PR URL"):
            parse_pr_url("https://github.com/owner/repo/pull/")

    def test_invalid_path_non_numeric(self):
        """Test that URLs with non-numeric PR are rejected."""
        with pytest.raises(ValueError, match="Not a valid PR URL"):
            parse_pr_url("https://github.com/owner/repo/pull/abc")

    def test_invalid_path_repo_only(self):
        """Test that repo-only URLs are rejected."""
        with pytest.raises(ValueError, match="Not a valid PR URL"):
            parse_pr_url("https://github.com/owner/repo")


class TestPRReference:
    """Tests for PRReference dataclass."""

    def test_api_base(self):
        """Test api_base property."""
        ref = PRReference(owner="anthropics", repo="claude", number=42)
        assert ref.api_base == "https://api.github.com/repos/anthropics/claude"

    def test_frozen(self):
        """Test that PRReference is immutable."""
        ref = PRReference(owner="owner", repo="repo", number=1)
        with pytest.raises(AttributeError):
            ref.number = 2

    def test_hashable(self):
        """Test that PRReference is hashable."""
        ref = PRReference(owner="owner", repo="repo", number=1)
        # Should not raise
        hash(ref)
        # Can be used in sets
        refs = {ref}
        assert ref in refs

    def test_equality(self):
        """Test PRReference equality."""
        ref1 = PRReference(owner="owner", repo="repo", number=1)
        ref2 = PRReference(owner="owner", repo="repo", number=1)
        ref3 = PRReference(owner="owner", repo="repo", number=2)
        assert ref1 == ref2
        assert ref1 != ref3
