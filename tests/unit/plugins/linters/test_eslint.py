"""Unit tests for ESLint linter plugin.

These tests mock subprocess calls to test the parsing logic without
requiring actual ESLint installation.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.eslint import ESLintLinter, SEVERITY_MAP, ESLINT_EXTENSIONS


def make_completed_process(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestESLintLinter:
    """Unit tests for ESLintLinter."""

    def test_name(self) -> None:
        """Test name property returns correct value."""
        linter = ESLintLinter()
        assert linter.name == "eslint"

    def test_languages(self) -> None:
        """Test languages property returns correct value."""
        linter = ESLintLinter()
        assert linter.languages == ["javascript", "typescript"]

    def test_supports_fix(self) -> None:
        """Test supports_fix property returns True."""
        linter = ESLintLinter()
        assert linter.supports_fix is True

    def test_get_version_success(self) -> None:
        """Test get_version with successful subprocess call."""
        linter = ESLintLinter()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "v8.56.0"

        with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
            with patch("subprocess.run", return_value=mock_result):
                version = linter.get_version()
                assert version == "8.56.0"

    def test_get_version_failure(self) -> None:
        """Test get_version returns unknown on failure."""
        linter = ESLintLinter()

        with patch.object(linter, "ensure_binary", side_effect=FileNotFoundError()):
            version = linter.get_version()
            assert version == "unknown"

    def test_ensure_binary_project_node_modules(self) -> None:
        """Test ensure_binary finds eslint in project node_modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create node_modules/.bin/eslint
            bin_dir = tmpdir_path / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True)
            eslint_path = bin_dir / "eslint"
            eslint_path.touch()

            linter = ESLintLinter(project_root=tmpdir_path)
            binary = linter.ensure_binary()
            assert binary == eslint_path

    def test_ensure_binary_system_path(self) -> None:
        """Test ensure_binary finds eslint in system PATH."""
        linter = ESLintLinter()

        with patch("shutil.which", return_value="/usr/local/bin/eslint"):
            binary = linter.ensure_binary()
            assert binary == Path("/usr/local/bin/eslint")

    def test_ensure_binary_not_found(self) -> None:
        """Test ensure_binary raises when eslint not found."""
        linter = ESLintLinter()

        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError) as exc_info:
                linter.ensure_binary()
            assert "ESLint is not installed" in str(exc_info.value)

    def test_lint_no_binary(self) -> None:
        """Test lint returns empty when binary not found."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", side_effect=FileNotFoundError("not found")):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_success(self) -> None:
        """Test lint parses output correctly."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            eslint_output = json.dumps([
                {
                    "filePath": "/test/src/file.js",
                    "messages": [
                        {
                            "ruleId": "no-unused-vars",
                            "severity": 2,
                            "message": "'x' is assigned a value but never used.",
                            "line": 10,
                            "column": 5,
                            "endLine": 10,
                            "endColumn": 6,
                        }
                    ],
                    "errorCount": 1,
                    "warningCount": 0,
                }
            ])

            mock_result = make_completed_process(
                returncode=1,
                stdout=eslint_output,
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
                with patch("lucidshark.plugins.linters.eslint.run_with_streaming", return_value=mock_result):
                    issues = linter.lint(context)

                    assert len(issues) == 1
                    assert issues[0].source_tool == "eslint"
                    assert issues[0].domain == ToolDomain.LINTING
                    assert "no-unused-vars" in issues[0].title
                    assert issues[0].line_start == 10
                    assert issues[0].severity == Severity.HIGH

    def test_lint_timeout(self) -> None:
        """Test lint handles timeout."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
                with patch("lucidshark.plugins.linters.eslint.run_with_streaming",
                          side_effect=subprocess.TimeoutExpired("eslint", 120)):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_subprocess_error(self) -> None:
        """Test lint handles subprocess error."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
                with patch("lucidshark.plugins.linters.eslint.run_with_streaming",
                          side_effect=OSError("command failed")):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_uses_src_dir_when_no_paths(self) -> None:
        """Test lint uses src directory when no paths specified."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create src directory
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[],  # Empty paths
                enabled_domains=[],
            )

            mock_result = make_completed_process(returncode=0, stdout="[]")

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
                with patch("lucidshark.plugins.linters.eslint.run_with_streaming", return_value=mock_result) as mock_run:
                    linter.lint(context)
                    # Check that src was passed
                    call_args = mock_run.call_args
                    cmd = call_args.kwargs.get("cmd") or call_args[1].get("cmd") or call_args[0][0]
                    assert str(src_dir) in cmd


class TestESLintFix:
    """Tests for ESLint fix functionality."""

    def test_fix_no_binary(self) -> None:
        """Test fix returns empty result when binary not found."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", side_effect=FileNotFoundError("not found")):
                result = linter.fix(context)
                assert result.issues_fixed == 0

    def test_fix_timeout(self) -> None:
        """Test fix handles timeout."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            mock_result = make_completed_process(returncode=0, stdout="[]")

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
                with patch("lucidshark.plugins.linters.eslint.run_with_streaming") as mock_run:
                    # First call (pre_issues lint) succeeds, second call (fix) times out
                    mock_run.side_effect = [
                        mock_result,
                        subprocess.TimeoutExpired("eslint", 120),
                    ]
                    result = linter.fix(context)
                    assert result.issues_fixed == 0

    def test_fix_success(self) -> None:
        """Test fix returns correct statistics."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            # Pre-fix: 2 issues
            pre_output = json.dumps([
                {
                    "filePath": "/test/file.js",
                    "messages": [
                        {"ruleId": "rule1", "severity": 2, "message": "Issue 1", "line": 1, "column": 1},
                        {"ruleId": "rule2", "severity": 2, "message": "Issue 2", "line": 2, "column": 1},
                    ],
                }
            ])

            # Post-fix: 1 issue remaining
            post_output = json.dumps([
                {
                    "filePath": "/test/file.js",
                    "messages": [
                        {"ruleId": "rule2", "severity": 2, "message": "Issue 2", "line": 2, "column": 1},
                    ],
                }
            ])

            pre_result = make_completed_process(returncode=1, stdout=pre_output)
            post_result = make_completed_process(returncode=1, stdout=post_output)

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
                with patch("lucidshark.plugins.linters.eslint.run_with_streaming") as mock_run:
                    mock_run.side_effect = [pre_result, post_result]
                    result = linter.fix(context)
                    assert result.issues_fixed == 1
                    assert result.issues_remaining == 1


class TestESLintOutputParsing:
    """Tests for ESLint output parsing."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        linter = ESLintLinter()
        issues = linter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_empty_json_array(self) -> None:
        """Test parsing empty JSON array."""
        linter = ESLintLinter()
        issues = linter._parse_output("[]", Path("/project"))
        assert issues == []

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON."""
        linter = ESLintLinter()
        issues = linter._parse_output("not json", Path("/project"))
        assert issues == []

    def test_parse_single_file_single_issue(self) -> None:
        """Test parsing single file with single issue."""
        linter = ESLintLinter()
        output = json.dumps([
            {
                "filePath": "/test/file.js",
                "messages": [
                    {
                        "ruleId": "no-unused-vars",
                        "severity": 2,
                        "message": "'x' is not used.",
                        "line": 5,
                        "column": 3,
                    }
                ],
            }
        ])

        issues = linter._parse_output(output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].line_start == 5
        assert "no-unused-vars" in issues[0].title

    def test_parse_multiple_files(self) -> None:
        """Test parsing multiple files."""
        linter = ESLintLinter()
        output = json.dumps([
            {
                "filePath": "/test/a.js",
                "messages": [
                    {"ruleId": "rule1", "severity": 2, "message": "Error 1", "line": 1, "column": 1}
                ],
            },
            {
                "filePath": "/test/b.js",
                "messages": [
                    {"ruleId": "rule2", "severity": 1, "message": "Warning 1", "line": 5, "column": 1}
                ],
            },
        ])

        issues = linter._parse_output(output, Path("/project"))

        assert len(issues) == 2

    def test_parse_file_with_no_messages(self) -> None:
        """Test parsing file with no messages."""
        linter = ESLintLinter()
        output = json.dumps([
            {
                "filePath": "/test/clean.js",
                "messages": [],
            }
        ])

        issues = linter._parse_output(output, Path("/project"))

        assert len(issues) == 0


class TestSeverityMapping:
    """Tests for ESLint severity mapping."""

    def test_severity_map_error(self) -> None:
        """Test that severity 2 maps to HIGH."""
        assert SEVERITY_MAP[2] == Severity.HIGH

    def test_severity_map_warning(self) -> None:
        """Test that severity 1 maps to MEDIUM."""
        assert SEVERITY_MAP[1] == Severity.MEDIUM

    def test_message_to_issue_error_severity(self) -> None:
        """Test message with error severity."""
        linter = ESLintLinter()
        message = {
            "ruleId": "test-rule",
            "severity": 2,
            "message": "Error message",
            "line": 1,
            "column": 1,
        }

        issue = linter._message_to_issue(message, "/test/file.js", Path("/project"))

        assert issue is not None
        assert issue.severity == Severity.HIGH

    def test_message_to_issue_warning_severity(self) -> None:
        """Test message with warning severity."""
        linter = ESLintLinter()
        message = {
            "ruleId": "test-rule",
            "severity": 1,
            "message": "Warning message",
            "line": 1,
            "column": 1,
        }

        issue = linter._message_to_issue(message, "/test/file.js", Path("/project"))

        assert issue is not None
        assert issue.severity == Severity.MEDIUM

    def test_message_to_issue_unknown_severity(self) -> None:
        """Test message with unknown severity defaults to MEDIUM."""
        linter = ESLintLinter()
        message = {
            "ruleId": "test-rule",
            "severity": 99,  # Unknown
            "message": "Message",
            "line": 1,
            "column": 1,
        }

        issue = linter._message_to_issue(message, "/test/file.js", Path("/project"))

        assert issue is not None
        assert issue.severity == Severity.MEDIUM


class TestIssueIdGeneration:
    """Tests for issue ID generation."""

    def test_generate_issue_id_deterministic(self) -> None:
        """Test that issue IDs are deterministic."""
        linter = ESLintLinter()

        id1 = linter._generate_issue_id("no-unused-vars", "test.js", 10, 5, "Variable not used")
        id2 = linter._generate_issue_id("no-unused-vars", "test.js", 10, 5, "Variable not used")

        assert id1 == id2

    def test_generate_issue_id_different_inputs(self) -> None:
        """Test that different inputs produce different IDs."""
        linter = ESLintLinter()

        id1 = linter._generate_issue_id("rule1", "test.js", 10, 5, "Message")
        id2 = linter._generate_issue_id("rule2", "test.js", 10, 5, "Message")

        assert id1 != id2

    def test_generate_issue_id_with_rule(self) -> None:
        """Test issue ID format with rule."""
        linter = ESLintLinter()

        issue_id = linter._generate_issue_id("no-unused-vars", "test.js", 10, 5, "Message")

        assert issue_id.startswith("eslint-no-unused-vars-")

    def test_generate_issue_id_without_rule(self) -> None:
        """Test issue ID format without rule."""
        linter = ESLintLinter()

        issue_id = linter._generate_issue_id("", "test.js", 10, 5, "Message")

        assert issue_id.startswith("eslint-")
        assert "eslint--" not in issue_id  # Should not have double dash

    def test_generate_issue_id_handles_none_values(self) -> None:
        """Test issue ID handles None line/column."""
        linter = ESLintLinter()

        # Should not raise
        issue_id = linter._generate_issue_id("rule", "file.js", None, None, "Message")
        assert issue_id.startswith("eslint-rule-")


class TestMessageToIssue:
    """Tests for message to issue conversion."""

    def test_message_with_fix(self) -> None:
        """Test message with fix information."""
        linter = ESLintLinter()
        message = {
            "ruleId": "semi",
            "severity": 2,
            "message": "Missing semicolon.",
            "line": 1,
            "column": 10,
            "fix": {"range": [9, 9], "text": ";"},
        }

        issue = linter._message_to_issue(message, "/test/file.js", Path("/project"))

        assert issue is not None
        assert issue.fixable is True

    def test_message_without_fix(self) -> None:
        """Test message without fix information."""
        linter = ESLintLinter()
        message = {
            "ruleId": "no-undef",
            "severity": 2,
            "message": "'x' is not defined.",
            "line": 1,
            "column": 1,
        }

        issue = linter._message_to_issue(message, "/test/file.js", Path("/project"))

        assert issue is not None
        assert issue.fixable is False

    def test_message_without_rule_id(self) -> None:
        """Test message without rule ID."""
        linter = ESLintLinter()
        message = {
            "severity": 2,
            "message": "Parsing error.",
            "line": 1,
            "column": 1,
        }

        issue = linter._message_to_issue(message, "/test/file.js", Path("/project"))

        assert issue is not None
        assert issue.title == "Parsing error."

    def test_message_relative_path(self) -> None:
        """Test message with relative path."""
        linter = ESLintLinter()
        message = {
            "ruleId": "test",
            "severity": 2,
            "message": "Test",
            "line": 1,
            "column": 1,
        }

        issue = linter._message_to_issue(message, "src/file.js", Path("/project"))

        assert issue is not None
        # Use Path for cross-platform comparison
        assert issue.file_path == Path("/project/src/file.js")

    def test_message_absolute_path(self) -> None:
        """Test message with absolute path."""
        linter = ESLintLinter()
        message = {
            "ruleId": "test",
            "severity": 2,
            "message": "Test",
            "line": 1,
            "column": 1,
        }

        issue = linter._message_to_issue(message, "/absolute/path/file.js", Path("/project"))

        assert issue is not None
        # Use Path for cross-platform comparison
        assert issue.file_path == Path("/absolute/path/file.js")

    def test_message_with_end_line(self) -> None:
        """Test message with end line."""
        linter = ESLintLinter()
        message = {
            "ruleId": "test",
            "severity": 2,
            "message": "Test",
            "line": 1,
            "column": 1,
            "endLine": 5,
            "endColumn": 10,
        }

        issue = linter._message_to_issue(message, "/test/file.js", Path("/project"))

        assert issue is not None
        assert issue.line_start == 1
        assert issue.line_end == 5


class TestESLintExtensions:
    """Tests for ESLINT_EXTENSIONS constant."""

    def test_js_extensions_included(self) -> None:
        """Test that JavaScript extensions are included."""
        assert ".js" in ESLINT_EXTENSIONS
        assert ".jsx" in ESLINT_EXTENSIONS
        assert ".mjs" in ESLINT_EXTENSIONS
        assert ".cjs" in ESLINT_EXTENSIONS

    def test_ts_extensions_included(self) -> None:
        """Test that TypeScript extensions are included."""
        assert ".ts" in ESLINT_EXTENSIONS
        assert ".tsx" in ESLINT_EXTENSIONS
        assert ".mts" in ESLINT_EXTENSIONS
        assert ".cts" in ESLINT_EXTENSIONS

    def test_non_js_extensions_not_included(self) -> None:
        """Test that non-JS/TS extensions are not included."""
        assert ".md" not in ESLINT_EXTENSIONS
        assert ".py" not in ESLINT_EXTENSIONS
        assert ".json" not in ESLINT_EXTENSIONS
        assert ".yaml" not in ESLINT_EXTENSIONS


class TestESLintPathFiltering:
    """Tests for ESLint path filtering to supported file types."""

    def test_filter_paths_js_files(self) -> None:
        """Test that JS files are included."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            js_file = tmpdir_path / "test.js"
            js_file.touch()

            result = linter._filter_paths([js_file], tmpdir_path)

            assert len(result) == 1
            assert js_file in [Path(p) for p in result]

    def test_filter_paths_ts_files(self) -> None:
        """Test that TypeScript files are included."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            ts_file = tmpdir_path / "test.ts"
            tsx_file = tmpdir_path / "test.tsx"
            ts_file.touch()
            tsx_file.touch()

            result = linter._filter_paths([ts_file, tsx_file], tmpdir_path)

            assert len(result) == 2

    def test_filter_paths_excludes_md_files(self) -> None:
        """Test that markdown files are excluded."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            md_file = tmpdir_path / "README.md"
            md_file.touch()

            result = linter._filter_paths([md_file], tmpdir_path)

            assert len(result) == 0

    def test_filter_paths_excludes_non_js_files(self) -> None:
        """Test that non-JS/TS files are excluded."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            py_file = tmpdir_path / "test.py"
            json_file = tmpdir_path / "config.json"
            yaml_file = tmpdir_path / "config.yaml"
            py_file.touch()
            json_file.touch()
            yaml_file.touch()

            result = linter._filter_paths([py_file, json_file, yaml_file], tmpdir_path)

            assert len(result) == 0

    def test_filter_paths_includes_directories(self) -> None:
        """Test that directories are passed through."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()

            result = linter._filter_paths([src_dir], tmpdir_path)

            assert len(result) == 1
            assert src_dir in [Path(p) for p in result]

    def test_filter_paths_mixed_files(self) -> None:
        """Test filtering with mixed file types."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create various file types
            js_file = tmpdir_path / "app.js"
            ts_file = tmpdir_path / "app.ts"
            md_file = tmpdir_path / "README.md"
            py_file = tmpdir_path / "script.py"
            src_dir = tmpdir_path / "src"

            js_file.touch()
            ts_file.touch()
            md_file.touch()
            py_file.touch()
            src_dir.mkdir()

            result = linter._filter_paths(
                [js_file, ts_file, md_file, py_file, src_dir],
                tmpdir_path,
            )

            # Should include: js_file, ts_file, src_dir
            # Should exclude: md_file, py_file
            result_paths = [Path(p) for p in result]
            assert len(result) == 3
            assert js_file in result_paths
            assert ts_file in result_paths
            assert src_dir in result_paths
            assert md_file not in result_paths
            assert py_file not in result_paths

    def test_filter_paths_all_extensions(self) -> None:
        """Test all supported extensions are included."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            extensions = [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"]
            files = []
            for ext in extensions:
                f = tmpdir_path / f"test{ext}"
                f.touch()
                files.append(f)

            result = linter._filter_paths(files, tmpdir_path)

            assert len(result) == len(extensions)

    def test_lint_returns_empty_when_no_js_files(self) -> None:
        """Test lint returns empty when no JS/TS files to scan."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create only non-JS files
            md_file = tmpdir_path / "README.md"
            md_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[md_file],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
                # Should return empty without calling ESLint
                issues = linter.lint(context)
                assert issues == []

    def test_fix_returns_empty_when_no_js_files(self) -> None:
        """Test fix returns empty result when no JS/TS files to fix."""
        linter = ESLintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create only non-JS files
            md_file = tmpdir_path / "README.md"
            md_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[md_file],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/eslint")):
                result = linter.fix(context)
                assert result.issues_fixed == 0
                assert result.files_modified == 0
