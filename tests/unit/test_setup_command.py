"""Tests for setup command."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidscan.cli.commands.setup import (
    SetupCommand,
    LUCIDSCAN_MCP_ARGS,
    LUCIDSCAN_CLAUDE_MD_MARKER,
    LUCIDSCAN_CLAUDE_MD_INSTRUCTIONS,
)
from lucidscan.cli.exit_codes import EXIT_SUCCESS, EXIT_INVALID_USAGE


class TestSetupCommand:
    """Tests for SetupCommand."""

    def test_name(self) -> None:
        """Test command name property."""
        cmd = SetupCommand(version="1.0.0")
        assert cmd.name == "setup"

    def test_no_tool_specified_returns_invalid_usage(self, capsys) -> None:
        """Test that no tool specified returns EXIT_INVALID_USAGE."""
        cmd = SetupCommand(version="1.0.0")
        args = Namespace(
            claude_code=False,
            cursor=False,
            setup_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )
        exit_code = cmd.execute(args)
        assert exit_code == EXIT_INVALID_USAGE

        captured = capsys.readouterr()
        assert "No AI tool specified" in captured.out

    def test_setup_all_configures_both_tools(self, tmp_path: Path, capsys) -> None:
        """Test that --all configures both Claude Code and Cursor."""
        cmd = SetupCommand(version="1.0.0")
        args = Namespace(
            claude_code=False,
            cursor=False,
            setup_all=True,
            dry_run=True,
            force=False,
            remove=False,
        )

        claude_config = tmp_path / ".mcp.json"
        cursor_config = tmp_path / ".cursor" / "mcp.json"

        with patch.object(cmd, "_get_claude_code_config_path", return_value=claude_config):
            with patch.object(cmd, "_get_cursor_config_path", return_value=cursor_config):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Claude Code" in captured.out
        assert "Cursor" in captured.out


class TestSetupClaudeCode:
    """Tests for Claude Code setup."""

    def test_creates_new_config_file(self, tmp_path: Path, capsys) -> None:
        """Test creating a new Claude Code config file."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        args = Namespace(
            claude_code=True,
            cursor=False,
            setup_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
            with patch.object(cmd, "_find_lucidscan_path", return_value="/usr/local/bin/lucidscan"):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        assert config_path.exists()

        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "lucidscan" in config["mcpServers"]
        # Check that the full path is used in the config
        assert config["mcpServers"]["lucidscan"]["command"] == "/usr/local/bin/lucidscan"
        assert config["mcpServers"]["lucidscan"]["args"] == LUCIDSCAN_MCP_ARGS

    def test_preserves_existing_mcp_servers(self, tmp_path: Path) -> None:
        """Test that existing MCP servers are preserved."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config with another MCP server
        existing_config = {
            "mcpServers": {
                "other-tool": {
                    "command": "other-command",
                    "args": ["--some-flag"],
                }
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            cursor=False,
            setup_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
            with patch.object(cmd, "_find_lucidscan_path", return_value="/usr/local/bin/lucidscan"):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS

        config = json.loads(config_path.read_text())
        assert "other-tool" in config["mcpServers"]
        assert "lucidscan" in config["mcpServers"]

    def test_skips_if_already_configured(self, tmp_path: Path, capsys) -> None:
        """Test that setup skips if LucidScan already configured."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config with lucidscan
        existing_config = {
            "mcpServers": {
                "lucidscan": {
                    "command": "/some/path/lucidscan",
                    "args": LUCIDSCAN_MCP_ARGS,
                },
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            cursor=False,
            setup_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
            with patch.object(cmd, "_find_lucidscan_path", return_value="/usr/local/bin/lucidscan"):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "already configured" in captured.out

    def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        """Test that --force overwrites existing config."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config with different lucidscan config
        existing_config = {
            "mcpServers": {
                "lucidscan": {
                    "command": "old-command",
                    "args": ["--old-flag"],
                },
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            cursor=False,
            setup_all=False,
            dry_run=False,
            force=True,
            remove=False,
        )

        with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
            with patch.object(cmd, "_find_lucidscan_path", return_value="/usr/local/bin/lucidscan"):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS

        config = json.loads(config_path.read_text())
        assert config["mcpServers"]["lucidscan"]["command"] == "/usr/local/bin/lucidscan"
        assert config["mcpServers"]["lucidscan"]["args"] == LUCIDSCAN_MCP_ARGS

    def test_dry_run_does_not_write(self, tmp_path: Path, capsys) -> None:
        """Test that --dry-run does not write config file."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        args = Namespace(
            claude_code=True,
            cursor=False,
            setup_all=False,
            dry_run=True,
            force=False,
            remove=False,
        )

        with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
            with patch.object(cmd, "_find_lucidscan_path", return_value="/usr/local/bin/lucidscan"):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        assert not config_path.exists()

        captured = capsys.readouterr()
        assert "Would write" in captured.out

    def test_remove_deletes_lucidscan(self, tmp_path: Path, capsys) -> None:
        """Test that --remove removes LucidScan from config."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config with lucidscan and another tool
        existing_config = {
            "mcpServers": {
                "lucidscan": {
                    "command": "/some/path/lucidscan",
                    "args": LUCIDSCAN_MCP_ARGS,
                },
                "other-tool": {"command": "other"},
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            cursor=False,
            setup_all=False,
            dry_run=False,
            force=False,
            remove=True,
        )

        with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
            exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS

        config = json.loads(config_path.read_text())
        assert "lucidscan" not in config["mcpServers"]
        assert "other-tool" in config["mcpServers"]

        captured = capsys.readouterr()
        assert "Removed lucidscan" in captured.out

    def test_remove_not_found(self, tmp_path: Path, capsys) -> None:
        """Test removing when LucidScan not in config."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config without lucidscan
        existing_config = {
            "mcpServers": {
                "other-tool": {"command": "other"},
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            cursor=False,
            setup_all=False,
            dry_run=False,
            force=False,
            remove=True,
        )

        with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
            exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestSetupCursor:
    """Tests for Cursor setup."""

    def test_creates_cursor_config(self, tmp_path: Path) -> None:
        """Test creating Cursor config file."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".cursor" / "mcp.json"

        args = Namespace(
            claude_code=False,
            cursor=True,
            setup_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(cmd, "_get_cursor_config_path", return_value=config_path):
            with patch.object(cmd, "_find_lucidscan_path", return_value="/usr/local/bin/lucidscan"):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        assert config_path.exists()

        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "lucidscan" in config["mcpServers"]
        assert config["mcpServers"]["lucidscan"]["command"] == "/usr/local/bin/lucidscan"


class TestConfigureClaudeMd:
    """Tests for CLAUDE.md configuration."""

    def test_creates_new_claude_md(self, tmp_path: Path, capsys) -> None:
        """Test creating a new CLAUDE.md file."""
        cmd = SetupCommand(version="1.0.0")
        claude_md_path = tmp_path / ".claude" / "CLAUDE.md"

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=False)

        assert success
        assert claude_md_path.exists()
        content = claude_md_path.read_text()
        assert LUCIDSCAN_CLAUDE_MD_MARKER in content

    def test_appends_to_existing_claude_md(self, tmp_path: Path) -> None:
        """Test appending to existing CLAUDE.md."""
        cmd = SetupCommand(version="1.0.0")
        claude_md_path = tmp_path / ".claude" / "CLAUDE.md"
        claude_md_path.parent.mkdir(parents=True)
        claude_md_path.write_text("# Project Instructions\n\nSome existing content.")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=False)

        assert success
        content = claude_md_path.read_text()
        assert "# Project Instructions" in content
        assert "Some existing content" in content
        assert LUCIDSCAN_CLAUDE_MD_MARKER in content

    def test_skips_if_already_configured(self, tmp_path: Path, capsys) -> None:
        """Test that setup skips if lucidscan instructions already exist."""
        cmd = SetupCommand(version="1.0.0")
        claude_md_path = tmp_path / ".claude" / "CLAUDE.md"
        claude_md_path.parent.mkdir(parents=True)
        claude_md_path.write_text(f"# Project\n\n{LUCIDSCAN_CLAUDE_MD_INSTRUCTIONS}")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=False)

        assert success
        captured = capsys.readouterr()
        assert "already in" in captured.out

    def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        """Test that --force overwrites existing instructions."""
        cmd = SetupCommand(version="1.0.0")
        claude_md_path = tmp_path / ".claude" / "CLAUDE.md"
        claude_md_path.parent.mkdir(parents=True)
        claude_md_path.write_text(f"# Project\n\n{LUCIDSCAN_CLAUDE_MD_MARKER}\n\nOld instructions")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=True, remove=False)

        assert success
        content = claude_md_path.read_text()
        assert "Old instructions" not in content
        assert LUCIDSCAN_CLAUDE_MD_MARKER in content

    def test_dry_run_does_not_write(self, tmp_path: Path, capsys) -> None:
        """Test that --dry-run does not write CLAUDE.md."""
        cmd = SetupCommand(version="1.0.0")
        claude_md_path = tmp_path / ".claude" / "CLAUDE.md"

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=True, force=False, remove=False)

        assert success
        assert not claude_md_path.exists()
        captured = capsys.readouterr()
        assert "Would add" in captured.out

    def test_remove_deletes_instructions(self, tmp_path: Path, capsys) -> None:
        """Test that --remove removes lucidscan instructions."""
        cmd = SetupCommand(version="1.0.0")
        claude_md_path = tmp_path / ".claude" / "CLAUDE.md"
        claude_md_path.parent.mkdir(parents=True)
        claude_md_path.write_text(f"# Project\n\n{LUCIDSCAN_CLAUDE_MD_INSTRUCTIONS}\n\n## Other Section\n\nKeep this.")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=True)

        assert success
        content = claude_md_path.read_text()
        assert LUCIDSCAN_CLAUDE_MD_MARKER not in content
        assert "## Other Section" in content
        assert "Keep this" in content

    def test_remove_not_found(self, tmp_path: Path, capsys) -> None:
        """Test removing when instructions not in CLAUDE.md."""
        cmd = SetupCommand(version="1.0.0")
        claude_md_path = tmp_path / ".claude" / "CLAUDE.md"
        claude_md_path.parent.mkdir(parents=True)
        claude_md_path.write_text("# Project\n\nNo lucidscan here.")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=True)

        assert success
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestFindLucidscanPath:
    """Tests for _find_lucidscan_path method."""

    def test_finds_in_path(self) -> None:
        """Test finding lucidscan via shutil.which (in PATH)."""
        cmd = SetupCommand(version="1.0.0")
        with patch("shutil.which", return_value="/usr/local/bin/lucidscan"):
            path = cmd._find_lucidscan_path()
        assert path == "/usr/local/bin/lucidscan"

    def test_finds_in_venv(self, tmp_path: Path) -> None:
        """Test finding lucidscan in venv bin directory."""
        cmd = SetupCommand(version="1.0.0")
        # Create a fake lucidscan in the venv
        venv_bin = tmp_path / "venv" / "bin"
        venv_bin.mkdir(parents=True)
        lucidscan_exe = venv_bin / "lucidscan"
        lucidscan_exe.touch()

        with patch("shutil.which", return_value=None):
            with patch("sys.executable", str(venv_bin / "python")):
                path = cmd._find_lucidscan_path()
        assert path == str(lucidscan_exe)

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Test returning None when lucidscan not found."""
        cmd = SetupCommand(version="1.0.0")
        with patch("shutil.which", return_value=None):
            with patch("sys.executable", str(tmp_path / "nonexistent" / "python")):
                path = cmd._find_lucidscan_path()
        assert path is None

    def test_fallback_uses_bare_command(self, tmp_path: Path, capsys) -> None:
        """Test that fallback uses 'lucidscan' when path not found."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / ".cursor" / "mcp.json"

        args = Namespace(
            claude_code=False,
            cursor=True,
            setup_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(cmd, "_get_cursor_config_path", return_value=config_path):
            with patch.object(cmd, "_find_lucidscan_path", return_value=None):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS

        config = json.loads(config_path.read_text())
        # When not found, should fall back to bare "lucidscan" command
        assert config["mcpServers"]["lucidscan"]["command"] == "lucidscan"

        captured = capsys.readouterr()
        assert "Warning" in captured.out


class TestConfigPaths:
    """Tests for config path determination."""

    def test_claude_code_config_path(self) -> None:
        """Test Claude Code config path returns .mcp.json."""
        cmd = SetupCommand(version="1.0.0")
        path = cmd._get_claude_code_config_path()
        assert path is not None
        assert ".mcp.json" in str(path)

    def test_cursor_config_path_unix(self) -> None:
        """Test Cursor config path on Unix systems."""
        cmd = SetupCommand(version="1.0.0")
        with patch("sys.platform", "darwin"):
            path = cmd._get_cursor_config_path()
            assert path is not None
            assert ".cursor" in str(path)
            assert "mcp.json" in str(path)


class TestJsonConfigOperations:
    """Tests for JSON config read/write operations."""

    def test_read_nonexistent_file(self, tmp_path: Path) -> None:
        """Test reading nonexistent config file."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / "nonexistent.json"

        config, error = cmd._read_json_config(config_path)
        assert config == {}
        assert error is not None
        assert "does not exist" in error

    def test_read_empty_file(self, tmp_path: Path) -> None:
        """Test reading empty config file."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / "empty.json"
        config_path.write_text("")

        config, error = cmd._read_json_config(config_path)
        assert config == {}
        assert error is None

    def test_read_invalid_json(self, tmp_path: Path) -> None:
        """Test reading invalid JSON file."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / "invalid.json"
        config_path.write_text("{ not valid json }")

        config, error = cmd._read_json_config(config_path)
        assert config == {}
        assert error is not None
        assert "Invalid JSON" in error

    def test_write_config(self, tmp_path: Path) -> None:
        """Test writing config file."""
        cmd = SetupCommand(version="1.0.0")
        config_path = tmp_path / "test.json"

        config = {"key": "value"}
        success = cmd._write_json_config(config_path, config)

        assert success
        assert config_path.exists()

        written = json.loads(config_path.read_text())
        assert written == config
