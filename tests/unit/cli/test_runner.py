"""Tests for CLI runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from lucidscan.cli.runner import CLIRunner, get_version
from lucidscan.cli.exit_codes import (
    EXIT_SUCCESS,
    EXIT_INVALID_USAGE,
    EXIT_SCANNER_ERROR,
)


class TestGetVersion:
    """Tests for get_version function."""

    def test_get_version_from_metadata(self) -> None:
        """Test version retrieval from package metadata."""
        with patch("lucidscan.cli.runner.version", return_value="1.2.3"):
            result = get_version()
            assert result == "1.2.3"

    def test_get_version_fallback(self) -> None:
        """Test version fallback when metadata not available."""
        from importlib.metadata import PackageNotFoundError

        with patch(
            "lucidscan.cli.runner.version",
            side_effect=PackageNotFoundError("not found"),
        ):
            result = get_version()
            # Should return the fallback version from __init__.py
            assert result is not None


class TestCLIRunner:
    """Tests for CLIRunner class."""

    def test_initialization(self) -> None:
        """Test CLIRunner initialization."""
        runner = CLIRunner()
        assert runner.parser is not None
        assert runner.status_cmd is not None
        assert runner.scan_cmd is not None

    def test_run_help(self, capsys) -> None:
        """Test run with --help flag."""
        runner = CLIRunner()
        result = runner.run(["--help"])

        assert result == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower()

    def test_run_short_help(self, capsys) -> None:
        """Test run with -h flag."""
        runner = CLIRunner()
        result = runner.run(["-h"])

        assert result == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower()

    def test_run_version(self, capsys) -> None:
        """Test run with --version flag."""
        runner = CLIRunner()
        result = runner.run(["--version"])

        assert result == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert captured.out.strip()  # Non-empty version output

    def test_run_no_command(self, capsys) -> None:
        """Test run with no command shows help."""
        runner = CLIRunner()
        result = runner.run([])

        assert result == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower()

    def test_run_status_command(self, tmp_path: Path) -> None:
        """Test run status command."""
        home = tmp_path / ".lucidscan"
        home.mkdir(parents=True)

        with patch(
            "lucidscan.cli.commands.status.get_lucidscan_home",
            return_value=home,
        ):
            runner = CLIRunner()
            result = runner.run(["status"])
            assert result == EXIT_SUCCESS

    def test_run_init_command(self, tmp_path: Path) -> None:
        """Test run init command."""
        runner = CLIRunner()

        # Mock the InitCommand
        mock_init_cmd = MagicMock()
        mock_init_cmd.execute.return_value = EXIT_SUCCESS
        runner._init_cmd = mock_init_cmd

        # init uses positional path
        result = runner.run(["init", str(tmp_path)])
        assert result == EXIT_SUCCESS
        mock_init_cmd.execute.assert_called_once()

    def test_handle_init_not_available(self) -> None:
        """Test _handle_init when init command is not available."""
        runner = CLIRunner()
        runner._init_cmd = None

        # Create a mock args object
        args = MagicMock()

        # Patch the property to return None
        with patch.object(
            CLIRunner, "init_cmd", new_callable=PropertyMock, return_value=None
        ):
            result = runner._handle_init(args)
            assert result == EXIT_INVALID_USAGE

    def test_lazy_init_cmd_import_error(self) -> None:
        """Test lazy init_cmd property handles import error."""
        runner = CLIRunner()
        runner._init_cmd = None

        with patch(
            "lucidscan.cli.commands.init.InitCommand",
            side_effect=ImportError("not available"),
        ):
            runner._init_cmd = None
            # Access the property - should return None on import error
            result = runner.init_cmd
            assert result is None

    def test_handle_scan_no_domains_selected(self, capsys, tmp_path: Path) -> None:
        """Test scan command with no domains selected."""
        runner = CLIRunner()

        with patch(
            "lucidscan.cli.runner.load_config",
        ) as mock_load:
            mock_config = MagicMock()
            mock_config.get_enabled_domains.return_value = []
            mock_load.return_value = mock_config

            # scan uses positional path
            result = runner.run(["scan", str(tmp_path)])

            assert result == EXIT_SUCCESS
            captured = capsys.readouterr()
            assert "No scan domains selected" in captured.out

    def test_handle_scan_config_error(self, tmp_path: Path) -> None:
        """Test scan command with config error."""
        from lucidscan.config.loader import ConfigError

        runner = CLIRunner()

        with patch(
            "lucidscan.cli.runner.load_config",
            side_effect=ConfigError("Invalid config"),
        ):
            result = runner.run(["scan", str(tmp_path)])
            assert result == EXIT_INVALID_USAGE

    def test_handle_scan_file_not_found(self, tmp_path: Path) -> None:
        """Test scan command with file not found error."""
        runner = CLIRunner()

        with patch("lucidscan.cli.runner.load_config") as mock_load:
            mock_config = MagicMock()
            mock_config.get_enabled_domains.return_value = []
            mock_load.return_value = mock_config

            # Mock scan_cmd to raise FileNotFoundError
            runner.scan_cmd.execute = MagicMock(
                side_effect=FileNotFoundError("File not found")
            )

            result = runner.run(["scan", str(tmp_path), "--sca"])
            assert result == EXIT_INVALID_USAGE

    def test_handle_scan_generic_error(self, tmp_path: Path) -> None:
        """Test scan command with generic error."""
        runner = CLIRunner()

        with patch("lucidscan.cli.runner.load_config") as mock_load:
            mock_config = MagicMock()
            mock_config.get_enabled_domains.return_value = []
            mock_load.return_value = mock_config

            # Mock scan_cmd to raise generic exception
            runner.scan_cmd.execute = MagicMock(
                side_effect=RuntimeError("Scan failed")
            )

            result = runner.run(["scan", str(tmp_path), "--sca"])
            assert result == EXIT_SCANNER_ERROR

    def test_handle_scan_generic_error_with_debug(self, tmp_path: Path) -> None:
        """Test scan command with generic error and debug flag."""
        runner = CLIRunner()

        with patch("lucidscan.cli.runner.load_config") as mock_load:
            mock_config = MagicMock()
            mock_config.get_enabled_domains.return_value = []
            mock_load.return_value = mock_config

            # Mock scan_cmd to raise generic exception
            runner.scan_cmd.execute = MagicMock(
                side_effect=RuntimeError("Scan failed")
            )

            with patch("traceback.print_exc") as mock_traceback:
                result = runner.run(
                    ["--debug", "scan", str(tmp_path), "--sca"]
                )
                assert result == EXIT_SCANNER_ERROR
                mock_traceback.assert_called_once()

    def test_handle_serve_command(self, tmp_path: Path) -> None:
        """Test serve command."""
        runner = CLIRunner()

        with patch("lucidscan.cli.runner.load_config") as mock_load:
            mock_config = MagicMock()
            mock_load.return_value = mock_config

            with patch(
                "lucidscan.cli.commands.serve.ServeCommand"
            ) as mock_serve_class:
                mock_serve = MagicMock()
                mock_serve.execute.return_value = EXIT_SUCCESS
                mock_serve_class.return_value = mock_serve

                # serve uses positional path
                result = runner.run(["serve", str(tmp_path)])
                assert result == EXIT_SUCCESS

    def test_handle_serve_config_error(self, tmp_path: Path) -> None:
        """Test serve command with config error."""
        from lucidscan.config.loader import ConfigError

        runner = CLIRunner()

        with patch(
            "lucidscan.cli.runner.load_config",
            side_effect=ConfigError("Invalid config"),
        ):
            result = runner.run(["serve", str(tmp_path)])
            assert result == EXIT_INVALID_USAGE

    def test_handle_serve_import_error(self, tmp_path: Path) -> None:
        """Test serve command with import error."""
        runner = CLIRunner()

        with patch("lucidscan.cli.runner.load_config") as mock_load:
            mock_config = MagicMock()
            mock_load.return_value = mock_config

            with patch(
                "lucidscan.cli.commands.serve.ServeCommand",
                side_effect=ImportError("serve not available"),
            ):
                result = runner.run(["serve", str(tmp_path)])
                assert result == EXIT_INVALID_USAGE

    def test_handle_setup_command(self) -> None:
        """Test setup command."""
        runner = CLIRunner()

        with patch("lucidscan.cli.commands.setup.SetupCommand") as mock_setup_class:
            mock_setup = MagicMock()
            mock_setup.execute.return_value = EXIT_SUCCESS
            mock_setup_class.return_value = mock_setup

            # setup doesn't take a path argument
            result = runner.run(["setup", "--claude-code"])
            assert result == EXIT_SUCCESS

    def test_handle_setup_import_error(self) -> None:
        """Test setup command with import error."""
        runner = CLIRunner()

        with patch(
            "lucidscan.cli.commands.setup.SetupCommand",
            side_effect=ImportError("setup not available"),
        ):
            result = runner.run(["setup", "--claude-code"])
            assert result == EXIT_INVALID_USAGE
