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
        base_branch: Optional[str] = None,
        coverage_threshold_scope: Optional[str] = None,
        linting_threshold_scope: Optional[str] = None,
        type_checking_threshold_scope: Optional[str] = None,
        duplication_threshold_scope: Optional[str] = None,
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
            base_branch: Filter results to files changed since this branch (e.g., 'origin/main').
            coverage_threshold_scope: When using base_branch, apply coverage threshold to:
                'changed' (changed files only, default), 'project' (full project),
                or 'both' (fail if either is below threshold).
            linting_threshold_scope: When using base_branch, apply linting threshold to:
                'changed' (changed files only, default), 'project' (full project),
                or 'both' (fail if either has issues).
            type_checking_threshold_scope: When using base_branch, apply type checking threshold to:
                'changed' (changed files only, default), 'project' (full project),
                or 'both' (fail if either has errors).
            duplication_threshold_scope: When using base_branch, apply duplication threshold to:
                'changed' (changed files only, default), 'project' (full project),
                or 'both' (fail if either exceeds threshold).
            on_progress: Optional async callback for progress events (MCP notifications).

        Returns:
            Structured scan result with AI instructions.
        """
        # Convert domain strings to ToolDomain enums
        enabled_domains = self._parse_domains(domains)

        # Coverage requires testing to be enabled - testing produces the coverage files
        from lucidshark.core.models import ToolDomain
        if ToolDomain.COVERAGE in enabled_domains and ToolDomain.TESTING not in enabled_domains:
            return {
                "error": (
                    "Coverage requires testing to be enabled. Testing produces the coverage "
                    "files that coverage analysis reads. Add 'testing' to the domains list."
                ),
                "blocking": True,
                "total_issues": 0,
            }

        # Validate configured tools are available
        validation_result = self._validate_tools(enabled_domains)
        if not validation_result.success:
            return self._format_validation_error(validation_result.errors)

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
        # instrumentation (via testing domain) to generate .coverage file,
        # then coverage domain reads the file to generate reports.
        #
        # IMPORTANT: Coverage must run AFTER testing completes because it reads
        # the .coverage file that testing produces. We wrap both into a single
        # sequential coroutine so they execute in order while still running
        # concurrently with other domains (linting, security, etc.).
        if testing_enabled and coverage_enabled:
            async def _testing_then_coverage() -> List[UnifiedIssue]:
                """Run testing then coverage sequentially."""
                issues: List[UnifiedIssue] = []
                # Step 1: Run tests (always generates coverage data)
                testing_issues = await self._run_testing(context)
                if testing_issues:
                    issues.extend(testing_issues)
                # Step 2: Now that .coverage file exists, read it
                coverage_issues = await self._run_coverage(context)
                if coverage_issues:
                    issues.extend(coverage_issues)
                return issues

            tasks_with_names.append(
                ("testing+coverage", _testing_then_coverage())
            )
        elif testing_enabled:
            # Testing only (still generates coverage data as side effect)
            tasks_with_names.append(
                ("testing", self._run_testing(context))
            )
        elif coverage_enabled:
            # Coverage without testing is an error — tests must run to
            # produce coverage data
            from lucidshark.core.models import Severity
            all_issues.append(UnifiedIssue(
                id="coverage-requires-testing",
                domain=ToolDomain.COVERAGE,
                source_tool="lucidshark",
                severity=Severity.HIGH,
                rule_id="coverage-requires-testing",
                title="Coverage requires testing to be enabled",
                description=(
                    "Coverage analysis requires test execution to produce "
                    "coverage data. Enable the testing domain alongside "
                    "coverage, or remove the coverage domain."
                ),
                fixable=False,
            ))

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

        # Apply ignore_issues
        if self.config.ignore_issues:
            from lucidshark.core.ignore_issues import apply_ignore_issues

            ignore_warnings = apply_ignore_issues(all_issues, self.config.ignore_issues)
            for w in ignore_warnings:
                LOGGER.warning(w)

        # Apply base-branch filtering if specified
        # This filters results to only show issues/metrics for changed files
        # Store full results for scope-based threshold checking
        full_coverage_result = context.coverage_result
        full_duplication_result = context.duplication_result
        changed_files: Optional[List[Path]] = None

        if base_branch:
            from lucidshark.core.filtering import filter_issues_by_changed_files
            from lucidshark.core.git import get_changed_files_since_branch

            changed_files = get_changed_files_since_branch(
                self.project_root, base_branch
            )
            if changed_files is None:
                # Git command failed - return error
                return {
                    "error": (
                        f"Could not compare against branch '{base_branch}'. "
                        "Ensure the branch exists and git history is available "
                        "(use fetch-depth: 0 in CI)."
                    ),
                    "blocking": True,
                    "total_issues": 0,
                }

            if changed_files:
                LOGGER.info(
                    f"Filtering results to {len(changed_files)} files "
                    f"changed since {base_branch}"
                )

                # Filter issues (linting, type_checking)
                all_issues = filter_issues_by_changed_files(
                    all_issues, changed_files, self.project_root
                )

                # Filter coverage
                if context.coverage_result:
                    context.coverage_result = (
                        full_coverage_result.filter_to_changed_files(
                            changed_files, self.project_root
                        )
                    )

                # Filter duplication
                if context.duplication_result:
                    context.duplication_result = (
                        full_duplication_result.filter_to_changed_files(
                            changed_files, self.project_root
                        )
                    )
            else:
                LOGGER.warning(
                    f"No files changed since {base_branch}, showing full results"
                )

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

        # Add incremental scanning metadata if base_branch was used
        if base_branch:
            formatted_result["incremental_scan"] = {
                "base_branch": base_branch,
                "changed_files_count": len(changed_files) if changed_files else 0,
            }

        # Add coverage summary with scope-based threshold checking
        if context.coverage_result is not None:
            if base_branch and changed_files:
                scope = coverage_threshold_scope or "changed"

                # Compute effective passed based on scope
                if scope == "changed":
                    effective_passed = context.coverage_result.passed
                elif scope == "project":
                    effective_passed = full_coverage_result.passed
                else:  # "both"
                    effective_passed = (
                        context.coverage_result.passed
                        and full_coverage_result.passed
                    )

                LOGGER.debug(
                    f"Coverage threshold scope: {scope}, "
                    f"changed: {context.coverage_result.percentage:.1f}% "
                    f"(passed={context.coverage_result.passed}), "
                    f"project: {full_coverage_result.percentage:.1f}% "
                    f"(passed={full_coverage_result.passed}), "
                    f"effective_passed={effective_passed}"
                )

                coverage_dict = context.coverage_result.to_dict()
                coverage_dict["passed"] = effective_passed
                coverage_dict["threshold_scope"] = scope
                formatted_result["coverage_summary"] = coverage_dict
            else:
                formatted_result["coverage_summary"] = context.coverage_result.to_dict()

        # Add duplication summary with scope-based threshold checking
        if context.duplication_result is not None:
            if base_branch and changed_files:
                scope = duplication_threshold_scope or "changed"

                # Compute effective passed based on scope
                if scope == "changed":
                    effective_passed = context.duplication_result.passed
                elif scope == "project":
                    effective_passed = full_duplication_result.passed
                else:  # "both"
                    effective_passed = (
                        context.duplication_result.passed
                        and full_duplication_result.passed
                    )

                LOGGER.debug(
                    f"Duplication threshold scope: {scope}, "
                    f"changed: {context.duplication_result.duplication_percent:.1f}% "
                    f"(passed={context.duplication_result.passed}), "
                    f"project: {full_duplication_result.duplication_percent:.1f}% "
                    f"(passed={full_duplication_result.passed}), "
                    f"effective_passed={effective_passed}"
                )

                duplication_dict = context.duplication_result.to_dict()
                duplication_dict["passed"] = effective_passed
                duplication_dict["threshold_scope"] = scope
                formatted_result["duplication_summary"] = duplication_dict
            else:
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
                "Follow these steps: Analyze the codebase, ask 1-2 quick questions if needed, "
                "install any missing tools and add them to the project's dev dependencies, "
                "generate lucidshark.yml with smart defaults using the Write tool, "
                "validate it with the validate_config MCP tool, and run a verification scan."
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
                    "coverage_testing_dependency": (
                        "IMPORTANT: Coverage REQUIRES testing to be enabled. Testing produces the "
                        "coverage files that coverage analysis reads. If you enable coverage, you "
                        "MUST also enable testing in the generated config. The scan will fail if "
                        "coverage is enabled without testing."
                    ),
                },
                {
                    "step": 4,
                    "action": "Identify project-specific exclusions",
                    "guidance": (
                        "Examine the project's directory structure (use ls or tree) and identify directories "
                        "and file patterns that should NOT be scanned. Look for: generated code directories, "
                        "vendored dependencies, data/fixture directories, compiled/transpiled output, "
                        "documentation build output, IDE config directories, lock files, binary assets, "
                        "migration files, snapshot files, and any other paths that don't represent "
                        "hand-written source code. Add these to the global 'exclude' list alongside the "
                        "common exclusions from 'common_exclusions'. This is especially important for "
                        "duplication detection, which scans the entire project."
                    ),
                    "examples_to_look_for": [
                        "generated/, codegen/, *_generated.*, *_pb2.py, *.generated.ts",
                        "vendor/, third_party/, external/",
                        "data/, fixtures/, testdata/, samples/",
                        "docs/_build/, site/, .docusaurus/",
                        ".idea/, .vscode/ (IDE dirs)",
                        "*.min.js, *.min.css, *.bundle.js (minified/bundled files)",
                        "*.lock, package-lock.json, poetry.lock, Cargo.lock (lock files — context-dependent)",
                        "migrations/ (database migrations — repetitive structure)",
                        "static/, public/assets/, media/ (static assets)",
                        "*.snap, __snapshots__/ (test snapshots)",
                    ],
                },
                {
                    "step": 5,
                    "action": "Ask user 1-2 quick questions based on detection",
                    "guidance": (
                        "If tests detected: ask coverage threshold (suggest 80%). "
                        "If large legacy codebase: ask strict vs gradual mode. "
                        "Otherwise, use smart defaults and skip questions."
                    ),
                },
                {
                    "step": 6,
                    "action": "Read LucidShark documentation",
                    "tool_to_call": "get_help()",
                    "what_to_extract": (
                        "Read the 'Configuration Reference (lucidshark.yml)' section "
                        "to understand the full configuration format, available tools, "
                        "and valid options for each domain."
                    ),
                },
                {
                    "step": 7,
                    "action": "Install required tools and add to package manager",
                    "guidance": (
                        "IMPORTANT: Before generating the config, ensure all required tools are installed. "
                        "Claude MUST check if each tool is installed and install missing ones automatically. "
                        "Security tools (trivy, opengrep, checkov, duplo) are auto-downloaded by LucidShark. "
                        "Language-specific tools must be installed via package manager AND added to dev dependencies."
                    ),
                    "tools_by_language": {
                        "python": {
                            "tools": ["ruff", "mypy", "pytest", "coverage", "pytest-cov"],
                            "check_command": "pip list | grep -iE '^(ruff|mypy|pytest|coverage) '",
                            "install_command": "pip install {missing_tools}",
                            "add_to_file": {
                                "pyproject.toml": (
                                    "Add missing tools to [project.optional-dependencies] dev = [...] section. "
                                    "Example: dev = ['ruff>=0.4', 'mypy>=1.0', 'pytest>=7.0', 'coverage>=7.0', 'pytest-cov>=4.0']"
                                ),
                                "requirements-dev.txt": (
                                    "Append missing tools to requirements-dev.txt, one per line. "
                                    "Example: ruff>=0.4\\nmypy>=1.0\\npytest>=7.0\\ncoverage>=7.0\\npytest-cov>=4.0"
                                ),
                                "setup.py": (
                                    "Add to extras_require={'dev': [...]} in setup.py"
                                ),
                            },
                        },
                        "javascript_typescript": {
                            "tools": ["eslint", "typescript", "jest", "prettier"],
                            "check_command": "npm list {tool} || yarn list {tool}",
                            "install_command": "npm install --save-dev {missing_tools}",
                            "add_to_file": {
                                "package.json": (
                                    "Tools are automatically added to devDependencies when using npm install --save-dev"
                                ),
                            },
                        },
                        "java_kotlin": {
                            "tools": ["checkstyle", "spotbugs", "jacoco (all via Maven/Gradle plugins)"],
                            "note": (
                                "Java/Kotlin tools are configured via Maven/Gradle plugins, not installed separately. "
                                "Verify pom.xml or build.gradle has the required plugins configured."
                            ),
                        },
                        "rust": {
                            "tools": ["clippy", "cargo-tarpaulin"],
                            "check_command": "cargo --list | grep clippy && cargo install --list | grep tarpaulin",
                            "install_command": "rustup component add clippy && cargo install cargo-tarpaulin",
                        },
                        "go": {
                            "tools": ["golangci-lint", "go test (built-in)"],
                            "check_command": "which golangci-lint",
                            "install_command": "go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest",
                            "note": (
                                "Go has no built-in LucidShark plugins yet. Use 'command' field in lucidshark.yml: "
                                "linting.command: 'golangci-lint run --out-format json', "
                                "testing.command: 'go test -v ./...', "
                                "coverage.command: 'go test -coverprofile=coverage.out ./... && go tool cover -func=coverage.out'"
                            ),
                        },
                        "other_languages": {
                            "description": (
                                "For languages without built-in LucidShark plugins (C, C++, C#, Ruby, PHP, Swift, etc.), "
                                "you can still use LucidShark for:"
                            ),
                            "available_features": [
                                "Security scanning: trivy (SCA) and opengrep (SAST) work for most languages",
                                "Duplication detection: duplo supports C, C++, C#, Java, JavaScript, Python, Ruby, Go, and more",
                            ],
                            "custom_integration": (
                                "For linting, type checking, testing, and coverage, use the 'command' field to integrate "
                                "your own tools. Example for C++: "
                                "linting.command: 'clang-tidy src/**/*.cpp --export-fixes=fixes.yaml', "
                                "testing.command: 'ctest --output-on-failure'"
                            ),
                            "example_config": (
                                "pipeline:\\n"
                                "  linting:\\n"
                                "    enabled: true\\n"
                                "    command: 'your-linter-command'\\n"
                                "  testing:\\n"
                                "    enabled: true\\n"
                                "    command: 'your-test-command'\\n"
                                "  security:\\n"
                                "    enabled: true\\n"
                                "    tools:\\n"
                                "      - name: trivy\\n"
                                "        domains: [sca]\\n"
                                "      - name: opengrep\\n"
                                "        domains: [sast]\\n"
                                "  duplication:\\n"
                                "    enabled: true\\n"
                                "    tools: [duplo]"
                            ),
                        },
                    },
                    "execution_steps": [
                        "1. Check which tools are already installed using the check_command",
                        "2. Install any missing tools using the install_command",
                        "3. Add the tools to the appropriate dev dependencies file so they persist",
                        "4. Verify installation succeeded before proceeding",
                    ],
                },
                {
                    "step": 8,
                    "action": "Generate lucidshark.yml",
                    "output_file": "lucidshark.yml",
                    "template_guidance": (
                        "Based on detected languages/tools AND user answers, create a configuration "
                        "that enables appropriate domains. Include: version, project metadata, "
                        "pipeline configuration with detected tools, fail_on thresholds, "
                        "coverage threshold, and ignore patterns."
                    ),
                    "custom_commands_for_unsupported_languages": (
                        "IMPORTANT: For languages without built-in LucidShark plugins (Go, C, C++, C#, Ruby, PHP, Swift, etc.), "
                        "you MUST write appropriate 'command' fields to integrate the language's standard tools. "
                        "Do NOT leave these domains disabled or empty - find the right commands for the project."
                    ),
                    "command_examples_by_language": {
                        "go": {
                            "linting": "golangci-lint run ./...",
                            "type_checking": "go vet ./...",
                            "testing": "go test -v ./...",
                            "coverage": "go test -coverprofile=coverage.out ./... && go tool cover -func=coverage.out",
                        },
                        "c_cpp_cmake": {
                            "linting": "cmake --build build --target clang-tidy",
                            "testing": "ctest --test-dir build --output-on-failure",
                            "coverage": "cmake --build build --target coverage",
                        },
                        "c_cpp_make": {
                            "linting": "make lint",
                            "testing": "make test",
                        },
                        "csharp_dotnet": {
                            "linting": "dotnet format --verify-no-changes",
                            "testing": "dotnet test --verbosity normal",
                            "coverage": "dotnet test --collect:'XPlat Code Coverage'",
                        },
                        "ruby": {
                            "linting": "bundle exec rubocop",
                            "testing": "bundle exec rspec",
                            "coverage": "bundle exec rspec --format documentation",
                        },
                        "php": {
                            "linting": "vendor/bin/phpcs --standard=PSR12 src/",
                            "type_checking": "vendor/bin/phpstan analyse src/",
                            "testing": "vendor/bin/phpunit",
                        },
                        "swift": {
                            "linting": "swiftlint",
                            "testing": "swift test",
                        },
                        "elixir": {
                            "linting": "mix credo",
                            "type_checking": "mix dialyzer",
                            "testing": "mix test",
                        },
                    },
                    "command_field_rules": [
                        "Examine the project's build files (Makefile, CMakeLists.txt, package.json scripts, etc.) to find existing commands",
                        "If a standard tool exists for the language, use it even if not explicitly configured in the project",
                        "Always test that the command works before finalizing the config",
                        "Use 'post_command' for cleanup tasks like removing temp files or generating reports",
                    ],
                },
                {
                    "step": 9,
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
                    "step": 10,
                    "action": "Run verification scan and inform user",
                    "guidance": (
                        "After config is validated and tools are installed: "
                        "1) Run 'lucidshark scan --all' via the scan MCP tool to verify everything works, "
                        "2) If 'lucidshark init' hasn't been run, suggest it for AI integration,"
                        "3) IMPORTANT: Remind user to restart Claude Code for configuration changes to take effect."
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
                    "testing": "Enable if tests detected. Always fail on test failures. MUST be enabled if coverage is enabled.",
                    "coverage": "Enable if coverage tool detected. REQUIRES testing to be enabled (testing produces coverage files).",
                    "linting": "Enable with detected tool. Use strictness setting for fail_on.",
                    "type_checking": "Enable if tool detected. Use strictness setting for fail_on.",
                    "duplication": "Always enable duplication detection (duplo). Threshold 5%, min_lines 7.",
                },
            },
            "common_pitfalls": [
                (
                    "CRITICAL: The global 'exclude' list applies to ALL domains (linting, type_checking, "
                    "security, testing, coverage, AND duplication). Duplication detection scans the entire "
                    "project, so missing exclusions will cause it to scan build artifacts, caches, and "
                    "generated files — producing noisy false positives. Always include comprehensive "
                    "exclusions from the 'common_exclusions' section AND project-specific exclusions "
                    "discovered during directory analysis."
                ),
                "Merge 'always_include' + ALL relevant 'per_language' patterns + project-specific exclusions into the global 'exclude' list",
                "Examine the project directory tree for generated, vendored, compiled, or non-source directories and exclude them",
                "For legacy codebases: start with fail_on: none, fix issues gradually",
                "Check current coverage with 'pytest --cov' before setting threshold",
                "For Java with integration tests: use extra_args to skip tests requiring Docker",
            ],
            "common_exclusions": {
                "description": (
                    "CRITICAL: Always include comprehensive exclusions in the global 'exclude' (or 'ignore') "
                    "list. These apply to ALL domains including duplication, which scans the entire project. "
                    "Missing exclusions cause false positives, slow scans, and noise — especially for duplication. "
                    "In addition to these predefined patterns, you MUST also examine the project's directory "
                    "structure and add any project-specific directories that contain generated, vendored, "
                    "compiled, or non-source-code files."
                ),
                "always_include": [
                    "**/.git/**",
                    "**/node_modules/**",
                    "**/.venv/**",
                    "**/venv/**",
                    "**/__pycache__/**",
                    "**/dist/**",
                    "**/build/**",
                    "**/.lucidshark/**",
                ],
                "per_language": {
                    "python": [
                        "**/.venv/**",
                        "**/venv/**",
                        "**/__pycache__/**",
                        "**/*.egg-info/**",
                        "**/.eggs/**",
                        "**/.mypy_cache/**",
                        "**/.pytest_cache/**",
                        "**/.ruff_cache/**",
                        "**/htmlcov/**",
                        "**/.tox/**",
                        "**/.nox/**",
                    ],
                    "javascript_typescript": [
                        "**/node_modules/**",
                        "**/dist/**",
                        "**/build/**",
                        "**/coverage/**",
                        "**/.next/**",
                        "**/.nuxt/**",
                    ],
                    "java": [
                        "**/target/**",
                        "**/.gradle/**",
                        "**/build/**",
                    ],
                    "rust": [
                        "**/target/**",
                    ],
                    "go": [
                        "**/vendor/**",
                    ],
                    "c_cpp": [
                        "**/build/**",
                        "**/cmake-build-*/**",
                        "**/out/**",
                        "**/*.o",
                        "**/*.a",
                        "**/*.so",
                        "**/*.dylib",
                    ],
                    "csharp": [
                        "**/bin/**",
                        "**/obj/**",
                        "**/packages/**",
                        "**/.vs/**",
                    ],
                    "ruby": [
                        "**/vendor/bundle/**",
                        "**/.bundle/**",
                    ],
                    "php": [
                        "**/vendor/**",
                    ],
                },
                "project_specific_guidance": (
                    "After applying the above patterns, also examine the project's actual directory "
                    "structure and add exclusions for: generated code directories, vendored/third-party "
                    "code, data/fixture directories, documentation build output, IDE configs, minified "
                    "or bundled files, database migrations (if repetitive), static assets, and test "
                    "snapshots. If in doubt about a directory, exclude it — it's better to exclude too "
                    "much than to pollute duplication results with non-source-code."
                ),
            },
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
                "java_kotlin": {
                    "linter": "checkstyle",
                    "type_checker": "spotbugs (bug detection via static analysis)",
                    "test_runner": "maven (runs JUnit/TestNG tests)",
                    "coverage": "jacoco (Maven/Gradle plugin)",
                    "note": (
                        "For Java projects with integration tests requiring Docker or external services, "
                        "use extra_args to skip them: extra_args: [\"-DskipITs\", \"-Ddocker.skip=true\"]"
                    ),
                },
                "rust": {
                    "linter": "clippy (built into cargo)",
                    "type_checker": "cargo check (built into cargo)",
                    "test_runner": "cargo test (built into cargo)",
                    "coverage": "tarpaulin (cargo-tarpaulin)",
                },
                "go": {
                    "linter": "golangci-lint (use via command field)",
                    "type_checker": "go vet (built into go, use via command field)",
                    "test_runner": "go test (built into go, use via command field)",
                    "coverage": "go test -cover (use via command field)",
                    "note": (
                        "Go has no built-in LucidShark plugins. Use the 'command' field in lucidshark.yml "
                        "to integrate go tools. Example: linting.command: 'golangci-lint run --out-format json'"
                    ),
                },
                "other_languages": {
                    "note": (
                        "For C, C++, C#, Ruby, PHP, Swift, and other languages without built-in plugins: "
                        "use the 'command' field to integrate your own tools. Security scanning (trivy, opengrep) "
                        "and duplication detection (duplo) work for most languages out of the box."
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
    threshold: 5.0
    min_lines: 7
    tools: [duplo]

fail_on:
  linting: error
  type_checking: error
  security: high
  testing: any
  coverage: any
  duplication: any

ignore:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/__pycache__/**"
  - "**/*.egg-info/**"
  - "**/.eggs/**"
  - "**/.mypy_cache/**"
  - "**/.pytest_cache/**"
  - "**/.ruff_cache/**"
  - "**/htmlcov/**"
  - "**/.tox/**"
  - "**/.nox/**"
  - "**/dist/**"
  - "**/build/**"
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
    threshold: 5.0
    min_lines: 7
    tools: [duplo]

fail_on:
  linting: error
  type_checking: error
  security: high
  testing: any
  coverage: any
  duplication: any

ignore:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/coverage/**"
  - "**/.next/**"
  - "**/.nuxt/**"
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
    threshold: 5.0
    min_lines: 7
    tools: [duplo]

fail_on:
  linting: error
  security: high
  testing: any
  coverage: any
  duplication: any

ignore:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/target/**"
  - "**/.gradle/**"
  - "**/build/**"
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
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/__pycache__/**"
  - "**/*.egg-info/**"
  - "**/.eggs/**"
  - "**/.mypy_cache/**"
  - "**/.pytest_cache/**"
  - "**/.ruff_cache/**"
  - "**/htmlcov/**"
  - "**/dist/**"
  - "**/build/**"
""",
            },
            "post_config_steps": [
                "Tools should already be installed and added to dev dependencies (step 7)",
                "Run 'lucidshark init' if AI tool integration is not yet configured",
                "Run 'lucidshark scan --all' to verify the configuration (should be done in step 10)",
                "If many issues appear, consider relaxing thresholds (see gradual_adoption example)",
                "IMPORTANT: Restart Claude Code for the new configuration to take effect",
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
        linting_exclude = None
        linting_command = None
        linting_pre_command = None
        linting_post_command = None
        if self.config.pipeline.linting:
            if self.config.pipeline.linting.exclude:
                linting_exclude = self.config.pipeline.linting.exclude
            linting_command = self.config.pipeline.linting.command
            linting_pre_command = self.config.pipeline.linting.pre_command
            linting_post_command = self.config.pipeline.linting.post_command
        run_fn = functools.partial(
            self._runner.run_linting, context, fix,
            exclude_patterns=linting_exclude,
            command=linting_command,
            pre_command=linting_pre_command,
            post_command=linting_post_command,
        )
        return await loop.run_in_executor(None, run_fn)

    async def _run_type_checking(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run type checking asynchronously.

        Args:
            context: Scan context.

        Returns:
            List of type checking issues.
        """
        loop = asyncio.get_event_loop()
        tc_exclude = None
        tc_command = None
        tc_pre_command = None
        tc_post_command = None
        if self.config.pipeline.type_checking:
            if self.config.pipeline.type_checking.exclude:
                tc_exclude = self.config.pipeline.type_checking.exclude
            tc_command = self.config.pipeline.type_checking.command
            tc_pre_command = self.config.pipeline.type_checking.pre_command
            tc_post_command = self.config.pipeline.type_checking.post_command
        run_fn = functools.partial(
            self._runner.run_type_checking, context,
            exclude_patterns=tc_exclude,
            command=tc_command,
            pre_command=tc_pre_command,
            post_command=tc_post_command,
        )
        return await loop.run_in_executor(None, run_fn)

    async def _run_testing(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run test suite asynchronously.

        Tests always generate coverage data when the appropriate coverage
        tool is available.

        Args:
            context: Scan context.

        Returns:
            List of test failure issues.
        """
        loop = asyncio.get_event_loop()
        testing_exclude = None
        testing_command = None
        testing_pre_command = None
        testing_post_command = None
        if self.config.pipeline.testing:
            if self.config.pipeline.testing.exclude:
                testing_exclude = self.config.pipeline.testing.exclude
            testing_command = self.config.pipeline.testing.command
            testing_pre_command = self.config.pipeline.testing.pre_command
            testing_post_command = self.config.pipeline.testing.post_command
        run_fn = functools.partial(
            self._runner.run_tests, context,
            exclude_patterns=testing_exclude,
            command=testing_command,
            pre_command=testing_pre_command,
            post_command=testing_post_command,
        )
        return await loop.run_in_executor(None, run_fn)

    async def _run_coverage(
        self,
        context: ScanContext,
    ) -> List[UnifiedIssue]:
        """Run coverage analysis asynchronously.

        Coverage plugins only parse existing coverage data files. They never
        run tests independently. If no coverage data is found, an error issue
        is returned.

        Args:
            context: Scan context.

        Returns:
            List of coverage issues.
        """
        loop = asyncio.get_event_loop()
        coverage_threshold = 80.0
        coverage_exclude = None
        coverage_command = None
        coverage_pre_command = None
        coverage_post_command = None
        if self.config.pipeline.coverage:
            if self.config.pipeline.coverage.threshold is not None:
                coverage_threshold = self.config.pipeline.coverage.threshold
            if self.config.pipeline.coverage.exclude:
                coverage_exclude = self.config.pipeline.coverage.exclude
            coverage_command = self.config.pipeline.coverage.command
            coverage_pre_command = self.config.pipeline.coverage.pre_command
            coverage_post_command = self.config.pipeline.coverage.post_command
        run_coverage_fn = functools.partial(
            self._runner.run_coverage,
            context,
            threshold=coverage_threshold,
            exclude_patterns=coverage_exclude,
            command=coverage_command,
            pre_command=coverage_pre_command,
            post_command=coverage_post_command,
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
        security_exclude = None
        if self.config.pipeline.security and self.config.pipeline.security.exclude:
            security_exclude = self.config.pipeline.security.exclude
        run_fn = functools.partial(
            self._runner.run_security, context, domain, exclude_patterns=security_exclude
        )
        return await loop.run_in_executor(None, run_fn)

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
        threshold = 5.0
        min_lines = 7
        min_chars = 3
        exclude_patterns = None
        use_baseline = False
        use_cache = True
        use_git = True
        if self.config.pipeline.duplication:
            threshold = self.config.pipeline.duplication.threshold
            min_lines = self.config.pipeline.duplication.min_lines
            min_chars = self.config.pipeline.duplication.min_chars
            exclude_patterns = self.config.pipeline.duplication.exclude or None
            use_baseline = self.config.pipeline.duplication.baseline
            use_cache = self.config.pipeline.duplication.cache
            use_git = self.config.pipeline.duplication.use_git

        run_duplication_fn = functools.partial(
            self._runner.run_duplication,
            context,
            threshold=threshold,
            min_lines=min_lines,
            min_chars=min_chars,
            exclude_patterns=exclude_patterns,
            use_baseline=use_baseline,
            use_cache=use_cache,
            use_git=use_git,
        )
        issues = await loop.run_in_executor(None, run_duplication_fn)
        # Duplication result is stored in context.duplication_result by DomainRunner
        return issues

    def _validate_tools(self, enabled_domains: List[DomainType]):
        """Validate that all configured tools are available.

        Args:
            enabled_domains: List of enabled domain enums.

        Returns:
            ToolValidationResult with success status and any errors.
        """
        from lucidshark.core.tool_validation import validate_configured_tools

        # Convert domain enums to string names for validation
        domain_names: List[str] = []
        for domain in enabled_domains:
            if domain == ToolDomain.LINTING:
                domain_names.append("linting")
            elif domain == ToolDomain.TYPE_CHECKING:
                domain_names.append("type_checking")
            elif domain == ToolDomain.TESTING:
                domain_names.append("testing")
            elif domain == ToolDomain.COVERAGE:
                domain_names.append("coverage")
            elif domain == ToolDomain.DUPLICATION:
                domain_names.append("duplication")
            # Security domains (ScanDomain) don't need tool validation
            # because security tools are auto-downloaded

        return validate_configured_tools(self.config, self.project_root, domain_names)

    def _format_validation_error(self, errors) -> Dict[str, Any]:
        """Format validation errors for MCP response.

        Args:
            errors: List of ToolValidationError objects.

        Returns:
            Dict with error information for MCP response.
        """
        missing_tools = []
        for error in errors:
            tool_info = {
                "domain": error.domain,
                "tool": error.tool_name,
                "reason": error.reason,
            }
            if error.install_instruction:
                tool_info["install"] = error.install_instruction
            missing_tools.append(tool_info)

        return {
            "error": "Missing required tools",
            "missing_tools": missing_tools,
            "blocking": True,
            "total_issues": 0,
            "message": (
                "The following tools are configured but not installed. "
                "Please install them and try again. "
                "Note: Security tools (trivy, opengrep, checkov) and duplo "
                "are downloaded automatically."
            ),
        }
