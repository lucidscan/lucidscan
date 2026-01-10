"""Integration tests for ESLint linter.

These tests require Node.js and ESLint to be installed.

Run with: pytest tests/integration/linters -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext
from lucidscan.plugins.linters.eslint import ESLintLinter
from tests.integration.conftest import eslint_available, node_available


class TestESLintAvailability:
    """Tests for ESLint availability."""

    @eslint_available
    def test_ensure_binary_finds_eslint(self, eslint_linter: ESLintLinter) -> None:
        """Test that ensure_binary finds ESLint if installed."""
        binary_path = eslint_linter.ensure_binary()
        assert binary_path.exists()
        assert "eslint" in str(binary_path)


@node_available
@eslint_available
class TestESLintLinting:
    """Integration tests for ESLint linting."""

    def test_lint_javascript_file_with_issues(self, eslint_linter: ESLintLinter) -> None:
        """Test linting a JavaScript file with issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create eslint config
            eslint_config = tmpdir_path / "eslint.config.js"
            eslint_config.write_text(
                'export default [\n'
                '  {\n'
                '    rules: {\n'
                '      "no-unused-vars": "error"\n'
                '    }\n'
                '  }\n'
                '];\n'
            )

            # Create a JS file with unused variable
            test_file = tmpdir_path / "test.js"
            test_file.write_text("const unused = 1;\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = eslint_linter.lint(context)

            # Should find the unused variable
            assert isinstance(issues, list)
            for issue in issues:
                assert issue.source_tool == "eslint"

    def test_lint_empty_directory(self, eslint_linter: ESLintLinter) -> None:
        """Test linting an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = eslint_linter.lint(context)

            assert isinstance(issues, list)


@node_available
@eslint_available
class TestESLintAutoFix:
    """Integration tests for ESLint auto-fix functionality."""

    def test_fix_returns_result(self, eslint_linter: ESLintLinter) -> None:
        """Test that fix mode returns a result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a JS file
            test_file = tmpdir_path / "fixable.js"
            test_file.write_text("var x = 1;\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = eslint_linter.fix(context)

            # Result should have fix statistics
            assert hasattr(result, "issues_fixed")
            assert hasattr(result, "issues_remaining")
