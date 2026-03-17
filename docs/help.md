# LucidShark Reference Documentation

LucidShark is a unified code quality tool that combines linting, type checking, formatting, security scanning, testing, coverage analysis, and duplication detection into a single pipeline.

## Quick Start

### Installation

```bash
pip install lucidshark
```

### Recommended Setup (AI-Assisted)

```bash
# 1. Set up Claude Code
lucidshark init

# 2. Restart Claude Code, then ask:
#    "Autoconfigure LucidShark for this project"
```

Your AI assistant will analyze your codebase, ask a few questions, and generate `lucidshark.yml`.

### Run Scans

```bash
# Default: scan only changed files (uncommitted changes)
# No --base-branch needed for local development!
lucidshark scan --linting --type-checking

# Full project scan (all domains, all files)
lucidshark scan --all --all-files

# Run specific checks (on changed files by default)
lucidshark scan --linting        # Linting only
lucidshark scan --type-checking  # Type checking only
lucidshark scan --sca            # Dependency vulnerabilities (always project-wide)
lucidshark scan --sast           # Code security analysis

# Auto-fix linting issues (on changed files)
lucidshark scan --linting --fix

# PR/CI: filter results to files changed since branch
# (Note: this is different from default mode - full analysis runs,
# only reporting is filtered)
lucidshark scan --all --base-branch origin/main
```

---

## CLI Commands

### Global Options

These options are available for all commands:

| Option | Description |
|--------|-------------|
| `--version` | Show lucidshark version and exit |
| `--debug` | Enable debug logging |
| `--verbose`, `-v` | Enable verbose (info-level) logging |
| `--quiet`, `-q` | Reduce logging output to errors only |

### `lucidshark init`

Configure Claude Code to use LucidShark via MCP.

| Option | Description |
|--------|-------------|
| `--dry-run` | Show changes without applying |
| `--force` | Overwrite existing configuration |
| `--remove` | Remove LucidShark from tool configuration |

**Examples:**
```bash
lucidshark init
lucidshark init --remove
```

### `lucidshark scan`

Run the quality/security pipeline. By default, scans only changed files (uncommitted changes).

#### Scan Domains

| Flag | Domain | Description |
|------|--------|-------------|
| `--linting` | linting | Code style and linting (Ruff, ESLint, Biome, Clippy, Checkstyle, PMD, golangci-lint) |
| `--type-checking` | type_checking | Static type analysis (mypy, pyright, TypeScript, SpotBugs, cargo check, go vet) |
| `--formatting` | formatting | Code formatting (Ruff Format, Prettier, rustfmt, gofmt) |
| `--sca` | sca | Dependency vulnerability scanning (Trivy) |
| `--sast` | sast | Code security patterns (OpenGrep, gosec for Go) |
| `--iac` | iac | Infrastructure-as-Code scanning (Checkov) |
| `--container` | container | Container image scanning (Trivy) |
| `--testing` | testing | Run test suite (pytest, Jest, Vitest, Mocha, Karma, Playwright, Maven, cargo test, go test) |
| `--coverage` | coverage | Coverage analysis (coverage.py, Istanbul, Vitest, JaCoCo, Tarpaulin, go cover). **Requires `--testing`** |
| `--duplication` | duplication | Code duplication detection (Duplo) |
| `--all` | all | Enable all domains |

#### Target Options

| Option | Description |
|--------|-------------|
| `path` | Path to scan (default: `.`) |
| `--files FILE [FILE ...]` | Specific files to scan (overrides default changed-files behavior) |
| `--all-files` | Scan entire project instead of just changed files |
| `--image IMAGE` | Container image to scan; can be specified multiple times (with `--container`) |
| `--base-branch BRANCH` | **For PR/CI workflows:** Filter results to files changed since this branch (e.g., `origin/main`). Unlike the default mode (which scans only uncommitted changes), this runs full analysis then filters results. Applies to all domains: linting, type_checking, coverage, duplication. See [Incremental Scanning](incremental-scanning.md). |

#### Output Options

| Option | Description |
|--------|-------------|
| `--format {ai,json,table,sarif,summary}` | Output format (`ai` is optimized for AI agents) |

#### Configuration Options

| Option | Description |
|--------|-------------|
| `--fail-on {critical,high,medium,low}` | Failure threshold for security issues |
| `--coverage-threshold PERCENT` | Coverage threshold (default: 80) |
| `--coverage-threshold-scope {changed,project,both}` | With `--base-branch`: apply coverage threshold to changed files (default), project, or both |
| `--linting-threshold-scope {changed,project,both}` | With `--base-branch`: apply linting threshold to changed files (default), project, or both |
| `--type-checking-threshold-scope {changed,project,both}` | With `--base-branch`: apply type checking threshold to changed files (default), project, or both |
| `--duplication-threshold PERCENT` | Maximum allowed duplication percentage (default: 10) |
| `--duplication-threshold-scope {changed,project,both}` | With `--base-branch`: apply duplication threshold to changed files (default), project, or both |
| `--min-lines N` | Minimum lines for a duplicate block (default: 4) |
| `--config PATH` | Path to config file |

#### Execution Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Show what would be scanned without executing |
| `--sequential` | Disable parallel execution |
| `--fix` | Apply auto-fixes (linting and formatting) |
| `--stream` | Stream tool output in real-time as scans run |

**Examples:**
```bash
# Default: scan only changed files (uncommitted changes)
lucidshark scan --linting --type-checking

# Full project scan
lucidshark scan --all --all-files

# Scan specific files
lucidshark scan --linting --files src/main.py src/utils.py

# Lint with auto-fix (on changed files)
lucidshark scan --linting --fix

# Full security scan
lucidshark scan --sca --sast --all-files --fail-on high

# Full scan before commit
lucidshark scan --all --all-files --format sarif > results.sarif

# Container scanning
lucidshark scan --container --image myapp:latest

# Stream output during scan
lucidshark scan --all --stream

# PR-based incremental coverage (see CI Platform Integration section)
lucidshark scan --testing --coverage --base-branch origin/main
```

#### CI Platform Integration

Use `--base-branch` to filter results to files changed in a PR. All scans run fully — only reporting is filtered. Works with all domains: linting, type_checking, coverage, and duplication. See [Incremental Scanning](incremental-scanning.md) for comprehensive documentation.

**GitHub Actions:**
```yaml
- name: Run LucidShark Incremental Scan
  run: |
    lucidshark scan --all \
      --base-branch origin/${{ github.base_ref }} \
      --coverage-threshold 80 \
      --duplication-threshold 10
```

**GitLab CI:**
```yaml
test:
  script:
    - lucidshark scan --all \
        --base-branch origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME \
        --coverage-threshold 80
```

**Bitbucket Pipelines:**
```yaml
- step:
    script:
      - lucidshark scan --all \
          --base-branch origin/$BITBUCKET_PR_DESTINATION_BRANCH \
          --coverage-threshold 80
```

**Azure DevOps:**
```yaml
- script: |
    lucidshark scan --all \
      --base-branch origin/$(System.PullRequest.TargetBranch) \
      --coverage-threshold 80
```

**Important:** Use `fetch-depth: 0` (or equivalent) in your CI checkout step to ensure full git history is available for branch comparison.

### `lucidshark status`

Show configuration and tool status.

| Option | Description |
|--------|-------------|
| `--tools` | Show installed tool versions |
| `--config` | Show effective configuration |

**Examples:**
```bash
lucidshark status
lucidshark status --tools
```

### `lucidshark serve`

Run LucidShark as a server for AI tool integration.

| Option | Description |
|--------|-------------|
| `--mcp` | Run as MCP server (for Claude Code) |
| `--watch` | Watch files and run incremental checks |
| `--port PORT` | HTTP port for status endpoint (default: 7432) |
| `--debounce MS` | File watcher debounce delay (default: 1000) |
| `path` | Project directory to serve (default: `.`) |

**Examples:**
```bash
lucidshark serve --mcp
lucidshark serve --watch
lucidshark serve --watch --debounce 500
```


### `lucidshark help`

Display this documentation.

```bash
lucidshark help
```

### `lucidshark doctor`

Run health checks on the LucidShark setup and environment. Checks configuration, tools, environment, and AI integrations.

**Checks performed:**
- Configuration file exists and is valid
- Security tools installed (trivy, opengrep, gosec, checkov)
- Common linters/type checkers available (ruff, mypy, pyright)
- Python version (requires 3.10+)
- Git repository detected
- Claude Code MCP integration configured

**Examples:**
```bash
lucidshark doctor
```

### `lucidshark validate`

Validate a `lucidshark.yml` configuration file and report errors/warnings.

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to config file (default: find in current directory) |

**Exit codes:**
- 0: Configuration is valid (may have warnings)
- 1: Configuration has errors
- 3: Configuration file not found

**Examples:**
```bash
lucidshark validate
lucidshark validate --config custom-config.yml
```

### `lucidshark overview`

Generate a quality overview report (`QUALITY.md`) from scan results. This provides a git-committed quality dashboard - no server or SaaS required.

| Option | Description |
|--------|-------------|
| `--show` | Display overview to stdout (default if no mode specified) |
| `--preview` | Preview what would be written without saving |
| `--update` | Write QUALITY.md and update history file |
| `--scan` | Run a scan first if no cached results exist |
| `path` | Project directory (default: `.`) |

**IMPORTANT: Requires full project scan**

Overview requires a full project scan (`--all-files`) because it represents the entire repository's quality state. Partial/incremental scans are rejected:

```bash
# This will fail - incremental scan
lucidshark scan --all
lucidshark overview  # Error: requires full project scan

# This works - full project scan
lucidshark scan --all --all-files
lucidshark overview  # Success
```

**How it works:**
1. Reads cached scan results from `.lucidshark/last-scan.json`
2. Validates the scan was a full project scan (not incremental)
3. Calculates a health score (0-10) based on issues, coverage, and duplication
4. Generates a markdown overview with domain status, trends, and top files
5. Optionally saves to `QUALITY.md` and appends to history

**Examples:**
```bash
# View overview (default)
lucidshark overview

# Preview without saving
lucidshark overview --preview

# Update QUALITY.md and history
lucidshark overview --update

# Run scan first, then update
lucidshark scan --all && lucidshark overview --update
```

**CI Integration (recommended):**

Add to your CI pipeline to auto-commit quality updates on merge to main.

**GitHub Actions:**

Uses `GITHUB_TOKEN` with explicit write permissions. No secrets needed.

```yaml
jobs:
  update-quality:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: write  # Required for pushing commits
    steps:
      - uses: actions/checkout@v4
      - name: Update Quality Overview
        run: |
          lucidshark scan --all --all-files
          lucidshark overview --update
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add QUALITY.md .lucidshark/quality-history.json
          git diff --staged --quiet || git commit -m "chore: update quality overview"
          git push
```

**GitLab CI:**

Requires a Project Access Token with `write_repository` scope stored in `GL_TOKEN` variable.
Go to Settings → Access Tokens → Create token with `write_repository` scope, then add to CI/CD Variables.

```yaml
update-quality:
  stage: deploy
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
  script:
    - lucidshark scan --all --all-files
    - lucidshark overview --update
    - git config user.name "GitLab CI"
    - git config user.email "gitlab-ci@${CI_SERVER_HOST}"
    - git remote set-url origin "https://oauth2:${GL_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git"
    - git add QUALITY.md .lucidshark/quality-history.json
    - git diff --staged --quiet || git commit -m "chore: update quality overview"
    - git push origin HEAD:$CI_COMMIT_BRANCH
```

**Bitbucket Pipelines:**

Requires an SSH keypair with write access. Go to Repository Settings → Access keys → Add key (with write permission), then add the private key to Repository Settings → SSH keys.

```yaml
pipelines:
  branches:
    main:
      - step:
          name: Update Quality Overview
          script:
            - lucidshark scan --all --all-files
            - lucidshark overview --update
            - git config user.name "Bitbucket Pipelines"
            - git config user.email "pipelines@bitbucket.org"
            - git add QUALITY.md .lucidshark/quality-history.json
            - git diff --staged --quiet || git commit -m "chore: update quality overview"
            - git push origin main
```

**Azure DevOps:**

Grant the build service "Contribute" permission: Project Settings → Repositories → Security → [Build Service] → Contribute: Allow. Checkout with `persistCredentials: true`.

```yaml
trigger:
  branches:
    include:
      - main

steps:
  - checkout: self
    persistCredentials: true  # Required for pushing

  - script: |
      lucidshark scan --all --all-files
      lucidshark overview --update
      git config user.name "Azure Pipelines"
      git config user.email "azuredevops@microsoft.com"
      git add QUALITY.md .lucidshark/quality-history.json
      git diff --staged --quiet || git commit -m "chore: update quality overview"
      git push origin HEAD:$(Build.SourceBranchName)
    displayName: Update Quality Overview
```

**Output file:** `QUALITY.md` at project root (configurable via `overview.file` in config)

**History file:** `.lucidshark/quality-history.json` (tracks up to 90 snapshots for trend analysis)

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Issues found above threshold |
| 2 | Tool/scanner execution error |
| 3 | Configuration error |
| 4 | Bootstrap/download failure |

---

## MCP Tools Reference

LucidShark exposes these tools via MCP (Model Context Protocol) for AI agent integration:

### `scan`

Run quality checks on the codebase or specific files. Supports partial scanning via the `files` parameter for faster feedback on changed files.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `domains` | array of strings | `["all"]` | Domains to check |
| `files` | array of strings | (none) | Specific files to check (relative paths). When provided, only these files are scanned. |
| `all_files` | boolean | `false` | Scan entire project instead of just changed files. By default, only uncommitted changes are scanned. |
| `fix` | boolean | `false` | Apply auto-fixes for linting and formatting issues |
| `base_branch` | string | (none) | Filter results to files changed since this branch (e.g., `origin/main`). Full analysis runs; only reporting is filtered. |
| `coverage_threshold_scope` | string | `"changed"` | With `base_branch`: apply coverage threshold to `changed`, `project`, or `both` |
| `linting_threshold_scope` | string | `"changed"` | With `base_branch`: apply linting threshold to `changed`, `project`, or `both` |
| `type_checking_threshold_scope` | string | `"changed"` | With `base_branch`: apply type checking threshold to `changed`, `project`, or `both` |
| `duplication_threshold_scope` | string | `"both"` | With `base_branch`: apply duplication threshold to `changed`, `project`, or `both` |

**Valid domains:** `linting`, `type_checking`, `formatting`, `sast`, `sca`, `iac`, `container`, `testing`, `coverage`, `duplication`, `all`

**Default Behavior:** Partial scanning (changed files only) is the default. Use `all_files=true` for full project scans.

**Partial Scanning Support by Domain:**

| Domain | Partial Scan Support | Behavior |
|--------|---------------------|----------|
| `linting` | ⚠️ Partial support | Ruff/ESLint/Biome/golangci-lint support file args; Clippy is workspace-wide |
| `type_checking` | ⚠️ Partial support | mypy/pyright support file args; tsc/SpotBugs/cargo check/go vet scan full project |
| `formatting` | ⚠️ Partial support | Ruff Format/Prettier/gofmt support file args; rustfmt takes individual files only |
| `sast` | ✅ Full support | OpenGrep and gosec scan only specified/changed files |
| `sca` | ❌ Project-wide only | Trivy dependency scan is inherently project-wide |
| `iac` | ❌ Project-wide only | Checkov scans entire project |
| `testing` | ⚠️ Partial support | pytest/Jest/Vitest/Mocha/Playwright support file args; Karma/Maven/cargo test/go test are project-wide |
| `coverage` | ⚠️ Parse data, filter output | Coverage reads existing data files; output can be filtered to changed files; Tarpaulin/JaCoCo/go cover always project-wide |
| `duplication` | ❌ Project-wide only | Duplo scans entire project to detect cross-file duplicates |

**Response format:**
```json
{
  "total_issues": 5,
  "blocking": true,
  "summary": "5 issues found: 1 critical, 2 high, 2 medium",
  "severity_counts": {"critical": 1, "high": 2, "medium": 2},
  "domain_status": {
    "linting": {"status": "pass", "display": "Pass"},
    "type_checking": {"status": "fail", "display": "3 issues"},
    "sast": {"status": "pass", "display": "Pass"},
    "sca": {"status": "fail", "display": "2 issues"},
    "testing": {"status": "skipped", "display": "Skipped"},
    "coverage": {"status": "skipped", "display": "Skipped"}
  },
  "instructions": [
    {
      "priority": 1,
      "action": "FIX_SECURITY_VULNERABILITY",
      "summary": "Hardcoded password in config.py:23",
      "file": "config.py",
      "line": 23,
      "problem": "Hardcoded credentials detected",
      "fix_steps": ["Remove hardcoded password", "Use environment variable"],
      "issue_id": "security-123"
    }
  ]
}
```

The `domain_status` field shows all configured domains with their status:
- `pass`: Domain executed with no issues
- `fail`: Domain executed with issues found
- `skipped`: Domain is configured but wasn't executed in this scan
```

**Examples:**
```
# Default: scan only changed files (uncommitted changes)
scan(domains=["linting", "type_checking"])

# Explicit full project scan
scan(domains=["all"], all_files=true)

# Scan specific files only
scan(domains=["linting", "type_checking"], files=["src/main.py", "src/utils.py"])

# Lint with auto-fix (on changed files by default)
scan(domains=["linting"], fix=true)

# Security scan - SAST scans changed files, SCA always project-wide
scan(domains=["sca", "sast"])

# Incremental scan - filter to files changed since main
scan(domains=["all"], base_branch="origin/main")

# Incremental scan with scope configuration
scan(
    domains=["all"],
    base_branch="origin/main",
    coverage_threshold_scope="changed",
    linting_threshold_scope="changed"
)
```

### `check_file`

Check a specific file and return issues with fix instructions. This is a convenience wrapper for partial scanning that automatically detects the file type and runs appropriate checks (linting, type checking) for that single file.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | Path to file (relative to project root) |

**When to use:**
- Quick feedback on a single file you just modified
- Checking a specific file before committing
- Faster than `scan()` when you only need to check one file

**Example:**
```
check_file(file_path="src/main.py")
```

**Note:** For checking multiple files, use `scan(files=["file1.py", "file2.py"])` instead.

### `get_fix_instructions`

Get detailed fix instructions for a specific issue. Use the `issue_id` from scan results.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `issue_id` | string | Yes | Issue identifier from scan result |

**Example:**
```
get_fix_instructions(issue_id="security-123")
```

### `apply_fix`

Apply auto-fix for a fixable issue. Supports linting and formatting issues.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `issue_id` | string | Yes | Issue identifier to fix |

**Example:**
```
apply_fix(issue_id="linting-456")
```

### `get_status`

Get current LucidShark status and configuration.

**Parameters:** None

**Response format:**
```json
{
  "project_root": "/path/to/project",
  "available_tools": {
    "scanners": ["trivy", "opengrep", "gosec", "checkov"],
    "linters": ["ruff", "eslint", "biome", "clippy", "pmd", "golangci_lint"],
    "formatters": ["ruff_format", "prettier", "rustfmt", "gofmt"],
    "type_checkers": ["mypy", "pyright", "typescript", "spotbugs", "cargo_check", "go_vet"],
    "test_runners": ["pytest", "jest", "vitest", "karma", "playwright", "maven", "cargo", "go_test"],
    "coverage": ["coverage_py", "istanbul", "vitest_coverage", "jacoco", "tarpaulin", "go_cover"],
    "duplication": ["duplo"]
  },
  "enabled_domains": ["sca", "sast", "linting"],
  "cached_issues": 5
}
```

### `get_help`

Get this documentation.

**Parameters:** None

**Response format:**
```json
{
  "documentation": "# LucidShark Reference Documentation...",
  "format": "markdown"
}
```

### `autoconfigure`

**This is the primary way to set up LucidShark for a project.** Returns step-by-step instructions for analyzing the codebase, installing required tools, and generating `lucidshark.yml`. The AI analyzes the project, installs missing tools, asks 1-2 questions if needed, generates the configuration, validates it, and runs a verification scan.

**Parameters:** None

**Usage:**
```
autoconfigure()
```

**Workflow after calling this tool:**

1. **Detect languages** -- Check for marker files (`package.json`, `pyproject.toml`, `go.mod`, `pom.xml`, `Cargo.toml`, etc.)
2. **Detect existing tools** -- Check for configs like `.eslintrc*`, `ruff.toml`, `tsconfig.json`, `mypy.ini`, `biome.json`
3. **Detect test frameworks** -- Check for `conftest.py`, `jest.config.*`, `karma.conf.*`, `playwright.config.*`
4. **Identify project-specific exclusions** -- Examine directory structure for generated code, vendored deps, etc.
5. **Ask 1-2 questions** -- Coverage threshold (if tests detected), strict vs gradual mode (for legacy codebases)
6. **Call `get_help()`** -- Read the Configuration Reference section for the full `lucidshark.yml` format
7. **Install required tools** -- Check if tools are installed, install missing ones, AND add them to dev dependencies (pyproject.toml, requirements-dev.txt, package.json, etc.)
8. **Generate `lucidshark.yml`** -- Write the config file based on detected project characteristics
9. **Call `validate_config()`** -- Verify the configuration is valid, fix any errors
10. **Run verification scan** -- Execute `scan(domains=["all"])` to verify everything works

**Tool recommendations by language:**

| Language | Linter | Formatter | Type Checker | Test Runner | Coverage |
|----------|--------|-----------|-------------|-------------|----------|
| Python | ruff | ruff_format | mypy or pyright | pytest | coverage_py |
| JavaScript/TypeScript | eslint or biome | prettier | typescript (tsc) | jest, vitest, karma, or playwright | istanbul or vitest_coverage |
| Java | checkstyle, pmd | -- | spotbugs | maven (JUnit) | jacoco |
| Kotlin | -- | -- | -- | maven (JUnit) | jacoco |
| Rust | clippy | rustfmt | cargo_check | cargo | tarpaulin |
| Go | golangci_lint | gofmt | go_vet | go_test | go_cover |

**Security tools** (always recommended for all languages): trivy (SCA) + opengrep (SAST) + gosec (SAST, Go-specific)

**Response format:**
```json
{
  "instructions": "Follow these steps to configure LucidShark...",
  "analysis_steps": [
    {
      "step": 1,
      "action": "Detect languages and package managers",
      "files_to_check": ["package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml", "build.gradle"],
      "what_to_look_for": "Presence of these files indicates the primary language(s)"
    },
    {
      "step": 2,
      "action": "Detect existing tools",
      "files_to_check": [".eslintrc*", "ruff.toml", "tsconfig.json", "mypy.ini", "biome.json"],
      "what_to_look_for": "Existing tool configurations to preserve"
    }
  ],
  "questions_to_ask": {
    "conditional_questions": [
      {
        "id": "coverage_threshold",
        "ask_when": "Tests detected",
        "default": 80
      },
      {
        "id": "strictness",
        "ask_when": "Large existing codebase",
        "options": ["strict (fail on issues)", "gradual (report only)"]
      }
    ]
  }
}
```

### `validate_config`

Validate a `lucidshark.yml` configuration file. Returns validation results with errors and warnings. Use after generating or modifying configuration to ensure it's valid.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `config_path` | string | No | Path to config file (relative to project root). Default: find `lucidshark.yml` |

**Response format:**
```json
{
  "valid": true,
  "config_path": "lucidshark.yml",
  "errors": [],
  "warnings": [
    {
      "message": "Unknown key 'output.formatt'",
      "key": "output.formatt",
      "suggestion": "format"
    }
  ]
}
```

**Examples:**
```
validate_config()
validate_config(config_path="lucidshark.yml")
validate_config(config_path="configs/custom.yml")
```

**Validation includes:**
- YAML syntax errors
- Unknown configuration keys (with typo suggestions)
- Type errors (e.g., string where boolean expected)
- Invalid values (e.g., unknown severity level)

**Best practice:** Always call `validate_config()` after generating or modifying `lucidshark.yml` to catch configuration errors early.

---

## Configuration Reference (`lucidshark.yml`)

LucidShark auto-detects your project, but you can customize behavior with `lucidshark.yml` in your project root.

### Complete Configuration Example

```yaml
version: 1

# Project metadata
project:
  name: my-project
  languages:
    - python
    - typescript

# Pipeline configuration
pipeline:
  max_workers: 4  # Parallel execution workers

  linting:
    enabled: true
    exclude:          # Patterns to exclude from linting
      - "migrations/**"
      - "generated/**"
    tools:
      - name: ruff
        config: ruff.toml  # Optional custom config path
      - name: eslint
      - name: biome
      - name: clippy           # For Rust projects
      - name: checkstyle       # For Java projects (style checking)
      - name: pmd              # For Java projects (bug detection, managed)
      - name: golangci_lint    # For Go projects

  type_checking:
    enabled: true
    exclude:          # Patterns to exclude from type checking
      - "**/*_pb2.py"
    tools:
      - name: mypy
        strict: true
      - name: pyright
      - name: typescript
      - name: spotbugs     # For Java projects (requires compiled classes)
      - name: cargo_check  # For Rust projects
      - name: go_vet       # For Go projects

  formatting:
    enabled: true
    tools:
      - name: ruff_format
      - name: prettier
      - name: rustfmt
      - name: gofmt

  security:
    enabled: true
    exclude:          # Patterns to exclude from security scanning
      - "tests/**"
      - "examples/**"
    tools:
      - name: trivy
        domains: [sca, container]
      - name: opengrep
        domains: [sast]
      - name: checkov
        domains: [iac]

  testing:
    enabled: true
    command: "npm test"             # Optional: custom shell command overrides plugin-based runner
    post_command: "npm run cleanup" # Optional: runs after command completes
    exclude:          # Patterns to exclude from test execution
      - "tests/integration/**"
    tools:
      - name: pytest      # Python unit tests
      - name: jest        # JavaScript/TypeScript tests
      - name: karma       # Angular unit tests (Jasmine)
      - name: playwright  # E2E tests
      - name: maven       # Java tests (JUnit/TestNG via Maven/Gradle)
      - name: cargo       # Rust tests (cargo test)
      - name: go_test     # Go tests (go test)

  # IMPORTANT: Coverage requires testing to be enabled (see "Testing and Coverage Integration")
  # Testing produces the coverage files that coverage analysis reads
  coverage:
    enabled: true
    exclude:          # Patterns to exclude from coverage analysis
      - "scripts/**"
    tools: [coverage_py]  # coverage_py for Python, istanbul/vitest_coverage for JS/TS, jacoco for Java, tarpaulin for Rust, go_cover for Go
    threshold: 80  # Fail if coverage below this
    # extra_args: ["-DskipITs", "-Ddocker.skip=true"]  # For Java: skip integration tests

  duplication:
    enabled: true
    threshold: 10.0  # Max allowed duplication percentage
    min_lines: 4     # Minimum lines for a duplicate block
    min_chars: 3     # Minimum characters per line
    exclude:         # Patterns to exclude from duplication scan
      - "htmlcov/**"
      - "generated/**"

# Failure thresholds (per-domain)
fail_on:
  linting: error           # error, none
  type_checking: error     # error, none
  security: high           # critical, high, medium, low, info, none
  testing: any             # any, none
  coverage: below_threshold  # below_threshold, any, none
  duplication: above_threshold  # above_threshold, any, none, or percentage (e.g., "5%")

# Alternative: single threshold for all security
# fail_on: high

# Ignore specific issues by rule ID (acknowledged but excluded from fail thresholds)
ignore_issues:
  - E501                                    # Simple form: just the rule ID (global)
  - rule_id: CVE-2021-3807                  # Structured form with reason
    reason: "Not exploitable in our context"
  - rule_id: CKV_AWS_18                     # Structured form with reason and expiry
    reason: "Access logging not required for dev buckets"
    expires: 2026-06-01
  - rule_id: S101                           # Path-scoped: only ignore in specific files
    reason: "Assert is OK in tests"
    paths:
      - "tests/**"
      - "**/test_*.py"

# Global file/directory excludes (applies to all domains)
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/__pycache__/**"
  - "**/.mypy_cache/**"
  - "**/.pytest_cache/**"
  - "**/.ruff_cache/**"
  - "**/htmlcov/**"

# Global settings
settings:
  strict_mode: true  # All configured tools must run successfully (default: true)

# Output format
output:
  format: json  # ai, json, table, sarif, summary

# Quality Overview (QUALITY.md generation)
overview:
  enabled: true              # Enable overview generation
  file: QUALITY.md           # Output file name
  history_file: .lucidshark/quality-history.json  # History storage
  history_limit: 90          # Max snapshots to keep
  domains:                   # Domains to include (null = all executed domains)
    - linting
    - type_checking
    - sast
    - sca
    - coverage
    - duplication
  top_files: 5               # Number of top files by issues to show
  health_score: true         # Show health score section
  domain_table: true         # Show domain status table
  issue_breakdown: true      # Show issues by severity
  security_summary: true     # Show security summary
  coverage_breakdown: true   # Show coverage section
  trend_chart: true          # Show score trend chart
```

#### Strict Mode and Tool Execution

By default, LucidShark runs in **strict mode** (`settings.strict_mode: true`). This means:

- **Every configured tool must run successfully** — if a tool is skipped (not installed, missing prerequisites, execution failed), the scan fails with a HIGH severity issue
- **Testing failures block the scan** — if tests fail, a HIGH severity issue is created
- **Coverage with no data fails** — if coverage analysis finds 0 lines measured, the scan fails

**Skip reasons that cause failures in strict mode:**
| Skip Reason | Example | Blocks Scan? |
|-------------|---------|--------------|
| Tool not installed | mypy not installed | ✅ Yes |
| Missing prerequisite | SpotBugs: no compiled classes | ✅ Yes |
| Execution failed | Tool timed out or crashed | ✅ Yes |
| No applicable files | No `.py` files for mypy | ❌ No (informational) |

**To disable strict mode** (allow tool skips without failing):
```yaml
settings:
  strict_mode: false
```

**Per-tool mandatory flag** (for fine-grained control when strict_mode is false):
```yaml
settings:
  strict_mode: false  # Lenient by default

pipeline:
  type_checking:
    tools:
      - name: mypy
        mandatory: true  # This specific tool must run
      - name: pyright
        mandatory: false  # Optional
```

#### Custom Commands

All pipeline domains support `command`, `pre_command`, and `post_command` fields for custom shell commands.
This provides a unified way to override plugin-based runners across linting, type checking,
testing, and coverage domains.

**`pre_command`** runs a shell command before the main command (or plugin-based runner)
executes. If the pre-command fails (non-zero exit code), it is logged as a warning but
does **not** fail the pipeline. Use this for setup steps like starting services,
generating files, or preparing the environment.

**`command`** replaces the plugin-based runner with a custom shell command. When set,
LucidShark executes the command via the shell from the project root directory and skips
plugin discovery entirely (the `tools` list is ignored). A non-zero exit code is reported
as a HIGH-severity issue.

**`post_command`** runs a shell command after the main command (or plugin-based runner)
completes. If the post-command fails (non-zero exit code), it is logged as a warning but
does **not** fail the pipeline.

```yaml
pipeline:
  linting:
    command: "npm run lint -- --format json"  # Custom linting
  type_checking:
    command: "npm run typecheck"              # Custom type checking
  testing:
    pre_command: "docker compose up -d db"    # Start dependencies first
    command: "docker compose run --rm app pytest -x"
    post_command: "npm run cleanup"
  coverage:
    command: "npm run test:coverage"
```

Common use cases:

- **Environment setup**: `pre_command: "docker compose up -d db"` to start dependencies before running tests
- **Code generation**: `pre_command: "npm run codegen"` to generate types or schemas before type checking
- **Custom build steps**: `command: "make test"` when your workflow requires a build system
- **Docker-based environments**: `command: "docker compose run --rm app pytest"` to run inside a container
- **Cleanup**: `post_command: "rm -rf tmp/test-artifacts"` to remove temporary files
- **Report generation**: `post_command: "node scripts/merge-reports.js"` to post-process output

### Tool Availability

⚠️ **CRITICAL FOR AUTOCONFIGURE**: Only use tools from the lists below. NEVER use tools not listed here - they are not supported by LucidShark and will cause validation errors.

LucidShark validates that all configured tools are installed before running scans. If a configured tool is missing, the scan fails immediately with an error message and install instructions.

#### Complete List of Supported Tools

**LINTING (lucidshark.linters):**
- ✅ `ruff` - Python linter (manual install: `pip install ruff`)
- ✅ `eslint` - JavaScript/TypeScript linter (manual install: `npm install -g eslint`)
- ✅ `biome` - JavaScript/TypeScript linter (manual install: `npm install -g @biomejs/biome`)
- ✅ `clippy` - Rust linter (manual install: `rustup component add clippy`)
- ✅ `golangci_lint` - Go linter (manual install: `go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest`)
- ✅ `checkstyle` - Java linter (auto-downloaded)
- ✅ `pmd` - Java linter (auto-downloaded)

**TYPE_CHECKING (lucidshark.type_checkers):**
- ✅ `mypy` - Python type checker (manual install: `pip install mypy`)
- ✅ `pyright` - Python type checker (manual install: `pip install pyright`)
- ✅ `typescript` - TypeScript type checker (manual install: `npm install -g typescript`)
- ✅ `spotbugs` - Java type checker (auto-downloaded)
- ✅ `cargo_check` - Rust type checker (included with rustup)
- ✅ `go_vet` - Go type checker (included with Go toolchain)

**TESTING (lucidshark.test_runners):**
- ✅ `pytest` - Python test runner (manual install: `pip install pytest`)
- ✅ `jest` - JavaScript/TypeScript test runner (manual install: `npm install jest`)
- ✅ `vitest` - JavaScript/TypeScript test runner (manual install: `npm install vitest`)
- ✅ `mocha` - JavaScript/TypeScript test runner (manual install: `npm install mocha`)
- ✅ `karma` - JavaScript/TypeScript test runner (manual install: `npm install karma`)
- ✅ `playwright` - JavaScript/TypeScript E2E test runner (manual install: `npm install @playwright/test`)
- ✅ `maven` - Java test runner (manual install: `brew install maven` or download)
- ✅ `cargo` - Rust test runner (included with rustup)
- ✅ `go_test` - Go test runner (included with Go toolchain)

**COVERAGE (lucidshark.coverage):**
- ✅ `coverage_py` - Python coverage (manual install: `pip install coverage pytest-cov`)
- ✅ `istanbul` - JavaScript/TypeScript coverage (manual install: `npm install nyc`)
- ✅ `vitest_coverage` - JavaScript/TypeScript coverage (manual install: `npm install @vitest/coverage-v8`)
- ✅ `jacoco` - Java coverage (Maven/Gradle plugin in pom.xml/build.gradle)
- ✅ `tarpaulin` - Rust coverage (manual install: `cargo install cargo-tarpaulin`)
- ✅ `go_cover` - Go coverage (included with Go toolchain)

**FORMATTING (lucidshark.formatters):**
- ✅ `ruff_format` - Python formatter (manual install: `pip install ruff`)
- ✅ `prettier` - JavaScript/TypeScript formatter (manual install: `npm install -g prettier`)
- ✅ `rustfmt` - Rust formatter (manual install: `rustup component add rustfmt`)
- ✅ `gofmt` - Go formatter (included with Go toolchain)

**SECURITY SCANNERS (lucidshark.scanners):**
- ✅ `trivy` - SCA/Container scanner (auto-downloaded)
- ✅ `opengrep` - SAST scanner (auto-downloaded)
- ✅ `gosec` - Go SAST scanner (auto-downloaded)
- ✅ `checkov` - IaC scanner (auto-downloaded)

**DUPLICATION (lucidshark.duplication):**
- ✅ `duplo` - Code duplication detector (auto-downloaded)

#### Auto-Downloaded Tools (No Manual Install Required)

The following tools are **automatically downloaded** by LucidShark:

| Tool | Domain | Description |
|------|--------|-------------|
| `trivy` | Security (SCA, Container) | Vulnerability scanner for dependencies and containers |
| `opengrep` | Security (SAST) | Static analysis for code security patterns |
| `gosec` | Security (SAST) | Go-specific security scanner with CWE-mapped rules |
| `checkov` | Security (IaC) | Infrastructure-as-Code security scanner |
| `duplo` | Duplication | Code duplication detection |
| `pmd` | Linting (Java) | Bug detection, design issues, complexity analysis |
| `checkstyle` | Linting (Java) | Style checking with Google or custom checks |
| `spotbugs` | Type Checking (Java) | Static analysis for bugs in compiled Java bytecode |

#### Manually Installed Tools

All other tools must be installed manually before use. If you configure a tool that isn't installed, LucidShark will fail with an error showing the install command.

**Linters:**

| Tool | Languages | Install Command |
|------|-----------|-----------------|
| `ruff` | Python | `pip install ruff` |
| `eslint` | JavaScript, TypeScript | `npm install -g eslint` |
| `biome` | JavaScript, TypeScript | `npm install -g @biomejs/biome` |
| `clippy` | Rust | `rustup component add clippy` |
| `golangci_lint` | Go | `go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest` |

**Type Checkers:**

| Tool | Languages | Install Command |
|------|-----------|-----------------|
| `mypy` | Python | `pip install mypy` |
| `pyright` | Python | `pip install pyright` |
| `typescript` | TypeScript | `npm install -g typescript` |
| `cargo_check` | Rust | Included with Rust toolchain (`rustup`) |
| `go_vet` | Go | Included with Go toolchain |

**Test Runners:**

| Tool | Languages | Install Command |
|------|-----------|-----------------|
| `pytest` | Python | `pip install pytest` |
| `jest` | JavaScript, TypeScript | `npm install jest` |
| `vitest` | JavaScript, TypeScript | `npm install vitest` |
| `mocha` | JavaScript, TypeScript | `npm install mocha` |
| `karma` | JavaScript, TypeScript | `npm install karma` |
| `playwright` | JavaScript, TypeScript | `npm install @playwright/test` |
| `maven` | Java | `brew install maven` (macOS) or download from maven.apache.org |
| `cargo` | Rust | Included with Rust toolchain (`rustup`) |
| `go_test` | Go | Included with Go toolchain |

**Coverage Tools:**

| Tool | Languages | Install Command |
|------|-----------|-----------------|
| `coverage_py` | Python | `pip install coverage pytest-cov` |
| `istanbul` | JavaScript, TypeScript | `npm install nyc` |
| `vitest_coverage` | JavaScript, TypeScript | `npm install @vitest/coverage-v8` or `@vitest/coverage-istanbul` |
| `jacoco` | Java | Maven/Gradle plugin (configured in pom.xml/build.gradle) |
| `tarpaulin` | Rust | `cargo install cargo-tarpaulin` |
| `go_cover` | Go | Included with Go toolchain |

**Formatters:**

| Tool | Languages | Install Command |
|------|-----------|-----------------|
| `ruff_format` | Python | `pip install ruff` (same as ruff linter) |
| `prettier` | JavaScript, TypeScript | `npm install -g prettier` |
| `rustfmt` | Rust | `rustup component add rustfmt` |
| `gofmt` | Go | Included with Go toolchain |

#### Validation Behavior

- Validation runs at the **start** of every scan (both CLI and MCP)
- Only tools **explicitly configured** in `lucidshark.yml` are validated
- Auto-detected tools (when no `tools` array is specified) are not validated
- Missing tools cause immediate failure with exit code 3 (CLI) or error response (MCP)

**Example error message:**

```
Error: Missing required tools

The following tools are configured but not installed:

  [linting] ruff
    Install: pip install ruff

  [type_checking] mypy
    Install: pip install mypy

Please install the missing tools and try again.

Note: Security tools (trivy, opengrep, gosec, checkov), duplo, pmd, checkstyle,
and spotbugs are downloaded automatically - no manual installation required.
```

### Common Configuration Examples

Copy-paste-ready configs for common project setups.

#### Python Only (Minimal)

Linting with Ruff and type checking with mypy. Good starting point for any Python project.

```yaml
version: 1
project:
  name: my-python-app
  languages: [python]
pipeline:
  linting:
    enabled: true
    tools:
      - name: ruff
  type_checking:
    enabled: true
    tools:
      - name: mypy
fail_on:
  linting: error
  type_checking: error
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/__pycache__/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/.mypy_cache/**"
  - "**/.ruff_cache/**"
  - "**/*.egg-info/**"
  - "**/htmlcov/**"
  - "**/dist/**"
  - "**/build/**"
```

#### TypeScript Only (Minimal)

Linting with ESLint and type checking with tsc. Works for any TypeScript or JavaScript project.

```yaml
version: 1
project:
  name: my-ts-app
  languages: [typescript, javascript]
pipeline:
  linting:
    enabled: true
    tools:
      - name: eslint
  type_checking:
    enabled: true
    tools:
      - name: typescript
fail_on:
  linting: error
  type_checking: error
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/coverage/**"
```

#### Python with Testing and Coverage

Full Python quality pipeline: Ruff, mypy, pytest, and coverage.py with an 80% threshold.

```yaml
version: 1
project:
  name: my-python-app
  languages: [python]
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
  testing:
    enabled: true
    tools:
      - name: pytest
  coverage:
    enabled: true
    tools:
      - name: coverage_py
    threshold: 80
fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: below_threshold
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/__pycache__/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/.mypy_cache/**"
  - "**/.pytest_cache/**"
  - "**/.ruff_cache/**"
  - "**/*.egg-info/**"
  - "**/.eggs/**"
  - "**/htmlcov/**"
  - "**/.tox/**"
  - "**/dist/**"
  - "**/build/**"
```

#### TypeScript Full Stack

ESLint, tsc, Jest, and Istanbul coverage. Suitable for React, Next.js, or Node.js projects.

```yaml
version: 1
project:
  name: my-fullstack-app
  languages: [typescript, javascript]
pipeline:
  linting:
    enabled: true
    tools:
      - name: eslint
  type_checking:
    enabled: true
    tools:
      - name: typescript
  testing:
    enabled: true
    tools:
      - name: jest
  coverage:
    enabled: true
    tools:
      - name: istanbul
    threshold: 80
fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: below_threshold
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/coverage/**"
  - "**/.next/**"
  - "**/.nuxt/**"
```

#### Security Only (Any Language)

Dependency vulnerability scanning (Trivy SCA) and code security patterns (OpenGrep SAST, gosec for Go). No language-specific tools needed.

```yaml
version: 1
project:
  name: my-project
pipeline:
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
fail_on:
  security: high
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/node_modules/**"
  - "**/__pycache__/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/dist/**"
  - "**/build/**"
```

#### Java Project

Checkstyle and PMD for linting, SpotBugs for type/bug analysis, Maven for testing, and JaCoCo for coverage. Checkstyle enforces coding style, while PMD detects bugs, design issues, and complexity problems.

```yaml
version: 1
project:
  name: my-java-app
  languages: [java]
pipeline:
  linting:
    enabled: true
    tools:
      - name: checkstyle
      - name: pmd
  type_checking:
    enabled: true
    tools:
      - name: spotbugs
  testing:
    enabled: true
    tools:
      - name: maven
  coverage:
    enabled: true
    tools:
      - name: jacoco
    threshold: 80
    extra_args: ["-DskipITs"]
fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: below_threshold
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/target/**"
  - "**/.gradle/**"
  - "**/build/**"
```

#### Rust Project

Clippy for linting, cargo check for type checking, cargo test for testing, and Tarpaulin for coverage.

```yaml
version: 1
project:
  name: my-rust-app
  languages: [rust]
pipeline:
  linting:
    enabled: true
    tools:
      - name: clippy
  type_checking:
    enabled: true
    tools:
      - name: cargo_check
  testing:
    enabled: true
    tools:
      - name: cargo
  coverage:
    enabled: true
    tools:
      - name: tarpaulin
    threshold: 80
fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: below_threshold
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/target/**"
```

#### Go Project

golangci-lint for linting, go vet for type checking, go test for testing, gofmt for formatting, and go cover for coverage.

```yaml
version: 1
project:
  name: my-go-app
  languages: [go]
pipeline:
  linting:
    enabled: true
    tools:
      - name: golangci_lint
  formatting:
    enabled: true
    tools:
      - name: gofmt
  type_checking:
    enabled: true
    tools:
      - name: go_vet
  testing:
    enabled: true
    tools:
      - name: go_test
  coverage:
    enabled: true
    tools:
      - name: go_cover
    threshold: 80
fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: below_threshold
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/vendor/**"
```

### Configuration Sections

#### `project`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Project name |
| `languages` | array | Detected/specified languages |

#### `pipeline`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_workers` | int | 4 | Maximum parallel workers |
| `linting.enabled` | bool | true | Enable linting |
| `linting.exclude` | array | [] | Patterns to exclude from linting (combined with global `exclude`) |
| `linting.threshold_scope` | string | "changed" | With `--base-branch`: apply threshold to `changed`, `project`, or `both` |
| `linting.tools` | array | (auto) | List of linting tools |
| `type_checking.enabled` | bool | true | Enable type checking |
| `type_checking.exclude` | array | [] | Patterns to exclude from type checking (combined with global `exclude`) |
| `type_checking.threshold_scope` | string | "changed" | With `--base-branch`: apply threshold to `changed`, `project`, or `both` |
| `type_checking.tools` | array | (auto) | List of type checkers |
| `security.enabled` | bool | true | Enable security scanning |
| `security.exclude` | array | [] | Patterns to exclude from security scanning (combined with global `exclude`) |
| `security.tools` | array | (auto) | Security tools with domains |
| `linting.pre_command` | string | (none) | Shell command to run before linting starts |
| `linting.command` | string | (none) | Custom shell command (overrides plugin-based runner) |
| `linting.post_command` | string | (none) | Shell command to run after linting completes |
| `type_checking.pre_command` | string | (none) | Shell command to run before type checking starts |
| `type_checking.command` | string | (none) | Custom shell command (overrides plugin-based runner) |
| `type_checking.post_command` | string | (none) | Shell command to run after type checking completes |
| `testing.enabled` | bool | false | Enable test execution |
| `testing.pre_command` | string | (none) | Shell command to run before tests start (e.g., start services) |
| `testing.command` | string | (none) | Custom shell command to run tests (overrides plugin-based runner) |
| `testing.post_command` | string | (none) | Shell command to run after tests complete (cleanup, reports, etc.) |
| `testing.exclude` | array | [] | Patterns to exclude from test execution (combined with global `exclude`) |
| `testing.tools` | array | (auto) | Test frameworks |
| `coverage.enabled` | bool | false | Enable coverage analysis |
| `coverage.pre_command` | string | (none) | Shell command to run before coverage analysis starts |
| `coverage.command` | string | (none) | Custom shell command (overrides plugin-based runner) |
| `coverage.post_command` | string | (none) | Shell command to run after coverage completes |
| `coverage.exclude` | array | [] | Patterns to exclude from coverage analysis (combined with global `exclude`) |
| `coverage.tools` | array | **required** | Coverage tools (coverage_py, istanbul, vitest_coverage, jacoco, tarpaulin) |
| `coverage.threshold` | int | 80 | Coverage percentage threshold |
| `coverage.threshold_scope` | string | "changed" | With `--base-branch`: apply threshold to `changed`, `project`, or `both` |
| `coverage.extra_args` | array | [] | Extra Maven/Gradle arguments (Java only) |
| `duplication.enabled` | bool | false | Enable duplication detection |
| `duplication.threshold` | float | 10.0 | Max allowed duplication percentage |
| `duplication.threshold_scope` | string | "both" | With `--base-branch`: apply threshold to `changed`, `project`, or `both`. The default `both` prevents project-wide duplication from creeping up over time. See [Incremental Scanning](incremental-scanning.md#duplication) for details. |
| `duplication.min_lines` | int | 4 | Minimum lines for a duplicate block |
| `duplication.min_chars` | int | 3 | Minimum characters per line |
| `duplication.exclude` | array | [] | Patterns to exclude from duplication scan (combined with global `exclude`) |
| `duplication.baseline` | bool | false | Only report NEW duplicates after first run |
| `duplication.cache` | bool | true | Cache processed files for faster re-runs |
| `duplication.use_git` | bool | true | Use git ls-files for file discovery when available |
| `duplication.tools` | array | (auto) | Duplication detection tools (duplo) |

#### Tool Configuration

Each tool in a pipeline section can have:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Tool identifier (ruff, mypy, trivy, etc.) |
| `config` | string | Path to tool-specific config file |
| `strict` | bool | Enable strict mode (type checkers) |
| `domains` | array | Security domains for scanner (sca, sast, iac, container) |
| `options` | object | Tool-specific options (passed through) |

#### `fail_on`

Per-domain failure thresholds:

| Domain | Valid Values |
|--------|--------------|
| `linting` | `error`, `none` |
| `type_checking` | `error`, `none` |
| `security` | `critical`, `high`, `medium`, `low`, `info`, `none` |
| `testing` | `any`, `none` |
| `coverage` | `below_threshold`, `any`, `none` |
| `duplication` | `above_threshold`, `any`, `none`, or percentage (e.g., `5%`) |

**Threshold-based values:**
- `below_threshold` (coverage): Fail if coverage percentage is below `pipeline.coverage.threshold`
- `above_threshold` (duplication): Fail if duplication percentage exceeds `pipeline.duplication.threshold`

#### `exclude`

Global array of glob patterns for files/directories to exclude from all domains:

```yaml
exclude:
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/test_*.py"
```

Per-domain `exclude` patterns can be set in each pipeline section for domain-specific exclusions. The effective excludes for any domain are the union of global `exclude`, `.lucidsharkignore`, and the domain's own `exclude` patterns. See [Exclude Patterns](exclude-patterns.md) for the full reference.

#### `ignore_issues`

Ignore specific issues by rule ID. Ignored issues are **acknowledged** -- they still appear in output (tagged as ignored) but are excluded from `fail_on` threshold checks and do not affect the exit code.

Supports both simple strings and structured objects:

```yaml
ignore_issues:
  # Simple: just the rule ID (applies globally)
  - E501
  - CVE-2021-3807

  # Structured: with optional reason and expiry
  - rule_id: CKV_AWS_18
    reason: "Access logging not required for dev buckets"
    expires: 2026-06-01

  # Path-scoped: only ignore in specific files/directories
  - rule_id: S101
    reason: "Assert is the standard way to write tests"
    paths:
      - "tests/**"
      - "**/test_*.py"
```

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `rule_id` | yes | string | Native scanner rule ID (e.g., `E501`, `CVE-2021-3807`, `CKV_AWS_1`) |
| `reason` | no | string | Why this issue is being ignored |
| `expires` | no | date | ISO date (`YYYY-MM-DD`). After this date, the ignore stops working and a warning is emitted |
| `paths` | no | list | Gitignore-style patterns to scope the ignore. If not specified or empty, the ignore applies globally |

**Behavior:**
- Matched issues are tagged `ignored: true` in all output formats
- Ignored issues do not count toward `fail_on` thresholds
- Path-scoped ignores only suppress issues in files matching the specified patterns
- Empty or missing `paths` = global ignore (applies to all files)
- Issues without file paths (e.g., some SCA vulnerabilities) are not matched by path-scoped ignores
- Expired ignores stop working and produce a warning
- Unmatched rule IDs (typos, stale entries) produce a warning

Works across all domains -- linting, type checking, security, testing, coverage, and duplication. See [Exclude Patterns](exclude-patterns.md) for detailed examples of path-scoped ignores.

#### `overview`

Configuration for quality overview generation (`QUALITY.md`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | true | Enable overview generation |
| `file` | string | "QUALITY.md" | Output file path (relative to project root) |
| `history_file` | string | ".lucidshark/quality-history.json" | History file path |
| `history_limit` | int | 90 | Maximum snapshots to retain in history |
| `domains` | array | (all) | Domains to include in overview. If null/empty, includes all executed domains |
| `top_files` | int | 5 | Number of top files by issue count to display (0 to disable) |
| `health_score` | bool | true | Show health score section with visual bar |
| `domain_table` | bool | true | Show domain status table with trends |
| `issue_breakdown` | bool | true | Show issues grouped by severity |
| `security_summary` | bool | true | Show security-specific summary (SAST/SCA/IaC/Container) |
| `coverage_breakdown` | bool | true | Show test coverage section |
| `trend_chart` | bool | true | Show score trend chart from history |

**Health Score Calculation:**

The health score (0-10) is calculated as:
- Start with 10.0
- Deduct for issues: Critical (-2.0 each, max -4.0), High (-1.0 each, max -3.0), Medium (-0.3 each, max -2.0), Low (-0.1 each, max -1.0)
- Coverage bonus/penalty: Above 80% up to +0.5, below 60% up to -1.0
- Duplication penalty: Above 10% up to -1.0

**Example overview output:**

```markdown
# Repository Quality Overview

> **Branch:** main | **Updated:** 2026-03-11 | **Commit:** `abc1234`

## Health Score: 8.5 / 10  ████████░░

| Domain | Status | Issues | Trend |
|--------|--------|--------|-------|
| Linting | ✓ Pass | 0 | → |
| Type Checking | ✓ Pass | 0 | ↑ -2 |
| Coverage | ✓ Pass | 0 | → |

## Issues by Severity
- 🔴 **Critical:** 0
- 🟠 **High:** 0
- 🟡 **Medium:** 3
- 🔵 **Low:** 12

## Test Coverage
**82.5%** ████████░░ ↑ +2.3%
```

### Config File Locations

LucidShark searches for configuration in this order:

1. CLI `--config PATH` flag
2. Project root: `.lucidshark.yml`, `.lucidshark.yaml`, `lucidshark.yml`, `lucidshark.yaml`
3. Global: `~/.lucidshark/config/config.yml`
4. Built-in defaults

### Environment Variable Expansion

Use `${VAR}` or `${VAR:-default}` syntax in configuration:

```yaml
project:
  name: ${PROJECT_NAME:-my-project}
```

---

## AI Tool Setup

### Claude Code

```bash
lucidshark init
```

This creates:
- `.mcp.json` - MCP server configuration (auto-detects lucidshark path)
- `.claude/skills/lucidshark/SKILL.md` - Proactive scanning skill for Claude
- `.claude/CLAUDE.md` - Adds a managed section with scanning instructions
- `.claude/settings.json` - PostToolUse hooks for scan reminders after code edits

Or manually create `.mcp.json`:
```json
{
  "mcpServers": {
    "lucidshark": {
      "command": "lucidshark",
      "args": ["serve", "--mcp"]
    }
  }
}
```

**Note:** The `command` path is auto-detected. For venv installs, it will use the relative path (e.g., `.venv/bin/lucidshark`). For standalone installs, it uses `./lucidshark`.

---

## Best Practices for AI Agents

### Developer Experience Principles

LucidShark aims to provide a **fast, practical, and informative** experience that instills confidence. When using LucidShark via MCP, follow these principles:

1. **Keep the user informed** - Always communicate what you're doing at each step
2. **Be complete** - Show results for all domains that were checked
3. **Be actionable** - Every issue should have a clear path to resolution
4. **Be consistent** - Use the same output format every time for predictability

### Communicating Progress

Before and during scans, tell the user what's happening:

- **Before scanning**: "Running linting and type checks on changed files..."
- **During multi-domain scans**: "Checking linting... type checking... security..."
- **After scanning**: Present results in the structured format below

### Output Format Requirements

After every scan, present results in this structure:

#### 1. Issues List (grouped by domain)

List all issues organized by domain. For each domain, show:
- Domain name and issue count
- Individual issues with: file:line, severity, description, fix action

Example:
```
## Linting (3 issues)
- src/utils.py:45 [MEDIUM] Unused import 'os' → Remove import
- src/main.py:12 [LOW] Line too long → Auto-fixable
- src/main.py:89 [LOW] Missing docstring → Add docstring

## Type Checking (1 issue)
- src/api.py:67 [HIGH] Type 'str | None' incompatible with 'str'

## Security
✓ No issues found

## SCA
✓ No issues found
```

#### 2. Summary (always at the end)

Conclude with a summary across all domains. **Important:** Show ALL configured domains, not just the ones that were executed. Domains that weren't run in this scan should show "Skipped" status:

```
---
**Summary**: 4 total issues (0 critical, 1 high, 1 medium, 2 low)

| Domain | Status |
|--------|--------|
| Linting | 3 issues (2 auto-fixable) |
| Type Checking | 1 issue |
| Security | ✓ Pass |
| SCA | ✓ Pass |
| Testing | ⊘ Skipped |
| Coverage | ⊘ Skipped |
| Duplication | ⊘ Skipped |

**Recommended action**: Run `scan(fix=true)` to auto-fix 2 linting issues, then address the type error.
```

The "Skipped" status indicates domains that are configured in `lucidshark.yml` but weren't included in this specific scan run. This helps users understand what checks exist vs what was actually executed.

#### 3. When All Checks Pass

Even with no issues, confirm what was checked. Show all configured domains with their status:

```
**Scan Complete**: All checks passed ✓

| Domain | Status |
|--------|--------|
| Linting | ✓ Pass |
| Type Checking | ✓ Pass |
| Security | ✓ Pass |
| SCA | ✓ Pass |
| Testing | ⊘ Skipped |
| Coverage | ⊘ Skipped |

Ready to proceed.
```

This makes it clear which domains were executed (Pass) vs which are configured but not run (Skipped).

### Recommended Workflow

1. **After code changes**: Run scan (automatically checks only changed files)
   ```
   scan(domains=["linting", "type_checking"])
   ```

2. **Before commit**: Run full scan (comprehensive)
   ```
   scan(domains=["all"], all_files=true)
   ```

3. **To fix issues**: Use auto-fix (on changed files by default)
   ```
   scan(domains=["linting"], fix=true)
   ```

4. **For detailed guidance**: Get fix instructions
   ```
   get_fix_instructions(issue_id="...")
   ```

### Default Partial Scanning

LucidShark scans only changed files (uncommitted changes) by default. This is the recommended workflow:

| Scenario | Approach | Example |
|----------|----------|---------|
| After editing files | Default scan | `scan(domains=["linting", "type_checking"])` - scans changed files automatically |
| Quick single-file check | Use check_file | `check_file(file_path="src/main.py")` |
| Scan specific files | Use files param | `scan(domains=["linting"], files=["src/a.py", "src/b.py"])` |
| Before commit | Full scan | `scan(domains=["all"], all_files=true)` |
| Security audit | Full scan | `scan(domains=["sca", "sast", "iac"], all_files=true)` |

**Note:** SCA (dependency scanning) always runs project-wide. SAST (OpenGrep, gosec) and most other tools scan only changed files by default.

### Domain Selection Guidelines

| Scenario | Recommended Domains |
|----------|---------------------|
| Quick style check | `["linting"]` (scans changed files by default) |
| After editing Python | `["linting", "type_checking"]` |
| After editing TypeScript | `["linting", "type_checking"]` |
| Before commit | `["all"]` with `all_files=true` |
| Security audit | `["sca", "sast", "iac"]` with `all_files=true` |
| Pre-release | `["all"]` with `all_files=true` and `fix=true` for linting |

### Handling Issues

1. **Priority order**: Fix high-priority issues first (priority 1-2)
2. **Auto-fixable**: Use `apply_fix()` for linting issues
3. **Manual fixes**: Follow `fix_steps` from instructions
4. **Re-scan**: Always re-scan after fixes to verify

### Performance Tips

- **Default is fast**: Just call `scan()` - it automatically scans only changed files
- **Use `check_file()`**: For single-file checks, this is the fastest option
- **Reserve full scans for commits**: Use `all_files=true` only before committing
- **SCA is always full**: Dependency scanning requires full project context
- **Auto-fix is smart**: `scan(domains=["linting"], fix=true)` fixes only changed files

---

## Supported Tools

For detailed per-language tool coverage, detection, and configuration examples, see the [Language Reference](languages/README.md).

### Linting

| Tool | Languages | Partial Scan |
|------|-----------|--------------|
| Ruff | Python | ✅ Yes |
| ESLint | JavaScript, TypeScript | ✅ Yes |
| Biome | JavaScript, TypeScript, JSON | ✅ Yes |
| Checkstyle | Java | ✅ Yes |
| PMD | Java | ✅ Yes |
| Clippy | Rust | ❌ No (Cargo workspace) |
| golangci-lint | Go | ✅ Yes |

All linting tools support the `files` parameter for partial scanning, except Clippy which operates on the full Cargo workspace.

### Type Checking

| Tool | Languages | Partial Scan |
|------|-----------|--------------|
| mypy | Python | ✅ Yes |
| pyright | Python | ✅ Yes |
| TypeScript (tsc) | TypeScript | ❌ No (project-wide only) |
| SpotBugs (managed) | Java | ❌ No (requires compiled classes) |
| cargo check | Rust | ❌ No (Cargo workspace) |
| go vet | Go | ❌ No (package-wide) |

**Note:** TypeScript (tsc) does not support file-level scanning - it always analyzes the full project based on `tsconfig.json`. SpotBugs requires compiled Java classes (run `mvn compile` or `gradle build` first). cargo check operates on the full Cargo workspace. go vet operates on Go packages.

### Security Scanning

| Tool | Domains | Partial Scan |
|------|---------|--------------|
| Trivy | SCA (dependencies), Container images | ❌ No (project-wide) |
| OpenGrep | SAST (code patterns) | ✅ Yes |
| gosec | SAST (Go-specific) | ✅ Yes (Go projects only) |
| Checkov | IaC (Terraform, K8s, CloudFormation) | ❌ No (project-wide) |

**Note:** OpenGrep (SAST) and gosec (Go SAST) support partial scanning and will scan only changed files by default. Trivy (SCA) and Checkov (IaC) always scan the entire project - dependency analysis requires full project context.

### Testing

| Tool | Languages | Partial Scan |
|------|-----------|--------------|
| pytest | Python | ✅ Yes |
| Jest | JavaScript, TypeScript | ✅ Yes |
| Vitest | JavaScript, TypeScript | ✅ Yes |
| Karma | JavaScript, TypeScript (Angular) | ❌ No (config-based) |
| Playwright | JavaScript, TypeScript (E2E) | ✅ Yes |
| Maven | Java (JUnit/TestNG) | ❌ No (project-wide) |
| cargo test | Rust | ❌ No (Cargo workspace) |
| go test | Go | ⚠️ Partial (package-level) |

**Note:** Most test runners (pytest, jest, vitest, maven, go test) include coverage instrumentation automatically. Others (cargo test, karma, playwright) do not — their coverage is handled by separate tools (tarpaulin) or project config (karma). While test runners support running specific test files, it's recommended to run the full test suite before commits to catch regressions.

### Coverage

| Tool | Languages | Partial Scan |
|------|-----------|--------------|
| coverage.py | Python | ⚠️ Partial (filter output) |
| Istanbul/nyc | JavaScript, TypeScript | ⚠️ Partial (filter output) |
| Vitest coverage | JavaScript, TypeScript | ⚠️ Partial (filter output) |
| JaCoCo | Java | ❌ No (project-wide) |
| Tarpaulin | Rust | ❌ No (Cargo workspace) |
| go cover | Go | ❌ No (project-wide) |

**Note:** Coverage plugins only parse existing coverage data files — they never run tests. The testing domain produces coverage files, and the coverage domain reads them. If no coverage data is found, coverage returns a `no_coverage_data` error. Coverage output can be filtered to show only changed files.

**Java Coverage (JaCoCo):** For Java projects with integration tests that require Docker or external services, use `extra_args` to skip them:
```yaml
pipeline:
  coverage:
    enabled: true
    tools: [jacoco]
    threshold: 80
    extra_args: ["-DskipITs", "-Ddocker.skip=true"]
```

### Duplication Detection

| Tool | Languages | Partial Scan |
|------|-----------|--------------|
| Duplo | Python, Rust, Java, JavaScript, TypeScript, C, C++, C#, Go, Ruby, Erlang, VB, HTML, CSS | ❌ No (project-wide) |

**Note:** Duplication detection always scans the entire project to find cross-file duplicates. This means missing exclusions in either the global `exclude` list or the domain-specific `exclude` will cause it to scan build artifacts, caches, vendored code, and generated files — producing noisy false positives. Always ensure comprehensive exclusions are in place. Examine your project's directory structure and exclude any directories that contain non-source-code files.

All domains support `exclude` — the effective excludes are the union of global `exclude`, `.lucidsharkignore`, and the domain's own `exclude` patterns.

**Configuration example:**
```yaml
pipeline:
  duplication:
    enabled: true
    threshold: 10.0    # Max allowed duplication percentage
    min_lines: 4       # Minimum lines for a duplicate block
    min_chars: 3       # Minimum characters per line
    exclude:           # Patterns to exclude from duplication scan
      - "htmlcov/**"
      - "generated/**"
      - "**/vendor/**"
      - "**/migrations/**"
      - "**/*.min.js"
      - "**/*.min.css"
      - "**/__snapshots__/**"
      - "**/fixtures/**"
      - "**/testdata/**"

# IMPORTANT: Also ensure global excludes are comprehensive
exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/__pycache__/**"
  - "**/dist/**"
  - "**/build/**"
  # Add language-specific and project-specific excludes here
```

---

## Testing and Coverage Integration

**IMPORTANT: Coverage requires testing.** The coverage domain does not run tests itself — it analyzes coverage files produced by the testing domain. When you enable coverage, you MUST also enable testing.

### How It Works

1. **Most test runners generate coverage data automatically** — pytest, jest, vitest, maven, and go test include coverage instrumentation (e.g., `jest --coverage`, `coverage run -m pytest`, `mvn test jacoco:report`, `go test -coverprofile`). Others (cargo test, karma, playwright) require separate coverage tooling
2. **Coverage plugins only parse existing data** — The coverage domain reads coverage files produced by the testing domain. Coverage plugins never run tests themselves
3. **Error if no coverage data found** — If coverage plugins cannot find existing coverage data files, they return a `no_coverage_data` error issue directing users to enable the testing domain
4. **Error if coverage without testing** — If you try to run coverage without testing enabled, LucidShark returns an error

### Coverage Files by Language

Test runners that support it produce coverage files that the corresponding coverage plugin reads:

| Language | Test Runner | Coverage Plugin | How Coverage Is Generated | Coverage Data File |
|----------|-------------|-----------------|--------------------------|-------------------|
| **Python** | pytest | coverage_py | pytest auto-wraps with `coverage run -m pytest` | `.coverage` |
| **JavaScript/TypeScript** | jest | istanbul | `jest --coverage` (requires `.nyc_output/` via NYC config) | `.nyc_output/` |
| **JavaScript/TypeScript** | vitest | vitest_coverage | `vitest run --coverage` | `coverage/coverage-summary.json` |
| **Java (Maven)** | maven | jacoco | `mvn test jacoco:report` | `target/site/jacoco/jacoco.xml` |
| **Java (Gradle)** | maven | jacoco | `gradle test jacocoTestReport` | `build/reports/jacoco/test/jacocoTestReport.xml` |
| **Rust** | cargo | tarpaulin | Separate: `cargo tarpaulin --out json` | `target/tarpaulin/tarpaulin-report.json` |
| **Go** | go_test | go_cover | `go test -coverprofile=coverage.out ./...` | `coverage.out` |

**Note:** For Rust, `cargo test` does not produce coverage data. Tarpaulin is a separate tool that runs its own instrumented test suite. For Karma and Playwright, coverage depends on project-level configuration, not LucidShark flags.

### Configuration Requirements

When configuring coverage in `lucidshark.yml`, you MUST also enable testing:

```yaml
pipeline:
  # REQUIRED: Testing must be enabled for coverage to work
  testing:
    enabled: true
    tools: [pytest]  # or jest, maven, cargo, go_test, etc.

  # Coverage analyzes the output from testing
  coverage:
    enabled: true
    tools: [coverage_py]  # or istanbul, vitest_coverage, jacoco, tarpaulin, go_cover
    threshold: 80
```

**Error example:** The following configuration is INVALID and will fail validation:

```yaml
# INVALID: Coverage without testing
pipeline:
  testing:
    enabled: false  # ERROR: Testing must be enabled for coverage
  coverage:
    enabled: true
```

### CLI Usage

When running scans from the command line:

```bash
# Correct: Both testing and coverage
lucidshark scan --testing --coverage

# Correct: Use --all (includes both testing and coverage if configured)
lucidshark scan --all

# ERROR: Coverage without testing
lucidshark scan --coverage  # Will fail with error
```

### MCP Usage

When using the MCP scan tool:

```
# Correct: Both testing and coverage
scan(domains=["testing", "coverage"])

# Correct: Use "all"
scan(domains=["all"])

# ERROR: Coverage without testing
scan(domains=["coverage"])  # Will return error
```
