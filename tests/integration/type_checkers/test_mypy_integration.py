"""Integration tests for mypy type checker.

These tests actually run mypy against real targets.
They require mypy to be installed (via pip).

Run with: pytest tests/integration/type_checkers -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext, Severity, ToolDomain
from lucidscan.plugins.type_checkers.mypy import MypyChecker
from tests.integration.conftest import mypy_available


class TestMypyAvailability:
    """Tests for mypy availability."""

    @mypy_available
    def test_ensure_binary_finds_mypy(self, mypy_checker: MypyChecker) -> None:
        """Test that ensure_binary finds mypy if installed."""
        binary_path = mypy_checker.ensure_binary()
        assert binary_path.exists()
        assert "mypy" in binary_path.name


@mypy_available
class TestMypyTypeChecking:
    """Integration tests for mypy type checking."""

    def test_check_file_with_type_errors(self, mypy_checker: MypyChecker) -> None:
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

            issues = mypy_checker.check(context)

            # Should find the type error
            assert len(issues) > 0
            assert issues[0].source_tool == "mypy"
            assert issues[0].scanner == ToolDomain.TYPE_CHECKING

    def test_check_clean_typed_file(self, mypy_checker: MypyChecker) -> None:
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

            issues = mypy_checker.check(context)

            # Clean file should have no issues
            assert len(issues) == 0

    def test_check_empty_directory(self, mypy_checker: MypyChecker) -> None:
        """Test checking an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = mypy_checker.check(context)

            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_check_multiple_errors(self, mypy_checker: MypyChecker) -> None:
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

            issues = mypy_checker.check(context)

            # Should find multiple errors
            assert len(issues) >= 2


class TestMypyOutputParsing:
    """Tests for mypy output parsing."""

    @mypy_available
    def test_severity_mapping(self, mypy_checker: MypyChecker) -> None:
        """Test that mypy severities are mapped correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "severity.py"
            test_file.write_text("x: int = 'string'\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = mypy_checker.check(context)

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

    @mypy_available
    def test_issue_id_is_deterministic(self, mypy_checker: MypyChecker) -> None:
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

            issues1 = mypy_checker.check(context)
            issues2 = mypy_checker.check(context)

            if issues1 and issues2:
                # Same file should produce same IDs
                assert issues1[0].id == issues2[0].id

    @mypy_available
    def test_file_path_in_issues(self, mypy_checker: MypyChecker) -> None:
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

            issues = mypy_checker.check(context)

            if issues:
                assert issues[0].file_path is not None
                assert "test_path.py" in str(issues[0].file_path)
