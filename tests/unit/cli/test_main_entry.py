"""Tests for lucidshark.cli.__main__ entry point."""

from __future__ import annotations

from unittest.mock import patch


class TestMainEntry:
    """Tests for the __main__ module entry point."""

    @patch("lucidshark.cli.main", return_value=0)
    def test_main_called(self, mock_main) -> None:
        """Verify main() is callable and returns exit code."""
        from lucidshark.cli import main
        result = main()
        assert result == 0

    @patch("lucidshark.cli.CLIRunner")
    def test_main_creates_runner(self, mock_runner_cls) -> None:
        """Verify main() creates CLIRunner and calls run."""
        mock_runner = mock_runner_cls.return_value
        mock_runner.run.return_value = 0

        from lucidshark.cli import main
        result = main()

        assert result == 0
        mock_runner.run.assert_called_once_with(None)

    @patch("lucidshark.cli.CLIRunner")
    def test_main_passes_argv(self, mock_runner_cls) -> None:
        """Verify main() passes argv to runner."""
        mock_runner = mock_runner_cls.return_value
        mock_runner.run.return_value = 1

        from lucidshark.cli import main
        result = main(["scan", "--all"])

        assert result == 1
        mock_runner.run.assert_called_once_with(["scan", "--all"])
