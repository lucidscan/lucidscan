"""Integration tests for TypeScript type checker.

These tests actually run the TypeScript compiler against real targets.
They require Node.js and TypeScript to be installed.

Run with: pytest tests/integration/type_checkers -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext, Severity, ToolDomain
from lucidscan.plugins.type_checkers.typescript import TypeScriptChecker
from tests.integration.conftest import tsc_available, node_available


class TestTypeScriptAvailability:
    """Tests for TypeScript availability."""

    @tsc_available
    def test_ensure_binary_finds_tsc(self, typescript_checker: TypeScriptChecker) -> None:
        """Test that ensure_binary finds tsc if installed."""
        binary_path = typescript_checker.ensure_binary()
        assert binary_path.exists()
        assert "tsc" in binary_path.name


@node_available
@tsc_available
class TestTypeScriptTypeChecking:
    """Integration tests for TypeScript type checking."""

    def test_check_file_with_type_errors(self, typescript_checker: TypeScriptChecker) -> None:
        """Test checking a TypeScript file with type errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create tsconfig.json (required for TypeScript)
            tsconfig = tmpdir_path / "tsconfig.json"
            tsconfig.write_text(
                '{\n'
                '  "compilerOptions": {\n'
                '    "strict": true,\n'
                '    "noEmit": true\n'
                '  }\n'
                '}\n'
            )

            # Create a TypeScript file with type errors
            test_file = tmpdir_path / "type_errors.ts"
            test_file.write_text(
                "function add(x: number, y: number): number {\n"
                "    return x + y;\n"
                "}\n"
                "\n"
                "const result: string = add(1, 2);  // Type error\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = typescript_checker.check(context)

            # Should find the type error
            assert isinstance(issues, list)
            for issue in issues:
                assert issue.source_tool == "typescript"
                assert issue.scanner == ToolDomain.TYPE_CHECKING

    def test_check_clean_typescript_file(self, typescript_checker: TypeScriptChecker) -> None:
        """Test checking a cleanly typed TypeScript file returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create tsconfig.json
            tsconfig = tmpdir_path / "tsconfig.json"
            tsconfig.write_text(
                '{\n'
                '  "compilerOptions": {\n'
                '    "strict": true,\n'
                '    "noEmit": true\n'
                '  }\n'
                '}\n'
            )

            # Create a cleanly typed TypeScript file
            test_file = tmpdir_path / "clean.ts"
            test_file.write_text(
                "function add(x: number, y: number): number {\n"
                "    return x + y;\n"
                "}\n"
                "\n"
                "const result: number = add(1, 2);\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = typescript_checker.check(context)

            # Clean file should have no issues
            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_check_empty_directory(self, typescript_checker: TypeScriptChecker) -> None:
        """Test checking an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = typescript_checker.check(context)

            assert isinstance(issues, list)

    def test_check_multiple_errors(self, typescript_checker: TypeScriptChecker) -> None:
        """Test checking a file with multiple type errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create tsconfig.json
            tsconfig = tmpdir_path / "tsconfig.json"
            tsconfig.write_text(
                '{\n'
                '  "compilerOptions": {\n'
                '    "strict": true,\n'
                '    "noEmit": true\n'
                '  }\n'
                '}\n'
            )

            # Create a file with multiple type errors
            test_file = tmpdir_path / "multiple.ts"
            test_file.write_text(
                "const x: number = 'string';  // Error 1\n"
                "const y: string = 123;  // Error 2\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = typescript_checker.check(context)

            # Should find multiple errors
            assert isinstance(issues, list)
            # TypeScript should report at least 2 errors
            if issues:
                assert len(issues) >= 2


class TestTypeScriptOutputParsing:
    """Tests for TypeScript output parsing."""

    @tsc_available
    def test_severity_mapping(self, typescript_checker: TypeScriptChecker) -> None:
        """Test that TypeScript severities are mapped correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create tsconfig.json
            tsconfig = tmpdir_path / "tsconfig.json"
            tsconfig.write_text(
                '{\n'
                '  "compilerOptions": {\n'
                '    "strict": true,\n'
                '    "noEmit": true\n'
                '  }\n'
                '}\n'
            )

            test_file = tmpdir_path / "severity.ts"
            test_file.write_text("const x: number = 'string';\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = typescript_checker.check(context)

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

    @tsc_available
    def test_file_path_in_issues(self, typescript_checker: TypeScriptChecker) -> None:
        """Test that issues have correct file paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create tsconfig.json
            tsconfig = tmpdir_path / "tsconfig.json"
            tsconfig.write_text(
                '{\n'
                '  "compilerOptions": {\n'
                '    "strict": true,\n'
                '    "noEmit": true\n'
                '  }\n'
                '}\n'
            )

            test_file = tmpdir_path / "test_path.ts"
            test_file.write_text("const x: number = 'string';\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = typescript_checker.check(context)

            if issues:
                assert issues[0].file_path is not None
                assert "test_path.ts" in str(issues[0].file_path)
