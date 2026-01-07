# GitHub PR Monitor MCP Server

A FastMCP server that monitors GitHub pull requests until they reach a terminal state (merged, closed, or all CI checks complete).

## Features

- Monitor PRs by URL (e.g., `https://github.com/owner/repo/pull/123`)
- Background task execution with progress reporting
- Comprehensive PR status: state, CI checks, reviews, labels, assignees, comments
- Configurable polling interval and timeout
- Rate limit handling with automatic recovery
- Optional GitHub authentication via `GITHUB_TOKEN` environment variable

## Installation

```bash
uv sync
```

## Usage with Claude Code

Add the server to your Claude Code MCP configuration:

```bash
claude mcp add github-pr-monitor -- uv run --directory /path/to/github-pr-mcp python main.py
```

Or manually add to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "github-pr-monitor": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/github-pr-mcp", "python", "main.py"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

Once configured, you can ask Claude Code to monitor PRs:

> "Monitor https://github.com/owner/repo/pull/123 and let me know when the checks complete"

## Tool: `monitor_pr`

Monitors a GitHub PR until it reaches a terminal state.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pr_url` | string | required | GitHub PR URL |
| `poll_interval_seconds` | float | 30.0 | Seconds between status checks (min: 5) |
| `max_timeout_seconds` | float | 3600.0 | Maximum monitoring duration (1 hour default) |

**Terminal conditions:**

- PR is merged
- PR is closed
- All CI checks complete (passed or failed)

**Returns:**

```json
{
  "success": true,
  "reason": "checks_complete",
  "checks_passed": true,
  "elapsed_seconds": 45.2,
  "poll_count": 2,
  "final_status": {
    "number": 123,
    "title": "Add new feature",
    "state": "open",
    "is_merged": false,
    "check_runs": [...],
    "reviews": [...],
    "labels": [...],
    "assignees": [...],
    "comment_count": 5
  }
}
```

## Authentication

Set `GITHUB_TOKEN` in the MCP server config (as shown above) for authenticated API access (5,000 requests/hour). Without it, the server uses unauthenticated access (60 requests/hour).

## Development

### Run tests

```bash
uv run pytest
```

### Lint and format

```bash
uv run ruff check .
uv run ruff format .
```
