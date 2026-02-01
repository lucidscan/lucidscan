# LucidShark

<p align="center">
  <img src="docs/lucidshark.png" alt="LucidShark" width="400">
</p>

[![CI](https://github.com/lucidshark-code/lucidshark/actions/workflows/ci.yml/badge.svg)](https://github.com/lucidshark-code/lucidshark/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/lucidshark-code/lucidshark/graph/badge.svg)](https://codecov.io/gh/lucidshark-code/lucidshark)
[![PyPI version](https://img.shields.io/pypi/v/lucidshark)](https://pypi.org/project/lucidshark/)
[![Python](https://img.shields.io/pypi/pyversions/lucidshark)](https://pypi.org/project/lucidshark/)
[![License](https://img.shields.io/github/license/lucidshark-code/lucidshark)](https://github.com/lucidshark-code/lucidshark/blob/main/LICENSE)

**Unified code quality pipeline for AI-assisted development.**

```
AI writes code → LucidShark checks → AI fixes → repeat
```

## Why LucidShark

- **Local-first** - No server, no SaaS account. Runs on your machine and in CI with the same results.

- **Configuration-as-code** - `lucidshark.yml` lives in your repo. Same rules for everyone, changes go through code review.

- **AI-native** - MCP integration with Claude Code and Cursor. Structured feedback that AI agents can act on directly.

- **Unified pipeline** - Linting, type checking, security (SAST/SCA/IaC), tests, and coverage in one tool. Stop configuring 5+ separate tools.

- **Open source & extensible** - Apache 2.0 licensed. Add your own tools via the plugin system.

## Quick Start

```bash
# 1. Install LucidShark (choose one)

# Option A: pip (requires Python 3.10+)
pip install lucidshark

# Option B: Standalone binary (no Python required)
# Linux/macOS:
curl -fsSL https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.sh | bash
# Windows (PowerShell):
irm https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.ps1 | iex

# 2. Set up your AI tools (Claude Code and/or Cursor)
lucidshark init --all

# 3. Restart your AI tool, then ask it:
#    "Autoconfigure LucidShark for this project"
```

That's it! Your AI assistant will analyze your codebase, ask you a few questions, and generate the `lucidshark.yml` configuration.

### Installation Options

| Method | Command | Notes |
|--------|---------|-------|
| **pip** | `pip install lucidshark` | Requires Python 3.10+ |
| **Binary (Linux/macOS)** | `curl -fsSL .../install.sh \| bash` | No Python required |
| **Binary (Windows)** | `irm .../install.ps1 \| iex` | No Python required |
| **Manual** | Download from [Releases](https://github.com/lucidshark-code/lucidshark/releases) | Pre-built binaries |

The install scripts will prompt you to choose:
- **Global install** (`~/.local/bin` or `%LOCALAPPDATA%\Programs\lucidshark`) - available system-wide
- **Project-local install** (`.lucidshark/bin`) - project-specific, auto-detected by LucidShark

### Alternative: CLI Configuration

If you prefer to configure without AI:

```bash
lucidshark autoconfigure
```

### Running Scans

```bash
# Run the full quality pipeline
lucidshark scan --all

# Run specific checks
lucidshark scan --linting           # Linting (Ruff, ESLint, Biome)
lucidshark scan --type-checking     # Type checking (mypy, pyright, tsc)
lucidshark scan --sast              # Security code analysis (OpenGrep)
lucidshark scan --sca               # Dependency vulnerabilities (Trivy)
lucidshark scan --iac               # Infrastructure-as-Code (Checkov)
lucidshark scan --container         # Container image scanning (Trivy)
lucidshark scan --testing           # Run tests (pytest, Jest)
lucidshark scan --coverage          # Coverage analysis
lucidshark scan --duplication       # Code duplication detection

# Auto-fix linting issues
lucidshark scan --linting --fix
```

### AI Tool Setup

#### Claude Code

```bash
lucidshark init --claude-code
```

This:
- Adds LucidShark to your Claude Code MCP configuration (`.mcp.json`)
- Creates `.claude/CLAUDE.md` with scan workflow instructions

Restart Claude Code to activate.

#### Cursor

```bash
lucidshark init --cursor
```

This:
- Adds LucidShark to Cursor's MCP configuration (`~/.cursor/mcp.json`)
- Creates `.cursor/rules/lucidshark.mdc` with auto-scan rules

#### All AI Tools

```bash
lucidshark init --all
```

Configures both Claude Code and Cursor.

## What It Checks

| Domain | Tools | What It Catches |
|--------|-------|-----------------|
| **Linting** | Ruff, ESLint, Biome, Checkstyle | Style issues, code smells |
| **Type Checking** | mypy, pyright, TypeScript | Type errors |
| **Security (SAST)** | OpenGrep | Code vulnerabilities |
| **Security (SCA)** | Trivy | Dependency vulnerabilities |
| **Security (IaC)** | Checkov | Infrastructure misconfigurations |
| **Security (Container)** | Trivy | Container image vulnerabilities |
| **Testing** | pytest, Jest, Karma (Angular), Playwright (E2E) | Test failures |
| **Coverage** | coverage.py, Istanbul | Coverage gaps |
| **Duplication** | Duplo | Code clones, duplicate blocks |

All results are normalized to a common format.

## Configuration

LucidShark auto-detects your project. For custom settings, create `lucidshark.yml`:

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

  duplication:
    enabled: true
    threshold: 10.0  # Max allowed duplication percentage

fail_on:
  linting: error
  security: high
  testing: any
  coverage: below_threshold
  duplication: above_threshold

ignore:
  - "**/node_modules/**"
  - "**/.venv/**"
```

## CLI Reference

```bash
# Configure AI tools (Claude Code, Cursor)
lucidshark init --claude-code             # Configure Claude Code
lucidshark init --cursor                  # Configure Cursor
lucidshark init --all                     # Configure all AI tools

# Auto-configure project (detect languages, generate lucidshark.yml)
lucidshark autoconfigure [--ci github|gitlab|bitbucket] [--non-interactive]

# Run quality pipeline
lucidshark scan [--linting] [--type-checking] [--sca] [--sast] [--iac] [--container] [--testing] [--coverage] [--all]
lucidshark scan [--fix] [--stream] [--format table|json|sarif|summary]
lucidshark scan [--fail-on critical|high|medium|low]

# Server mode
lucidshark serve --mcp                    # Run MCP server
lucidshark serve --watch                  # Watch mode with auto-checking

# Show status
lucidshark status [--tools]
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
git clone https://github.com/lucidshark-code/lucidshark.git
cd lucidshark
pip install -e ".[dev]"
pytest tests/
```

## Documentation

- [LLM Reference Documentation](docs/help.md) - For AI agents and detailed reference
- [Full Specification](docs/main.md)
- [Roadmap](docs/roadmap.md)

## License

Apache 2.0
