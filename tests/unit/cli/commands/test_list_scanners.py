"""Tests for list_scanners command."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch, MagicMock


from lucidscan.cli.commands.list_scanners import ListScannersCommand
from lucidscan.cli.exit_codes import EXIT_SUCCESS


class TestListScannersCommand:
    """Tests for ListScannersCommand."""

    def test_command_name(self) -> None:
        """Test command name property."""
        cmd = ListScannersCommand()
        assert cmd.name == "list_scanners"

    def test_execute_with_plugins(self, capsys) -> None:
        """Test execute with available plugins."""
        # Create mock plugin class
        mock_plugin = MagicMock()
        mock_plugin.domains = []
        mock_plugin.get_version.return_value = "1.0.0"

        mock_plugin_class = MagicMock(return_value=mock_plugin)

        plugins = {"test-scanner": mock_plugin_class}

        with patch(
            "lucidscan.cli.commands.list_scanners.discover_scanner_plugins",
            return_value=plugins,
        ):
            cmd = ListScannersCommand()
            result = cmd.execute(Namespace())

            assert result == EXIT_SUCCESS
            captured = capsys.readouterr()
            assert "test-scanner" in captured.out
            assert "Version: 1.0.0" in captured.out

    def test_execute_with_no_plugins(self, capsys) -> None:
        """Test execute with no available plugins."""
        with patch(
            "lucidscan.cli.commands.list_scanners.discover_scanner_plugins",
            return_value={},
        ):
            cmd = ListScannersCommand()
            result = cmd.execute(Namespace())

            assert result == EXIT_SUCCESS
            captured = capsys.readouterr()
            assert "No plugins discovered" in captured.out

    def test_execute_with_plugin_error(self, capsys) -> None:
        """Test execute when a plugin raises an error during instantiation."""
        def raise_error():
            raise RuntimeError("Plugin initialization failed")

        mock_plugin_class = MagicMock(side_effect=raise_error)
        plugins = {"broken-scanner": mock_plugin_class}

        with patch(
            "lucidscan.cli.commands.list_scanners.discover_scanner_plugins",
            return_value=plugins,
        ):
            cmd = ListScannersCommand()
            result = cmd.execute(Namespace())

            assert result == EXIT_SUCCESS
            captured = capsys.readouterr()
            assert "broken-scanner" in captured.out
            assert "error loading plugin" in captured.out

    def test_execute_shows_domains(self, capsys) -> None:
        """Test execute shows plugin domains."""
        from lucidscan.core.models import ScanDomain

        mock_plugin = MagicMock()
        mock_plugin.domains = [ScanDomain.SAST, ScanDomain.SCA]
        mock_plugin.get_version.return_value = "2.0.0"

        mock_plugin_class = MagicMock(return_value=mock_plugin)

        plugins = {"multi-domain-scanner": mock_plugin_class}

        with patch(
            "lucidscan.cli.commands.list_scanners.discover_scanner_plugins",
            return_value=plugins,
        ):
            cmd = ListScannersCommand()
            result = cmd.execute(Namespace())

            assert result == EXIT_SUCCESS
            captured = capsys.readouterr()
            assert "SAST" in captured.out
            assert "SCA" in captured.out
