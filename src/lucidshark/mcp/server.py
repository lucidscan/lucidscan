"""MCP server implementation for LucidShark.

Exposes LucidShark tools to AI agents via the Model Context Protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from lucidshark.config import LucidSharkConfig
from lucidshark.core.logging import get_logger
from lucidshark.mcp.tools import MCPToolExecutor

LOGGER = get_logger(__name__)


class LucidSharkMCPServer:
    """MCP server exposing LucidShark tools to AI agents."""

    def __init__(self, project_root: Path, config: LucidSharkConfig):
        """Initialize LucidSharkMCPServer.

        Args:
            project_root: Project root directory.
            config: LucidShark configuration.
        """
        self.project_root = project_root
        self.config = config
        self.executor = MCPToolExecutor(project_root, config)
        self.server = Server("lucidshark")
        self._register_tools()

    def _register_tools(self):
        """Register MCP tools."""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="scan",
                    description=(
                        "Run comprehensive code quality checks. LucidShark is a unified pipeline "
                        "for: LINTING (Ruff, ESLint, Biome, Checkstyle, Clippy - style issues, code smells); "
                        "TYPE_CHECKING (mypy, Pyright, tsc, SpotBugs, cargo check - type errors); "
                        "SAST security (OpenGrep - code vulnerabilities); "
                        "SCA security (Trivy - dependency vulnerabilities); "
                        "IAC security (Checkov - infrastructure misconfigurations); "
                        "CONTAINER security (Trivy - container image vulnerabilities); "
                        "TESTING (pytest, Jest, Karma, Playwright, JUnit, cargo test - runs tests); "
                        "COVERAGE (coverage.py, Istanbul, JaCoCo, Tarpaulin - coverage gaps); "
                        "DUPLICATION (Duplo - code clones). "
                        "By default, scans only changed files (uncommitted changes). "
                        "Use all_files=true for full project scan. "
                        "WHEN TO CALL: Run proactively after editing/writing code files, "
                        "after fixing bugs, before reporting tasks as done, and before commits. "
                        "Use fix=true to auto-fix linting issues. "
                        "DOMAIN SELECTION: Pick domains based on files changed — "
                        ".py/.js/.ts/.rs/.go/.java → [\"linting\", \"type_checking\"]; "
                        "Dockerfile → [\"container\"]; Terraform/K8s → [\"iac\"]; "
                        "dependency files → [\"sca\"]; security-sensitive code → [\"sast\"]; "
                        "to run tests → [\"testing\"]; to check coverage → [\"coverage\"]; "
                        "before commits or mixed changes → [\"all\"]. "
                        "OUTPUT FORMAT: (1) Announce what you're checking. "
                        "(2) List ALL issues grouped by domain. "
                        "(3) Show pass/fail status for EVERY domain checked. "
                        "(4) End with summary: total issues, count by severity, status per domain."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Domains to check. Options: linting, type_checking, "
                                    "sast, sca, iac, container, testing, coverage, duplication, all"
                                ),
                                "default": ["all"],
                            },
                            "files": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of specific files to check (relative paths)",
                            },
                            "all_files": {
                                "type": "boolean",
                                "description": (
                                    "Scan entire project instead of just changed files. "
                                    "By default, only uncommitted changes are scanned."
                                ),
                                "default": False,
                            },
                            "fix": {
                                "type": "boolean",
                                "description": "Whether to apply auto-fixes for fixable issues",
                                "default": False,
                            },
                            "base_branch": {
                                "type": "string",
                                "description": (
                                    "Filter coverage results to files changed since this branch "
                                    "(e.g., 'origin/main'). Full tests still run; only reporting "
                                    "is filtered. Use in CI pipelines for PR-based coverage."
                                ),
                            },
                            "coverage_threshold_scope": {
                                "type": "string",
                                "enum": ["changed", "project", "both"],
                                "description": (
                                    "When using base_branch, apply coverage threshold to: "
                                    "'changed' (changed files only, default), "
                                    "'project' (full project), or "
                                    "'both' (fail if either is below threshold)."
                                ),
                            },
                            "linting_threshold_scope": {
                                "type": "string",
                                "enum": ["changed", "project", "both"],
                                "description": (
                                    "When using base_branch, apply linting threshold to: "
                                    "'changed' (default), 'project', or 'both'."
                                ),
                            },
                            "type_checking_threshold_scope": {
                                "type": "string",
                                "enum": ["changed", "project", "both"],
                                "description": (
                                    "When using base_branch, apply type checking threshold to: "
                                    "'changed' (default), 'project', or 'both'."
                                ),
                            },
                            "duplication_threshold_scope": {
                                "type": "string",
                                "enum": ["changed", "project", "both"],
                                "description": (
                                    "When using base_branch, apply duplication threshold to: "
                                    "'changed' (default), 'project', or 'both'."
                                ),
                            },
                        },
                    },
                ),
                Tool(
                    name="check_file",
                    description=(
                        "Check a specific file and return issues with fix instructions. "
                        "Automatically detects the file type and runs relevant checks."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to check (relative to project root)",
                            },
                        },
                        "required": ["file_path"],
                    },
                ),
                Tool(
                    name="get_fix_instructions",
                    description=(
                        "Get detailed fix instructions for a specific issue. "
                        "Use after running scan to get more details about how to fix an issue."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_id": {
                                "type": "string",
                                "description": "The issue identifier from a scan result",
                            },
                        },
                        "required": ["issue_id"],
                    },
                ),
                Tool(
                    name="apply_fix",
                    description=(
                        "Apply auto-fix for a fixable issue. "
                        "Currently only supports linting issues."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_id": {
                                "type": "string",
                                "description": "The issue identifier to fix",
                            },
                        },
                        "required": ["issue_id"],
                    },
                ),
                Tool(
                    name="get_status",
                    description=(
                        "Get current LucidShark status, configuration, and capabilities. "
                        "Shows which scan domains are enabled (linting, type_checking, sast, sca, "
                        "iac, container, testing, coverage, duplication), available tools per domain, "
                        "thresholds, and any cached issues from previous scans."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                Tool(
                    name="get_help",
                    description=(
                        "Get LucidShark documentation for AI agents. "
                        "Returns comprehensive markdown reference for initialization, "
                        "configuration, CLI commands, and MCP tools."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                Tool(
                    name="autoconfigure",
                    description=(
                        "Get instructions for auto-configuring LucidShark for this project. "
                        "Call this MCP tool to get step-by-step instructions, then: "
                        "1) Analyze the codebase (package files, existing tool configs), "
                        "2) Call get_help() for configuration format reference, "
                        "3) Write the lucidshark.yml file directly, "
                        "4) Call validate_config() to verify it's correct."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                Tool(
                    name="validate_config",
                    description=(
                        "Validate a lucidshark.yml configuration file. "
                        "Returns validation results with errors and warnings. "
                        "Use after generating or modifying configuration to ensure it's valid."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "config_path": {
                                "type": "string",
                                "description": (
                                    "Path to configuration file (relative to project root). "
                                    "If not provided, finds lucidshark.yml in project root."
                                ),
                            },
                        },
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls."""
            import json

            # Get progress token from request metadata (if client requested progress)
            meta = self.server.request_context.meta
            progress_token = meta.progressToken if meta else None

            # Create progress callback that uses proper MCP progress notifications
            async def send_progress(event: Dict[str, Any]) -> None:
                """Send progress event via MCP progress notification.

                Uses the standard MCP progress notification mechanism which
                clients (Claude Code) display prominently during tool execution.
                Falls back to MCP logging if progress tokens are not supported.
                """
                tool_name = event.get("tool", "lucidshark")
                content = event.get("content", "")
                message = f"[{tool_name}] {content}"

                try:
                    session = self.server.request_context.session

                    if progress_token is not None:
                        # Use progress notifications if client requested them
                        await session.send_progress_notification(
                            progress_token=progress_token,
                            progress=event.get("progress", 0),
                            total=event.get("total"),
                            message=message,
                        )
                    else:
                        # Fall back to MCP log messages for visibility
                        await session.send_log_message(
                            level="info",
                            data=message,
                        )
                except Exception as e:
                    LOGGER.debug(f"Failed to send progress notification: {e}")

            try:
                if name == "scan":
                    result = await self.executor.scan(
                        domains=arguments.get("domains", ["all"]),
                        files=arguments.get("files"),
                        all_files=arguments.get("all_files", False),
                        fix=arguments.get("fix", False),
                        base_branch=arguments.get("base_branch"),
                        coverage_threshold_scope=arguments.get("coverage_threshold_scope"),
                        linting_threshold_scope=arguments.get("linting_threshold_scope"),
                        type_checking_threshold_scope=arguments.get("type_checking_threshold_scope"),
                        duplication_threshold_scope=arguments.get("duplication_threshold_scope"),
                        on_progress=send_progress,
                    )
                elif name == "check_file":
                    result = await self.executor.check_file(
                        file_path=arguments["file_path"],
                    )
                elif name == "get_fix_instructions":
                    result = await self.executor.get_fix_instructions(
                        issue_id=arguments["issue_id"],
                    )
                elif name == "apply_fix":
                    result = await self.executor.apply_fix(
                        issue_id=arguments["issue_id"],
                    )
                elif name == "get_status":
                    result = await self.executor.get_status()
                elif name == "get_help":
                    result = await self.executor.get_help()
                elif name == "autoconfigure":
                    result = await self.executor.autoconfigure()
                elif name == "validate_config":
                    result = await self.executor.validate_config(
                        config_path=arguments.get("config_path"),
                    )
                else:
                    result = {"error": f"Unknown tool: {name}"}

                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )]
            except Exception as e:
                LOGGER.error(f"Tool {name} failed: {e}")
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}),
                )]

    async def run(self):
        """Run the MCP server over stdio."""
        LOGGER.info(f"LucidShark MCP server starting for {self.project_root}")

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )
