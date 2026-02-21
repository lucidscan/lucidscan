"""Tests for init command (AI tool configuration)."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


from lucidshark.cli.commands.init import (
    InitCommand,
    LUCIDSHARK_MCP_ARGS,
    LUCIDSHARK_SKILL_CONTENT,
    LUCIDSHARK_CLAUDE_MD_SECTION,
)
from lucidshark.cli.exit_codes import EXIT_SUCCESS, EXIT_INVALID_USAGE


class TestInitCommand:
    """Tests for InitCommand."""

    def test_name(self) -> None:
        """Test command name property."""
        cmd = InitCommand(version="1.0.0")
        assert cmd.name == "init"

    def test_no_tool_specified_returns_invalid_usage(self, capsys) -> None:
        """Test that no tool specified returns EXIT_INVALID_USAGE."""
        cmd = InitCommand(version="1.0.0")
        args = Namespace(
            claude_code=False,
            init_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )
        exit_code = cmd.execute(args)
        assert exit_code == EXIT_INVALID_USAGE

        captured = capsys.readouterr()
        assert "No AI tool specified" in captured.out

    def test_init_all_configures_claude_code(self, tmp_path: Path, capsys) -> None:
        """Test that --all configures Claude Code."""
        cmd = InitCommand(version="1.0.0")
        args = Namespace(
            claude_code=False,
            init_all=True,
            dry_run=True,
            force=False,
            remove=False,
        )

        claude_config = tmp_path / ".mcp.json"

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=claude_config):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Claude Code" in captured.out


class TestSetupClaudeCode:
    """Tests for Claude Code setup."""

    def test_creates_new_config_file(self, tmp_path: Path, capsys) -> None:
        """Test creating a new Claude Code config file."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        args = Namespace(
            claude_code=True,
            init_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
                with patch.object(cmd, "_find_lucidshark_path", return_value="/usr/local/bin/lucidshark"):
                    exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        assert config_path.exists()

        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "lucidshark" in config["mcpServers"]
        # Check that the full path is used in the config
        assert config["mcpServers"]["lucidshark"]["command"] == "/usr/local/bin/lucidshark"
        assert config["mcpServers"]["lucidshark"]["args"] == LUCIDSHARK_MCP_ARGS

    def test_preserves_existing_mcp_servers(self, tmp_path: Path) -> None:
        """Test that existing MCP servers are preserved."""
        cmd = InitCommand(version="1.0.0")
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
            init_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
                with patch.object(cmd, "_find_lucidshark_path", return_value="/usr/local/bin/lucidshark"):
                    exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS

        config = json.loads(config_path.read_text())
        assert "other-tool" in config["mcpServers"]
        assert "lucidshark" in config["mcpServers"]

    def test_skips_if_already_configured(self, tmp_path: Path, capsys) -> None:
        """Test that setup skips if LucidShark already configured."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config with lucidshark
        existing_config = {
            "mcpServers": {
                "lucidshark": {
                    "command": "/some/path/lucidshark",
                    "args": LUCIDSHARK_MCP_ARGS,
                },
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            init_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
                with patch.object(cmd, "_find_lucidshark_path", return_value="/usr/local/bin/lucidshark"):
                    exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "already configured" in captured.out

    def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        """Test that --force overwrites existing config."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config with different lucidshark config
        existing_config = {
            "mcpServers": {
                "lucidshark": {
                    "command": "old-command",
                    "args": ["--old-flag"],
                },
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            init_all=False,
            dry_run=False,
            force=True,
            remove=False,
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
                with patch.object(cmd, "_find_lucidshark_path", return_value="/usr/local/bin/lucidshark"):
                    exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS

        config = json.loads(config_path.read_text())
        assert config["mcpServers"]["lucidshark"]["command"] == "/usr/local/bin/lucidshark"
        assert config["mcpServers"]["lucidshark"]["args"] == LUCIDSHARK_MCP_ARGS

    def test_dry_run_does_not_write(self, tmp_path: Path, capsys) -> None:
        """Test that --dry-run does not write config file."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        args = Namespace(
            claude_code=True,
            init_all=False,
            dry_run=True,
            force=False,
            remove=False,
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
                with patch.object(cmd, "_find_lucidshark_path", return_value="/usr/local/bin/lucidshark"):
                    exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        assert not config_path.exists()

        captured = capsys.readouterr()
        assert "Would write" in captured.out

    def test_remove_deletes_lucidshark(self, tmp_path: Path, capsys) -> None:
        """Test that --remove removes LucidShark from config."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config with lucidshark and another tool
        existing_config = {
            "mcpServers": {
                "lucidshark": {
                    "command": "/some/path/lucidshark",
                    "args": LUCIDSHARK_MCP_ARGS,
                },
                "other-tool": {"command": "other"},
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            init_all=False,
            dry_run=False,
            force=False,
            remove=True,
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS

        config = json.loads(config_path.read_text())
        assert "lucidshark" not in config["mcpServers"]
        assert "other-tool" in config["mcpServers"]

        captured = capsys.readouterr()
        assert "Removed lucidshark" in captured.out

    def test_remove_not_found(self, tmp_path: Path, capsys) -> None:
        """Test removing when LucidShark not in config."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        # Create existing config without lucidshark
        existing_config = {
            "mcpServers": {
                "other-tool": {"command": "other"},
            }
        }
        config_path.write_text(json.dumps(existing_config))

        args = Namespace(
            claude_code=True,
            init_all=False,
            dry_run=False,
            force=False,
            remove=True,
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
                exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestConfigureClaudeSkill:
    """Tests for Claude skill configuration."""

    def test_creates_new_skill_file(self, tmp_path: Path, capsys) -> None:
        """Test creating a new Claude skill file."""
        cmd = InitCommand(version="1.0.0")
        skill_path = tmp_path / ".claude" / "skills" / "lucidshark" / "SKILL.md"

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_skill(dry_run=False, force=False, remove=False)

        assert success
        assert skill_path.exists()
        content = skill_path.read_text(encoding="utf-8")
        assert "LucidShark" in content

    def test_skips_if_already_configured(self, tmp_path: Path, capsys) -> None:
        """Test that setup skips if lucidshark skill already exists."""
        cmd = InitCommand(version="1.0.0")
        skill_path = tmp_path / ".claude" / "skills" / "lucidshark" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text(LUCIDSHARK_SKILL_CONTENT, encoding="utf-8")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_skill(dry_run=False, force=False, remove=False)

        assert success
        captured = capsys.readouterr()
        assert "already exists" in captured.out

    def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        """Test that --force overwrites existing skill."""
        cmd = InitCommand(version="1.0.0")
        skill_path = tmp_path / ".claude" / "skills" / "lucidshark" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("Old skill content")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_skill(dry_run=False, force=True, remove=False)

        assert success
        content = skill_path.read_text(encoding="utf-8")
        assert "Old skill content" not in content
        assert "LucidShark" in content

    def test_dry_run_does_not_write(self, tmp_path: Path, capsys) -> None:
        """Test that --dry-run does not write skill file."""
        cmd = InitCommand(version="1.0.0")
        skill_path = tmp_path / ".claude" / "skills" / "lucidshark" / "SKILL.md"

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_skill(dry_run=True, force=False, remove=False)

        assert success
        assert not skill_path.exists()
        captured = capsys.readouterr()
        assert "Would create" in captured.out

    def test_remove_deletes_skill(self, tmp_path: Path, capsys) -> None:
        """Test that --remove removes lucidshark skill."""
        cmd = InitCommand(version="1.0.0")
        skill_path = tmp_path / ".claude" / "skills" / "lucidshark" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text(LUCIDSHARK_SKILL_CONTENT, encoding="utf-8")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_skill(dry_run=False, force=False, remove=True)

        assert success
        assert not skill_path.exists()
        captured = capsys.readouterr()
        assert "Removed" in captured.out

    def test_remove_not_found(self, tmp_path: Path, capsys) -> None:
        """Test removing when skill does not exist."""
        cmd = InitCommand(version="1.0.0")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_skill(dry_run=False, force=False, remove=True)

        assert success
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestFindLucidsharkPath:
    """Tests for _find_lucidshark_path method."""

    def test_finds_in_path(self) -> None:
        """Test finding lucidshark via shutil.which (in PATH)."""
        cmd = InitCommand(version="1.0.0")
        with patch("shutil.which", return_value="/usr/local/bin/lucidshark"):
            path = cmd._find_lucidshark_path()
        assert path == "/usr/local/bin/lucidshark"

    def test_finds_in_venv(self, tmp_path: Path) -> None:
        """Test finding lucidshark in venv bin directory."""
        cmd = InitCommand(version="1.0.0")
        # Create a fake lucidshark in the venv with platform-appropriate paths
        if sys.platform == "win32":
            # Windows uses Scripts directory and .exe extension
            venv_bin = tmp_path / "venv" / "Scripts"
            venv_bin.mkdir(parents=True)
            lucidshark_exe = venv_bin / "lucidshark.exe"
        else:
            # Unix uses bin directory
            venv_bin = tmp_path / "venv" / "bin"
            venv_bin.mkdir(parents=True)
            lucidshark_exe = venv_bin / "lucidshark"
        lucidshark_exe.touch()

        with patch("shutil.which", return_value=None):
            with patch("sys.executable", str(venv_bin / "python")):
                path = cmd._find_lucidshark_path()
        assert path == str(lucidshark_exe)

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Test returning None when lucidshark not found."""
        cmd = InitCommand(version="1.0.0")
        with patch("shutil.which", return_value=None):
            with patch("sys.executable", str(tmp_path / "nonexistent" / "python")):
                path = cmd._find_lucidshark_path()
        assert path is None

    def test_fallback_uses_bare_command(self, tmp_path: Path, capsys) -> None:
        """Test that fallback uses 'lucidshark' when path not found."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / ".mcp.json"

        args = Namespace(
            claude_code=True,
            init_all=False,
            dry_run=False,
            force=False,
            remove=False,
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch.object(cmd, "_get_claude_code_config_path", return_value=config_path):
                with patch.object(cmd, "_find_lucidshark_path", return_value=None):
                    exit_code = cmd.execute(args)

        assert exit_code == EXIT_SUCCESS

        config = json.loads(config_path.read_text())
        # When not found, should fall back to bare "lucidshark" command
        assert config["mcpServers"]["lucidshark"]["command"] == "lucidshark"

        captured = capsys.readouterr()
        assert "Warning" in captured.out


class TestConfigPaths:
    """Tests for config path determination."""

    def test_claude_code_config_path(self) -> None:
        """Test Claude Code config path returns .mcp.json."""
        cmd = InitCommand(version="1.0.0")
        path = cmd._get_claude_code_config_path()
        assert path is not None
        assert ".mcp.json" in str(path)


class TestConfigureClaudeMd:
    """Tests for CLAUDE.md configuration."""

    def test_creates_new_claude_md(self, tmp_path: Path, capsys) -> None:
        """Test creating a new CLAUDE.md with LucidShark section."""
        cmd = InitCommand(version="1.0.0")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=False)

        assert success
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- lucidshark:start" in content
        assert "<!-- lucidshark:end -->" in content
        assert "mcp__lucidshark__scan" in content
        assert "Smart Domain Selection" in content

    def test_appends_to_existing_claude_md(self, tmp_path: Path) -> None:
        """Test appending to an existing CLAUDE.md without LucidShark section."""
        cmd = InitCommand(version="1.0.0")
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# My Project\n\nExisting instructions here.\n")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=False)

        assert success
        content = claude_md.read_text(encoding="utf-8")
        assert content.startswith("# My Project")
        assert "Existing instructions here." in content
        assert "<!-- lucidshark:start" in content

    def test_skips_if_section_already_exists(self, tmp_path: Path, capsys) -> None:
        """Test that setup skips if LucidShark section already exists."""
        cmd = InitCommand(version="1.0.0")
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "# Project\n" + LUCIDSHARK_CLAUDE_MD_SECTION, encoding="utf-8"
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=False)

        assert success
        captured = capsys.readouterr()
        assert "already exists" in captured.out

    def test_force_updates_existing_section(self, tmp_path: Path) -> None:
        """Test that --force replaces the existing LucidShark section."""
        cmd = InitCommand(version="1.0.0")
        claude_md = tmp_path / "CLAUDE.md"
        old_content = (
            "# Project\n\n"
            "<!-- lucidshark:start - managed by lucidshark init, do not edit manually -->\n"
            "Old lucidshark content\n"
            "<!-- lucidshark:end -->\n\n"
            "## Other stuff\n"
        )
        claude_md.write_text(old_content, encoding="utf-8")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=True, remove=False)

        assert success
        content = claude_md.read_text(encoding="utf-8")
        assert "Old lucidshark content" not in content
        assert "Smart Domain Selection" in content
        assert "## Other stuff" in content

    def test_dry_run_does_not_write(self, tmp_path: Path, capsys) -> None:
        """Test that --dry-run does not create CLAUDE.md."""
        cmd = InitCommand(version="1.0.0")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=True, force=False, remove=False)

        assert success
        assert not (tmp_path / "CLAUDE.md").exists()
        captured = capsys.readouterr()
        assert "Would create" in captured.out

    def test_remove_deletes_section(self, tmp_path: Path, capsys) -> None:
        """Test that --remove removes the LucidShark section from CLAUDE.md."""
        cmd = InitCommand(version="1.0.0")
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "# Project\n" + LUCIDSHARK_CLAUDE_MD_SECTION + "\n## Other\n",
            encoding="utf-8",
        )

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=True)

        assert success
        content = claude_md.read_text(encoding="utf-8")
        assert "lucidshark:start" not in content
        assert "lucidshark:end" not in content
        assert "# Project" in content
        assert "## Other" in content

    def test_remove_deletes_file_if_empty(self, tmp_path: Path, capsys) -> None:
        """Test that --remove deletes CLAUDE.md if only LucidShark content remains."""
        cmd = InitCommand(version="1.0.0")
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(LUCIDSHARK_CLAUDE_MD_SECTION, encoding="utf-8")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=True)

        assert success
        assert not claude_md.exists()
        captured = capsys.readouterr()
        assert "was empty" in captured.out

    def test_remove_not_found(self, tmp_path: Path, capsys) -> None:
        """Test removing when LucidShark section does not exist."""
        cmd = InitCommand(version="1.0.0")

        with patch.object(Path, "cwd", return_value=tmp_path):
            success = cmd._configure_claude_md(dry_run=False, force=False, remove=True)

        assert success
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestManagedSectionHelpers:
    """Tests for _remove_managed_section and _replace_managed_section."""

    def test_remove_managed_section(self) -> None:
        """Test removing a managed section from content."""
        content = (
            "before\n"
            "<!-- lucidshark:start - managed -->\n"
            "managed content\n"
            "<!-- lucidshark:end -->\n"
            "after"
        )
        result = InitCommand._remove_managed_section(
            content, "<!-- lucidshark:start", "<!-- lucidshark:end -->"
        )
        assert "managed content" not in result
        assert "before" in result
        assert "after" in result

    def test_replace_managed_section(self) -> None:
        """Test replacing a managed section in content."""
        content = (
            "before\n"
            "<!-- lucidshark:start - managed -->\n"
            "old content\n"
            "<!-- lucidshark:end -->\n"
            "after"
        )
        new_section = (
            "<!-- lucidshark:start - managed -->\n"
            "new content\n"
            "<!-- lucidshark:end -->"
        )
        result = InitCommand._replace_managed_section(
            content, "<!-- lucidshark:start", "<!-- lucidshark:end -->", new_section
        )
        assert "old content" not in result
        assert "new content" in result
        assert "before" in result
        assert "after" in result


class TestJsonConfigOperations:
    """Tests for JSON config read/write operations."""

    def test_read_nonexistent_file(self, tmp_path: Path) -> None:
        """Test reading nonexistent config file."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / "nonexistent.json"

        config, error = cmd._read_json_config(config_path)
        assert config == {}
        assert error is not None
        assert "does not exist" in error

    def test_read_empty_file(self, tmp_path: Path) -> None:
        """Test reading empty config file."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / "empty.json"
        config_path.write_text("")

        config, error = cmd._read_json_config(config_path)
        assert config == {}
        assert error is None

    def test_read_invalid_json(self, tmp_path: Path) -> None:
        """Test reading invalid JSON file."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / "invalid.json"
        config_path.write_text("{ not valid json }")

        config, error = cmd._read_json_config(config_path)
        assert config == {}
        assert error is not None
        assert "Invalid JSON" in error

    def test_write_config(self, tmp_path: Path) -> None:
        """Test writing config file."""
        cmd = InitCommand(version="1.0.0")
        config_path = tmp_path / "test.json"

        config = {"key": "value"}
        success = cmd._write_json_config(config_path, config)

        assert success
        assert config_path.exists()

        written = json.loads(config_path.read_text())
        assert written == config
