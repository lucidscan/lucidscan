# LucidShark

## 1. Problem Statement

AI coding assistants have fundamentally changed software development. Tools like Claude Code, Cursor, GitHub Copilot, and Windsurf can generate hundreds of lines of code in seconds. But this speed creates a new problem: **developers cannot trust AI-generated code**.

The trust gap manifests in several ways:

- **Security vulnerabilities**: AI can introduce injection flaws, hardcoded secrets, insecure configurations
- **Code quality issues**: Linting errors, type mismatches, inconsistent patterns
- **Test gaps**: AI-generated code often lacks test coverage
- **Best practice violations**: AI doesn't know your team's conventions

Developers currently address this through manual review and fragmented tooling:

- Run ESLint, then Ruff, then mypy separately
- Run security scanners (Trivy, Semgrep) as an afterthought
- Copy-paste error messages back to the AI for fixes
- Repeat until the code passes all checks

This workflow is **slow, manual, and error-prone**. The feedback loop between AI agents and deterministic quality tools is broken.

### 1.1 The Missing Layer

What developers need is a **trust layer** that:

1. **Auto-configures** quality tools for any codebase with a single command
2. **Unifies** linting, security, testing, and coverage in one pipeline
3. **Feeds back to AI agents** in real-time, instructing them to fix issues automatically

This trust layer doesn't replace existing tools - it orchestrates them and bridges the gap between deterministic analysis and AI-assisted development.

### 1.2 Vision: Guardrails for AI Coding

LucidShark is the **trust layer for AI-assisted development**. It provides:

```
lucidshark init --all
→ Configures AI tools (Claude Code, Cursor)

"Autoconfigure LucidShark" (via AI)
→ AI analyzes your codebase
→ Asks you targeted questions
→ Generates lucidshark.yml configuration
AI writes code → LucidShark checks → AI fixes → repeat
```

The core insight: **deterministic tools catch mistakes reliably, but the feedback loop to AI agents is broken**. LucidShark bridges this gap by letting your AI assistant configure and run quality checks.

| Traditional Workflow | LucidShark Workflow |
|---------------------|-------------------|
| AI writes code | AI writes code |
| Human runs linters manually | LucidShark runs automatically |
| Human reads error output | LucidShark formats instructions |
| Human tells AI what to fix | LucidShark tells AI what to fix |
| AI fixes, human re-runs | AI fixes, LucidShark re-checks |
| Repeat 5-10 times | Automated loop |

---

## 2. Goals

LucidShark is a **unified code quality pipeline** with native AI agent integration. It achieves:

### 2.1 Zero-Config Initialization

```bash
# 1. Set up AI tools
lucidshark init --all

# 2. Ask your AI: "Autoconfigure LucidShark for this project"
```

The AI-assisted setup:
- Detects languages, frameworks, and existing tools in your codebase
- Asks targeted questions about coverage thresholds and strictness
- Generates a complete `lucidshark.yml` configuration

Alternative CLI approach:
```bash
lucidshark autoconfigure              # Interactive
lucidshark autoconfigure --non-interactive  # Use defaults
```

### 2.2 Unified Pipeline

A single configuration file controls:

| Domain | Tools | What It Catches |
|--------|-------|-----------------|
| **Linting** | Ruff, ESLint, Biome | Style, formatting, code smells |
| **Type Checking** | mypy, TypeScript, Pyright | Type errors |
| **Security** | Trivy, OpenGrep, Checkov | Vulnerabilities, misconfigurations |
| **Testing** | pytest, Jest, Go test | Test failures |
| **Coverage** | coverage.py, Istanbul, Go cover | Coverage gaps |
| **Duplication** | Duplo | Code clones, duplicate blocks |

All results normalized to a common schema. One exit code for automation.

### 2.3 AI Agent Integration

LucidShark bridges deterministic tools and AI agents via MCP (Model Context Protocol):

```bash
# Configure AI tools (creates MCP config and instructions)
lucidshark init --claude-code  # Configure Claude Code
lucidshark init --cursor       # Configure Cursor
lucidshark init --all          # Configure all AI tools

# Then restart your AI tool for changes to take effect
```

When configured:
- LucidShark runs as an MCP server that AI tools connect to
- Issues are formatted as structured instructions for the AI
- The AI receives: "Fix issue X in file Y by doing Z"
- Automatic feedback loop until code passes

---

## 3. Non-Goals

LucidShark focuses on orchestration and integration, not reimplementing tools:

### 3.1 Not a Scanner/Linter

LucidShark does **not** implement:
- Custom linting rules (uses ESLint, Ruff, etc.)
- Custom security scanning (uses Trivy, OpenGrep, etc.)
- Custom test runners (uses pytest, Jest, etc.)

It orchestrates existing best-in-class tools.

### 3.2 Not a Dashboard

LucidShark is **CLI-first**:
- No web dashboard
- No hosted service
- No accounts or authentication

Results are local. Output uses standard mechanisms (exit codes, SARIF).

### 3.3 Not AI-Driven

AI does **not** make decisions:
- AI cannot suppress findings
- AI cannot change severity levels
- AI cannot skip checks

LucidShark uses AI to **explain and fix** issues, not to decide what matters.

---

## 4. Target Users

### 4.1 Primary: Developers Using AI Coding Tools

Developers who:
- Use Claude Code, Cursor, Copilot, or similar AI assistants
- Want confidence that AI-generated code is production-ready
- Need fast feedback loops without manual tool orchestration
- Work in teams with shared quality standards

**Key motivation**: "I want to trust AI-generated code without manually running 5 different tools."

### 4.2 Secondary: DevOps Engineers

Engineers who:
- Want consistent quality gates across projects
- Need to onboard new projects quickly
- Manage tool versions and configurations

**Key motivation**: "I want to set up comprehensive quality checks in 5 minutes, not 5 hours."

### 4.3 Teams Adopting AI Coding

Teams that:
- Are increasing AI tool usage but worry about code quality
- Want guardrails before AI code reaches main branches
- Need visibility into what AI is introducing

**Key motivation**: "We want AI velocity with human-level quality."

---

## 5. Core Product Requirements

### 5.1 The `autoconfigure` Command

The `lucidshark autoconfigure` command is the primary entry point for project setup. It MUST:

#### 5.1.1 Codebase Detection

Automatically detect:
- **Languages**: Python, JavaScript/TypeScript, Go, Rust, Java, etc.
- **Package managers**: npm, pip, cargo, go.mod, etc.
- **Frameworks**: React, Django, FastAPI, Express, etc.
- **Existing tools**: .eslintrc, pyproject.toml, ruff.toml, etc.

Detection MUST be fast (<5 seconds for typical repos).

#### 5.1.2 Interactive Configuration

Ask targeted questions based on detection:

```
Detected: Python 3.11, FastAPI, pytest

? Linter: [Ruff (recommended)] / Flake8 / Skip
? Type checker: [mypy (recommended)] / Pyright / Skip
? Security scanner: [Trivy + OpenGrep (recommended)] / Trivy only / Skip
? Test runner: [pytest (detected)] / Skip
? Coverage threshold: [80%] / Custom / Skip
```

Questions MUST:
- Respect existing configuration (don't ask about tools already configured)
- Provide sensible defaults
- Allow skipping any category
- Complete in <2 minutes for typical setups

#### 5.1.3 Configuration Generation

Generate `lucidshark.yml` with all settings:

```yaml
# Generated by lucidshark autoconfigure
version: 1

project:
  name: my-fastapi-app
  languages: [python]

pipeline:
  linting:
    enabled: true
    tools:
      - name: ruff
        config: pyproject.toml

  type_checking:
    enabled: true
    tools:
      - name: mypy
        strict: true

  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]

  testing:
    enabled: true
    tools:
      - name: pytest
        args: ["-v"]

  coverage:
    enabled: true
    threshold: 80
    tools:
      - name: coverage_py

  duplication:
    enabled: true
    threshold: 10.0  # Max allowed duplication percentage
    min_lines: 4     # Minimum lines for a duplicate block
    tools:
      - name: duplo

fail_on:
  linting: error
  type_checking: error
  security: high
  testing: any
  coverage: below_threshold  # Fail if coverage below pipeline.coverage.threshold
  duplication: above_threshold  # Fail if duplication exceeds pipeline.duplication.threshold

ignore:
  - "**/__pycache__/**"
  - "**/node_modules/**"
  - "**/.venv/**"
```

### 5.2 The `scan` Command

```bash
lucidshark scan [--fix] [--format FORMAT]
```

#### 5.2.1 Pipeline Execution

Execute the configured pipeline in order:

1. **Linting** → Run configured linters
2. **Type Checking** → Run type checkers
3. **Security** → Run security scanners
4. **Testing** → Run test suites
5. **Coverage** → Check coverage thresholds
6. **Duplication** → Detect code clones

Each stage produces normalized results. Stages can run in parallel where independent.

#### 5.2.2 Partial Scanning (Default Behavior)

LucidShark scans only changed files (uncommitted changes) by default. Use `--all-files` (CLI) or `all_files=true` (MCP) for full project scans.

| Domain | Partial Scan Support | Behavior |
|--------|---------------------|----------|
| **Linting** | ✅ Full | Only lints changed/specified files |
| **Type Checking** | ⚠️ Partial | mypy/pyright yes, tsc always full |
| **SAST** | ✅ Full | OpenGrep scans only changed/specified files |
| **SCA** | ❌ None | Trivy dependency scan always project-wide |
| **IaC** | ❌ None | Checkov always project-wide |
| **Testing** | ✅ Full | Can run specific test files |
| **Coverage** | ⚠️ Partial | Run full tests, filter output |

**Default workflow (partial scans):**
- After modifying files - scans changed files automatically
- During iterative development
- When fixing specific issues

**When to use full scans (`--all-files`):**
- Before committing code
- For comprehensive security audits
- For release preparation

#### 5.2.3 Unified Output

All results normalized to common schema:

```json
{
  "issues": [
    {
      "id": "ruff-E501-abc123",
      "domain": "linting",
      "source_tool": "ruff",
      "severity": "medium",
      "rule_id": "E501",
      "title": "[E501] Line too long (120 > 88)",
      "description": "Line too long (120 > 88)",
      "documentation_url": "https://docs.astral.sh/ruff/rules/line-too-long",
      "file_path": "src/main.py",
      "line_start": 42,
      "column_start": 89,
      "fixable": true,
      "suggested_fix": "Split line or increase line length limit",
      "metadata": {}
    }
  ],
  "summary": {
    "linting": { "errors": 0, "warnings": 3 },
    "type_checking": { "errors": 1, "warnings": 0 },
    "security": { "critical": 0, "high": 1, "medium": 2 },
    "testing": { "passed": 42, "failed": 0 },
    "coverage": { "percentage": 85, "threshold": 80, "passed": true }
  },
  "passed": false,
  "exit_code": 1
}
```

#### 5.2.4 Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Issues found above threshold |
| 2 | Tool execution error |
| 3 | Configuration error |

#### 5.2.5 Auto-Fix Mode

```bash
lucidshark scan --fix
```

When `--fix` is enabled:
- Run fixable linters in fix mode (ruff --fix, eslint --fix)
- Report what was fixed
- Re-run checks to verify fixes

### 5.3 The `serve` Command (AI Integration)

```bash
lucidshark serve [--mcp] [--port PORT]
```

#### 5.3.1 MCP Server Mode

Run as an MCP (Model Context Protocol) server that AI tools can connect to:

```bash
lucidshark serve --mcp
```

The MCP server provides:
- `scan` tool: Run full pipeline or specific domains
- `check_file` tool: Check a specific file
- `get_issues` tool: Get current issues
- `explain_issue` tool: Get AI-friendly explanation of an issue

#### 5.3.2 File Watcher Mode

```bash
lucidshark serve --watch
```

Watch for file changes and run relevant checks:
- On Python file change → Run Ruff, mypy for that file
- On JS/TS file change → Run ESLint, TypeScript for that file
- Debounce rapid changes

#### 5.3.3 AI Instruction Format

When serving AI agents, issues are formatted as actionable instructions:

```json
{
  "instruction": "Fix security vulnerability in src/api/auth.py",
  "issue": {
    "type": "security",
    "severity": "high",
    "rule": "opengrep.python.security.hardcoded-password"
  },
  "location": {
    "file": "src/api/auth.py",
    "line": 23,
    "code_snippet": "password = \"admin123\""
  },
  "fix_guidance": {
    "description": "Hardcoded password detected. Move to environment variable.",
    "suggested_fix": "password = os.environ.get('DB_PASSWORD')",
    "steps": [
      "Import os module if not already imported",
      "Replace hardcoded password with os.environ.get('DB_PASSWORD')",
      "Add DB_PASSWORD to .env.example with placeholder value",
      "Document the required environment variable"
    ]
  }
}
```

### 5.4 Configuration

#### 5.4.1 Configuration File

`lucidshark.yml` in project root:

```yaml
version: 1

project:
  name: string
  languages: [string]

pipeline:
  linting:
    enabled: boolean
    tools:
      - name: string
        config: string  # Path to tool config
        args: [string]  # Additional arguments

  type_checking:
    enabled: boolean
    tools:
      - name: string
        strict: boolean
        args: [string]

  security:
    enabled: boolean
    tools:
      - name: string
        domains: [sca, sast, iac, container]
        severity_threshold: string

  testing:
    enabled: boolean
    tools:
      - name: string
        args: [string]
        coverage: boolean

  coverage:
    enabled: boolean
    threshold: number  # Default: 80
    tools:
      - name: string  # coverage_py for Python, istanbul for JS/TS

  duplication:
    enabled: boolean
    threshold: number  # Default: 10.0 (max allowed duplication %)
    min_lines: number  # Default: 4 (minimum lines for duplicate block)
    min_chars: number  # Default: 3 (minimum characters per line)
    exclude: [string]  # Patterns to exclude from duplication scan
    tools:
      - name: string  # duplo

fail_on:
  linting: error | none
  type_checking: error | none
  security: critical | high | medium | low | info | none
  testing: any | none
  coverage: below_threshold | any | none
  duplication: above_threshold | any | none | percentage (e.g., "5%")

ignore:
  - string  # Glob patterns

output:
  format: json | table | sarif | summary
```

> **Note**: AI tool integration is configured via `lucidshark init --claude-code` or `lucidshark init --cursor`, not through lucidshark.yml.

#### 5.4.2 Ignore File

`.lucidsharkignore` supports gitignore syntax:

```
# Dependencies
node_modules/
.venv/
vendor/

# Build artifacts
dist/
build/
*.pyc

# Generated files
*.generated.ts
```

#### 5.4.3 Inline Ignores

Support tool-native inline ignores:
- Ruff: `# noqa: E501`
- ESLint: `// eslint-disable-next-line`
- OpenGrep: `# nosemgrep`
- Checkov: `# checkov:skip=CKV_AWS_1`

### 5.5 Tool Management

#### 5.5.1 Automatic Installation

Tools are installed automatically when needed:

```bash
$ lucidshark scan
Installing ruff 0.8.0... done
Installing trivy 0.58.0... done
Running pipeline...
```

Installation uses:
- pip for Python tools (ruff, mypy, coverage)
- npm for JS tools (eslint, typescript) - only if package.json exists
- Direct binary download for standalone tools (trivy, opengrep)

#### 5.5.2 Version Pinning

LucidShark pins tool versions internally for reproducibility. Versions are defined in `pyproject.toml` under `[tool.lucidshark.tools]`:

```toml
# pyproject.toml
[tool.lucidshark.tools]
trivy = "0.68.2"
opengrep = "1.15.0"
checkov = "3.2.499"
ruff = "0.14.11"
biome = "2.3.11"
```

When installed as a package, LucidShark uses hardcoded fallback versions.

#### 5.5.3 Binary Cache

Binaries cached at `~/.lucidshark/`:

```
~/.lucidshark/
├── bin/
│   ├── trivy/0.58.0/trivy
│   ├── opengrep/1.12.0/opengrep
│   └── checkov/3.2.0/checkov
├── cache/
│   └── trivy/db/  # Vulnerability database
└── config.yml     # Global settings
```

---

## 6. System Architecture

### 6.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        LucidShark CLI                            │
├─────────────────────────────────────────────────────────────────┤
│  Commands                                                       │
│  ├── init      → Codebase detection, config generation          │
│  ├── scan      → Pipeline execution                             │
│  ├── serve     → MCP server / file watcher                      │
│  └── status    → Show configuration and tool versions           │
├─────────────────────────────────────────────────────────────────┤
│  Pipeline Orchestrator                                          │
│  ├── Stage execution (lint → typecheck → security → test)       │
│  ├── Parallel execution where possible                          │
│  ├── Result aggregation                                         │
│  └── Threshold evaluation                                       │
├─────────────────────────────────────────────────────────────────┤
│  Tool Plugins                                                   │
│  ├── Linting:     RuffPlugin, ESLintPlugin, BiomePlugin         │
│  ├── TypeCheck:   MypyPlugin, TypeScriptPlugin, PyrightPlugin   │
│  ├── Security:    TrivyPlugin, OpenGrepPlugin, CheckovPlugin    │
│  ├── Testing:     PytestPlugin, JestPlugin, GoTestPlugin        │
│  ├── Coverage:    CoveragePlugin, IstanbulPlugin, GoCoverPlugin │
│  └── Duplication: DuploPlugin                                   │
├─────────────────────────────────────────────────────────────────┤
│  Output Layer                                                   │
│  ├── Reporters:   JSON, Table, SARIF, Summary                   │
│  └── AI Format:   Structured instructions for AI agents         │
├─────────────────────────────────────────────────────────────────┤
│  AI Integration Layer                                           │
│  ├── MCP Server:  Tools for AI agents to invoke                 │
│  ├── File Watcher: Real-time checking                           │
│  └── Instruction Formatter: Issue → actionable fix guidance     │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Plugin Interface

All tool plugins implement a common interface:

```python
class ToolPlugin(ABC):
    """Base class for all tool plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier (e.g., 'ruff', 'trivy')."""

    @property
    @abstractmethod
    def domain(self) -> ToolDomain:
        """Domain: LINTING, TYPE_CHECKING, SECURITY, TESTING, COVERAGE."""

    @property
    @abstractmethod
    def languages(self) -> list[str]:
        """Languages this plugin supports."""

    @abstractmethod
    def detect(self, context: ProjectContext) -> bool:
        """Return True if this plugin is applicable to the project."""

    @abstractmethod
    def ensure_installed(self) -> Path:
        """Ensure the tool is installed, return path to binary."""

    @abstractmethod
    def run(self, context: ScanContext) -> list[Issue]:
        """Execute the tool and return normalized issues."""

    def fix(self, context: ScanContext) -> FixResult:
        """Run in fix mode if supported. Default: not supported."""
        raise NotImplementedError("This tool does not support auto-fix")
```

### 6.3 Codebase Detector

The codebase detector identifies project characteristics:

```python
@dataclass
class ProjectContext:
    root: Path
    languages: list[str]           # ["python", "typescript"]
    package_managers: list[str]    # ["pip", "npm"]
    frameworks: list[str]          # ["fastapi", "react"]
    existing_tools: dict[str, Path]  # {"ruff": "pyproject.toml"}
    git_root: Path | None
```

Detection strategy:
1. Scan for marker files (package.json, pyproject.toml, go.mod, etc.)
2. Parse lockfiles to identify dependencies
3. Check for existing tool configurations

### 6.4 MCP Server

The MCP server exposes tools for AI agents. By default, scans only changed files (uncommitted changes):

```python
class LucidSharkMCPServer:
    """MCP server for AI agent integration."""

    @tool
    def scan(
        self,
        domains: list[str] = ["all"],
        files: list[str] | None = None,
        all_files: bool = False,
        fix: bool = False
    ) -> ScanResult:
        """Run quality checks on the codebase or specific files.

        Default Behavior: Scans only changed files (uncommitted changes).

        Parameters:
        - files: Override to scan specific files only
        - all_files: Set to True for full project scan
        - fix: Apply auto-fixes for linting issues

        Note: SCA (dependency scanning) always runs project-wide.
        """

    @tool
    def check_file(self, file_path: str) -> list[Issue]:
        """Check a specific file and return issues.

        Convenience method for single-file scanning.
        Automatically detects the file type and runs appropriate checks.
        """

    @tool
    def get_fix_instructions(self, issue_id: str) -> FixInstruction:
        """Get detailed fix instructions for a specific issue."""

    @tool
    def apply_fix(self, issue_id: str) -> FixResult:
        """Apply auto-fix for a fixable issue."""
```

**Partial Scanning Support (Default Behavior):**

| Domain | Partial Scan | Notes |
|--------|--------------|-------|
| Linting | ✅ Yes | All linters support file-level scanning |
| Type Checking | ⚠️ Partial | mypy/pyright yes, tsc no |
| SAST | ✅ Yes | OpenGrep supports file-level scanning |
| SCA | ❌ No | Trivy dependency scan always project-wide |
| IaC | ❌ No | Checkov always project-wide |
| Testing | ✅ Yes | Can run specific test files |
| Coverage | ⚠️ Partial | Run full tests, filter output |
| Duplication | ❌ No | Duplo always scans project-wide for cross-file duplicates |

### 6.5 Unified Issue Schema

All tools normalize to this schema:

```python
@dataclass
class UnifiedIssue:
    # Core identification
    id: str                        # Unique identifier
    domain: DomainType             # linting, type_checking, sast, sca, iac, etc.
    source_tool: str               # "ruff", "trivy", "mypy", etc.
    severity: Severity             # CRITICAL, HIGH, MEDIUM, LOW, INFO

    # Content
    rule_id: str                   # Rule identifier (E501, CVE-2024-1234, CKV_AWS_1)
    title: str                     # Short issue title
    description: str               # Detailed description
    recommendation: str | None     # How to fix
    documentation_url: str | None  # Link to rule documentation

    # Location
    file_path: Path | None         # File containing the issue
    line_start: int | None         # Starting line number
    line_end: int | None           # Ending line number
    column_start: int | None       # Starting column
    column_end: int | None         # Ending column
    code_snippet: str | None       # Relevant code

    # Fix information
    fixable: bool                  # Whether auto-fix is available
    suggested_fix: str | None      # Suggested code fix

    # Domain-specific fields
    dependency: str | None         # For SCA (e.g., "lodash@4.17.20")
    iac_resource: str | None       # For IaC (e.g., "aws_s3_bucket.public")

    # Extensibility
    metadata: dict[str, Any]       # Tool-specific data
```

---

## 7. AI Integration Specification

### 7.1 Integration Modes

LucidShark supports multiple integration modes with AI coding tools:

#### 7.1.1 MCP Server Mode (Recommended)

LucidShark runs as an MCP server that AI tools connect to:

```bash
lucidshark serve --mcp
```

**For Claude Code** (`~/.claude/mcp_servers.json`):
```json
{
  "lucidshark": {
    "command": "lucidshark",
    "args": ["serve", "--mcp"],
    "cwd": "/path/to/project"
  }
}
```

**For Cursor** (MCP configuration):
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

#### 7.1.2 Hooks Mode

LucidShark can run via editor hooks:

**Claude Code hooks** (`~/.claude/settings.json`):
```json
{
  "hooks": {
    "post_tool_call": [
      {
        "match": { "tool": "write", "edit": "*" },
        "command": "lucidshark scan --files $CHANGED_FILES --format ai"
      }
    ]
  }
}
```

#### 7.1.3 File Watcher Mode

For editors without MCP/hooks support:

```bash
lucidshark serve --watch --output /tmp/lucidshark-issues.json
```

Editor plugins can read the output file and display issues.

### 7.2 AI Instruction Format

When providing feedback to AI agents, issues are formatted for actionability:

```json
{
  "total_issues": 3,
  "blocking": true,
  "instructions": [
    {
      "priority": 1,
      "action": "FIX_SECURITY_VULNERABILITY",
      "summary": "Hardcoded password in auth.py:23",
      "details": {
        "issue_type": "security",
        "severity": "high",
        "rule": "opengrep.python.security.hardcoded-password",
        "file": "src/api/auth.py",
        "line": 23,
        "current_code": "password = \"admin123\"",
        "problem": "Hardcoded passwords are a security risk. They can be extracted from source code and version history.",
        "fix_steps": [
          "Add 'import os' at the top of the file if not present",
          "Replace the hardcoded password with: password = os.environ.get('DB_PASSWORD')",
          "Ensure DB_PASSWORD is set in your environment or .env file"
        ],
        "fixed_code": "password = os.environ.get('DB_PASSWORD')"
      }
    },
    {
      "priority": 2,
      "action": "FIX_TYPE_ERROR",
      "summary": "Type mismatch in utils.py:45",
      "details": {
        "issue_type": "type_checking",
        "severity": "error",
        "rule": "mypy.arg-type",
        "file": "src/utils.py",
        "line": 45,
        "current_code": "process_items(items: str)",
        "problem": "Argument 'items' has type 'str' but expected 'list[str]'",
        "fix_steps": [
          "Change the function call to pass a list instead of a string",
          "Or update the function signature if it should accept a string"
        ]
      }
    }
  ]
}
```

### 7.3 Feedback Loop

The AI integration creates an automated feedback loop with partial scanning for speed:

```
1. AI writes/modifies code
2. LucidShark runs partial scan on changed files (via MCP files parameter)
3. Issues are formatted as instructions
4. AI receives instructions and applies fixes
5. LucidShark re-checks (partial scan on fixed files)
6. Repeat until clean
7. Before commit: run full scan for comprehensive check
```

The feedback loop is driven by instructions provided to the AI tool via `lucidshark init`, which creates:
- `.claude/CLAUDE.md` for Claude Code with scan workflow instructions
- `.cursor/rules/lucidshark.mdc` for Cursor with auto-scan rules

These instruct the AI to:
- Run **default scans** (changed files only) after code changes for fast feedback
- Run **full scans** (with `all_files=true`) before commits for comprehensive checking

### 7.4 Partial Scanning for AI Agents (Default Behavior)

LucidShark scans only changed files by default, enabling fast feedback loops:

| Scenario | Scan Type | Example |
|----------|-----------|---------|
| After editing files | Default (changed files) | `scan(domains=["linting", "type_checking"])` |
| Single file check | Partial | `check_file(file_path="src/main.py")` |
| Specific files | Partial | `scan(domains=["linting"], files=["src/a.py", "src/b.py"])` |
| Before commit | Full | `scan(domains=["all"], all_files=true)` |
| Security audit | Full | `scan(domains=["sca", "sast", "iac"], all_files=true)` |

**Tool-Level Partial Scan Support:**

| Tool Category | Tools | Partial Scan Support |
|---------------|-------|---------------------|
| **Linting** | Ruff, ESLint, Biome, Checkstyle | ✅ All support file args |
| **Type Checking** | mypy, pyright | ✅ Support file args |
| **Type Checking** | TypeScript (tsc) | ❌ Project-wide only |
| **SAST** | OpenGrep | ✅ Supports file args |
| **SCA** | Trivy | ❌ Project-wide by design |
| **IaC** | Checkov | ❌ Project-wide by design |
| **Testing** | pytest, Jest, Playwright | ✅ Support file args |
| **Testing** | Karma | ❌ Config-based only |
| **Coverage** | coverage.py, Istanbul | ⚠️ Run full, filter output |
| **Duplication** | Duplo | ❌ Project-wide by design |

---

## 8. CLI Specification

### 8.1 Global Options

```
lucidshark [OPTIONS] COMMAND [ARGS]

Global Options:
  --config, -c PATH    Configuration file (default: lucidshark.yml)
  --verbose, -v        Verbose output
  --quiet, -q          Minimal output
  --debug              Debug mode with full traces
  --version            Show version
  --help, -h           Show help
```

### 8.2 Commands

#### 8.2.1 `init`

```
lucidshark init [OPTIONS]

Configure AI tools (Claude Code, Cursor) to use LucidShark.

Options:
  --claude-code        Configure Claude Code MCP settings
  --cursor             Configure Cursor MCP settings
  --all                Configure all supported AI tools
  --dry-run            Show changes without applying
  --force              Overwrite existing configuration
  --remove             Remove LucidShark from tool configuration

Examples:
  lucidshark init --claude-code      # Configure Claude Code
  lucidshark init --cursor           # Configure Cursor
  lucidshark init --all              # Configure all AI tools
```

#### 8.2.2 `autoconfigure`

```
lucidshark autoconfigure [OPTIONS]

Auto-configure LucidShark for the current project (detect languages, generate lucidshark.yml).

Options:
  --non-interactive    Use defaults without prompting
  --force              Overwrite existing configuration

Examples:
  lucidshark autoconfigure                    # Interactive setup
  lucidshark autoconfigure --non-interactive  # Use all defaults
```

#### 8.2.3 `scan`

```
lucidshark scan [OPTIONS] [PATHS...]

Run the quality pipeline. By default, scans only changed files (uncommitted changes).

Options:
  --domain, -d DOMAIN  Run specific domain (linting, security, testing, etc.)
  --files FILE...      Check specific files only
  --all-files          Scan entire project instead of just changed files
  --fix                Apply auto-fixes where possible
  --stream             Stream tool output in real-time as scans run
  --format FORMAT      Output format (table, json, sarif, ai)
  --fail-on LEVEL      Override fail threshold

Examples:
  lucidshark scan --linting          # Lint changed files (default)
  lucidshark scan --all --all-files  # Full project scan
  lucidshark scan --files src/a.py   # Scan specific files
  lucidshark scan --fix              # Auto-fix changed files
  lucidshark scan --stream           # See live output
  lucidshark scan --format json      # JSON output
```

#### 8.2.4 `serve`

```
lucidshark serve [OPTIONS]

Run LucidShark as a server for AI integration.

Options:
  --mcp                Run as MCP server
  --watch              Watch files for changes
  --port PORT          HTTP port for status endpoint (default: 7432)

Examples:
  lucidshark serve --mcp             # MCP server for Claude Code/Cursor
  lucidshark serve --watch           # File watcher mode
```

#### 8.2.5 `status`

```
lucidshark status [OPTIONS]

Show current configuration and tool status.

Options:
  --tools              Show installed tool versions
  --config             Show effective configuration

Examples:
  lucidshark status                  # Overview
  lucidshark status --tools          # Tool versions
```

### 8.3 Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success, no issues above threshold |
| 1 | Issues found above threshold |
| 2 | Tool execution error |
| 3 | Configuration error |
| 4 | Installation/bootstrap error |

---

## 9. Supported Tools

### 9.1 Linting

| Tool | Languages | Install Method | Partial Scan |
|------|-----------|----------------|--------------|
| Ruff | Python | pip / binary | ✅ Yes |
| ESLint | JavaScript, TypeScript | npm | ✅ Yes |
| Biome | JavaScript, TypeScript, JSON | npm / binary | ✅ Yes |
| Checkstyle | Java | binary (jar) | ✅ Yes |

All linting tools support partial scanning via the `files` parameter.

### 9.2 Type Checking

| Tool | Languages | Install Method | Partial Scan |
|------|-----------|----------------|--------------|
| mypy | Python | pip | ✅ Yes |
| Pyright | Python | pip / npm / binary | ✅ Yes |
| TypeScript (tsc) | TypeScript | npm | ❌ No |

**Note:** TypeScript (tsc) does not support file-level CLI arguments - it uses `tsconfig.json` to determine what to check.

### 9.3 Security

| Tool | Domains | Install Method | Partial Scan |
|------|---------|----------------|--------------|
| Trivy | SCA, Container | binary | ❌ No |
| OpenGrep | SAST | binary | ✅ Yes |
| Checkov | IaC | pip / binary | ❌ No |

**Note:** OpenGrep (SAST) supports partial scanning and scans only changed files by default. Trivy (SCA) always scans the entire project - dependency analysis requires full project context. Checkov (IaC) also scans project-wide.

### 9.4 Testing

| Tool | Languages | Install Method | Partial Scan |
|------|-----------|----------------|--------------|
| pytest | Python | pip | ✅ Yes |
| Jest | JavaScript, TypeScript | npm | ✅ Yes |
| Karma | JavaScript, TypeScript (Angular) | npm | ❌ No |
| Playwright | JavaScript, TypeScript (E2E) | npm | ✅ Yes |

**Note:** While most test runners support running specific test files, running the full test suite is recommended before commits to catch regressions.

### 9.5 Coverage

| Tool | Languages | Install Method | Partial Scan |
|------|-----------|----------------|--------------|
| coverage.py | Python | pip | ⚠️ Partial |
| Istanbul/nyc | JavaScript, TypeScript | npm | ⚠️ Partial |

**Note:** Coverage tools can run specific tests but measure all executed code. For partial scanning, coverage output can be filtered to show only changed files.

### 9.6 Duplication Detection

| Tool | Languages | Install Method | Partial Scan |
|------|-----------|----------------|--------------|
| Duplo | Python, Rust, Java, JavaScript, TypeScript, C, C++, C#, Go, Ruby, Erlang, VB, HTML, CSS | binary | ❌ No |

**Note:** Duplication detection always scans the entire project to find cross-file duplicates. Use the `pipeline.duplication.exclude` configuration to skip generated or vendor files (e.g., `htmlcov/**`, `generated/**`).

---

## 10. Development Phases

### Phase 1: Foundation ✅ COMPLETE

**Goal**: Core pipeline with `init` and `scan` commands

- [x] Codebase detector (languages, frameworks, existing tools)
- [x] Configuration generator (`lucidshark init`)
- [x] Pipeline orchestrator
- [x] Initial tool plugins:
  - [x] Ruff (Python linting)
  - [x] ESLint (JS/TS linting)
  - [x] mypy (Python type checking)
  - [x] Trivy (SCA, container security)
  - [x] OpenGrep (SAST)
  - [x] pytest (Python testing)
- [x] Reporters: Table, JSON, SARIF

**Milestone**: `lucidshark init && lucidshark scan` works end-to-end

### Phase 2: Expanded Coverage ✅ COMPLETE

**Goal**: More tools

- [x] Additional tool plugins:
  - [x] Biome (JS/TS)
  - [x] Checkov (IaC)
  - [x] Checkstyle (Java)
  - [x] Jest (JS/TS testing)
  - [x] Karma (Angular testing)
  - [x] Playwright (E2E testing)
  - [x] coverage.py (Python coverage)
  - [x] Istanbul (JS/TS coverage)
  - [x] pyright (Python type checking)
  - [x] TypeScript (tsc)
  - [x] Duplo (duplication detection)
- [x] Auto-fix mode (`--fix`)

**Milestone**: Support for Python, JavaScript/TypeScript, Java projects

### Phase 3: AI Integration ✅ COMPLETE

**Goal**: MCP server and AI feedback loop

- [x] MCP server implementation (`lucidshark serve --mcp`)
- [x] AI instruction formatter
- [x] File watcher mode
- [x] Claude Code integration guide
- [x] Cursor integration guide
- [x] Feedback loop configuration

**Milestone**: AI agents can invoke LucidShark and receive fix instructions

### Phase 4: Polish

**Goal**: Production readiness

- [ ] Comprehensive documentation
- [ ] Plugin SDK for third-party tools
- [ ] Performance optimization (caching, incremental checks)
- [ ] Telemetry (opt-in, anonymized)
- [ ] Error handling hardening

**Milestone**: v1.0 release

---

## 12. Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| **Domain** | Category of checks: linting, type checking, security, testing, coverage |
| **Tool** | Underlying program (Ruff, Trivy, pytest) |
| **Plugin** | LucidShark adapter for a tool |
| **Pipeline** | Sequence of domains to execute |
| **Issue** | Single finding from any tool |
| **MCP** | Model Context Protocol, standard for AI tool integration |

### B. Configuration Schema

Full JSON Schema for `lucidshark.yml` available at:
`https://lucidshark.dev/schema/v1.json`

### C. Environment Variables

| Variable | Purpose |
|----------|---------|
| `LUCIDSHARK_CONFIG` | Path to config file |
| `LUCIDSHARK_CACHE_DIR` | Cache directory (default: `~/.lucidshark`) |
| `LUCIDSHARK_NO_COLOR` | Disable colored output |
