# LucidScan

[![CI](https://github.com/voldeq/lucidscan/actions/workflows/ci.yml/badge.svg)](https://github.com/voldeq/lucidscan/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/voldeq/lucidscan/graph/badge.svg)](https://codecov.io/gh/voldeq/lucidscan)
[![PyPI version](https://img.shields.io/pypi/v/lucidscan)](https://pypi.org/project/lucidscan/)
[![Python](https://img.shields.io/pypi/pyversions/lucidscan)](https://pypi.org/project/lucidscan/)
[![License](https://img.shields.io/github/license/voldeq/lucidscan)](https://github.com/voldeq/lucidscan/blob/main/LICENSE)

**The trust layer for AI-assisted development.**

LucidScan unifies linting, type checking, security scanning, testing, and coverage into a single pipeline that auto-configures for any project and integrates with AI coding tools like Claude Code and Cursor.

```
AI writes code → LucidScan checks → AI fixes → repeat
```

## Quick Start

### Installation

```bash
pip install lucidscan
```

### Console Usage

```bash
# Initialize for your project (auto-detects languages and tools)
lucidscan init

# Run the full quality pipeline
lucidscan scan --all

# Run specific checks
lucidscan scan --lint              # Linting (Ruff, ESLint, Biome)
lucidscan scan --type-check        # Type checking (mypy, pyright, tsc)
lucidscan scan --sast              # Security code analysis (OpenGrep)
lucidscan scan --sca               # Dependency vulnerabilities (Trivy)
lucidscan scan --test              # Run tests (pytest, Jest)
lucidscan scan --coverage          # Coverage analysis

# Auto-fix linting issues
lucidscan scan --lint --fix

# Check tool status
lucidscan status
```

### Claude Code Integration

The easiest way to set up Claude Code:

```bash
lucidscan setup --claude-code
```

This command:
- Adds LucidScan to your Claude Code MCP configuration (`.mcp.json`)
- Creates `.claude/CLAUDE.md` with instructions for Claude on when and how to run scans (tiered workflow: fast scans after code changes, full scans before commits)

Restart Claude Code to activate.

**Manual setup** (if preferred):

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "lucidscan": {
      "command": ".venv/bin/lucidscan",
      "args": ["serve", "--mcp"]
    }
  }
}
```

This project-scoped configuration uses a relative path to your venv, making it portable and suitable for version control. Adjust the path based on your virtual environment location.

Once configured, Claude Code can:
- Run quality checks on code it writes
- Get structured fix instructions with priorities
- Apply auto-fixes for linting issues

### Cursor Integration

```bash
lucidscan setup --cursor
```

This command:
- Adds LucidScan to Cursor's MCP configuration (`~/.cursor/mcp.json`)
- Creates `.cursor/rules/lucidscan.mdc` with rules that instruct Cursor to run scans automatically after code changes

Or manually add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "lucidscan": {
      "command": "lucidscan",
      "args": ["serve", "--mcp"]
    }
  }
}
```

### Configure All AI Tools

```bash
lucidscan setup --all
```

This configures both Claude Code and Cursor with their respective MCP configurations and instruction files.

## What It Checks

| Domain | Tools | What It Catches |
|--------|-------|-----------------|
| **Linting** | Ruff, ESLint, Biome, Checkstyle | Style issues, code smells |
| **Type Checking** | mypy, pyright, TypeScript | Type errors |
| **Security (SAST)** | OpenGrep | Code vulnerabilities |
| **Security (SCA)** | Trivy | Dependency vulnerabilities |
| **Security (IaC)** | Checkov | Infrastructure misconfigurations |
| **Testing** | pytest, Jest | Test failures |
| **Coverage** | coverage.py, Istanbul | Coverage gaps |

All results are normalized to a common format. One exit code for CI.

## CI Integration

### GitHub Actions

```yaml
name: Quality

on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install lucidscan
      - run: lucidscan scan --all
```

### With SARIF Upload (GitHub Code Scanning)

```yaml
- run: lucidscan scan --all --format sarif > results.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: results.sarif
```

### GitLab CI

```yaml
lucidscan:
  image: python:3.11
  script:
    - pip install lucidscan
    - lucidscan scan --all
```

## Configuration

LucidScan auto-detects your project. For custom settings, create `lucidscan.yml`:

```yaml
version: 1

pipeline:
  linting:
    enabled: true
    tools:
      - name: ruff

  type_checking:
    enabled: true
    tools:
      - name: mypy
        strict: true

  security:
    enabled: true
    tools:
      - name: trivy
      - name: opengrep

  testing:
    enabled: true
    tools:
      - name: pytest

  coverage:
    enabled: true
    threshold: 80

fail_on:
  linting: error
  security: high
  testing: any

ignore:
  - "**/node_modules/**"
  - "**/.venv/**"
```

## CLI Reference

```bash
# Initialize project
lucidscan init [--ci github|gitlab|bitbucket] [--non-interactive]

# Run quality pipeline
lucidscan scan [--lint] [--type-check] [--sca] [--sast] [--iac] [--test] [--coverage] [--all]
lucidscan scan [--fix] [--format table|json|sarif|summary]
lucidscan scan [--fail-on critical|high|medium|low]

# AI tool integration
lucidscan serve --mcp                    # Run MCP server
lucidscan serve --watch                  # Watch mode with auto-checking
lucidscan setup --claude-code            # Configure Claude Code
lucidscan setup --cursor                 # Configure Cursor
lucidscan setup --all                    # Configure all AI tools

# Show status
lucidscan status [--tools]
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Issues found above threshold |
| 2 | Tool execution error |
| 3 | Configuration error |

## Development

```bash
git clone https://github.com/voldeq/lucidscan.git
cd lucidscan
pip install -e ".[dev]"
pytest tests/
```

## Documentation

- [Full Specification](docs/main.md)
- [Roadmap](docs/roadmap.md)

## License

Apache 2.0
