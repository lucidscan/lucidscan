"""Extended unit tests for MCP server - covering call_tool dispatch and list_tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    TextContent,
)
from mcp.server.lowlevel.server import request_ctx

from lucidshark.config import LucidSharkConfig
from lucidshark.mcp.server import LucidSharkMCPServer


def _make_server(tmp_path: Path) -> LucidSharkMCPServer:
    """Create a server instance."""
    config = LucidSharkConfig()
    return LucidSharkMCPServer(tmp_path, config)


def _set_request_context(progress_token=None):
    """Set a mocked request context in the ContextVar."""
    mock_meta = MagicMock()
    mock_meta.progressToken = progress_token
    mock_session = AsyncMock()
    mock_rc = MagicMock()
    mock_rc.meta = mock_meta
    mock_rc.session = mock_session
    token = request_ctx.set(mock_rc)
    return mock_rc, token


class TestMCPServerListToolsHandler:
    """Tests for the list_tools handler."""

    async def test_list_tools_returns_all_expected_tools(
        self, tmp_path: Path
    ) -> None:
        """Test that list_tools returns all expected tool definitions."""
        server = _make_server(tmp_path)
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[ListToolsRequest]
            req = ListToolsRequest(method="tools/list")
            result = await handler(req)
            assert isinstance(result.root, ListToolsResult)
            tool_names = [t.name for t in result.root.tools]
            assert "scan" in tool_names
            assert "check_file" in tool_names
            assert "get_fix_instructions" in tool_names
            assert "apply_fix" in tool_names
            assert "get_status" in tool_names
            assert "get_help" in tool_names
            assert "autoconfigure" in tool_names
            assert "validate_config" in tool_names
            assert len(tool_names) == 8
        finally:
            request_ctx.reset(ctx_token)

    async def test_scan_tool_has_correct_schema(self, tmp_path: Path) -> None:
        """Test the scan tool has correct input schema properties."""
        server = _make_server(tmp_path)
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[ListToolsRequest]
            req = ListToolsRequest(method="tools/list")
            result = await handler(req)
            assert isinstance(result.root, ListToolsResult)
            scan_tool = next(t for t in result.root.tools if t.name == "scan")
            props = scan_tool.inputSchema["properties"]
            assert "domains" in props
            assert "files" in props
            assert "all_files" in props
            assert "fix" in props
        finally:
            request_ctx.reset(ctx_token)

    async def test_check_file_tool_requires_file_path(
        self, tmp_path: Path
    ) -> None:
        """Test the check_file tool requires file_path."""
        server = _make_server(tmp_path)
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[ListToolsRequest]
            req = ListToolsRequest(method="tools/list")
            result = await handler(req)
            assert isinstance(result.root, ListToolsResult)
            check_file_tool = next(t for t in result.root.tools if t.name == "check_file")
            assert "file_path" in check_file_tool.inputSchema.get("required", [])
        finally:
            request_ctx.reset(ctx_token)


class TestMCPServerCallToolHandler:
    """Tests for the call_tool dispatch handler."""

    async def test_dispatch_scan(self, tmp_path: Path) -> None:
        """Test dispatching to scan."""
        server = _make_server(tmp_path)
        server.executor.scan = AsyncMock(return_value={"total_issues": 0, "instructions": []})  # type: ignore[method-assign]
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="scan", arguments={"domains": ["linting"]}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert len(result.root.content) == 1
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert parsed["total_issues"] == 0
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_check_file(self, tmp_path: Path) -> None:
        """Test dispatching to check_file."""
        server = _make_server(tmp_path)
        server.executor.check_file = AsyncMock(return_value={"total_issues": 0})  # type: ignore[method-assign]
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="check_file", arguments={"file_path": "test.py"}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert "total_issues" in parsed
            server.executor.check_file.assert_called_once_with(file_path="test.py")
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_get_fix_instructions(self, tmp_path: Path) -> None:
        """Test dispatching to get_fix_instructions."""
        server = _make_server(tmp_path)
        server.executor.get_fix_instructions = AsyncMock(  # type: ignore[method-assign]
            return_value={"priority": 1, "fix_steps": ["Step 1"]}
        )
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="get_fix_instructions", arguments={"issue_id": "issue-1"}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert parsed["priority"] == 1
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_apply_fix(self, tmp_path: Path) -> None:
        """Test dispatching to apply_fix."""
        server = _make_server(tmp_path)
        server.executor.apply_fix = AsyncMock(  # type: ignore[method-assign]
            return_value={"success": True, "message": "Fixed"}
        )
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="apply_fix", arguments={"issue_id": "issue-1"}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert parsed["success"] is True
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_get_status(self, tmp_path: Path) -> None:
        """Test dispatching to get_status."""
        server = _make_server(tmp_path)
        server.executor.get_status = AsyncMock(  # type: ignore[method-assign]
            return_value={"project_root": str(tmp_path), "available_tools": []}
        )
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="get_status", arguments={}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert "project_root" in parsed
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_get_help(self, tmp_path: Path) -> None:
        """Test dispatching to get_help."""
        server = _make_server(tmp_path)
        server.executor.get_help = AsyncMock(  # type: ignore[method-assign]
            return_value={"documentation": "# Help", "format": "markdown"}
        )
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="get_help", arguments={}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert parsed["format"] == "markdown"
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_autoconfigure(self, tmp_path: Path) -> None:
        """Test dispatching to autoconfigure."""
        server = _make_server(tmp_path)
        server.executor.autoconfigure = AsyncMock(  # type: ignore[method-assign]
            return_value={"instructions": "Do this"}
        )
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="autoconfigure", arguments={}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert "instructions" in parsed
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_validate_config(self, tmp_path: Path) -> None:
        """Test dispatching to validate_config."""
        server = _make_server(tmp_path)
        server.executor.validate_config = AsyncMock(  # type: ignore[method-assign]
            return_value={"valid": True, "errors": [], "warnings": []}
        )
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="validate_config", arguments={"config_path": "lucidshark.yml"}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert parsed["valid"] is True
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_unknown_tool_returns_error(
        self, tmp_path: Path
    ) -> None:
        """Test unknown tool name returns error in response."""
        server = _make_server(tmp_path)
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="nonexistent_tool", arguments={}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert "error" in parsed
            assert "Unknown tool" in parsed["error"]
        finally:
            request_ctx.reset(ctx_token)

    async def test_dispatch_exception_returns_error(
        self, tmp_path: Path
    ) -> None:
        """Test exception in tool execution returns error."""
        server = _make_server(tmp_path)
        server.executor.scan = AsyncMock(side_effect=RuntimeError("Boom"))  # type: ignore[method-assign]
        mock_rc, ctx_token = _set_request_context()
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="scan", arguments={"domains": ["linting"]}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert "error" in parsed
            assert "Boom" in parsed["error"]
        finally:
            request_ctx.reset(ctx_token)

    async def test_progress_notification_with_token(
        self, tmp_path: Path
    ) -> None:
        """Test progress notifications are sent when token is present."""
        server = _make_server(tmp_path)

        async def mock_scan(**kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                await on_progress({
                    "tool": "lucidshark",
                    "content": "Scanning...",
                    "progress": 0,
                    "total": 1,
                })
            return {"total_issues": 0, "instructions": []}

        server.executor.scan = AsyncMock(side_effect=mock_scan)  # type: ignore[method-assign]

        mock_rc, ctx_token = _set_request_context(progress_token="prog-token-1")
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="scan", arguments={"domains": ["linting"]}),
            )
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert parsed["total_issues"] == 0
            mock_rc.session.send_progress_notification.assert_called()
        finally:
            request_ctx.reset(ctx_token)

    async def test_progress_fallback_to_log_without_token(
        self, tmp_path: Path
    ) -> None:
        """Test progress falls back to log messages when no token."""
        server = _make_server(tmp_path)

        async def mock_scan(**kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                await on_progress({
                    "tool": "lucidshark",
                    "content": "Scanning...",
                    "progress": 0,
                    "total": 1,
                })
            return {"total_issues": 0, "instructions": []}

        server.executor.scan = AsyncMock(side_effect=mock_scan)  # type: ignore[method-assign]

        mock_rc, ctx_token = _set_request_context(progress_token=None)
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="scan", arguments={"domains": ["linting"]}),
            )
            await handler(req)
            mock_rc.session.send_log_message.assert_called()
        finally:
            request_ctx.reset(ctx_token)

    async def test_progress_error_handled_gracefully(
        self, tmp_path: Path
    ) -> None:
        """Test that errors in progress notification don't crash."""
        server = _make_server(tmp_path)

        async def mock_scan(**kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                await on_progress({
                    "tool": "lucidshark",
                    "content": "Scanning...",
                    "progress": 0,
                    "total": 1,
                })
            return {"total_issues": 0, "instructions": []}

        server.executor.scan = AsyncMock(side_effect=mock_scan)  # type: ignore[method-assign]

        mock_rc, ctx_token = _set_request_context(progress_token="token-1")
        mock_rc.session.send_progress_notification = AsyncMock(
            side_effect=RuntimeError("Progress failed")
        )
        try:
            handler = server.server.request_handlers[CallToolRequest]
            req = CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="scan", arguments={"domains": ["linting"]}),
            )
            # Should not raise despite progress notification failure
            result = await handler(req)
            assert isinstance(result.root, CallToolResult)
            assert isinstance(result.root.content[0], TextContent)
            parsed = json.loads(result.root.content[0].text)
            assert parsed["total_issues"] == 0
        finally:
            request_ctx.reset(ctx_token)
