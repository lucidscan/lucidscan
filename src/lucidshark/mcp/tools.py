"""MCP tool executor for LucidShark operations.

Executes LucidShark scan operations and formats results for AI agents.
"""

from __future__ import annotations

import asyncio
import functools
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from lucidshark.config import LucidSharkConfig
from lucidshark.core.domain_runner import (
    DomainRunner,
    detect_language,
    get_domains_for_language,
)
from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    DomainType,
    ScanContext,
    ScanDomain,
    ToolDomain,
    UnifiedIssue,
    parse_domain,
)
from lucidshark.core.streaming import (
    CLIStreamHandler,
    MCPStreamHandler,
    StreamEvent,
    StreamHandler,
)
from lucidshark.mcp.formatter import InstructionFormatter

LOGGER = get_logger(__name__)


class MCPToolExecutor:
    """Executes LucidShark operations for MCP tools."""

    def __init__(self, project_root: Path, config: LucidSharkConfig):
        """Initialize MCPToolExecutor.

        Args:
            project_root: Project root directory.
            config: LucidShark configuration.
        """
        self.project_root = project_root
        self.config = config
        self.instruction_formatter = InstructionFormatter()
        self._issue_cache: Dict[str, UnifiedIssue] = {}
        self._tools_bootstrapped = False
        # Use DomainRunner with debug logging for MCP (less verbose)
        self._runner = DomainRunner(project_root, config, log_level="debug")

    def _bootstrap_security_tools(self, security_domains: List[ScanDomain]) -> None:
        """Ensure security tool binaries are available.

        Downloads tools if not already present. Called before first scan
        to ensure tools are ready before async scan operations begin.

        Args:
            security_domains: List of security domains that need to be bootstrapped.
        """
        if self._tools_bootstrapped:
            return

        from lucidshark.plugins.scanners import get_scanner_plugin

        # Get unique scanners needed based on requested security domains only
        scanners_to_bootstrap: set[str] = set()
        for domain in security_domains:
            plugin_name = self.config.get_plugin_for_domain(domain.value)
            if plugin_name:
                scanners_to_bootstrap.add(plugin_name)

        for scanner_name in scanners_to_bootstrap:
            try:
                LOGGER.info(f"Bootstrapping {scanner_name}...")
                scanner = get_scanner_plugin(scanner_name, project_root=self.project_root)
                if scanner:
                    scanner.ensure_binary()
                    LOGGER.debug(f"{scanner_name} ready")
            except Exception as e:
                LOGGER.error(f"Failed to bootstrap {scanner_name}: {e}")

        self._tools_bootstrapped = True

    async def scan(
        self,
        domains: List[str],
        files: Optional[List[str]] = None,
        all_files: bool = False,
        fix: bool = False,
        on_progress: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
    ) -> Dict[str, Any]:
        """Execute scan and return AI-formatted results.

        Default behavior: Scans only changed files (uncommitted changes).
        - If `files` is provided, scan only those specific files
        - If `all_files` is True, scan entire project
        - Otherwise, scan only changed files (git diff)

        Args:
            domains: List of domain names to scan (e.g., ["linting", "security"]).
            files: Optional list of specific files to scan.
            all_files: If True, scan entire project instead of just changed files.
            fix: Whether to apply auto-fixes (linting only).
            on_progress: Optional async callback for progress events (MCP notifications).

        Returns:
            Structured scan result with AI instructions.
        """
        # Convert domain strings to ToolDomain enums
        enabled_domains = self._parse_domains(domains)

        # Bootstrap security tools if needed (before async operations)
        security_domains = [d for d in enabled_domains if isinstance(d, ScanDomain)]
        if security_domains and not self._tools_bootstrapped:
            if on_progress:
                await on_progress({
                    "tool": "lucidshark",
                    "content": "Downloading security tools...",
                    "progress": 0,
                    "total": None,
                })
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._bootstrap_security_tools, security_domains)

        # Create stream handler for progress output
        stream_handler: Optional[StreamHandler] = None

        if on_progress:
            # Use MCP stream handler for async notifications
            async def on_event(event: StreamEvent) -> None:
                event_dict = {
                    "tool": event.tool_name,
                    "type": event.stream_type.value,
                    "content": event.content,
                }
                await on_progress(event_dict)

            stream_handler = MCPStreamHandler(on_event=on_event)
        else:
            # Default: write progress to stderr
            stream_handler = CLIStreamHandler(
                output=sys.stderr,
                show_output=True,
                use_rich=False,
            )

        # Build context with stream handler and partial scanning logic
        context = self._build_context(enabled_domains, files, all_files, stream_handler)

        # Run scans in parallel for different domains
        all_issues: List[UnifiedIssue] = []

        # Build list of tasks with their domain names for progress tracking
        tasks_with_names: List[tuple[str, Coroutine]] = []
        if ToolDomain.LINTING in enabled_domains:
            tasks_with_names.append(("linting", self._run_linting(context, fix)))
        if ToolDomain.TYPE_CHECKING in enabled_domains:
            tasks_with_names.append(("type_checking", self._run_type_checking(context)))
        if ScanDomain.SAST in enabled_domains:
            tasks_with_names.append(("sast", self._run_security(context, ScanDomain.SAST)))
        if ScanDomain.SCA in enabled_domains:
            tasks_with_names.append(("sca", self._run_security(context, ScanDomain.SCA)))
        if ScanDomain.IAC in enabled_domains:
            tasks_with_names.append(("iac", self._run_security(context, ScanDomain.IAC)))
        if ScanDomain.CONTAINER in enabled_domains:
            tasks_with_names.append(("container", self._run_security(context, ScanDomain.CONTAINER)))

        # Check if both testing and coverage are enabled
        testing_enabled = ToolDomain.TESTING in enabled_domains
        coverage_enabled = ToolDomain.COVERAGE in enabled_domains

        # When both testing and coverage are enabled, run tests WITH coverage
        # instrumentation (via testing domain) to generate .coverage file.
        # Then coverage domain just reads the file to generate reports.
        if testing_enabled:
            # Run tests, with coverage instrumentation if coverage is also enabled
            tasks_with_names.append(
                ("testing", self._run_testing(context, with_coverage=coverage_enabled))
            )

        if coverage_enabled:
            # If testing ran with coverage, just read the .coverage file
            # Otherwise, run tests to generate coverage data
            run_tests_for_coverage = not testing_enabled
            tasks_with_names.append(
                ("coverage", self._run_coverage(context, run_tests=run_tests_for_coverage))
            )

        # Check if duplication detection is enabled
        duplication_enabled = ToolDomain.DUPLICATION in enabled_domains
        if duplication_enabled:
            tasks_with_names.append(("duplication", self._run_duplication(context)))

        total_domains = len(tasks_with_names)

        if tasks_with_names:
            # Send initial progress notification
            if on_progress and total_domains > 0:
                domain_names = [name for name, _ in tasks_with_names]
                await on_progress({
                    "tool": "lucidshark",
                    "content": f"Scanning {total_domains} domain(s): {', '.join(domain_names)}",
                    "progress": 0,
                    "total": total_domains,
                })

            # Wrap each task to report progress on completion
            completed_count = 0

            async def run_with_progress(
                domain_name: str, coro: Coroutine
            ) -> List[UnifiedIssue]:
                nonlocal completed_count
                try:
                    if on_progress:
                        await on_progress({
                            "tool": domain_name,
                            "content": "started",
                            "progress": completed_count,
                            "total": total_domains,
                        })
                    result = await coro
                    completed_count += 1
                    if on_progress:
                        await on_progress({
                            "tool": domain_name,
                            "content": "completed",
                            "progress": completed_count,
                            "total": total_domains,
                        })
                    return result if result is not None else []
                except Exception as e:
                    completed_count += 1
                    if on_progress:
                        await on_progress({
                            "tool": domain_name,
                            "content": f"failed: {e}",
                            "progress": completed_count,
                            "total": total_domains,
                        })
                    raise

            # Run all tasks with progress tracking
            tasks = [run_with_progress(name, coro) for name, coro in tasks_with_names]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, BaseException):
                    LOGGER.warning(f"Scan task failed: {result}")
                elif result is not None:
                    all_issues.extend(result)

        # Cache issues for later reference
        for issue in all_issues:
            self._issue_cache[issue.id] = issue

        # Build list of checked domain names for the formatter
        checked_domain_names: List[str] = []
        for domain in enabled_domains:
            checked_domain_names.append(domain.value)

        # Format as AI instructions with domain status
        formatted_result = self.instruction_formatter.format_scan_result(
            all_issues,
            checked_domains=checked_domain_names,
            duplication_result=context.duplication_result,
        )

        # Add coverage summary if coverage was run
        if context.coverage_result is not None:
            formatted_result["coverage_summary"] = context.coverage_result.to_dict()

        # Add duplication summary if duplication detection was run
        if context.duplication_result is not None:
            formatted_result["duplication_summary"] = context.duplication_result.to_dict()

        return formatted_result

    async def check_file(self, file_path: str) -> Dict[str, Any]:
        """Check a single file.

        Args:
            file_path: Path to the file (relative to project root).

        Returns:
            Structured scan result for the file.
        """
        path = self.project_root / file_path
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        # Detect language and run appropriate checks
        language = detect_language(path)
        domains = get_domains_for_language(language)

        return await self.scan(domains, files=[file_path])

    async def get_fix_instructions(self, issue_id: str) -> Dict[str, Any]:
        """Get detailed fix instructions for an issue.

        Args:
            issue_id: The issue identifier.

        Returns:
            Detailed fix instructions.
        """
        issue = self._issue_cache.get(issue_id)
        if not issue:
            return {"error": f"Issue not found: {issue_id}"}

        return self.instruction_formatter.format_single_issue(issue, detailed=True)

    async def apply_fix(self, issue_id: str) -> Dict[str, Any]:
        """Apply auto-fix for an issue.

        Args:
            issue_id: The issue identifier to fix.

        Returns:
            Result of the fix operation.
        """
        issue = self._issue_cache.get(issue_id)
        if not issue:
            return {"error": f"Issue not found: {issue_id}"}

        # Only linting issues are auto-fixable
        if issue.domain != ToolDomain.LINTING:
            return {
                "error": "Only linting issues support auto-fix",
                "issue_type": issue.domain.value if issue.domain else "unknown",
            }

        # Run linter in fix mode for the specific file
        if not issue.file_path:
            return {"error": "Issue has no file path for fixing"}

        try:
            # Create stream handler for progress output (writes to stderr)
            stream_handler = CLIStreamHandler(
                output=sys.stderr,
                show_output=True,
                use_rich=False,
            )
            context = self._build_context(
                [ToolDomain.LINTING],
                files=[str(issue.file_path)],
                stream_handler=stream_handler,
            )
            await self._run_linting(context, fix=True)
            return {
                "success": True,
                "message": f"Applied fix for {issue_id}",
                "file": str(issue.file_path),
            }
        except Exception as e:
            return {"error": f"Failed to apply fix: {e}"}

    async def get_status(self) -> Dict[str, Any]:
        """Get current LucidShark status and configuration.

        Returns:
            Status information.
        """
        from lucidshark.plugins.discovery import get_all_available_tools

        return {
            "project_root": str(self.project_root),
            "available_tools": get_all_available_tools(),
            "enabled_domains": self.config.get_enabled_domains(),
            "cached_issues": len(self._issue_cache),
        }

    async def get_help(self) -> Dict[str, Any]:
        """Get LucidShark documentation.

        Returns:
            Documentation content in markdown format.
        """
        from lucidshark.cli.commands.help import get_help_content

        content = get_help_content()
        return {
            "documentation": content,
            "format": "markdown",
        }

    async def validate_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Validate a configuration file.

        Args:
            config_path: Optional path to config file (relative to project root).
                If not provided, searches for lucidshark.yml in project root.

        Returns:
            Structured validation result with valid flag, errors, and warnings.
        """
        from lucidshark.config.validation import validate_config_at_path

        result = validate_config_at_path(self.project_root, config_path)

        if result.error_message:
            response: Dict[str, Any] = {
                "valid": False,
                "error": result.error_message,
                "errors": [],
                "warnings": [],
            }
            if result.config_path is None:
                response["searched_for"] = [
                    ".lucidshark.yml",
                    ".lucidshark.yaml",
                    "lucidshark.yml",
                    "lucidshark.yaml",
                ]
            return response

        return {
            "valid": result.is_valid,
            "config_path": str(result.config_path),
            "errors": [issue.to_dict() for issue in result.errors],
            "warnings": [issue.to_dict() for issue in result.warnings],
        }

    async def autoconfigure(self) -> Dict[str, Any]:
        """Get instructions for auto-configuring LucidShark.

        Returns guidance for AI to analyze the codebase, ask the user
        important configuration questions, and generate an appropriate
        lucidshark.yml configuration file.

        Returns:
            Instructions and guidance for configuration generation.
        """
        return {
            "instructions": (
                "IMPORTANT: Do NOT run the CLI 'lucidshark autoconfigure' command. "
                "Follow these steps manually: Analyze the codebase, ask 1-2 quick questions if needed, "
                "then generate lucidshark.yml with smart defaults using the Write tool, "
                "and finally validate it with the validate_config MCP tool."
            ),
            "analysis_steps": [
                {
                    "step": 1,
                    "action": "Detect languages and package managers",
                    "files_to_check": [
                        "package.json",
                        "pyproject.toml",
                        "setup.py",
                        "requirements.txt",
                        "Cargo.toml",
                        "go.mod",
                        "pom.xml",
                        "build.gradle",
                    ],
                    "what_to_look_for": (
                        "Presence of these files indicates the primary language(s). "
                        "package.json = JavaScript/TypeScript, "
                        "pyproject.toml/setup.py/requirements.txt = Python, "
                        "Cargo.toml = Rust, go.mod = Go, pom.xml/build.gradle = Java"
                    ),
                },
                {
                    "step": 2,
                    "action": "Detect existing linting/type checking tools",
                    "files_to_check": [
                        ".eslintrc",
                        ".eslintrc.js",
                        ".eslintrc.json",
                        "eslint.config.js",
                        "biome.json",
                        "ruff.toml",
                        "pyproject.toml (look for [tool.ruff] section)",
                        ".flake8",
                        "tsconfig.json",
                        "mypy.ini",
                        "pyproject.toml (look for [tool.mypy] section)",
                        "pyrightconfig.json",
                    ],
                    "what_to_look_for": (
                        "Existing tool configurations to preserve. "
                        "If a tool is already configured, use it rather than replacing. "
                        "For Python: ruff or flake8 for linting, mypy or pyright for types. "
                        "For JS/TS: eslint or biome for linting, tsconfig.json for TypeScript."
                    ),
                },
                {
                    "step": 3,
                    "action": "Detect test frameworks and coverage",
                    "files_to_check": [
                        "pytest.ini",
                        "pyproject.toml (look for [tool.pytest] and [tool.coverage] sections)",
                        "conftest.py",
                        ".coveragerc",
                        "jest.config.js",
                        "jest.config.ts",
                        "karma.conf.js",
                        "playwright.config.ts",
                        ".nycrc",
                        ".nycrc.json",
                        "pom.xml (look for jacoco-maven-plugin and surefire-plugin)",
                        "build.gradle (look for jacoco plugin and test configuration)",
                        "src/test/java/ (standard Maven/Gradle test directory)",
                    ],
                    "what_to_look_for": (
                        "Test framework configurations and existing coverage settings. "
                        "Check if there's an existing coverage threshold defined. "
                        "pytest = Python tests, jest = JS/TS tests, "
                        "karma = Angular tests, playwright = E2E tests, "
                        "maven/gradle with JaCoCo = Java tests with coverage. "
                        "For Java: check if project has integration tests (src/test/java/**/*IT.java) "
                        "that require Docker - if so, suggest extra_args to skip them."
                    ),
                },
                {
                    "step": 4,
                    "action": "Ask user 1-2 quick questions based on detection",
                    "guidance": (
                        "If tests detected: ask coverage threshold (suggest 80%). "
                        "If large legacy codebase: ask strict vs gradual mode. "
                        "Otherwise, use smart defaults and skip questions."
                    ),
                },
                {
                    "step": 5,
                    "action": "Read LucidShark documentation",
                    "tool_to_call": "get_help()",
                    "what_to_extract": (
                        "Read the 'Configuration Reference (lucidshark.yml)' section "
                        "to understand the full configuration format, available tools, "
                        "and valid options for each domain."
                    ),
                },
                {
                    "step": 6,
                    "action": "Generate lucidshark.yml",
                    "output_file": "lucidshark.yml",
                    "template_guidance": (
                        "Based on detected languages/tools AND user answers, create a configuration "
                        "that enables appropriate domains. Include: version, project metadata, "
                        "pipeline configuration with detected tools, fail_on thresholds, "
                        "coverage threshold, and ignore patterns."
                    ),
                },
                {
                    "step": 7,
                    "action": "Validate the generated configuration",
                    "tool_to_call": "validate_config()",
                    "what_to_do": (
                        "After writing lucidshark.yml, call validate_config() to verify "
                        "the configuration is valid. If there are errors, fix them before "
                        "proceeding. Warnings can be addressed but are not blocking."
                    ),
                    "on_error": (
                        "If validation returns errors, edit lucidshark.yml to fix the issues "
                        "and call validate_config() again until it passes."
                    ),
                },
                {
                    "step": 8,
                    "action": "Inform user about tool installation and next steps",
                    "guidance": (
                        "After generating the config, tell the user: "
                        "1) Which tools need to be installed (security tools are auto-downloaded), "
                        "2) Run 'lucidshark init --claude-code' or '--cursor' for AI integration, "
                        "3) Run 'lucidshark scan --all' to verify the configuration works, "
                        "4) IMPORTANT: Restart Claude Code or Cursor for the configuration to take effect."
                    ),
                },
            ],
            "questions_to_ask": {
                "description": (
                    "Ask 1-3 quick questions based on codebase. Use smart defaults for the rest."
                ),
                "conditional_questions": [
                    {
                        "id": "coverage_threshold",
                        "ask_when": "Tests detected (pytest.ini, jest.config.*, conftest.py, etc.)",
                        "question": "What coverage threshold? (80% recommended, or lower for legacy code)",
                        "default": 80,
                        "skip_if": "No tests detected - disable coverage, inform user they can enable later",
                    },
                    {
                        "id": "strictness",
                        "ask_when": "Large existing codebase with no lucidshark.yml",
                        "question": "Strict mode (fail on issues) or gradual adoption (report only)?",
                        "options": {
                            "strict": "fail_on errors - recommended for new/clean projects",
                            "gradual": "report only - recommended for legacy codebases to avoid blocking work",
                        },
                        "how_to_detect": (
                            "If you see many existing linting/type errors when analyzing, "
                            "suggest gradual mode. Otherwise, default to strict."
                        ),
                    },
                    {
                        "id": "java_extra_args",
                        "ask_when": "Java project with integration tests (*IT.java files) or Docker dependencies",
                        "question": "Skip integration tests during coverage? (Recommended if tests need Docker/databases)",
                        "options": {
                            "skip": "Add extra_args: [\"-DskipITs\", \"-Ddocker.skip=true\"] to skip integration tests",
                            "include": "Run all tests including integration tests (requires Docker running)",
                        },
                        "how_to_detect": (
                            "Look for src/test/java/**/*IT.java files (integration tests), "
                            "or pom.xml containing docker-maven-plugin, testcontainers dependency, "
                            "or failsafe-maven-plugin configuration."
                        ),
                        "applies_to": "coverage.extra_args in lucidshark.yml",
                    },
                ],
                "always_use_defaults": {
                    "security": "Always enable security scanning (trivy + opengrep). Fail on 'high' severity.",
                    "testing": "Enable if tests detected. Always fail on test failures.",
                    "linting": "Enable with detected tool. Use strictness setting for fail_on.",
                    "type_checking": "Enable if tool detected. Use strictness setting for fail_on.",
                    "duplication": "Always enable duplication detection (duplo). Threshold 10%, min_lines 4.",
                },
            },
            "common_pitfalls": [
                "Always add '**/.venv/**' and '**/node_modules/**' to ignore list",
                "For Java projects: add '**/target/**' to ignore list",
                "For legacy codebases: start with fail_on: none, fix issues gradually",
                "Check current coverage with 'pytest --cov' before setting threshold",
                "For Java with integration tests: use extra_args to skip tests requiring Docker",
            ],
            "tool_recommendations": {
                "python": {
                    "linter": "ruff (recommended, fast and comprehensive) or flake8",
                    "type_checker": "mypy (recommended, widely used) or pyright",
                    "test_runner": "pytest (standard choice)",
                    "coverage": "coverage.py (via pytest-cov)",
                },
                "javascript_typescript": {
                    "linter": "eslint (most popular) or biome (faster, newer)",
                    "type_checker": "typescript (tsc) - enabled via tsconfig.json",
                    "test_runner": "jest (most common), karma (Angular), or playwright (E2E)",
                    "coverage": "istanbul/nyc (usually included with jest)",
                },
                "java": {
                    "linter": "checkstyle",
                    "test_runner": "maven (runs JUnit/TestNG tests)",
                    "coverage": "jacoco (Maven/Gradle plugin)",
                    "note": (
                        "For Java projects with integration tests requiring Docker or external services, "
                        "use extra_args to skip them: extra_args: [\"-DskipITs\", \"-Ddocker.skip=true\"]"
                    ),
                },
            },
            "security_tools": {
                "always_recommended": [
                    "trivy (for SCA - dependency vulnerability scanning)",
                    "opengrep (for SAST - code pattern security analysis)",
                ],
                "optional": [
                    "checkov (for IaC scanning - Terraform, Kubernetes, CloudFormation)",
                ],
                "note": "Security tools are downloaded automatically - no manual installation needed.",
            },
            "example_config": {
                "description": "Example configurations with common settings",
                "python_with_coverage": """version: 1

project:
  name: my-python-project
  languages: [python]

pipeline:
  linting:
    enabled: true
    tools: [ruff]
  type_checking:
    enabled: true
    tools: [mypy]
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
  testing:
    enabled: true
    tools: [pytest]
  coverage:
    enabled: true
    tools: [coverage_py]
    threshold: 80
  duplication:
    enabled: true
    threshold: 10.0
    min_lines: 4
    tools: [duplo]

fail_on:
  linting: error
  type_checking: error
  security: high
  testing: any
  coverage: any
  duplication: any

ignore:
  - "**/.venv/**"
  - "**/__pycache__/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/.git/**"
""",
                "typescript_with_coverage": """version: 1

project:
  name: my-typescript-project
  languages: [typescript]

pipeline:
  linting:
    enabled: true
    tools: [eslint]
  type_checking:
    enabled: true
    tools: [typescript]
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
  testing:
    enabled: true
    tools: [jest]
  coverage:
    enabled: true
    tools: [istanbul]
    threshold: 80
  duplication:
    enabled: true
    threshold: 10.0
    min_lines: 4
    tools: [duplo]

fail_on:
  linting: error
  type_checking: error
  security: high
  testing: any
  coverage: any
  duplication: any

ignore:
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/coverage/**"
  - "**/.git/**"
""",
                "java_with_coverage": """version: 1

project:
  name: my-java-project
  languages: [java]

pipeline:
  linting:
    enabled: true
    tools: [checkstyle]
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
  testing:
    enabled: true
    tools: [maven]
  coverage:
    enabled: true
    tools: [jacoco]
    threshold: 80
    # Use extra_args to skip integration tests that require Docker or external services
    # extra_args: ["-DskipITs", "-Ddocker.skip=true"]
  duplication:
    enabled: true
    threshold: 10.0
    min_lines: 4
    tools: [duplo]

fail_on:
  linting: error
  security: high
  testing: any
  coverage: any
  duplication: any

ignore:
  - "**/target/**"
  - "**/.git/**"
""",
                "gradual_adoption": """# Configuration for gradual adoption (legacy codebase)
version: 1

project:
  name: legacy-project
  languages: [python]

pipeline:
  linting:
    enabled: true
    tools: [ruff]
  type_checking:
    enabled: true
    tools: [mypy]
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
  testing:
    enabled: true
    tools: [pytest]
  coverage:
    enabled: false  # Enable later when tests are added

# Relaxed thresholds for gradual adoption
fail_on:
  linting: none        # Report only, don't fail
  type_checking: none  # Report only, don't fail
  security: critical   # Only fail on critical issues
  testing: any

ignore:
  - "**/.venv/**"
  - "**/__pycache__/**"
""",
            },
            "post_config_steps": [
                "Run 'lucidshark init --claude-code' or 'lucidshark init --cursor' to set up AI tool integration",
                "Install required linting/testing tools via package manager (security tools auto-download)",
                "Run 'lucidshark scan --all' to test the configuration and see initial results",
                "If many issues appear, consider starting with relaxed thresholds (see gradual_adoption example)",
                "IMPORTANT: Restart Claude Code or Cursor for the new configuration to take effect",
            ],
        }

    def _parse_domains(self, domains: List[str]) -> List[DomainType]:
        """Parse domain strings to domain enums.

        When "all" is specified, returns domains based on what's configured
        in lucidshark.yml. If no config exists, uses sensible defaults.

        Args:
            domains: List of domain names.

        Returns:
            List of domain enums (ToolDomain or ScanDomain).
        """
        if "all" in domains:
            result: List[DomainType] = []

            # Include tool domains based on pipeline config
            # If explicitly configured, respect the enabled flag
            # If not configured (None), enable by default for "all"
            if self.config.pipeline.linting is None or self.config.pipeline.linting.enabled:
                result.append(ToolDomain.LINTING)
            if self.config.pipeline.type_checking is None or self.config.pipeline.type_checking.enabled:
                result.append(ToolDomain.TYPE_CHECKING)
            if self.config.pipeline.testing and self.config.pipeline.testing.enabled:
                result.append(ToolDomain.TESTING)
            if self.config.pipeline.coverage and self.config.pipeline.coverage.enabled:
                result.append(ToolDomain.COVERAGE)
            if self.config.pipeline.duplication and self.config.pipeline.duplication.enabled:
                result.append(ToolDomain.DUPLICATION)

            # Include security domains based on config (both legacy and pipeline)
            # Only run security domains that are explicitly configured
            security_domains = self.config.get_enabled_domains()
            for domain_str in security_domains:
                try:
                    result.append(ScanDomain(domain_str))
                except ValueError:
                    LOGGER.warning(f"Unknown security domain in config: {domain_str}")

            return result

        result = []
        for domain in domains:
            parsed = parse_domain(domain)
            if parsed is not None:
                result.append(parsed)
            else:
                LOGGER.warning(f"Unknown domain: {domain}")

        return result

    def _build_context(
        self,
        domains: List[DomainType],
        files: Optional[List[str]] = None,
        all_files: bool = False,
        stream_handler: Optional[StreamHandler] = None,
    ) -> ScanContext:
        """Build scan context with partial scanning support.

        Priority:
        1. If `files` is provided, scan only those specific files
        2. If `all_files` is True, scan entire project
        3. Otherwise, scan only changed files (uncommitted changes)

        Args:
            domains: Enabled domains.
            files: Optional specific files to scan.
            all_files: If True, scan entire project.
            stream_handler: Optional handler for streaming output.

        Returns:
            ScanContext instance.
        """
        return ScanContext.create(
            project_root=self.project_root,
            config=self.config,
            enabled_domains=domains,
            files=files,
            all_files=all_files,
            stream_handler=stream_handler,
        )

    async def _run_linting(
        self,
        context: ScanContext,
        fix: bool = False,
    ) -> List[UnifiedIssue]:
        """Run linting checks asynchronously.

        Args:
            context: Scan context.
            fix: Whether to apply fixes.

        Returns:
            List of linting issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_linting, context, fix
        )

    async def _run_type_checking(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run type checking asynchronously.

        Args:
            context: Scan context.

        Returns:
            List of type checking issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_type_checking, context
        )

    async def _run_testing(
        self, context: ScanContext, with_coverage: bool = False
    ) -> List[UnifiedIssue]:
        """Run test suite asynchronously.

        Args:
            context: Scan context.
            with_coverage: If True, run tests with coverage instrumentation.

        Returns:
            List of test failure issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_tests, context, with_coverage
        )

    async def _run_coverage(
        self,
        context: ScanContext,
        run_tests: bool = True,
    ) -> List[UnifiedIssue]:
        """Run coverage analysis asynchronously.

        Args:
            context: Scan context.
            run_tests: Whether to run tests for coverage measurement.

        Returns:
            List of coverage issues.
        """
        loop = asyncio.get_event_loop()
        # Use functools.partial to pass run_tests parameter
        run_coverage_fn = functools.partial(
            self._runner.run_coverage,
            context,
            run_tests=run_tests,
        )
        issues = await loop.run_in_executor(None, run_coverage_fn)
        # Coverage result is stored in context.coverage_result by DomainRunner
        return issues

    async def _run_security(
        self,
        context: ScanContext,
        domain: ScanDomain,
    ) -> List[UnifiedIssue]:
        """Run security scanner asynchronously.

        Args:
            context: Scan context.
            domain: Scanner domain (SAST, SCA, IAC, CONTAINER).

        Returns:
            List of security issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_security, context, domain
        )

    async def _run_duplication(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run duplication detection asynchronously.

        Note: Duplication detection always scans the entire project to
        detect cross-file duplicates, regardless of paths in context.

        Args:
            context: Scan context.

        Returns:
            List of duplication issues.
        """
        loop = asyncio.get_event_loop()
        # Get threshold and options from config
        threshold = 10.0
        min_lines = 4
        min_chars = 3
        exclude_patterns = None
        if self.config.pipeline.duplication:
            threshold = self.config.pipeline.duplication.threshold
            min_lines = self.config.pipeline.duplication.min_lines
            min_chars = self.config.pipeline.duplication.min_chars
            exclude_patterns = self.config.pipeline.duplication.exclude or None

        run_duplication_fn = functools.partial(
            self._runner.run_duplication,
            context,
            threshold=threshold,
            min_lines=min_lines,
            min_chars=min_chars,
            exclude_patterns=exclude_patterns,
        )
        issues = await loop.run_in_executor(None, run_duplication_fn)
        # Duplication result is stored in context.duplication_result by DomainRunner
        return issues
