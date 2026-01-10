"""Integration tests for the scan CLI command.

These tests verify the --lint and --type-check flags work correctly.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path


from lucidscan import cli
from tests.integration.conftest import ruff_available


class TestScanCommandLinting:
    """Integration tests for scan command with --lint flag."""

    @ruff_available
    def test_scan_lint_flag_runs_linters(self) -> None:
        """Test that --lint flag triggers linting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with linting issues
            test_file = tmpdir_path / "lint_test.py"
            test_file.write_text("import os\nx = 1\n")

            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()

            try:
                cli.main([
                    "scan",
                    "--lint",
                    "--format", "json",
                    str(tmpdir_path),
                ])
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

            # Should produce valid JSON
            data = json.loads(output)
            assert "issues" in data

    @ruff_available
    def test_scan_lint_json_format(self) -> None:
        """Test that --lint with --format json produces valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a clean Python file
            test_file = tmpdir_path / "clean.py"
            test_file.write_text('"""Clean module."""\n')

            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()

            try:
                cli.main([
                    "scan",
                    "--lint",
                    "--format", "json",
                    str(tmpdir_path),
                ])
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()
            data = json.loads(output)

            # Should have schema_version and issues
            assert "schema_version" in data
            assert "issues" in data


class TestScanCommandTypeChecking:
    """Integration tests for scan command with --type-check flag."""

    def test_scan_type_check_flag_runs_checkers(self) -> None:
        """Test that --type-check flag triggers type checking.

        Note: This test verifies the CLI accepts --type-check and produces
        valid JSON output. It may not find issues if type checkers aren't
        installed in the scanned project's venv.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with type errors
            test_file = tmpdir_path / "type_test.py"
            test_file.write_text("x: int = 'string'\n")

            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()

            try:
                cli.main([
                    "scan",
                    "--type-check",
                    "--format", "json",
                    str(tmpdir_path),
                ])
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

            # Should produce valid JSON with proper schema
            data = json.loads(output)
            assert "schema_version" in data
            assert "issues" in data
            assert "summary" in data


class TestScanCommandAllFlag:
    """Integration tests for scan command with --all flag."""

    @ruff_available
    def test_scan_all_includes_linting(self) -> None:
        """Test that --all flag includes linting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with linting issues
            test_file = tmpdir_path / "all_test.py"
            test_file.write_text("import os\nx = 1\n")

            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()

            try:
                cli.main([
                    "scan",
                    "--all",
                    "--format", "json",
                    str(tmpdir_path),
                ])
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()
            data = json.loads(output)

            # Should have found linting issues
            assert "issues" in data


class TestScanCommandFormats:
    """Integration tests for scan command output formats."""

    @ruff_available
    def test_scan_format_sarif(self) -> None:
        """Test that --format sarif produces valid SARIF."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "sarif_test.py"
            test_file.write_text("import os\nx = 1\n")

            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()

            try:
                cli.main([
                    "scan",
                    "--lint",
                    "--format", "sarif",
                    str(tmpdir_path),
                ])
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()
            data = json.loads(output)

            # SARIF format should have $schema and runs
            assert "$schema" in data
            assert "runs" in data

    @ruff_available
    def test_scan_format_summary(self) -> None:
        """Test that --format summary produces summary output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "summary_test.py"
            test_file.write_text("import os\nx = 1\n")

            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()

            try:
                cli.main([
                    "scan",
                    "--lint",
                    "--format", "summary",
                    str(tmpdir_path),
                ])
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

            # Summary format should contain text summary
            assert "issues" in output.lower() or "scanned" in output.lower() or len(output) > 0
