# LucidShark Roadmap

> **Vision**: The trust layer for AI-assisted development

LucidShark unifies code quality tools (linting, type checking, security, testing, coverage, duplication detection) into a single pipeline that auto-configures for any project and integrates with AI coding tools like Claude Code and Cursor.

---

## Roadmap Overview

```
    v0.1-v0.5         v0.5.25           v0.6-v0.8           v0.9              v1.0
        |               |                  |                 |                 |
   ─────●───────────────●──────────────────●─────────────────●─────────────────●─────
        |               |                  |                 |                 |
    COMPLETE        COMPLETE           Language           CI/CD           Production
                   Partial+Java        Expansion        Integration           Ready
                   DX+Presets

  ┌─────────────┐ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
  │ Core        │ │ Git-aware   │  │ 5 Languages │  │ GitHub      │  │ Docs        │
  │ Security    │ │ Partial     │  │ Go, C#      │  │ Actions     │  │ Performance │
  │ MCP Server  │ │ Java tools  │  │ More tools  │  │ GitLab CI   │  │ Stability   │
  │ AI Tools    │ │ DX tooling  │  │             │  │             │  │             │
  └─────────────┘ └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

---

## Completed (v0.1 - v0.5.25)

All foundational work is complete. LucidShark is a fully functional code quality platform with AI integration, partial scanning, full Java support, binary distribution, and developer experience tooling.

### What's Built

| Component | Details |
|-----------|---------|
| **Core Framework** | CLI with subcommands, plugin system, pipeline orchestrator, configuration system |
| **Security Scanning** | Trivy (SCA, Container), OpenGrep (SAST), Checkov (IaC) |
| **Linting** | Ruff (Python), ESLint (JS/TS), Biome (JS/TS), Checkstyle (Java) |
| **Type Checking** | mypy (Python), pyright (Python), TypeScript (tsc), SpotBugs (Java) |
| **Testing** | pytest (Python), Jest (JS/TS), Karma (Angular), Playwright (E2E), Maven/Gradle (Java) |
| **Coverage** | coverage.py (Python), Istanbul (JS/TS), JaCoCo (Java) |
| **Duplication** | Duplo (multi-language code clone detection) |
| **AI Integration** | MCP server, file watcher, Claude Code skill, structured AI instructions |
| **Output** | JSON, Table, SARIF, Summary reporters |
| **Partial Scanning** | Git-aware scanning (changed files only by default) |
| **Presets** | python-strict, python-minimal, typescript-strict, typescript-minimal, minimal |
| **DX Tooling** | Dry-run mode, doctor command, validate command, streaming output |
| **Distribution** | PyPI package, standalone binary (macOS, Linux), install scripts with shell integration |
| **Tool Bootstrap** | Automatic download and management of tool binaries (Trivy, OpenGrep, Ruff, Biome, etc.) |

### Current Language Support

| Language | Linting | Type Checking | Testing | Coverage |
|----------|---------|---------------|---------|----------|
| Python | Ruff | mypy, pyright | pytest | coverage.py |
| JavaScript/TypeScript | ESLint, Biome | TypeScript | Jest, Karma, Playwright | Istanbul |
| Java/Kotlin | Checkstyle | SpotBugs | Maven/Gradle (JUnit) | JaCoCo |

### Commands Available Today

```bash
lucidshark init --claude-code         # Configure Claude Code
lucidshark init --cursor              # Configure Cursor
lucidshark autoconfigure              # Generate lucidshark.yml
lucidshark scan --all                 # Run complete pipeline
lucidshark scan --linting --fix       # Lint with auto-fix
lucidshark scan --type-checking       # Type checking
lucidshark scan --testing --coverage  # Tests with coverage
lucidshark scan --preset python-strict  # Scan with a preset
lucidshark scan --dry-run --all       # Preview what would run
lucidshark serve --mcp                # MCP server for AI tools
lucidshark status                     # Show tool status
lucidshark doctor                     # Check setup health
lucidshark validate                   # Validate lucidshark.yml
lucidshark help                       # Show LLM-friendly docs
```

---

## Completed - Partial Scans (Git-Aware Scanning)

**Status**: IMPLEMENTED in v0.5.x (current: v0.5.25)

LucidShark now defaults to scanning only changed files (uncommitted changes).

### How It Works

| Scenario | Behavior |
|----------|----------|
| Git repo with uncommitted changes | Scan only changed files |
| Git repo with no changes | Report "no files to scan" (or scan all if `--all-files`) |
| Not a git repo | Scan entire project |
| Explicit `--files` provided | Scan specified files (ignore git status) |
| Explicit `--all-files` flag | Scan entire project |

### Usage

```bash
# Default: scan only changed files (git diff + untracked)
lucidshark scan --linting --type-checking

# Explicit full project scan
lucidshark scan --linting --type-checking --all-files

# Explicit file list
lucidshark scan --linting --files src/foo.py src/bar.py
```

### MCP Server

```python
# Default: scan changed files only
scan(domains=["linting", "type_checking"])

# Full project scan
scan(domains=["linting", "type_checking"], all_files=True)

# Explicit file list
scan(domains=["linting"], files=["src/foo.py"])
```

### Partial Scan Support by Domain

| Domain | Partial Scan Support | Notes |
|--------|---------------------|-------|
| **Linting** | ✅ Full | All linters support file args |
| **Type Checking** | ⚠️ Partial | mypy/pyright yes, tsc project-wide |
| **SAST** | ✅ Full | OpenGrep supports file args |
| **SCA** | ❌ Project-wide | Dependency scan requires full project |
| **IaC** | ❌ Project-wide | Checkov scans full project |
| **Testing** | ✅ Full | But full suite recommended |
| **Coverage** | ⚠️ Partial | Run full tests, filter output |
| **Duplication** | ❌ Project-wide | Cross-file detection requires full project |

---

## v0.6 - v0.8 - Language Expansion

**Goal**: Support 5 popular languages with 2 tools per domain each

### Target Language Matrix

| Language | Linting | Type Checking | Testing | Coverage |
|----------|---------|---------------|---------|----------|
| **Python** | Ruff, Flake8 | mypy, pyright | pytest, unittest | coverage.py |
| **JS/TS** | ESLint, Biome | TypeScript (tsc) | Jest, Vitest | Istanbul, c8 |
| **Java** | Checkstyle | SpotBugs | JUnit (Maven/Gradle), TestNG | JaCoCo, Cobertura |
| **Go** | golangci-lint, staticcheck | (compiler) | go test, testify | go cover |
| **C#** | StyleCop, Roslyn | (compiler) | xUnit, NUnit | Coverlet, dotCover |

### Implementation by Version

#### v0.6 - Complete Python & JS/TS

| Task | Status |
|------|--------|
| Flake8 linter plugin | Planned |
| unittest test runner plugin | Planned |
| Vitest test runner plugin | Planned |
| c8 coverage plugin | Planned |

#### v0.7 - Add Go Language

| Task | Status |
|------|--------|
| Go language detection | Planned |
| golangci-lint plugin | Planned |
| staticcheck plugin | Planned |
| go test integration | Planned |
| go cover integration | Planned |
| TestNG test runner plugin | Planned |
| Cobertura coverage plugin | Planned |

> **Note**: SpotBugs, Maven/Gradle test runner, and JaCoCo plugins were originally planned for v0.7 but shipped early in v0.5.x.

#### v0.8 - Add C#

| Task | Status |
|------|--------|
| C# language detection | Planned |
| StyleCop linter plugin | Planned |
| Roslyn analyzer plugin | Planned |
| xUnit test runner plugin | Planned |
| NUnit test runner plugin | Planned |
| Coverlet coverage plugin | Planned |
| dotCover coverage plugin | Planned |

### Security Domains (Unchanged)

Security scanning remains the same across all languages:
- **SCA**: Trivy (dependency vulnerabilities)
- **SAST**: OpenGrep (code patterns)
- **IaC**: Checkov (infrastructure as code)
- **Container**: Trivy (image scanning)

---

## v0.9 - CI Integration

**Goal**: Native CI/CD pipeline support for automated quality gates

### Key Deliverables

| Feature | Description |
|---------|-------------|
| **GitHub Actions** | Generate `.github/workflows/lucidshark.yml` |
| **GitLab CI** | Generate `.gitlab-ci.yml` with LucidShark job |
| **SARIF upload** | Automatic upload to GitHub Security tab |
| **CI output mode** | Optimized output for CI environments |
| **Exit codes** | Clear pass/fail for pipeline gating |

### User Experience

```bash
# Generate CI configuration
lucidshark init --github-actions      # Create GitHub workflow
lucidshark init --gitlab-ci           # Create GitLab CI config

# CI-optimized scanning
lucidshark scan --all --ci            # CI mode with proper exit codes
lucidshark scan --all --sarif-upload  # Upload results to GitHub
```

### Generated GitHub Actions Workflow

```yaml
# .github/workflows/lucidshark.yml
name: LucidShark
on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install LucidShark
        run: pip install lucidshark
      - name: Run quality checks
        run: lucidshark scan --all --format sarif --output results.sarif
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: results.sarif
```

---

## v1.0 - Production Ready

**Goal**: Polish, stability, and comprehensive documentation

### Key Deliverables

| Feature | Description |
|---------|-------------|
| **Documentation** | Complete user guide, API reference, plugin development guide |
| **Performance** | Incremental checking, result caching, parallel execution |
| **Stability** | Error handling, graceful degradation, clear error messages |
| **Distribution** | Docker image, Homebrew formula (PyPI and standalone binary already available) |

### Success Criteria

- [ ] Complete documentation with examples
- [ ] Performance optimized for large codebases (10k+ files)
- [ ] Stable API (no breaking changes in 1.x)
- [ ] Production use validated by early adopters

---

## Future Considerations

Beyond v1.0, potential directions include:

| Direction | Description |
|-----------|-------------|
| **More languages** | Rust, PHP, Swift (Kotlin partially supported via Java tooling) |
| **VS Code extension** | Native IDE integration beyond MCP |
| **Team features** | Shared configs, policy enforcement, dashboards |
| **Custom rules** | User-defined linting and security rules |
| **Cloud service** | Optional SaaS for team management |

These are not committed - they depend on user feedback and adoption.

---

## Changelog

| Version | Status | Highlights |
|---------|--------|------------|
| v0.1-v0.5 | ✅ Complete | Core framework, security scanning, linting, type checking, testing, coverage, MCP server, AI integration |
| v0.5.12-v0.5.13 | ✅ Complete | Centralized tool version management, streaming support, duplication detection (Duplo) |
| v0.5.19 | ✅ Complete | Binary distribution (standalone macOS/Linux builds), Checkov standalone binary, Windows compatibility |
| v0.5.22 | ✅ Complete | DX improvements: dry-run mode, doctor command, presets, Claude Code skill auto-generation |
| v0.5.25 | ✅ Complete | SSL certificate fixes for macOS binary, install scripts with shell integration, local binary detection for MCP |
| v0.5.x | ✅ Complete | Partial scans (git-aware), full Java support (SpotBugs, Maven/Gradle, JaCoCo), config validation |
| v0.6 | Planned | Complete Python (Flake8, unittest) and JS/TS (Vitest, c8) tool coverage |
| v0.7 | Planned | Add Go support (golangci-lint, staticcheck, go test, go cover) |
| v0.8 | Planned | Add C# support (StyleCop, Roslyn, xUnit, NUnit, Coverlet, dotCover) |
| v0.9 | Planned | CI integration (GitHub Actions, GitLab CI) |
| v1.0 | Planned | Production ready (docs, performance, stability) |

---

## Contributing

See the [full specification](main.md) for detailed technical requirements.

To contribute:
1. Pick an item from the current milestone
2. Open an issue to discuss approach
3. Submit a PR

We welcome contributions for:
- New tool plugins (especially Go and C#)
- CI integration templates
- Documentation improvements
- Bug fixes and testing
