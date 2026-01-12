# LucidScan Reference Documentation

LucidScan is a unified code quality tool that combines linting, type checking, security scanning, testing, and coverage analysis into a single pipeline.

## Quick Start

### Installation

```bash
# Using pip
pip install lucidscan

# Using pipx (recommended for CLI tools)
pipx install lucidscan

# Using uv
uv pip install lucidscan
```

### Initialize Project

```bash
# Auto-detect languages and generate lucidscan.yml
lucidscan init

# Initialize with CI configuration
lucidscan init --ci github
lucidscan init --ci gitlab
lucidscan init --ci bitbucket

# Non-interactive mode (use defaults)
lucidscan init -y
```

### Run Your First Scan

```bash
# Run all quality checks
lucidscan scan --all

# Run specific checks
lucidscan scan --lint           # Linting only
lucidscan scan --type-check     # Type checking only
lucidscan scan --sca            # Dependency vulnerabilities
lucidscan scan --sast           # Code security analysis

# Auto-fix linting issues
lucidscan scan --lint --fix
```

---

## CLI Commands

### `lucidscan init`

Initialize LucidScan for a project. Auto-detects languages, frameworks, and generates `lucidscan.yml`.

| Option | Description |
|--------|-------------|
| `--ci {github,gitlab,bitbucket}` | Generate CI configuration for platform |
| `--non-interactive`, `-y` | Use defaults without prompting |
| `--force`, `-f` | Overwrite existing configuration |
| `path` | Project directory (default: `.`) |

**Examples:**
```bash
lucidscan init
lucidscan init --ci github --non-interactive
lucidscan init /path/to/project -f
```

### `lucidscan scan`

Run the quality/security pipeline.

#### Scan Domains

| Flag | Domain | Description |
|------|--------|-------------|
| `--lint` | Linting | Code style and linting (Ruff, ESLint, Biome, Checkstyle) |
| `--type-check` | Type Checking | Static type analysis (mypy, pyright, TypeScript) |
| `--sca` | SCA | Dependency vulnerability scanning (Trivy) |
| `--sast` | SAST | Code security patterns (OpenGrep) |
| `--iac` | IaC | Infrastructure-as-Code scanning (Checkov) |
| `--container` | Container | Container image scanning (Trivy) |
| `--test` | Testing | Run test suite (pytest, Jest) |
| `--coverage` | Coverage | Coverage analysis (coverage.py, Istanbul) |
| `--all` | All | Enable all domains |

#### Output Options

| Option | Description |
|--------|-------------|
| `--format {json,table,sarif,summary}` | Output format |

#### Configuration Options

| Option | Description |
|--------|-------------|
| `--fail-on {critical,high,medium,low}` | Failure threshold for security issues |
| `--coverage-threshold PERCENT` | Coverage threshold (default: 80) |
| `--config PATH` | Path to config file |

#### Execution Options

| Option | Description |
|--------|-------------|
| `--sequential` | Disable parallel execution |
| `--fix` | Apply auto-fixes (linting only) |
| `--image IMAGE` | Container image to scan (with `--container`) |

**Examples:**
```bash
lucidscan scan --all
lucidscan scan --lint --type-check
lucidscan scan --lint --fix
lucidscan scan --sca --fail-on high
lucidscan scan --all --format sarif > results.sarif
lucidscan scan --container --image myapp:latest
```

### `lucidscan status`

Show configuration and tool status.

| Option | Description |
|--------|-------------|
| `--tools` | Show installed tool versions |
| `--config` | Show effective configuration |

**Examples:**
```bash
lucidscan status
lucidscan status --tools
```

### `lucidscan serve`

Run LucidScan as a server for AI tool integration.

| Option | Description |
|--------|-------------|
| `--mcp` | Run as MCP server (for Claude Code, Cursor) |
| `--watch` | Watch files and run incremental checks |
| `--port PORT` | HTTP port for status endpoint (default: 7432) |
| `--debounce MS` | File watcher debounce delay (default: 1000) |

**Examples:**
```bash
lucidscan serve --mcp
lucidscan serve --watch
lucidscan serve --watch --debounce 500
```

### `lucidscan setup`

Configure AI tools to use LucidScan.

| Option | Description |
|--------|-------------|
| `--claude-code` | Configure Claude Code MCP settings |
| `--cursor` | Configure Cursor MCP settings |
| `--all` | Configure all supported AI tools |
| `--dry-run` | Show changes without applying |
| `--force` | Overwrite existing configuration |
| `--remove` | Remove LucidScan from tool configuration |

**Examples:**
```bash
lucidscan setup --claude-code
lucidscan setup --cursor
lucidscan setup --all
lucidscan setup --claude-code --remove
```

### `lucidscan help`

Display this documentation.

```bash
lucidscan help
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

LucidScan exposes these tools via MCP (Model Context Protocol) for AI agent integration:

### `scan`

Run quality checks on the codebase or specific files.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `domains` | array of strings | `["all"]` | Domains to check |
| `files` | array of strings | (none) | Specific files to check (relative paths) |
| `fix` | boolean | `false` | Apply auto-fixes for linting issues |

**Valid domains:** `linting`, `type_checking`, `security`, `sca`, `sast`, `iac`, `testing`, `coverage`, `all`

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
scan(domains=["linting", "type_checking"])
scan(domains=["all"], files=["src/main.py", "src/utils.py"])
scan(domains=["linting"], fix=true)
```

### `check_file`

Check a specific file and return issues with fix instructions. Automatically detects file type.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | Path to file (relative to project root) |

**Example:**
```
check_file(file_path="src/main.py")
```

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

Get current LucidScan status and configuration.

**Parameters:** None

**Response format:**
```json
{
  "project_root": "/path/to/project",
  "available_tools": {
    "scanners": ["trivy", "opengrep", "checkov"],
    "linters": ["ruff", "eslint", "biome"],
    "type_checkers": ["mypy", "pyright", "typescript"]
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
  "documentation": "# LucidScan Reference Documentation...",
  "format": "markdown"
}
```

---

## Configuration Reference (`lucidscan.yml`)

LucidScan auto-detects your project, but you can customize behavior with `lucidscan.yml` in your project root.

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
    tools:
      - name: ruff
        config: ruff.toml  # Optional custom config path
      - name: eslint
      - name: biome
      - name: checkstyle  # For Java projects

  type_checking:
    enabled: true
    tools:
      - name: mypy
        strict: true
      - name: pyright
      - name: typescript

  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca, container]
      - name: opengrep
        domains: [sast]
      - name: checkov
        domains: [iac]

  testing:
    enabled: true
    tools:
      - name: pytest
      - name: jest

  coverage:
    enabled: true
    threshold: 80  # Fail if coverage below this

# Failure thresholds (per-domain)
fail_on:
  linting: error      # error, none
  type_checking: error
  security: high      # critical, high, medium, low, info, none
  testing: any        # any, none
  coverage: any       # any, none

# Alternative: single threshold for all security
# fail_on: high

# Files/directories to ignore
ignore:
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/__pycache__/**"

# Output format
output:
  format: json  # json, table, sarif, summary
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
| `linting.tools` | array | (auto) | List of linting tools |
| `type_checking.enabled` | bool | true | Enable type checking |
| `type_checking.tools` | array | (auto) | List of type checkers |
| `security.enabled` | bool | true | Enable security scanning |
| `security.tools` | array | (auto) | Security tools with domains |
| `testing.enabled` | bool | false | Enable test execution |
| `testing.tools` | array | (auto) | Test frameworks |
| `coverage.enabled` | bool | false | Enable coverage analysis |
| `coverage.threshold` | int | 80 | Coverage percentage threshold |

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
| `coverage` | `any`, `none` |

#### `ignore`

Array of glob patterns for files/directories to skip:

```yaml
ignore:
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/test_*.py"
```

### Config File Locations

LucidScan searches for configuration in this order:

1. CLI `--config PATH` flag
2. Project root: `.lucidscan.yml`, `.lucidscan.yaml`, `lucidscan.yml`, `lucidscan.yaml`
3. Global: `~/.lucidscan/config/config.yml`
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
lucidscan setup --claude-code
```

This creates:
- `.mcp.json` - MCP server configuration
- `.claude/CLAUDE.md` - Instructions for Claude

Or manually create `.mcp.json`:
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

### Cursor

```bash
lucidscan setup --cursor
```

This creates:
- `~/.cursor/mcp.json` - MCP server configuration
- `.cursor/rules/lucidscan.mdc` - Cursor rules

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

---

## Best Practices for AI Agents

### Recommended Workflow

1. **After code changes**: Run fast scan
   ```
   scan(domains=["linting", "type_checking"], files=["changed/files.py"])
   ```

2. **Before commit**: Run full scan
   ```
   scan(domains=["all"])
   ```

3. **To fix issues**: Use auto-fix when available
   ```
   scan(domains=["linting"], fix=true)
   ```

4. **For detailed guidance**: Get fix instructions
   ```
   get_fix_instructions(issue_id="...")
   ```

### Domain Selection Guidelines

| Scenario | Recommended Domains |
|----------|---------------------|
| Quick style check | `["linting"]` |
| Before commit | `["all"]` |
| Python code review | `["linting", "type_checking", "security"]` |
| TypeScript code review | `["linting", "type_checking"]` |
| Security audit | `["sca", "sast", "iac"]` |
| Pre-release | `["all"]` with `fix=true` for linting |

### Handling Issues

1. **Priority order**: Fix high-priority issues first (priority 1-2)
2. **Auto-fixable**: Use `apply_fix()` for linting issues
3. **Manual fixes**: Follow `fix_steps` from instructions
4. **Re-scan**: Always re-scan after fixes to verify

### Performance Tips

- Use `files` parameter to scan only changed files
- Run `["linting", "type_checking"]` for quick feedback
- Reserve `["all"]` for comprehensive checks
- Use `fix=true` to auto-fix linting issues in one pass

---

## Supported Tools

### Linting

| Tool | Languages |
|------|-----------|
| Ruff | Python |
| ESLint | JavaScript, TypeScript |
| Biome | JavaScript, TypeScript, JSON |
| Checkstyle | Java |

### Type Checking

| Tool | Languages |
|------|-----------|
| mypy | Python |
| pyright | Python |
| TypeScript (tsc) | TypeScript |

### Security Scanning

| Tool | Domains |
|------|---------|
| Trivy | SCA (dependencies), Container images |
| OpenGrep | SAST (code patterns) |
| Checkov | IaC (Terraform, K8s, CloudFormation) |

### Testing

| Tool | Languages |
|------|-----------|
| pytest | Python |
| Jest | JavaScript, TypeScript |

### Coverage

| Tool | Languages |
|------|-----------|
| coverage.py | Python |
| Istanbul/nyc | JavaScript, TypeScript |
