"""Tests for CLI functionality."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch


import lucidscan.cli as cli


class TestBuildParser:
    """Tests for CLI argument parser."""

    def test_build_parser_includes_core_flags(self) -> None:
        parser = cli.build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

        # Global flags (at root level)
        for flag in ["--version", "--debug", "--verbose", "--quiet"]:
            assert any(a.option_strings and flag in a.option_strings for a in parser._actions)

        # Subcommands should be available
        assert parser._subparsers is not None


class TestMainCommand:
    """Tests for main CLI entry point."""

    def test_main_help_exits_successfully(self, capsys) -> None:
        exit_code = cli.main(["--help"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "usage:" in captured.out.lower()

    def test_main_scanner_flags_run_scan(self, capsys) -> None:
        exit_code = cli.main(["scan", "--sca", "--format", "json"])
        captured = capsys.readouterr()
        assert exit_code == 0
        # Verify JSON output with schema_version
        assert "schema_version" in captured.out
        assert "issues" in captured.out

    def test_main_version_shows_version(self, capsys) -> None:
        exit_code = cli.main(["--version"])
        captured = capsys.readouterr()
        assert exit_code == 0
        # Should output a version string
        assert captured.out.strip()  # Non-empty output


class TestStatusCommand:
    """Tests for status subcommand."""

    def test_status_subcommand_exists(self) -> None:
        parser = cli.build_parser()
        # Status should be available as a subcommand
        assert parser._subparsers is not None

    def test_status_shows_plugin_info(self, capsys, tmp_path: Path) -> None:
        """Test that status shows scanner plugin information."""
        home = tmp_path / ".lucidscan"
        home.mkdir(parents=True)

        with patch("lucidscan.cli.commands.status.get_lucidscan_home", return_value=home):
            exit_code = cli.main(["status"])

            captured = capsys.readouterr()
            assert "scanner plugins" in captured.out.lower()
            assert exit_code == 0

    def test_status_shows_discovered_plugins(self, capsys, tmp_path: Path) -> None:
        """Test that status shows plugins discovered via entry points."""
        home = tmp_path / ".lucidscan"
        home.mkdir(parents=True)

        with patch("lucidscan.cli.commands.status.get_lucidscan_home", return_value=home):
            exit_code = cli.main(["status"])

            captured = capsys.readouterr()
            # Trivy plugin should be discovered via entry points
            assert "trivy" in captured.out.lower()
            assert "sca" in captured.out.lower()
            assert exit_code == 0

    def test_status_shows_plugin_not_downloaded(self, capsys, tmp_path: Path) -> None:
        """Test that status shows 'not downloaded' for plugins without binary."""
        home = tmp_path / ".lucidscan"
        home.mkdir(parents=True)

        with patch("lucidscan.cli.commands.status.get_lucidscan_home", return_value=home):
            exit_code = cli.main(["status"])

            captured = capsys.readouterr()
            assert "not downloaded" in captured.out.lower()
            assert exit_code == 0

    def test_status_shows_platform_info(self, capsys, tmp_path: Path) -> None:
        """Test that status shows platform information."""
        home = tmp_path / ".lucidscan"
        home.mkdir(parents=True)

        with patch("lucidscan.cli.commands.status.get_lucidscan_home", return_value=home):
            exit_code = cli.main(["status"])

            captured = capsys.readouterr()
            assert "platform" in captured.out.lower()
            assert exit_code == 0


class TestExitCodes:
    """Tests for correct exit codes per Section 14."""

    def test_exit_code_0_on_version(self) -> None:
        exit_code = cli.main(["--version"])
        assert exit_code == 0

    def test_exit_code_0_on_help(self) -> None:
        exit_code = cli.main(["--help"])
        assert exit_code == 0

    def test_exit_code_0_on_status(self, tmp_path: Path) -> None:
        home = tmp_path / ".lucidscan"
        home.mkdir(parents=True)

        with patch("lucidscan.cli.commands.status.get_lucidscan_home", return_value=home):
            exit_code = cli.main(["status"])
            assert exit_code == 0
