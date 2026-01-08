"""MCP server implementation for LucidScan.

Exposes LucidScan tools to AI agents via the Model Context Protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from lucidscan.config import LucidScanConfig
from lucidscan.core.logging import get_logger
from lucidscan.mcp.tools import MCPToolExecutor

LOGGER = get_logger(__name__)


class LucidScanMCPServer:
    """MCP server exposing LucidScan tools to AI agents."""

    def __init__(self, project_root: Path, config: LucidScanConfig):
        """Initialize LucidScanMCPServer.

        Args:
            project_root: Project root directory.
            config: LucidScan configuration.
        """
        self.project_root = project_root
        self.config = config
        self.executor = MCPToolExecutor(project_root, config)
        self.server = Server("lucidscan")
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
                        "Returns structured issues with fix instructions."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Domains to check. Options: linting, type_checking, "
                                    "security, sca, iac, testing, coverage, all"
                                ),
                                "default": ["all"],
                            },
                            "files": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of specific files to check (relative paths)",
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
                        "Get current LucidScan status and configuration. "
                        "Shows available tools, enabled domains, and cached issues."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls."""
            import json

            try:
                if name == "scan":
                    result = await self.executor.scan(
                        domains=arguments.get("domains", ["all"]),
                        files=arguments.get("files"),
                        fix=arguments.get("fix", False),
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
        LOGGER.info(f"LucidScan MCP server starting for {self.project_root}")

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )
