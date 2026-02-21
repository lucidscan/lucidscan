# LucidShark Reference Documentation

LucidShark is a unified code quality tool that combines linting, type checking, security scanning, testing, coverage analysis, and duplication detection into a single pipeline.

## Quick Start

### Installation

```bash
pip install lucidshark
```

### Recommended Setup (AI-Assisted)

```bash
# 1. Set up Claude Code
lucidshark init --claude-code

# 2. Restart Claude Code, then ask:
#    "Autoconfigure LucidShark for this project"
```

Your AI assistant will analyze your codebase, ask a few questions, and generate `lucidshark.yml`.

### Run Scans

```bash
# Default: scan only changed files (uncommitted changes)
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
| `--claude-code` | Configure Claude Code MCP settings |
| `--dry-run` | Show changes without applying |
| `--force` | Overwrite existing configuration |
| `--remove` | Remove LucidShark from tool configuration |

**Examples:**
```bash
lucidshark init --claude-code
lucidshark init --claude-code --remove
```

### `lucidshark scan`

Run the quality/security pipeline. By default, scans only changed files (uncommitted changes).

#### Scan Domains

| Flag | Domain | Description |
|------|--------|-------------|
| `--linting` | linting | Code style and linting (Ruff, ESLint, Biome, Checkstyle, Clippy) |
| `--type-checking` | type_checking | Static type analysis (mypy, pyright, TypeScript, SpotBugs, cargo check) |
| `--sca` | sca | Dependency vulnerability scanning (Trivy) |
| `--sast` | sast | Code security patterns (OpenGrep) |
| `--iac` | iac | Infrastructure-as-Code scanning (Checkov) |
| `--container` | container | Container image scanning (Trivy) |
| `--testing` | testing | Run test suite (pytest, Jest, Karma, Playwright, Maven, cargo test) |
| `--coverage` | coverage | Coverage analysis (coverage.py, Istanbul, JaCoCo, Tarpaulin) |
| `--duplication` | duplication | Code duplication detection (Duplo) |
| `--all` | all | Enable all domains |

#### Target Options

| Option | Description |
|--------|-------------|
| `path` | Path to scan (default: `.`) |
| `--files FILE [FILE ...]` | Specific files to scan (overrides default changed-files behavior) |
| `--all-files` | Scan entire project instead of just changed files |
| `--image IMAGE` | Container image to scan; can be specified multiple times (with `--container`) |

#### Output Options

| Option | Description |
|--------|-------------|
| `--format {json,table,sarif,summary}` | Output format |

#### Configuration Options

| Option | Description |
|--------|-------------|
| `--fail-on {critical,high,medium,low}` | Failure threshold for security issues |
| `--coverage-threshold PERCENT` | Coverage threshold (default: 80) |
| `--duplication-threshold PERCENT` | Maximum allowed duplication percentage (default: 10) |
| `--min-lines N` | Minimum lines for a duplicate block (default: 4) |
| `--config PATH` | Path to config file |

#### Execution Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Show what would be scanned without executing |
| `--sequential` | Disable parallel execution |
| `--fix` | Apply auto-fixes (linting only) |
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
```

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
- Security tools installed (trivy, opengrep, checkov)
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
| `fix` | boolean | `false` | Apply auto-fixes for linting issues |

**Valid domains:** `linting`, `type_checking`, `sast`, `sca`, `iac`, `container`, `testing`, `coverage`, `duplication`, `all`

**Default Behavior:** Partial scanning (changed files only) is the default. Use `all_files=true` for full project scans.

**Partial Scanning Support by Domain:**

| Domain | Partial Scan Support | Behavior |
|--------|---------------------|----------|
| `linting` | ⚠️ Partial support | Ruff/ESLint/Biome/Checkstyle support file args; Clippy is workspace-wide |
| `type_checking` | ⚠️ Partial support | mypy/pyright support file args; tsc/SpotBugs/cargo check scan full project |
| `sast` | ✅ Full support | OpenGrep scans only specified/changed files |
| `sca` | ❌ Project-wide only | Trivy dependency scan is inherently project-wide |
| `iac` | ❌ Project-wide only | Checkov scans entire project |
| `testing` | ⚠️ Partial support | pytest/Jest/Playwright support file args; Karma/Maven/cargo test are project-wide |
| `coverage` | ⚠️ Run full, filter output | Tests run fully, but coverage can be filtered to changed files; Tarpaulin/JaCoCo always project-wide |
| `duplication` | ❌ Project-wide only | Duplo scans entire project to detect cross-file duplicates |

**Response format:**
```json
{
  "total_issues": 5,
  "blocking": true,
  "summary": "5 issues found: 1 critical, 2 high, 2 medium",
  "severity_counts": {"critical": 1, "high": 2, "medium": 2},
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

Apply auto-fix for a fixable issue. Currently only supports linting issues.

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
    "scanners": ["trivy", "opengrep", "checkov"],
    "linters": ["ruff", "eslint", "biome", "checkstyle", "clippy"],
    "type_checkers": ["mypy", "pyright", "typescript", "spotbugs", "cargo_check"],
    "test_runners": ["pytest", "jest", "karma", "playwright", "maven", "cargo"],
    "coverage": ["coverage_py", "istanbul", "jacoco", "tarpaulin"],
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

**This is the primary way to set up LucidShark for a project.** Returns step-by-step instructions for analyzing the codebase and generating `lucidshark.yml`. The AI analyzes the project, asks the user 1-2 questions if needed, generates the configuration, and validates it.

**Parameters:** None

**Usage:**
```
autoconfigure()
```

**Workflow after calling this tool:**

1. **Detect languages** -- Check for marker files (`package.json`, `pyproject.toml`, `go.mod`, `pom.xml`, `Cargo.toml`, etc.)
2. **Detect existing tools** -- Check for configs like `.eslintrc*`, `ruff.toml`, `tsconfig.json`, `mypy.ini`, `biome.json`
3. **Detect test frameworks** -- Check for `conftest.py`, `jest.config.*`, `karma.conf.*`, `playwright.config.*`
4. **Ask 1-2 questions** -- Coverage threshold (if tests detected), strict vs gradual mode (for legacy codebases)
5. **Call `get_help()`** -- Read the Configuration Reference section for the full `lucidshark.yml` format
6. **Generate `lucidshark.yml`** -- Write the config file based on detected project characteristics
7. **Call `validate_config()`** -- Verify the configuration is valid, fix any errors
8. **Inform the user** -- Which tools need installation, suggest running `lucidshark scan --all` to verify

**Tool recommendations by language:**

| Language | Linter | Type Checker | Test Runner | Coverage |
|----------|--------|-------------|-------------|----------|
| Python | ruff | mypy or pyright | pytest | coverage_py |
| JavaScript/TypeScript | eslint or biome | typescript (tsc) | jest, karma, or playwright | istanbul |
| Java | checkstyle | spotbugs | maven (JUnit) | jacoco |
| Kotlin | -- | -- | maven (JUnit) | jacoco |
| Rust | clippy | cargo_check | cargo | tarpaulin |

**Security tools** (always recommended for all languages): trivy (SCA) + opengrep (SAST)

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
      - name: checkstyle  # For Java projects
      - name: clippy      # For Rust projects

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
    exclude:          # Patterns to exclude from test execution
      - "tests/integration/**"
    tools:
      - name: pytest      # Python unit tests
      - name: jest        # JavaScript/TypeScript tests
      - name: karma       # Angular unit tests (Jasmine)
      - name: playwright  # E2E tests
      - name: maven       # Java tests (JUnit/TestNG via Maven/Gradle)
      - name: cargo       # Rust tests (cargo test)

  coverage:
    enabled: true
    exclude:          # Patterns to exclude from coverage analysis
      - "scripts/**"
    tools: [coverage_py]  # coverage_py for Python, istanbul for JS/TS, jacoco for Java, tarpaulin for Rust
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

# Global file/directory excludes (applies to all domains)
exclude:
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/__pycache__/**"

# Output format
output:
  format: json  # json, table, sarif, summary
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
  - "**/__pycache__/**"
  - "**/.venv/**"
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
  - "**/node_modules/**"
  - "**/dist/**"
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
  - "**/__pycache__/**"
  - "**/.venv/**"
  - "**/.pytest_cache/**"
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
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/coverage/**"
```

#### Security Only (Any Language)

Dependency vulnerability scanning (Trivy SCA) and code security patterns (OpenGrep SAST). No language-specific tools needed.

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
  - "**/node_modules/**"
  - "**/__pycache__/**"
  - "**/.venv/**"
```

#### Java Project

Checkstyle for linting, SpotBugs for type/bug analysis, Maven for testing, and JaCoCo for coverage.

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
  - "**/target/**"
  - "**/.gradle/**"
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
  - "**/target/**"
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
| `linting.tools` | array | (auto) | List of linting tools |
| `type_checking.enabled` | bool | true | Enable type checking |
| `type_checking.exclude` | array | [] | Patterns to exclude from type checking (combined with global `exclude`) |
| `type_checking.tools` | array | (auto) | List of type checkers |
| `security.enabled` | bool | true | Enable security scanning |
| `security.exclude` | array | [] | Patterns to exclude from security scanning (combined with global `exclude`) |
| `security.tools` | array | (auto) | Security tools with domains |
| `testing.enabled` | bool | false | Enable test execution |
| `testing.exclude` | array | [] | Patterns to exclude from test execution (combined with global `exclude`) |
| `testing.tools` | array | (auto) | Test frameworks |
| `coverage.enabled` | bool | false | Enable coverage analysis |
| `coverage.exclude` | array | [] | Patterns to exclude from coverage analysis (combined with global `exclude`) |
| `coverage.tools` | array | **required** | Coverage tools (coverage_py, istanbul, jacoco, tarpaulin) |
| `coverage.threshold` | int | 80 | Coverage percentage threshold |
| `coverage.extra_args` | array | [] | Extra Maven/Gradle arguments (Java only) |
| `duplication.enabled` | bool | false | Enable duplication detection |
| `duplication.threshold` | float | 10.0 | Max allowed duplication percentage |
| `duplication.min_lines` | int | 4 | Minimum lines for a duplicate block |
| `duplication.min_chars` | int | 3 | Minimum characters per line |
| `duplication.exclude` | array | [] | Patterns to exclude from duplication scan (combined with global `exclude`) |
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
lucidshark init --claude-code
```

This creates:
- `.mcp.json` - MCP server configuration (auto-detects lucidshark path)
- `.claude/skills/lucidshark/SKILL.md` - Proactive scanning skill for Claude

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

Conclude with a summary across all domains:

```
---
**Summary**: 4 total issues (0 critical, 1 high, 1 medium, 2 low)

| Domain | Status |
|--------|--------|
| Linting | 3 issues (2 auto-fixable) |
| Type Checking | 1 issue |
| Security | ✓ Pass |
| SCA | ✓ Pass |

**Recommended action**: Run `scan(fix=true)` to auto-fix 2 linting issues, then address the type error.
```

#### 3. When All Checks Pass

Even with no issues, confirm what was checked:

```
**Scan Complete**: All checks passed ✓

| Domain | Status |
|--------|--------|
| Linting | ✓ Pass |
| Type Checking | ✓ Pass |
| Security | ✓ Pass |

Ready to proceed.
```

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

**Note:** SCA (dependency scanning) always runs project-wide. SAST (OpenGrep) and most other tools scan only changed files by default.

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
| Clippy | Rust | ❌ No (Cargo workspace) |

All linting tools support the `files` parameter for partial scanning, except Clippy which operates on the full Cargo workspace.

### Type Checking

| Tool | Languages | Partial Scan |
|------|-----------|--------------|
| mypy | Python | ✅ Yes |
| pyright | Python | ✅ Yes |
| TypeScript (tsc) | TypeScript | ❌ No (project-wide only) |
| SpotBugs | Java | ❌ No (requires compiled classes) |
| cargo check | Rust | ❌ No (Cargo workspace) |

**Note:** TypeScript (tsc) does not support file-level scanning - it always analyzes the full project based on `tsconfig.json`. SpotBugs requires compiled Java classes (run `mvn compile` or `gradle build` first). cargo check operates on the full Cargo workspace.

### Security Scanning

| Tool | Domains | Partial Scan |
|------|---------|--------------|
| Trivy | SCA (dependencies), Container images | ❌ No (project-wide) |
| OpenGrep | SAST (code patterns) | ✅ Yes |
| Checkov | IaC (Terraform, K8s, CloudFormation) | ❌ No (project-wide) |

**Note:** OpenGrep (SAST) supports partial scanning and will scan only changed files by default. Trivy (SCA) and Checkov (IaC) always scan the entire project - dependency analysis requires full project context.

### Testing

| Tool | Languages | Partial Scan |
|------|-----------|--------------|
| pytest | Python | ✅ Yes |
| Jest | JavaScript, TypeScript | ✅ Yes |
| Karma | JavaScript, TypeScript (Angular) | ❌ No (config-based) |
| Playwright | JavaScript, TypeScript (E2E) | ✅ Yes |
| Maven | Java (JUnit/TestNG) | ❌ No (project-wide) |
| cargo test | Rust | ❌ No (Cargo workspace) |

**Note:** While test runners support running specific test files, it's recommended to run the full test suite before commits to catch regressions. cargo test runs unit tests, integration tests, and doc tests.

### Coverage

| Tool | Languages | Partial Scan |
|------|-----------|--------------|
| coverage.py | Python | ⚠️ Partial (filter output) |
| Istanbul/nyc | JavaScript, TypeScript | ⚠️ Partial (filter output) |
| JaCoCo | Java | ❌ No (project-wide) |
| Tarpaulin | Rust | ❌ No (Cargo workspace) |

**Note:** Coverage tools run the full test suite but can filter the coverage report to show only changed files. Tarpaulin (`cargo-tarpaulin`) instruments the Rust binary and runs the full test suite.

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

**Note:** Duplication detection always scans the entire project to find cross-file duplicates. Use domain-specific `exclude` patterns to skip generated or vendor files. All domains support `exclude` -- the effective excludes are the union of global `exclude`, `.lucidsharkignore`, and the domain's own `exclude` patterns.

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
```
