"""Argument parser construction for lucidshark CLI.

This module builds the argument parser with subcommands:
- lucidshark init          - Configure AI tools (Claude Code, Cursor)
- lucidshark autoconfigure - Auto-configure project (generate lucidshark.yml)
- lucidshark scan          - Run security/quality scans
- lucidshark status        - Show configuration and tool status
- lucidshark serve         - Run as MCP server or file watcher
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _add_global_options(parser: argparse.ArgumentParser) -> None:
    """Add global options available to all commands."""
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show lucidshark version and exit.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (info-level) logging.",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce logging output to errors only.",
    )


def _build_init_parser(subparsers: argparse._SubParsersAction) -> None:
    """Build the 'init' subcommand parser.

    This command configures AI tools (Claude Code, Cursor) to use LucidShark.
    """
    init_parser = subparsers.add_parser(
        "init",
        help="Configure AI tools to use LucidShark.",
        description=(
            "Configure Claude Code, Cursor, or other MCP-compatible AI tools "
            "to use LucidShark for code quality checks."
        ),
    )

    # Tool selection
    tool_group = init_parser.add_argument_group("AI tools")
    tool_group.add_argument(
        "--claude-code",
        action="store_true",
        help="Configure Claude Code MCP settings.",
    )
    tool_group.add_argument(
        "--cursor",
        action="store_true",
        help="Configure Cursor MCP settings.",
    )
    tool_group.add_argument(
        "--all",
        action="store_true",
        dest="init_all",
        help="Configure all supported AI tools.",
    )

    # Options
    options_group = init_parser.add_argument_group("options")
    options_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes.",
    )
    options_group.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing LucidShark configuration.",
    )
    options_group.add_argument(
        "--remove",
        action="store_true",
        help="Remove LucidShark from the specified tool's configuration.",
    )


def _build_autoconfigure_parser(subparsers: argparse._SubParsersAction) -> None:
    """Build the 'autoconfigure' subcommand parser.

    This command detects project characteristics and generates lucidshark.yml.
    """
    autoconfigure_parser = subparsers.add_parser(
        "autoconfigure",
        help="Auto-configure LucidShark for the current project.",
        description=(
            "Analyze your codebase, detect languages and frameworks, "
            "and generate lucidshark.yml configuration."
        ),
    )
    autoconfigure_parser.add_argument(
        "--non-interactive", "-y",
        action="store_true",
        help="Use defaults without prompting (non-interactive mode).",
    )
    autoconfigure_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing configuration files.",
    )
    autoconfigure_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory to autoconfigure (default: current directory).",
    )


def _build_scan_parser(subparsers: argparse._SubParsersAction) -> None:
    """Build the 'scan' subcommand parser."""
    scan_parser = subparsers.add_parser(
        "scan",
        help="Run the quality/security pipeline.",
        description=(
            "Execute configured scanners and linters. "
            "Results are output in the specified format."
        ),
    )

    # Domain selection
    domain_group = scan_parser.add_argument_group("scan domains")
    domain_group.add_argument(
        "--sca",
        action="store_true",
        help="Scan dependencies for known vulnerabilities (uses Trivy).",
    )
    domain_group.add_argument(
        "--container",
        action="store_true",
        help="Scan container images for vulnerabilities. Use with --image.",
    )
    domain_group.add_argument(
        "--iac",
        action="store_true",
        help="Scan Infrastructure-as-Code (Terraform, K8s, CloudFormation).",
    )
    domain_group.add_argument(
        "--sast",
        action="store_true",
        help="Static application security testing (code pattern analysis).",
    )
    domain_group.add_argument(
        "--linting",
        action="store_true",
        help="Run linting checks (Ruff for Python, ESLint for JS/TS).",
    )
    domain_group.add_argument(
        "--type-checking",
        action="store_true",
        help="Run type checking (mypy/pyright for Python, tsc for TypeScript).",
    )
    domain_group.add_argument(
        "--testing",
        action="store_true",
        help="Run test suite (pytest for Python, Jest for JS/TS).",
    )
    domain_group.add_argument(
        "--coverage",
        action="store_true",
        help="Run coverage analysis (coverage.py for Python, Istanbul for JS/TS).",
    )
    domain_group.add_argument(
        "--duplication",
        action="store_true",
        help="Run code duplication detection (duplo).",
    )
    domain_group.add_argument(
        "--all",
        action="store_true",
        help="Enable all domains (sca, sast, iac, container, linting, type_checking, testing, coverage, duplication).",
    )

    # Target options
    target_group = scan_parser.add_argument_group("targets")
    target_group.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to scan (default: current directory).",
    )
    target_group.add_argument(
        "--files",
        nargs="+",
        metavar="FILE",
        help="Specific files to scan (overrides default changed-files behavior).",
    )
    target_group.add_argument(
        "--all-files",
        action="store_true",
        dest="all_files",
        help="Scan entire project instead of just changed files.",
    )
    target_group.add_argument(
        "--image",
        action="append",
        dest="images",
        metavar="IMAGE",
        help="Container image to scan (can be specified multiple times).",
    )

    # Output options
    output_group = scan_parser.add_argument_group("output")
    output_group.add_argument(
        "--format",
        choices=["json", "table", "sarif", "summary"],
        default=None,
        help="Output format (default: json, or as specified in config file).",
    )

    # Configuration options
    config_group = scan_parser.add_argument_group("configuration")
    config_group.add_argument(
        "--preset",
        metavar="NAME",
        help="Use a preset configuration (python-strict, python-minimal, typescript-strict, typescript-minimal, minimal).",
    )
    config_group.add_argument(
        "--fail-on",
        choices=["critical", "high", "medium", "low"],
        default=None,
        help="Exit with code 1 if issues at or above this severity are found.",
    )
    config_group.add_argument(
        "--coverage-threshold",
        type=float,
        default=None,
        metavar="PERCENT",
        help="Coverage percentage threshold (default: 80). Fail if below.",
    )
    config_group.add_argument(
        "--duplication-threshold",
        type=float,
        default=None,
        metavar="PERCENT",
        help="Maximum allowed duplication percentage (default: 10). Fail if above.",
    )
    config_group.add_argument(
        "--min-lines",
        type=int,
        default=None,
        metavar="N",
        help="Minimum lines for a duplicate block (default: 4).",
    )
    config_group.add_argument(
        "--config",
        metavar="PATH",
        type=Path,
        help="Path to config file (default: .lucidshark.yml in project root).",
    )

    # Execution options
    exec_group = scan_parser.add_argument_group("execution")
    exec_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be scanned without executing.",
    )
    exec_group.add_argument(
        "--sequential",
        action="store_true",
        help="Disable parallel scanner execution (for debugging).",
    )
    exec_group.add_argument(
        "--fix",
        action="store_true",
        help="Apply auto-fixes where possible (linting only).",
    )
    exec_group.add_argument(
        "--stream",
        action="store_true",
        help="Stream tool output in real-time as scans run.",
    )


def _build_status_parser(subparsers: argparse._SubParsersAction) -> None:
    """Build the 'status' subcommand parser."""
    status_parser = subparsers.add_parser(
        "status",
        help="Show configuration and tool status.",
        description=(
            "Display lucidshark version, platform info, installed tools, "
            "and scanner plugin status."
        ),
    )
    status_parser.add_argument(
        "--tools",
        action="store_true",
        help="Show detailed installed tool versions.",
    )
    status_parser.add_argument(
        "--config",
        action="store_true",
        dest="show_config",
        help="Show effective configuration.",
    )


def _build_serve_parser(subparsers: argparse._SubParsersAction) -> None:
    """Build the 'serve' subcommand parser."""
    serve_parser = subparsers.add_parser(
        "serve",
        help="Run LucidShark as a server for AI integration.",
        description=(
            "Run LucidShark as an MCP server for Claude Code, Cursor, "
            "or as a file watcher for real-time checking."
        ),
    )

    # Server mode options
    mode_group = serve_parser.add_argument_group("server mode")
    mode_group.add_argument(
        "--mcp",
        action="store_true",
        help="Run as MCP server (for Claude Code, Cursor).",
    )
    mode_group.add_argument(
        "--watch",
        action="store_true",
        help="Watch files and run incremental checks on changes.",
    )

    # Server configuration
    config_group = serve_parser.add_argument_group("configuration")
    config_group.add_argument(
        "--port",
        type=int,
        default=7432,
        help="HTTP port for status endpoint (default: 7432).",
    )
    config_group.add_argument(
        "--debounce",
        type=int,
        default=1000,
        metavar="MS",
        help="Debounce delay in milliseconds for file watcher (default: 1000).",
    )
    config_group.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory to serve (default: current directory).",
    )


def _build_help_parser(subparsers: argparse._SubParsersAction) -> None:
    """Build the 'help' subcommand parser."""
    subparsers.add_parser(
        "help",
        help="Show LLM-friendly documentation.",
        description=(
            "Display comprehensive LucidShark documentation including "
            "CLI commands, MCP tools, and configuration reference."
        ),
    )


def _build_validate_parser(subparsers: argparse._SubParsersAction) -> None:
    """Build the 'validate' subcommand parser.

    This command validates lucidshark.yml configuration files.
    """
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate lucidshark.yml configuration file.",
        description=(
            "Check a LucidShark configuration file for errors and warnings. "
            "Reports issues with suggestions for fixes."
        ),
    )
    validate_parser.add_argument(
        "--config",
        metavar="PATH",
        type=Path,
        help="Path to config file (default: find lucidshark.yml in current directory).",
    )


def _build_doctor_parser(subparsers: argparse._SubParsersAction) -> None:
    """Build the 'doctor' subcommand parser.

    This command runs health checks on the LucidShark setup.
    """
    subparsers.add_parser(
        "doctor",
        help="Check LucidShark setup and environment health.",
        description=(
            "Run diagnostic checks on your LucidShark installation. "
            "Checks configuration, tools, environment, and AI integrations."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for lucidshark CLI.

    Returns:
        Configured ArgumentParser instance with subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="lucidshark",
        description="LucidShark - The trust layer for AI-assisted development.",
        epilog=(
            "Examples:\n"
            "  lucidshark init --claude-code       # Configure Claude Code\n"
            "  lucidshark init --cursor            # Configure Cursor\n"
            "  lucidshark autoconfigure            # Auto-configure project\n"
            "  lucidshark scan --sca               # Scan dependencies\n"
            "  lucidshark scan --all               # Run all scans\n"
            "  lucidshark scan --linting --fix     # Lint and auto-fix\n"
            "  lucidshark status                   # Show tool status\n"
            "  lucidshark serve --mcp              # Run MCP server\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    _add_global_options(parser)

    # Create subcommands
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        description="Available commands:",
        metavar="COMMAND",
    )

    _build_init_parser(subparsers)
    _build_autoconfigure_parser(subparsers)
    _build_scan_parser(subparsers)
    _build_status_parser(subparsers)
    _build_serve_parser(subparsers)
    _build_help_parser(subparsers)
    _build_validate_parser(subparsers)
    _build_doctor_parser(subparsers)

    return parser
