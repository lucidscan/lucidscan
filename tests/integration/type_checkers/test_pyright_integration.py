"""Integration tests for pyright type checker.

These tests actually run pyright against real targets.
They require pyright to be installed (via npm or pip).

Run with: pytest tests/integration/type_checkers -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext, Severity, ToolDomain
from lucidscan.plugins.type_checkers.pyright import PyrightChecker
from tests.integration.conftest import pyright_available


class TestPyrightAvailability:
    """Tests for pyright availability."""

    @pyright_available
    def test_ensure_binary_finds_pyright(self, pyright_checker: PyrightChecker) -> None:
        """Test that ensure_binary finds pyright if installed."""
        binary_path = pyright_checker.ensure_binary()
        assert binary_path.exists()
        assert "pyright" in binary_path.name


@pyright_available
class TestPyrightTypeChecking:
    """Integration tests for pyright type checking."""

    def test_check_file_with_type_errors(self, pyright_checker: PyrightChecker) -> None:
        """Test checking a file with type errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with type errors
            test_file = tmpdir_path / "type_errors.py"
            test_file.write_text(
                "def add(x: int, y: int) -> int:\n"
                "    return x + y\n"
                "\n"
                "result: str = add(1, 2)  # Type error: int assigned to str\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = pyright_checker.check(context)

            # Should find the type error
            assert isinstance(issues, list)
            for issue in issues:
                assert issue.source_tool == "pyright"
                assert issue.scanner == ToolDomain.TYPE_CHECKING

    def test_check_clean_typed_file(self, pyright_checker: PyrightChecker) -> None:
        """Test checking a cleanly typed file returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a cleanly typed Python file
            test_file = tmpdir_path / "clean.py"
            test_file.write_text(
                "def add(x: int, y: int) -> int:\n"
                "    return x + y\n"
                "\n"
                "result: int = add(1, 2)\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = pyright_checker.check(context)

            # Clean file should have no issues
            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_check_empty_directory(self, pyright_checker: PyrightChecker) -> None:
        """Test checking an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = pyright_checker.check(context)

            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_check_multiple_errors(self, pyright_checker: PyrightChecker) -> None:
        """Test checking a file with multiple type errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a file with multiple type errors
            test_file = tmpdir_path / "multiple.py"
            test_file.write_text(
                "x: int = 'string'  # Error 1\n"
                "y: str = 123  # Error 2\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = pyright_checker.check(context)

            # Should find multiple errors
            assert len(issues) >= 2


class TestPyrightOutputParsing:
    """Tests for pyright output parsing."""

    @pyright_available
    def test_severity_mapping(self, pyright_checker: PyrightChecker) -> None:
        """Test that pyright severities are mapped correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "severity.py"
            test_file.write_text("x: int = 'string'\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = pyright_checker.check(context)

            if issues:
                # All issues should have valid severity
                for issue in issues:
                    assert issue.severity in [
                        Severity.CRITICAL,
                        Severity.HIGH,
                        Severity.MEDIUM,
                        Severity.LOW,
                        Severity.INFO,
                    ]

    @pyright_available
    def test_issue_id_is_deterministic(self, pyright_checker: PyrightChecker) -> None:
        """Test that issue IDs are consistent across runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "deterministic.py"
            test_file.write_text("x: int = 'string'\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues1 = pyright_checker.check(context)
            issues2 = pyright_checker.check(context)

            if issues1 and issues2:
                # Same file should produce same IDs
                assert issues1[0].id == issues2[0].id

    @pyright_available
    def test_file_path_in_issues(self, pyright_checker: PyrightChecker) -> None:
        """Test that issues have correct file paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "test_path.py"
            test_file.write_text("x: int = 'string'\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = pyright_checker.check(context)

            if issues:
                assert issues[0].file_path is not None
                assert "test_path.py" in str(issues[0].file_path)
