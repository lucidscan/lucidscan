"""MCP (Model Context Protocol) integration for LucidScan.

This package provides MCP server functionality for AI agent integration,
enabling tools like Claude Code and Cursor to invoke LucidScan checks.
"""

from __future__ import annotations

from lucidscan.mcp.server import LucidScanMCPServer
from lucidscan.mcp.formatter import InstructionFormatter, FixInstruction
from lucidscan.mcp.tools import MCPToolExecutor
from lucidscan.mcp.watcher import LucidScanFileWatcher

__all__ = [
    "LucidScanMCPServer",
    "InstructionFormatter",
    "FixInstruction",
    "MCPToolExecutor",
    "LucidScanFileWatcher",
]
