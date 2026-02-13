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
                        "Run quality checks on the codebase or specific files. "
                        "By default, scans only changed files (uncommitted changes). "
                        "Use all_files=true for full project scan. "
                        "Returns structured issues with fix instructions. "
                        "IMPORTANT OUTPUT FORMAT: After receiving results, you MUST present them as: "
                        "(1) Announce what you're checking before the scan runs. "
                        "(2) List ALL issues grouped by domain (linting, type_checking, security, etc). "
                        "(3) Show pass/fail status for EVERY domain that was checked. "
                        "(4) End with a summary table showing: total issues, count by severity, "
                        "status per domain, and a recommended next action. "
                        "Even when no issues are found, confirm which domains passed."
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
                        "Get current LucidShark status and configuration. "
                        "Shows available tools, enabled domains, and cached issues."
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
                        "IMPORTANT: Do NOT run the CLI 'lucidshark autoconfigure' command. "
                        "Instead, call this MCP tool first to get instructions, then: "
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
                clients (Claude/Cursor) display prominently during tool execution.
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
