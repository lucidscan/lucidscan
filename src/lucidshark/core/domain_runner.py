"""Shared domain runner for executing scanner plugins.

This module provides shared functionality for running scanner plugins
across both CLI and MCP interfaces.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

if TYPE_CHECKING:
    from lucidshark.core.models import ToolDomain

from lucidshark.config import LucidSharkConfig
from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext, ScanDomain, UnifiedIssue
from lucidshark.core.streaming import StreamEvent, StreamHandler, StreamType

LOGGER = get_logger(__name__)

# Plugin to supported languages mapping
PLUGIN_LANGUAGES: Dict[str, List[str]] = {
    # Linters
    "ruff": ["python"],
    "eslint": ["javascript", "typescript"],
    "biome": ["javascript", "typescript"],
    "clippy": ["rust"],
    "golangci_lint": ["go"],
    "checkstyle": ["java"],
    "pmd": ["java"],
    # Type checkers
    "mypy": ["python"],
    "pyright": ["python"],
    "typescript": ["typescript"],
    "spotbugs": ["java"],
    "cargo_check": ["rust"],
    "go_vet": ["go"],
    # Test runners
    "pytest": ["python"],
    "jest": ["javascript", "typescript"],
    "vitest": ["javascript", "typescript"],
    "karma": ["javascript", "typescript"],
    "playwright": ["javascript", "typescript"],
    "maven": ["java", "kotlin"],
    "cargo": ["rust"],
    "go_test": ["go"],
    # Coverage
    "coverage_py": ["python"],
    "istanbul": ["javascript", "typescript"],
    "vitest_coverage": ["javascript", "typescript"],
    "jacoco": ["java", "kotlin"],
    "tarpaulin": ["rust"],
    "go_cover": ["go"],
    # Duplication detection
    "duplo": [
        "python",
        "rust",
        "java",
        "javascript",
        "typescript",
        "c",
        "c++",
        "csharp",
        "go",
        "ruby",
    ],
    # Formatters
    "ruff_format": ["python"],
    "prettier": ["javascript", "typescript"],
    "rustfmt": ["rust"],
    "google_java_format": ["java"],
    "gofmt": ["go"],
}

# File extension to language mapping
EXTENSION_LANGUAGE: Dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".tf": "terraform",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


def filter_plugins_by_language(
    plugins: Dict[str, Type[Any]],
    project_languages: List[str],
) -> Dict[str, Type[Any]]:
    """Filter plugins to only those supporting the project's languages.

    Args:
        plugins: Dict of plugin_name -> plugin_class.
        project_languages: List of languages from project config.

    Returns:
        Filtered dict of plugins that support at least one project language.
    """
    if not project_languages:
        return plugins

    filtered = {}
    for name, cls in plugins.items():
        supported_langs = PLUGIN_LANGUAGES.get(name, [])
        # Include plugin if it supports any of the project languages
        # or if the plugin has no language restrictions
        if not supported_langs or any(
            lang.lower() in [sl.lower() for sl in supported_langs]
            for lang in project_languages
        ):
            filtered[name] = cls

    return filtered


def filter_plugins_by_config(
    plugins: Dict[str, Type[Any]],
    config: LucidSharkConfig,
    domain: str,
    project_root: Optional[Path] = None,
) -> Dict[str, Type[Any]]:
    """Filter plugins based on configuration.

    First tries to filter by explicitly configured tools. If none are
    configured, falls back to language-based filtering. If no languages
    are configured, auto-detects languages from the project.

    Args:
        plugins: Dict of plugin_name -> plugin_class.
        config: LucidShark configuration.
        domain: Domain name (linting, type_checking, testing, coverage).
        project_root: Optional project root for auto-detecting languages.

    Returns:
        Filtered dict of plugins.
    """
    configured_tools = config.pipeline.get_enabled_tool_names(domain)
    if configured_tools:
        return {name: cls for name, cls in plugins.items() if name in configured_tools}

    # Use configured languages or auto-detect from project
    languages = config.project.languages
    if not languages and project_root:
        from lucidshark.detection.languages import detect_languages

        detected = detect_languages(project_root)
        languages = [lang.name.lower() for lang in detected]
        LOGGER.debug(f"Auto-detected languages: {languages}")

    return filter_plugins_by_language(plugins, languages)


def filter_scanners_by_config(
    scanners: Dict[str, Type[Any]],
    config: LucidSharkConfig,
    domain: str,
) -> Dict[str, Type[Any]]:
    """Filter scanner plugins based on configuration for a specific domain.

    Supports multiple scanners per domain for defense-in-depth (e.g., both gosec
    and opengrep for SAST).

    Args:
        scanners: Dict of scanner_name -> scanner_class.
        config: LucidShark configuration.
        domain: Scanner domain (sast, sca, iac, container).

    Returns:
        Filtered dict of scanners that are configured for this domain.
    """
    configured_plugins = config.get_plugins_for_domain(domain)
    if configured_plugins:
        return {
            name: cls for name, cls in scanners.items() if name in configured_plugins
        }
    return scanners


def detect_language(path: Path) -> str:
    """Detect language from file extension.

    Args:
        path: File path.

    Returns:
        Language name or "unknown".
    """
    suffix = path.suffix.lower()
    return EXTENSION_LANGUAGE.get(suffix, "unknown")


def get_domains_for_language(language: str) -> List[str]:
    """Get appropriate domains for a language.

    Args:
        language: Language name.

    Returns:
        List of domain names.
    """
    # Default domains for most languages - use specific security domains
    # "sast" for static analysis, "sca" for dependency scanning
    domains = ["linting", "sast", "sca"]

    if language == "python":
        domains.extend(["type_checking", "testing", "coverage", "formatting"])
    elif language in ("javascript", "typescript"):
        domains.extend(["type_checking", "testing", "coverage", "formatting"])
    elif language in ("java", "kotlin"):
        domains.extend(["type_checking", "testing", "coverage", "formatting"])
    elif language == "rust":
        domains.extend(["type_checking", "testing", "coverage", "formatting"])
    elif language == "go":
        domains.extend(["type_checking", "testing", "coverage", "formatting"])
    elif language == "terraform":
        domains = ["iac"]
    elif language in ("yaml", "json"):
        domains = ["iac", "sast"]

    return domains


def _has_vitest_config(project_root: Path) -> bool:
    """Check if project has Vitest configuration."""
    for name in (
        "vitest.config.ts",
        "vitest.config.js",
        "vitest.config.mts",
        "vitest.config.mjs",
        "vite.config.ts",
        "vite.config.js",
        "vite.config.mts",
        "vite.config.mjs",
    ):
        if (project_root / name).exists():
            return True
    return False


def _has_jest_config(project_root: Path) -> bool:
    """Check if project has Jest configuration."""
    for name in (
        "jest.config.js",
        "jest.config.ts",
        "jest.config.cjs",
        "jest.config.mjs",
        "jest.config.json",
    ):
        if (project_root / name).exists():
            return True
    # Check package.json for "jest" key
    pkg_json = project_root / "package.json"
    if pkg_json.exists():
        import json

        try:
            data = json.loads(pkg_json.read_text())
            if "jest" in data:
                return True
        except Exception:
            pass
    return False


class DomainRunner:
    """Executes plugin-based domain scans.

    Provides a unified interface for running linting, type checking,
    testing, coverage, and security scans across both CLI and MCP.
    """

    def __init__(
        self,
        project_root: Path,
        config: LucidSharkConfig,
        log_level: str = "info",
        verbose: bool = False,
        stream_handler: Optional[StreamHandler] = None,
    ):
        """Initialize DomainRunner.

        Args:
            project_root: Project root directory.
            config: LucidShark configuration.
            log_level: Logging level for plugin execution ("info" or "debug").
            verbose: If True, show command output on failure.
            stream_handler: Optional handler for streaming output events.
        """
        self.project_root = project_root
        self.config = config
        self._log_level = log_level
        self._verbose = verbose
        self._stream_handler = stream_handler

    def _log(self, level: str, message: str) -> None:
        """Log a message at the configured level."""
        if level == "info" and self._log_level == "info":
            LOGGER.info(message)
        else:
            LOGGER.debug(message)

    def _log_command_failure(
        self,
        label: str,
        result: subprocess.CompletedProcess[str],
        max_lines: int = 100,
    ) -> None:
        """Log command output when a command fails in verbose mode.

        Shows the last N lines of combined stdout/stderr to help debug failures.
        Output is emitted via stream_handler if available, or logged directly.

        Args:
            label: Label for the command (e.g., "testing.command").
            result: Completed process result with captured output.
            max_lines: Maximum number of lines to show (default 100).
        """
        if not self._verbose:
            return

        # Combine stdout and stderr, preferring stderr for errors
        output = ""
        if result.stderr and result.stderr.strip():
            output = result.stderr.strip()
        if result.stdout and result.stdout.strip():
            if output:
                output = f"{result.stdout.strip()}\n\n--- stderr ---\n{output}"
            else:
                output = result.stdout.strip()

        if not output:
            return

        # Truncate to last N lines
        lines = output.splitlines()
        if len(lines) > max_lines:
            truncated_lines = lines[-max_lines:]
            output = (
                f"... (showing last {max_lines} of {len(lines)} lines)\n"
                + "\n".join(truncated_lines)
            )
        else:
            output = "\n".join(lines)

        # Emit via stream handler if available
        if self._stream_handler:
            self._stream_handler.emit(
                StreamEvent(
                    tool_name=label,
                    stream_type=StreamType.STDERR,
                    content=f"\n=== Output from failed command ===\n{output}\n{'=' * 35}\n",
                )
            )
        else:
            # Fall back to logging
            LOGGER.info(f"{label} output:\n{output}")

    def _context_with_domain_excludes(
        self,
        context: ScanContext,
        domain_exclude_patterns: Optional[List[str]],
    ) -> ScanContext:
        """Create a ScanContext with domain-specific exclude patterns merged in.

        If domain_exclude_patterns is provided and non-empty, merges them
        with the context's existing ignore_patterns. Otherwise returns
        the context unchanged.

        Args:
            context: Original scan context.
            domain_exclude_patterns: Additional exclude patterns for this domain.

        Returns:
            ScanContext with merged ignore patterns, or the original context.
        """
        if not domain_exclude_patterns:
            return context
        from dataclasses import replace

        from lucidshark.config.ignore import IgnorePatterns

        domain_patterns = IgnorePatterns(
            domain_exclude_patterns, source="domain-config"
        )
        merged = IgnorePatterns.merge(context.ignore_patterns, domain_patterns)
        return replace(context, ignore_patterns=merged)

    def run_linting(
        self,
        context: ScanContext,
        fix: bool = False,
        exclude_patterns: Optional[List[str]] = None,
        command: Optional[str] = None,
        pre_command: Optional[str] = None,
        post_command: Optional[str] = None,
    ) -> List[UnifiedIssue]:
        """Run linting checks.

        Args:
            context: Scan context.
            fix: Whether to apply automatic fixes.
            exclude_patterns: Domain-specific exclude patterns to merge.
            command: Custom shell command to run instead of plugins.
            pre_command: Shell command to run before linting (e.g., cleanup).
            post_command: Shell command to run after linting completes.

        Returns:
            List of linting issues.
        """
        context = self._context_with_domain_excludes(context, exclude_patterns)
        from lucidshark.core.models import ToolDomain

        issues: List[UnifiedIssue] = []

        self._run_pre_command(pre_command, "linting.pre_command")

        if command:
            # Custom command overrides plugin-based execution
            result = self._run_shell_command(command, "lint_command")
            issues = self._parse_command_output(result, ToolDomain.LINTING, command)
            if result.returncode != 0:
                self._log_command_failure("lint_command", result)
            self._run_post_command(post_command, "post_lint_command")
            # Track custom command execution
            context.tools_executed.append(
                {
                    "name": "custom",
                    "domains": ["linting"],
                    "success": result.returncode == 0,
                    "error": None
                    if result.returncode == 0
                    else f"Exit code {result.returncode}",
                }
            )
            return issues

        # Fall through to existing plugin-based logic
        from lucidshark.plugins.linters import discover_linter_plugins

        linters = discover_linter_plugins()

        if not linters:
            LOGGER.warning("No linter plugins found")
            return issues

        linters = filter_plugins_by_config(
            linters, self.config, "linting", self.project_root
        )

        for name, plugin_class in linters.items():
            try:
                self._log("info", f"Running linter: {name}")
                plugin = plugin_class(project_root=self.project_root)

                if fix and plugin.supports_fix:
                    fix_result = plugin.fix(context)
                    self._log(
                        "info",
                        f"{name}: Fixed {fix_result.issues_fixed} issues, "
                        f"{fix_result.issues_remaining} remaining",
                    )
                    # Run again to get remaining issues
                    issues.extend(plugin.lint(context))
                else:
                    issues.extend(plugin.lint(context))

                context.tools_executed.append(
                    {
                        "name": name,
                        "domains": ["linting"],
                        "success": True,
                        "error": None,
                    }
                )

            except Exception as e:
                LOGGER.error(f"Linter {name} failed: {e}")

        self._run_post_command(post_command, "post_lint_command")
        return issues

    def run_formatting(
        self,
        context: ScanContext,
        fix: bool = False,
        exclude_patterns: Optional[List[str]] = None,
        command: Optional[str] = None,
        pre_command: Optional[str] = None,
        post_command: Optional[str] = None,
    ) -> List[UnifiedIssue]:
        """Run formatting checks.

        Args:
            context: Scan context.
            fix: Whether to apply automatic formatting.
            exclude_patterns: Domain-specific exclude patterns to merge.
            command: Custom shell command to run instead of plugins.
            pre_command: Shell command to run before formatting.
            post_command: Shell command to run after formatting.

        Returns:
            List of formatting issues.
        """
        context = self._context_with_domain_excludes(context, exclude_patterns)
        from lucidshark.core.models import ToolDomain

        issues: List[UnifiedIssue] = []

        self._run_pre_command(pre_command, "formatting.pre_command")

        if command:
            result = self._run_shell_command(command, "formatting_command")
            issues = self._parse_command_output(result, ToolDomain.FORMATTING, command)
            if result.returncode != 0:
                self._log_command_failure("formatting_command", result)
            self._run_post_command(post_command, "post_formatting_command")
            # Track custom command execution
            context.tools_executed.append(
                {
                    "name": "custom",
                    "domains": ["formatting"],
                    "success": result.returncode == 0,
                    "error": None
                    if result.returncode == 0
                    else f"Exit code {result.returncode}",
                }
            )
            return issues

        from lucidshark.plugins.formatters import discover_formatter_plugins

        formatters = discover_formatter_plugins()

        if not formatters:
            LOGGER.warning("No formatter plugins found")
            return issues

        formatters = filter_plugins_by_config(
            formatters, self.config, "formatting", self.project_root
        )

        for name, plugin_class in formatters.items():
            try:
                self._log("info", f"Running formatter: {name}")
                plugin = plugin_class(project_root=self.project_root)

                if fix and plugin.supports_fix:
                    fix_result = plugin.fix(context)
                    self._log(
                        "info",
                        f"{name}: Fixed {fix_result.issues_fixed} issues, "
                        f"{fix_result.issues_remaining} remaining",
                    )
                    issues.extend(plugin.check(context))
                else:
                    issues.extend(plugin.check(context))

                context.tools_executed.append(
                    {
                        "name": name,
                        "domains": ["formatting"],
                        "success": True,
                        "error": None,
                    }
                )

            except Exception as e:
                LOGGER.error(f"Formatter {name} failed: {e}")

        self._run_post_command(post_command, "post_formatting_command")
        return issues

    def run_type_checking(
        self,
        context: ScanContext,
        exclude_patterns: Optional[List[str]] = None,
        command: Optional[str] = None,
        pre_command: Optional[str] = None,
        post_command: Optional[str] = None,
    ) -> List[UnifiedIssue]:
        """Run type checking.

        Args:
            context: Scan context.
            exclude_patterns: Domain-specific exclude patterns to merge.
            command: Custom shell command to run instead of plugins.
            pre_command: Shell command to run before type checking (e.g., cleanup).
            post_command: Shell command to run after type checking completes.

        Returns:
            List of type checking issues.
        """
        context = self._context_with_domain_excludes(context, exclude_patterns)
        from lucidshark.core.models import ToolDomain

        issues: List[UnifiedIssue] = []

        self._run_pre_command(pre_command, "type_checking.pre_command")

        if command:
            # Custom command overrides plugin-based execution
            result = self._run_shell_command(command, "type_check_command")
            issues = self._parse_command_output(
                result, ToolDomain.TYPE_CHECKING, command
            )
            if result.returncode != 0:
                self._log_command_failure("type_check_command", result)
            self._run_post_command(post_command, "post_type_check_command")
            # Track custom command execution
            context.tools_executed.append(
                {
                    "name": "custom",
                    "domains": ["type_checking"],
                    "success": result.returncode == 0,
                    "error": None
                    if result.returncode == 0
                    else f"Exit code {result.returncode}",
                }
            )
            return issues

        # Fall through to existing plugin-based logic
        from lucidshark.plugins.type_checkers import discover_type_checker_plugins

        checkers = discover_type_checker_plugins()

        if not checkers:
            LOGGER.warning("No type checker plugins found")
            return issues

        checkers = filter_plugins_by_config(
            checkers, self.config, "type_checking", self.project_root
        )

        for name, plugin_class in checkers.items():
            try:
                self._log("info", f"Running type checker: {name}")
                plugin = plugin_class(project_root=self.project_root)
                issues.extend(plugin.check(context))

                context.tools_executed.append(
                    {
                        "name": name,
                        "domains": ["type_checking"],
                        "success": True,
                        "error": None,
                    }
                )

            except Exception as e:
                LOGGER.error(f"Type checker {name} failed: {e}")

        self._run_post_command(post_command, "post_type_check_command")
        return issues

    def _run_shell_command(
        self, command: str, label: str
    ) -> subprocess.CompletedProcess[str]:
        """Run a shell command and log its execution.

        Extends PATH to include common tool directories (Go, Rust, Node, etc.).

        Args:
            command: Shell command to execute.
            label: Label for logging (e.g., "testing.command", "linting.command").

        Returns:
            CompletedProcess result.
        """
        import os
        from pathlib import Path as PathLib

        # Build extended PATH with common tool directories
        extra_paths = []

        # Go tools: $GOPATH/bin and ~/go/bin
        gopath = os.getenv("GOPATH")
        if gopath:
            extra_paths.append(str(PathLib(gopath) / "bin"))
        home = PathLib.home()
        go_bin = home / "go" / "bin"
        if go_bin.exists():
            extra_paths.append(str(go_bin))

        # Rust tools: ~/.cargo/bin
        cargo_bin = home / ".cargo" / "bin"
        if cargo_bin.exists():
            extra_paths.append(str(cargo_bin))

        # Node tools: local node_modules/.bin
        node_bin = self.project_root / "node_modules" / ".bin"
        if node_bin.exists():
            extra_paths.append(str(node_bin))

        # Build environment with extended PATH
        env = os.environ.copy()
        if extra_paths:
            current_path = env.get("PATH", "")
            extended_path = os.pathsep.join(extra_paths + [current_path])
            env["PATH"] = extended_path

        self._log("info", f"Running {label}: {command}")
        return subprocess.run(
            command,
            shell=True,  # nosemgrep: subprocess-shell-true - command is from project config file, not untrusted input
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            env=env,
        )

    def _run_pre_command(self, pre_command: Optional[str], label: str) -> None:
        """Run a pre-command if provided and log any failures.

        Pre-commands run before the main operation, typically for cleanup
        (e.g., stopping leftover Docker containers before tests).

        Args:
            pre_command: Optional shell command to execute before main operation.
            label: Label for logging (e.g., "testing.pre_command").
        """
        if not pre_command:
            return
        pre_result = self._run_shell_command(pre_command, label)
        if pre_result.returncode != 0:
            LOGGER.warning(
                f"{label} failed (exit code {pre_result.returncode}): "
                f"{pre_result.stderr.strip()[:200] if pre_result.stderr else ''}"
            )
            self._log_command_failure(label, pre_result)

    def _run_post_command(self, post_command: Optional[str], label: str) -> None:
        """Run a post-command if provided and log any failures.

        Args:
            post_command: Optional shell command to execute after main operation.
            label: Label for logging (e.g., "post_lint_command", "testing.post_command").
        """
        if not post_command:
            return
        post_result = self._run_shell_command(post_command, label)
        if post_result.returncode != 0:
            LOGGER.warning(
                f"{label} failed (exit code {post_result.returncode}): "
                f"{post_result.stderr.strip()[:200] if post_result.stderr else ''}"
            )
            self._log_command_failure(label, post_result)

    def _parse_command_output(
        self,
        result: subprocess.CompletedProcess[str],
        domain: "ToolDomain",
        command: str,
    ) -> List[UnifiedIssue]:
        """Auto-detect and parse command output into UnifiedIssues.

        CRITICAL: Attempts to parse output REGARDLESS of exit code. Many linters
        (golangci-lint, eslint, etc.) return non-zero when they find issues but
        still produce parseable output. Only create a generic error if parsing fails.

        Tries formats in order: SARIF → JSON → plain text → generic error.

        Args:
            result: Completed process result from shell command.
            domain: The tool domain (linting, type_checking, etc.).
            command: The command that was run (for error messages).

        Returns:
            List of UnifiedIssue parsed from output.
        """
        from lucidshark.core.models import Severity

        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""
        issues: List[UnifiedIssue] = []

        # Try SARIF first (check for schema marker)
        if '"$schema"' in stdout and "sarif" in stdout.lower():
            try:
                sarif_issues = self._parse_sarif_output(stdout, domain)
                if sarif_issues:
                    LOGGER.debug(f"Parsed {len(sarif_issues)} issues from SARIF output")
                    return sarif_issues
            except Exception as e:
                LOGGER.debug(f"SARIF parsing failed: {e}")

        # Try JSON (array or object)
        if stdout.startswith("[") or stdout.startswith("{"):
            try:
                json_issues = self._parse_json_output(stdout, domain)
                if json_issues:
                    LOGGER.debug(f"Parsed {len(json_issues)} issues from JSON output")
                    return json_issues
            except Exception as e:
                LOGGER.debug(f"JSON parsing failed: {e}")

        # Try plain text parsing on both stdout and stderr
        # Many linters output issues to stderr (golangci-lint, eslint, etc.)
        for text_source, text_to_parse in [("stderr", stderr), ("stdout", stdout)]:
            if text_to_parse:
                text_issues = self._parse_text_output(text_to_parse, domain)
                if text_issues:
                    LOGGER.debug(
                        f"Parsed {len(text_issues)} issues from {text_source} (text output)"
                    )
                    return text_issues

        # Last resort: create generic issue ONLY if exit code is non-zero AND no issues parsed
        if result.returncode != 0:
            output = stderr or stdout or "Command failed with no output"
            # Truncate to avoid massive error messages
            output_snippet = output[:2000]
            issues.append(
                UnifiedIssue(
                    id=f"custom-{domain.value}-failure",
                    domain=domain,
                    source_tool="custom",
                    severity=Severity.MEDIUM,
                    rule_id=f"{domain.value}-failure",
                    title=f"Custom {domain.value} command failed",
                    description=f"Command `{command}` exited with code {result.returncode}.\n\nOutput:\n{output_snippet}",
                )
            )

        return issues

    def _parse_sarif_output(
        self,
        sarif_str: str,
        domain: "ToolDomain",
    ) -> List[UnifiedIssue]:
        """Parse SARIF 2.1.0 output into UnifiedIssues.

        Args:
            sarif_str: SARIF JSON string.
            domain: The tool domain for issues.

        Returns:
            List of UnifiedIssue parsed from SARIF.
        """
        import json

        from lucidshark.core.models import Severity

        data = json.loads(sarif_str)
        issues: List[UnifiedIssue] = []

        # SARIF level to Severity mapping
        level_to_severity = {
            "error": Severity.HIGH,
            "warning": Severity.MEDIUM,
            "note": Severity.LOW,
            "none": Severity.INFO,
        }

        for run in data.get("runs", []):
            tool_name = run.get("tool", {}).get("driver", {}).get("name", "unknown")
            rules = {
                r["id"]: r
                for r in run.get("tool", {}).get("driver", {}).get("rules", [])
            }

            for result in run.get("results", []):
                rule_id = result.get("ruleId", "unknown")
                level = result.get("level", "warning")
                message = result.get("message", {}).get("text", "")

                # Get location info
                locations = result.get("locations", [])
                file_path = None
                line = None
                if locations:
                    physical_loc = locations[0].get("physicalLocation", {})
                    artifact_loc = physical_loc.get("artifactLocation", {})
                    file_path = artifact_loc.get("uri")
                    region = physical_loc.get("region", {})
                    line = region.get("startLine")

                # Get rule info for title/description
                rule_info = rules.get(rule_id, {})
                title = rule_info.get("shortDescription", {}).get("text") or rule_id
                description = message or rule_info.get("fullDescription", {}).get(
                    "text", ""
                )

                issues.append(
                    UnifiedIssue(
                        id=f"{tool_name}-{rule_id}-{len(issues)}",
                        domain=domain,
                        source_tool=tool_name,
                        severity=level_to_severity.get(level, Severity.MEDIUM),
                        rule_id=rule_id,
                        title=title,
                        description=description,
                        file_path=file_path,
                        line_start=line,
                    )
                )

        return issues

    def _parse_json_output(
        self,
        json_str: str,
        domain: "ToolDomain",
    ) -> List[UnifiedIssue]:
        """Parse generic JSON output into UnifiedIssues.

        Supports common JSON formats from linters/type checkers.
        Tries to extract: file, line, column, message, severity, rule.

        Args:
            json_str: JSON string (array or object).
            domain: The tool domain for issues.

        Returns:
            List of UnifiedIssue parsed from JSON.
        """
        import json

        from lucidshark.core.models import Severity

        data = json.loads(json_str)
        issues: List[UnifiedIssue] = []

        # Common severity mappings
        severity_map = {
            "error": Severity.HIGH,
            "err": Severity.HIGH,
            "e": Severity.HIGH,
            "warning": Severity.MEDIUM,
            "warn": Severity.MEDIUM,
            "w": Severity.MEDIUM,
            "info": Severity.LOW,
            "information": Severity.LOW,
            "i": Severity.LOW,
            "hint": Severity.INFO,
            "note": Severity.INFO,
        }

        def parse_severity(val: Any) -> Severity:
            if isinstance(val, str):
                return severity_map.get(val.lower(), Severity.MEDIUM)
            if isinstance(val, int):
                # 1=error, 2=warning pattern (ESLint style)
                if val == 1:
                    return Severity.MEDIUM
                if val == 2:
                    return Severity.HIGH
            return Severity.MEDIUM

        def parse_item(item: Dict[str, Any], idx: int) -> Optional[UnifiedIssue]:
            """Parse a single item from the JSON output."""
            # Common field names for file path
            file_path = (
                item.get("file")
                or item.get("path")
                or item.get("filename")
                or item.get("filePath")
            )

            # Common field names for line number
            line = (
                item.get("line")
                or item.get("startLine")
                or item.get("lineNumber")
                or item.get("row")
            )

            # Common field names for message
            message = (
                item.get("message")
                or item.get("description")
                or item.get("text")
                or item.get("msg")
            )

            if not message:
                return None

            # Common field names for rule ID
            rule_id = (
                item.get("rule")
                or item.get("ruleId")
                or item.get("code")
                or item.get("check")
                or "unknown"
            )

            # Common field names for severity
            sev_val = (
                item.get("severity")
                or item.get("level")
                or item.get("type")
                or "warning"
            )

            return UnifiedIssue(
                id=f"custom-{domain.value}-{idx}",
                domain=domain,
                source_tool="custom",
                severity=parse_severity(sev_val),
                rule_id=str(rule_id),
                title=str(message)[:100],
                description=str(message),
                file_path=Path(file_path) if file_path else None,
                line_start=int(line) if line else None,
            )

        # Handle array of issues
        if isinstance(data, list):
            for idx, item in enumerate(data):
                if isinstance(item, dict):
                    issue = parse_item(item, idx)
                    if issue:
                        issues.append(issue)

        # Handle object with issues array (common pattern)
        elif isinstance(data, dict):
            # Look for common array field names
            items = (
                data.get("issues")
                or data.get("errors")
                or data.get("warnings")
                or data.get("diagnostics")
                or data.get("results")
                or data.get("messages")
                or []
            )
            if isinstance(items, list):
                for idx, item in enumerate(items):
                    if isinstance(item, dict):
                        issue = parse_item(item, idx)
                        if issue:
                            issues.append(issue)

        return issues

    def _parse_text_output(
        self,
        text: str,
        domain: "ToolDomain",
    ) -> List[UnifiedIssue]:
        """Parse plain text output into UnifiedIssues.

        Handles common text formats from linters/type checkers:
        - file.go:42:15: message
        - file.go:42: message
        - /path/to/file.go:42:15: message
        - file.py:42: error: message
        - file.py:42:15: E501 message

        Args:
            text: Plain text output from command.
            domain: The tool domain for issues.

        Returns:
            List of UnifiedIssue parsed from text.
        """
        import re

        from lucidshark.core.models import Severity

        issues: List[UnifiedIssue] = []
        lines = text.splitlines()

        # Common patterns for lint/type check output
        patterns = [
            # file.go:42:15: message or /path/to/file.go:42:15: message
            re.compile(
                r"^(.+?):(\d+):(\d+):\s*(?:(error|warning|info|note):?\s*)?(.+)$"
            ),
            # file.go:42: message or file.go:42: error: message
            re.compile(r"^(.+?):(\d+):\s*(?:(error|warning|info|note):?\s*)?(.+)$"),
            # file.py:42:15: E501 message (Python linter style)
            re.compile(r"^(.+?):(\d+):(\d+):\s*([A-Z]\d+)\s+(.+)$"),
            # file.py:42: E501 message
            re.compile(r"^(.+?):(\d+):\s*([A-Z]\d+)\s+(.+)$"),
        ]

        severity_keywords = {
            "error": Severity.HIGH,
            "err": Severity.HIGH,
            "warning": Severity.MEDIUM,
            "warn": Severity.MEDIUM,
            "info": Severity.LOW,
            "information": Severity.LOW,
            "note": Severity.INFO,
        }

        idx = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue

            matched = False
            for pattern in patterns:
                match = pattern.match(line)
                if match:
                    matched = True
                    groups = match.groups()

                    if len(groups) == 5:  # file:line:col:severity:message pattern
                        file_path, line_num, col_num, sev_str, message = groups
                        rule_id = "unknown"
                    elif len(groups) == 5 and groups[3].startswith(
                        ("E", "W", "F", "C")
                    ):  # file:line:col:RULE:message
                        file_path, line_num, col_num, rule_id, message = groups
                        sev_str = "warning"  # default for rule-based output
                    elif len(groups) == 4 and ":" in line:  # file:line:severity:message
                        file_path, line_num, sev_str, message = groups
                        col_num = None
                        rule_id = "unknown"
                    elif len(groups) == 4:  # file:line:RULE:message
                        file_path, line_num, rule_id, message = groups
                        col_num = None
                        sev_str = "warning"
                    else:
                        continue  # Skip if we can't parse properly

                    # Determine severity
                    severity = Severity.MEDIUM
                    if sev_str:
                        severity = severity_keywords.get(
                            sev_str.lower(), Severity.MEDIUM
                        )

                    # Skip empty messages
                    if not message or not message.strip():
                        continue

                    issues.append(
                        UnifiedIssue(
                            id=f"custom-{domain.value}-{idx}",
                            domain=domain,
                            source_tool="custom",
                            severity=severity,
                            rule_id=rule_id if rule_id != "unknown" else domain.value,
                            title=message.strip()[:100],
                            description=message.strip(),
                            file_path=Path(file_path) if file_path else None,
                            line_start=int(line_num) if line_num else None,
                            column_start=int(col_num) if col_num else None,
                        )
                    )
                    idx += 1
                    break

            # If no pattern matched and line looks like it might be an issue, skip it
            # This avoids creating issues from informational lines
            if not matched and any(
                keyword in line.lower()
                for keyword in ["error", "warning", "failed", "issue"]
            ):
                # Could be part of a summary or other output, skip
                pass

        return issues

    def run_tests(
        self,
        context: ScanContext,
        exclude_patterns: Optional[List[str]] = None,
        command: Optional[str] = None,
        pre_command: Optional[str] = None,
        post_command: Optional[str] = None,
    ) -> List[UnifiedIssue]:
        """Run test suite.

        Tests always generate coverage data when the appropriate coverage
        tool is available.

        Args:
            context: Scan context.
            exclude_patterns: Domain-specific exclude patterns to merge.
            command: Custom shell command to run tests. Overrides plugin-based runner.
            pre_command: Shell command to run before tests (e.g., cleanup containers).
            post_command: Shell command to run after tests complete.

        Returns:
            List of test failure issues.
        """
        context = self._context_with_domain_excludes(context, exclude_patterns)
        from lucidshark.core.models import Severity, ToolDomain

        issues: List[UnifiedIssue] = []

        self._run_pre_command(pre_command, "testing.pre_command")

        if command:
            # Custom command overrides plugin-based execution
            result = self._run_shell_command(command, "testing.command")

            if result.returncode != 0:
                # Non-zero exit code means test failures
                stderr_snippet = result.stderr.strip()[:2000] if result.stderr else ""
                stdout_snippet = result.stdout.strip()[:2000] if result.stdout else ""
                output = stderr_snippet or stdout_snippet or "Test command failed"
                issues.append(
                    UnifiedIssue(
                        id="custom-test-failure",
                        domain=ToolDomain.TESTING,
                        source_tool="custom",
                        severity=Severity.HIGH,
                        rule_id="test-failure",
                        title="Custom test command failed",
                        description=f"Command `{command}` exited with code {result.returncode}.\n\n{output}",
                    )
                )
                self._log(
                    "info", f"testing.command: FAILED (exit code {result.returncode})"
                )
                self._log_command_failure("testing.command", result)
            else:
                self._log("info", "testing.command: PASSED")

            self._run_post_command(post_command, "testing.post_command")
            # Track custom command execution
            context.tools_executed.append(
                {
                    "name": "custom",
                    "domains": ["testing"],
                    "success": result.returncode == 0,
                    "error": None
                    if result.returncode == 0
                    else f"Exit code {result.returncode}",
                }
            )
            return issues

        # Fall through to existing plugin-based logic
        from lucidshark.plugins.test_runners import discover_test_runner_plugins

        runners = discover_test_runner_plugins()

        if not runners:
            LOGGER.warning("No test runner plugins found")
        else:
            runners = filter_plugins_by_config(
                runners, self.config, "testing", self.project_root
            )

            for name, plugin_class in runners.items():
                try:
                    self._log("info", f"Running test runner: {name}")
                    plugin = plugin_class(project_root=self.project_root)
                    result = plugin.run_tests(context)

                    self._log(
                        "info",
                        f"{name}: {result.passed} passed, {result.failed} failed, "
                        f"{result.skipped} skipped, {result.errors} errors",
                    )

                    issues.extend(result.issues)

                    context.tools_executed.append(
                        {
                            "name": name,
                            "domains": ["testing"],
                            "success": True,
                            "error": None,
                        }
                    )

                    # Create summary issue if tests failed
                    if not result.success:
                        issues.append(
                            UnifiedIssue(
                                id=f"{name}-test-failure",
                                domain=ToolDomain.TESTING,
                                source_tool=name,
                                severity=Severity.HIGH,
                                rule_id="test-failure",
                                title=f"{name}: {result.failed} failed, {result.errors} errors",
                                description=(
                                    f"Test suite failed: {result.passed} passed, "
                                    f"{result.failed} failed, {result.skipped} skipped, "
                                    f"{result.errors} errors"
                                ),
                            )
                        )

                except FileNotFoundError:
                    LOGGER.debug(f"Test runner {name} not available")
                except Exception as e:
                    LOGGER.error(f"Test runner {name} failed: {e}")

        self._run_post_command(post_command, "testing.post_command")
        return issues

    def run_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
        exclude_patterns: Optional[List[str]] = None,
        command: Optional[str] = None,
        pre_command: Optional[str] = None,
        post_command: Optional[str] = None,
    ) -> List[UnifiedIssue]:
        """Run coverage analysis.

        Coverage plugins only parse existing coverage data files generated by
        test runners. They never run tests independently. If no coverage data
        is found, an error issue is returned.

        Args:
            context: Scan context.
            threshold: Coverage percentage threshold.
            exclude_patterns: Domain-specific exclude patterns to merge.
            command: Custom shell command to run coverage. Overrides plugin-based runner.
            pre_command: Shell command to run before coverage (e.g., cleanup).
            post_command: Shell command to run after coverage completes.

        Returns:
            List of coverage issues.
        """
        # Save reference to original context - _context_with_domain_excludes may
        # return a copy when exclude_patterns are provided, but we need to set
        # coverage_result on the original context for the caller to access it
        original_context = context
        context = self._context_with_domain_excludes(context, exclude_patterns)
        from lucidshark.core.models import Severity, ToolDomain

        issues: List[UnifiedIssue] = []

        self._run_pre_command(pre_command, "coverage.pre_command")

        if command:
            # Custom command overrides plugin-based execution
            result = self._run_shell_command(command, "coverage_command")

            if result.returncode != 0:
                # Non-zero exit code means coverage failure (below threshold or error)
                stderr_snippet = result.stderr.strip()[:2000] if result.stderr else ""
                stdout_snippet = result.stdout.strip()[:2000] if result.stdout else ""
                output = stderr_snippet or stdout_snippet or "Coverage command failed"
                issues.append(
                    UnifiedIssue(
                        id="custom-coverage-failure",
                        domain=ToolDomain.COVERAGE,
                        source_tool="custom",
                        severity=Severity.MEDIUM,
                        rule_id="coverage-failure",
                        title="Custom coverage command failed",
                        description=f"Command `{command}` exited with code {result.returncode}.\n\n{output}",
                    )
                )
                self._log(
                    "info", f"coverage_command: FAILED (exit code {result.returncode})"
                )
                self._log_command_failure("coverage_command", result)
                # Set a minimal coverage result to indicate coverage ran but failed
                from lucidshark.plugins.coverage.base import CoverageResult

                context.coverage_result = CoverageResult(
                    threshold=threshold,
                    tool="custom",
                    issues=issues.copy(),
                )
            else:
                self._log("info", "coverage_command: PASSED")
                # Set a minimal coverage result to indicate coverage ran
                # Custom commands don't provide detailed coverage data
                from lucidshark.plugins.coverage.base import CoverageResult

                context.coverage_result = CoverageResult(
                    threshold=threshold,
                    tool="custom",
                )

            self._run_post_command(post_command, "post_coverage_command")
            # Track custom command execution
            context.tools_executed.append(
                {
                    "name": "custom",
                    "domains": ["coverage"],
                    "success": result.returncode == 0,
                    "error": None
                    if result.returncode == 0
                    else f"Exit code {result.returncode}",
                }
            )
            # Copy coverage_result back to original context if we created a copy
            if original_context is not context:
                original_context.coverage_result = context.coverage_result
            return issues

        # Fall through to plugin-based logic
        from lucidshark.plugins.coverage import discover_coverage_plugins

        plugins = discover_coverage_plugins()

        if not plugins:
            LOGGER.warning("No coverage plugins found")
        else:
            plugins = filter_plugins_by_config(
                plugins, self.config, "coverage", self.project_root
            )

            # Deduplicate JS/TS coverage plugins when auto-detected (not explicitly configured)
            configured_tools = self.config.pipeline.get_enabled_tool_names("coverage")
            if (
                not configured_tools
                and "istanbul" in plugins
                and "vitest_coverage" in plugins
            ):
                if _has_vitest_config(self.project_root):
                    del plugins["istanbul"]
                    LOGGER.debug(
                        "Auto-selected vitest_coverage over istanbul (vitest config found)"
                    )
                elif _has_jest_config(self.project_root):
                    del plugins["vitest_coverage"]
                    LOGGER.debug(
                        "Auto-selected istanbul over vitest_coverage (jest config found)"
                    )
                else:
                    # Default: prefer istanbul (more widely used)
                    del plugins["vitest_coverage"]
                    LOGGER.debug(
                        "Auto-selected istanbul over vitest_coverage (default)"
                    )

            for name, plugin_class in plugins.items():
                try:
                    self._log("info", f"Running coverage: {name}")
                    plugin = plugin_class(project_root=self.project_root)
                    result = plugin.measure_coverage(context, threshold=threshold)

                    # Store the coverage result IMMEDIATELY after getting it
                    # This ensures it's set even if subsequent operations fail
                    context.coverage_result = result

                    status = "PASSED" if result.passed else "FAILED"

                    # Build log message with test stats if available
                    log_parts = [
                        f"{name}: {result.percentage:.1f}%",
                        f"({result.covered_lines}/{result.total_lines} lines)",
                        f"- threshold: {threshold}%",
                        f"- {status}",
                    ]
                    self._log("info", " ".join(log_parts))

                    issues.extend(result.issues)

                    context.tools_executed.append(
                        {
                            "name": name,
                            "domains": ["coverage"],
                            "success": True,
                            "error": None,
                        }
                    )

                except FileNotFoundError:
                    LOGGER.debug(f"Coverage plugin {name} not available")
                except Exception as e:
                    LOGGER.error(f"Coverage plugin {name} failed: {e}")

        self._run_post_command(post_command, "post_coverage_command")

        # Copy coverage_result back to original context if we created a copy
        if original_context is not context:
            original_context.coverage_result = context.coverage_result

        return issues

    def run_duplication(
        self,
        context: ScanContext,
        threshold: float = 10.0,
        min_lines: int = 4,
        min_chars: int = 3,
        exclude_patterns: Optional[List[str]] = None,
        use_baseline: bool = False,
        use_cache: bool = True,
        use_git: bool = True,
    ) -> List[UnifiedIssue]:
        """Run duplication detection.

        Note: Duplication detection always scans the entire project to
        detect cross-file duplicates, regardless of paths in context.

        Args:
            context: Scan context.
            threshold: Maximum allowed duplication percentage.
            min_lines: Minimum lines for a duplicate block.
            min_chars: Minimum characters per line.
            exclude_patterns: Additional patterns to exclude from duplication scan.
            use_baseline: If True, track known duplicates and only report new ones.
            use_cache: If True, cache processed files for faster re-runs.
            use_git: If True, use git ls-files for file discovery when in a git repo.

        Returns:
            List of duplication issues.
        """
        from lucidshark.plugins.duplication import discover_duplication_plugins

        issues: List[UnifiedIssue] = []
        plugins = discover_duplication_plugins()

        if not plugins:
            LOGGER.warning("No duplication plugins found")
            return issues

        plugins = filter_plugins_by_config(
            plugins, self.config, "duplication", self.project_root
        )

        for name, plugin_class in plugins.items():
            try:
                self._log("info", f"Running duplication detection: {name}")
                plugin = plugin_class(project_root=self.project_root)
                result = plugin.detect_duplication(
                    context,
                    threshold=threshold,
                    min_lines=min_lines,
                    min_chars=min_chars,
                    exclude_patterns=exclude_patterns,
                    use_baseline=use_baseline,
                    use_cache=use_cache,
                    use_git=use_git,
                )

                status = "PASSED" if result.passed else "FAILED"
                self._log(
                    "info",
                    f"{name}: {result.duplication_percent:.1f}% duplication "
                    f"({result.duplicate_blocks} blocks, {result.duplicate_lines} lines) "
                    f"- threshold: {threshold}% - {status}",
                )

                # Store result in context for CLI/MCP to access
                context.duplication_result = result

                issues.extend(result.issues)

                context.tools_executed.append(
                    {
                        "name": name,
                        "domains": ["duplication"],
                        "success": True,
                        "error": None,
                    }
                )

            except FileNotFoundError:
                LOGGER.debug(f"Duplication plugin {name} not available")
            except Exception as e:
                LOGGER.error(f"Duplication plugin {name} failed: {e}")

        return issues

    def run_security(
        self,
        context: ScanContext,
        domain: ScanDomain,
        exclude_patterns: Optional[List[str]] = None,
    ) -> List[UnifiedIssue]:
        """Run security scanner for a specific domain.

        Args:
            context: Scan context.
            domain: Scanner domain (SAST, SCA, IAC, CONTAINER).
            exclude_patterns: Domain-specific exclude patterns to merge.

        Returns:
            List of security issues.
        """
        context = self._context_with_domain_excludes(context, exclude_patterns)
        from lucidshark.plugins.scanners import discover_scanner_plugins

        issues: List[UnifiedIssue] = []
        scanners = discover_scanner_plugins()

        if not scanners:
            LOGGER.warning("No scanner plugins found")
            return issues

        # Filter by configured plugin for this domain
        domain_str = domain.value.lower()
        scanners = filter_scanners_by_config(scanners, self.config, domain_str)

        for name, scanner_class in scanners.items():
            try:
                scanner = scanner_class(project_root=self.project_root)
                if domain in scanner.domains:
                    self._log("info", f"Running {domain_str} scanner: {name}")
                    result = scanner.scan(context)
                    issues.extend(result)

            except Exception as e:
                LOGGER.error(f"Scanner {name} failed: {e}")

        return issues


def check_severity_threshold(
    issues: List[UnifiedIssue],
    threshold: Optional[str],
) -> bool:
    """Check if any issues meet or exceed the severity threshold.

    Args:
        issues: List of issues to check.
        threshold: Severity threshold ('critical', 'high', 'medium', 'low').

    Returns:
        True if issues at or above threshold exist, False otherwise.
    """
    if not threshold or not issues:
        return False

    threshold_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    threshold_level = threshold_order.get(threshold.lower(), 99)

    for issue in issues:
        issue_level = threshold_order.get(issue.severity.value, 99)
        if issue_level <= threshold_level:
            return True

    return False
