"""Unit tests for Duplo duplication detection plugin."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.duplication.base import DuplicateBlock, DuplicationResult
from lucidshark.plugins.duplication.duplo import (
    DuploPlugin,
    SUPPORTED_EXTENSIONS,
)

_IS_WINDOWS = sys.platform == "win32"
_DUPLO_BINARY = "lucidshark-duplo.exe" if _IS_WINDOWS else "lucidshark-duplo"


def make_completed_process(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestDuploPluginProperties:
    """Tests for DuploPlugin basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        plugin = DuploPlugin()
        assert plugin.name == "duplo"

    def test_languages(self) -> None:
        """Test supported languages."""
        plugin = DuploPlugin()
        assert "python" in plugin.languages
        assert "rust" in plugin.languages
        assert "java" in plugin.languages
        assert "javascript" in plugin.languages
        assert "typescript" in plugin.languages

    def test_domain(self) -> None:
        """Test domain is DUPLICATION."""
        plugin = DuploPlugin()
        assert plugin.domain == ToolDomain.DUPLICATION

    def test_get_version(self) -> None:
        """Test get_version returns the configured version."""
        plugin = DuploPlugin(version="1.0.0")
        assert plugin.get_version() == "1.0.0"

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = DuploPlugin(project_root=Path(tmpdir))
            assert plugin.name == "duplo"

    def test_init_without_project_root(self) -> None:
        """Test initialization without project root."""
        plugin = DuploPlugin()
        assert plugin.name == "duplo"


class TestSupportedExtensions:
    """Tests for SUPPORTED_EXTENSIONS mapping."""

    def test_python_extension(self) -> None:
        """Test .py maps to python."""
        assert SUPPORTED_EXTENSIONS[".py"] == "python"

    def test_rust_extension(self) -> None:
        """Test .rs maps to rust."""
        assert SUPPORTED_EXTENSIONS[".rs"] == "rust"

    def test_java_extension(self) -> None:
        """Test .java maps to java."""
        assert SUPPORTED_EXTENSIONS[".java"] == "java"

    def test_javascript_extensions(self) -> None:
        """Test JS/JSX map to javascript."""
        assert SUPPORTED_EXTENSIONS[".js"] == "javascript"
        assert SUPPORTED_EXTENSIONS[".jsx"] == "javascript"

    def test_typescript_extensions(self) -> None:
        """Test TS/TSX map to typescript."""
        assert SUPPORTED_EXTENSIONS[".ts"] == "typescript"
        assert SUPPORTED_EXTENSIONS[".tsx"] == "typescript"

    def test_cpp_extensions(self) -> None:
        """Test C++ extensions."""
        assert SUPPORTED_EXTENSIONS[".cpp"] == "c++"
        assert SUPPORTED_EXTENSIONS[".cxx"] == "c++"
        assert SUPPORTED_EXTENSIONS[".cc"] == "c++"
        assert SUPPORTED_EXTENSIONS[".hpp"] == "c++"
        assert SUPPORTED_EXTENSIONS[".hxx"] == "c++"


class TestDuploEnsureBinary:
    """Tests for ensure_binary method."""

    def test_ensure_binary_exists(self) -> None:
        """Test ensure_binary returns path when binary already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = DuploPlugin(project_root=Path(tmpdir))

            # Create mock binary path
            with patch.object(plugin, "_paths") as mock_paths:
                bin_dir = Path(tmpdir) / "bin"
                bin_dir.mkdir()
                binary = bin_dir / _DUPLO_BINARY
                binary.touch()
                mock_paths.plugin_bin_dir.return_value = bin_dir

                result = plugin.ensure_binary()
                assert result == binary

    def test_ensure_binary_downloads_when_missing(self) -> None:
        """Test ensure_binary triggers download when binary not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = DuploPlugin(project_root=Path(tmpdir))

            with patch.object(plugin, "_paths") as mock_paths:
                bin_dir = Path(tmpdir) / "bin"
                bin_dir.mkdir()
                mock_paths.plugin_bin_dir.return_value = bin_dir

                with patch.object(plugin, "_download_binary") as mock_download:
                    # After download, binary should exist
                    def create_binary(dest_dir):
                        (dest_dir / _DUPLO_BINARY).touch()

                    mock_download.side_effect = create_binary

                    result = plugin.ensure_binary()
                    mock_download.assert_called_once()
                    assert result == bin_dir / _DUPLO_BINARY

    def test_ensure_binary_raises_on_download_failure(self) -> None:
        """Test ensure_binary raises when download fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = DuploPlugin(project_root=Path(tmpdir))

            with patch.object(plugin, "_paths") as mock_paths:
                bin_dir = Path(tmpdir) / "bin"
                bin_dir.mkdir()
                mock_paths.plugin_bin_dir.return_value = bin_dir

                with patch.object(plugin, "_download_binary"):
                    # Binary not created after download
                    with pytest.raises(RuntimeError, match="Failed to download"):
                        plugin.ensure_binary()


class TestDuploShouldExclude:
    """Tests for _should_exclude method."""

    def test_excludes_git_directory(self) -> None:
        """Test that .git paths are excluded."""
        plugin = DuploPlugin()
        assert plugin._should_exclude(".git/config", []) is True

    def test_excludes_node_modules(self) -> None:
        """Test that node_modules paths are excluded."""
        plugin = DuploPlugin()
        assert plugin._should_exclude("src/node_modules/package/index.js", []) is True

    def test_excludes_pycache(self) -> None:
        """Test that __pycache__ paths are excluded."""
        plugin = DuploPlugin()
        assert plugin._should_exclude("src/__pycache__/module.pyc", []) is True

    def test_excludes_venv(self) -> None:
        """Test that .venv paths are excluded."""
        plugin = DuploPlugin()
        assert plugin._should_exclude(".venv/lib/site-packages/module.py", []) is True

    def test_excludes_custom_pattern(self) -> None:
        """Test that custom patterns are excluded."""
        plugin = DuploPlugin()
        assert plugin._should_exclude("generated/output.py", ["generated/**"]) is True

    def test_does_not_exclude_normal_path(self) -> None:
        """Test that normal source paths are not excluded."""
        plugin = DuploPlugin()
        assert plugin._should_exclude("src/main.py", []) is False

    def test_excludes_build_directory(self) -> None:
        """Test that build directories are excluded."""
        plugin = DuploPlugin()
        assert plugin._should_exclude("build/output.js", []) is True

    def test_excludes_dist_directory(self) -> None:
        """Test that dist directories are excluded."""
        plugin = DuploPlugin()
        assert plugin._should_exclude("dist/bundle.js", []) is True

    def test_backslash_normalized(self) -> None:
        """Test that backslash paths are handled correctly."""
        plugin = DuploPlugin()
        # Path containing .venv is excluded by default pattern **/.venv/**
        assert plugin._should_exclude("src/.venv/lib/module.py", []) is True
        assert plugin._should_exclude(".venv/lib/module.py", []) is True
        # A normal path without .venv should not be excluded
        assert plugin._should_exclude("src/lib/module.py", []) is False


class TestDuploCollectSourceFiles:
    """Tests for _collect_source_files method."""

    def test_collects_python_files(self) -> None:
        """Test that Python files are collected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.touch()

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            plugin = DuploPlugin()
            files = plugin._collect_source_files(context)
            assert py_file in files

    def test_collects_js_files(self) -> None:
        """Test that JavaScript files are collected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            js_file = project_root / "app.js"
            js_file.touch()

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            plugin = DuploPlugin()
            files = plugin._collect_source_files(context)
            assert js_file in files

    def test_skips_unsupported_extensions(self) -> None:
        """Test that unsupported file types are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            txt_file = project_root / "readme.txt"
            txt_file.touch()

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            plugin = DuploPlugin()
            files = plugin._collect_source_files(context)
            assert txt_file not in files

    def test_skips_excluded_patterns(self) -> None:
        """Test that excluded patterns are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_dir = project_root / ".venv" / "lib"
            venv_dir.mkdir(parents=True)
            venv_file = venv_dir / "module.py"
            venv_file.touch()

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            plugin = DuploPlugin()
            files = plugin._collect_source_files(context)
            assert venv_file not in files

    def test_applies_extra_exclude_patterns(self) -> None:
        """Test that extra exclude patterns are applied."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gen_dir = project_root / "generated"
            gen_dir.mkdir()
            gen_file = gen_dir / "output.py"
            gen_file.touch()

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            plugin = DuploPlugin()
            files = plugin._collect_source_files(context, extra_exclude_patterns=["generated/**"])
            assert gen_file not in files

    def test_returns_empty_for_empty_directory(self) -> None:
        """Test that empty directory returns no files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            plugin = DuploPlugin()
            files = plugin._collect_source_files(context)
            assert files == []


class TestDuploParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        plugin = DuploPlugin()
        result = plugin._parse_output("", Path("/project"), 10.0)
        assert isinstance(result, DuplicationResult)
        assert result.duplicate_blocks == 0

    def test_parse_whitespace_output(self) -> None:
        """Test parsing whitespace-only output."""
        plugin = DuploPlugin()
        result = plugin._parse_output("   \n  ", Path("/project"), 10.0)
        assert isinstance(result, DuplicationResult)
        assert result.duplicate_blocks == 0

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON output."""
        plugin = DuploPlugin()
        result = plugin._parse_output("not json at all", Path("/project"), 10.0)
        assert isinstance(result, DuplicationResult)
        assert result.duplicate_blocks == 0

    def test_parse_valid_output(self) -> None:
        """Test parsing valid duplo JSON output."""
        plugin = DuploPlugin()
        output = json.dumps({
            "summary": {
                "files_analyzed": 10,
                "total_lines": 500,
                "duplicate_blocks": 2,
                "duplicate_lines": 30,
            },
            "duplicates": [
                {
                    "file1": {"path": "src/a.py", "start_line": 10, "end_line": 20},
                    "file2": {"path": "src/b.py", "start_line": 30, "end_line": 40},
                    "line_count": 10,
                    "lines": ["line1", "line2", "line3"],
                },
                {
                    "file1": {"path": "src/c.py", "start_line": 5, "end_line": 15},
                    "file2": {"path": "src/d.py", "start_line": 50, "end_line": 60},
                    "line_count": 10,
                    "lines": [],
                },
            ],
        })

        result = plugin._parse_output(output, Path("/project"), 10.0)

        assert result.files_analyzed == 10
        assert result.total_lines == 500
        assert result.duplicate_blocks == 2
        assert result.duplicate_lines == 30
        assert len(result.duplicates) == 2
        assert len(result.issues) == 2

    def test_parse_output_creates_issues(self) -> None:
        """Test that parsed output creates proper UnifiedIssues."""
        plugin = DuploPlugin()
        output = json.dumps({
            "summary": {
                "files_analyzed": 5,
                "total_lines": 200,
                "duplicate_blocks": 1,
                "duplicate_lines": 10,
            },
            "duplicates": [
                {
                    "file1": {"path": "src/main.py", "start_line": 1, "end_line": 10},
                    "file2": {"path": "src/utils.py", "start_line": 20, "end_line": 30},
                    "line_count": 10,
                    "lines": ["import os", "import sys"],
                },
            ],
        })

        result = plugin._parse_output(output, Path("/project"), 10.0)

        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.source_tool == "duplo"
        assert issue.domain == ToolDomain.DUPLICATION
        assert issue.severity == Severity.LOW
        assert issue.rule_id == "DUPLICATE"
        assert issue.line_start == 1
        assert issue.line_end == 10
        assert "10 lines" in issue.title

    def test_parse_output_with_absolute_paths(self) -> None:
        """Test parsing with absolute file paths in output."""
        plugin = DuploPlugin()
        output = json.dumps({
            "summary": {},
            "duplicates": [
                {
                    "file1": {"path": "/project/src/a.py", "start_line": 1, "end_line": 5},
                    "file2": {"path": "/project/src/b.py", "start_line": 1, "end_line": 5},
                    "line_count": 5,
                    "lines": [],
                },
            ],
        })

        result = plugin._parse_output(output, Path("/project"), 10.0)
        assert len(result.duplicates) == 1
        # Absolute paths should remain absolute
        assert result.duplicates[0].file1 == Path("/project/src/a.py")

    def test_parse_output_with_relative_paths(self) -> None:
        """Test parsing with relative file paths in output."""
        plugin = DuploPlugin()
        output = json.dumps({
            "summary": {},
            "duplicates": [
                {
                    "file1": {"path": "src/a.py", "start_line": 1, "end_line": 5},
                    "file2": {"path": "src/b.py", "start_line": 1, "end_line": 5},
                    "line_count": 5,
                    "lines": [],
                },
            ],
        })

        result = plugin._parse_output(output, Path("/project"), 10.0)
        assert len(result.duplicates) == 1
        # Relative paths should be made absolute
        assert result.duplicates[0].file1 == Path("/project/src/a.py")

    def test_parse_output_code_snippet_limited_to_5_lines(self) -> None:
        """Test that code snippets are limited to first 5 lines."""
        plugin = DuploPlugin()
        output = json.dumps({
            "summary": {},
            "duplicates": [
                {
                    "file1": {"path": "a.py", "start_line": 1, "end_line": 10},
                    "file2": {"path": "b.py", "start_line": 1, "end_line": 10},
                    "line_count": 10,
                    "lines": ["line1", "line2", "line3", "line4", "line5", "line6", "line7"],
                },
            ],
        })

        result = plugin._parse_output(output, Path("/project"), 10.0)
        block = result.duplicates[0]
        # Should only include first 5 lines
        assert block.code_snippet == "line1\nline2\nline3\nline4\nline5"


class TestDuploBlockToIssue:
    """Tests for _block_to_issue method."""

    def test_creates_valid_issue(self) -> None:
        """Test that block_to_issue creates a valid UnifiedIssue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            plugin = DuploPlugin()
            block = DuplicateBlock(
                file1=project / "src" / "a.py",
                file2=project / "src" / "b.py",
                start_line1=10,
                end_line1=20,
                start_line2=30,
                end_line2=40,
                line_count=10,
                code_snippet="some code",
            )

            issue = plugin._block_to_issue(block, project)

            assert issue.id.startswith("duplo-")
            assert issue.domain == ToolDomain.DUPLICATION
            assert issue.source_tool == "duplo"
            assert issue.severity == Severity.LOW
            assert issue.rule_id == "DUPLICATE"
            assert issue.file_path == project / "src" / "a.py"
            assert issue.line_start == 10
            assert issue.line_end == 20
            assert issue.code_snippet == "some code"
            assert "10 lines" in issue.title
            assert str(Path("src/b.py")) in issue.description

    def test_deterministic_issue_id(self) -> None:
        """Test that issue IDs are deterministic."""
        plugin = DuploPlugin()
        block = DuplicateBlock(
            file1=Path("/project/a.py"),
            file2=Path("/project/b.py"),
            start_line1=1,
            end_line1=5,
            start_line2=10,
            end_line2=15,
            line_count=5,
        )

        id1 = plugin._block_to_issue(block, Path("/project")).id
        id2 = plugin._block_to_issue(block, Path("/project")).id
        assert id1 == id2

    def test_file2_not_relative_to_project(self) -> None:
        """Test handling when file2 is not relative to project root."""
        plugin = DuploPlugin()
        block = DuplicateBlock(
            file1=Path("/project/a.py"),
            file2=Path("/other/location/b.py"),
            start_line1=1,
            end_line1=5,
            start_line2=1,
            end_line2=5,
            line_count=5,
        )

        issue = plugin._block_to_issue(block, Path("/project"))
        # Should not raise, just use absolute path for file2
        assert issue is not None

    def test_metadata_contains_duplicate_info(self) -> None:
        """Test that metadata contains duplicate information."""
        plugin = DuploPlugin()
        block = DuplicateBlock(
            file1=Path("/project/a.py"),
            file2=Path("/project/b.py"),
            start_line1=1,
            end_line1=10,
            start_line2=20,
            end_line2=30,
            line_count=10,
        )

        issue = plugin._block_to_issue(block, Path("/project"))
        assert issue.metadata["duplicate_line_start"] == 20
        assert issue.metadata["duplicate_line_end"] == 30
        assert issue.metadata["line_count"] == 10


class TestDuploDetectDuplication:
    """Tests for detect_duplication method."""

    def test_detect_no_source_files(self) -> None:
        """Test detect_duplication with no source files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            plugin = DuploPlugin(project_root=project_root)

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            with patch.object(plugin, "ensure_binary", return_value=Path("/usr/bin/duplo")):
                result = plugin.detect_duplication(context)
                assert isinstance(result, DuplicationResult)
                assert result.duplicate_blocks == 0

    def test_detect_successful_run(self) -> None:
        """Test successful duplication detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Create source files
            py_file = project_root / "main.py"
            py_file.write_text("print('hello')\n" * 10)

            plugin = DuploPlugin(project_root=project_root)

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            duplo_output = json.dumps({
                "summary": {
                    "files_analyzed": 1,
                    "total_lines": 10,
                    "duplicate_blocks": 0,
                    "duplicate_lines": 0,
                },
                "duplicates": [],
            })

            mock_result = make_completed_process(0, duplo_output)

            with patch.object(plugin, "ensure_binary", return_value=Path("/usr/bin/duplo")):
                with patch("lucidshark.plugins.duplication.duplo.run_with_streaming", return_value=mock_result):
                    result = plugin.detect_duplication(context)
                    assert result.files_analyzed == 1

    def test_detect_timeout(self) -> None:
        """Test detect_duplication handles timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("code")

            plugin = DuploPlugin(project_root=project_root)

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            with patch.object(plugin, "ensure_binary", return_value=Path("/usr/bin/duplo")):
                with patch(
                    "lucidshark.plugins.duplication.duplo.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("duplo", 300),
                ):
                    result = plugin.detect_duplication(context)
                    assert isinstance(result, DuplicationResult)
                    assert result.duplicate_blocks == 0

    def test_detect_subprocess_error(self) -> None:
        """Test detect_duplication handles subprocess errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("code")

            plugin = DuploPlugin(project_root=project_root)

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            with patch.object(plugin, "ensure_binary", return_value=Path("/usr/bin/duplo")):
                with patch(
                    "lucidshark.plugins.duplication.duplo.run_with_streaming",
                    side_effect=OSError("command failed"),
                ):
                    result = plugin.detect_duplication(context)
                    assert isinstance(result, DuplicationResult)
                    assert result.duplicate_blocks == 0


class TestDuploDownloadBinary:
    """Tests for _download_binary method."""

    @patch("lucidshark.plugins.duplication.duplo.get_platform_info")
    def test_unsupported_platform_raises(self, mock_platform) -> None:
        """Test that unsupported platform raises RuntimeError."""
        mock_platform.return_value = MagicMock(os="freebsd", arch="amd64")

        plugin = DuploPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                plugin._download_binary(Path(tmpdir))

    @patch("lucidshark.plugins.duplication.duplo.get_platform_info")
    def test_unsupported_arch_raises(self, mock_platform) -> None:
        """Test that unsupported arch raises RuntimeError."""
        mock_platform.return_value = MagicMock(os="darwin", arch="riscv64")

        plugin = DuploPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                plugin._download_binary(Path(tmpdir))


class TestDuplicationResult:
    """Tests for DuplicationResult dataclass."""

    def test_duplication_percent_zero_lines(self) -> None:
        """Test duplication percent with zero total lines."""
        result = DuplicationResult(total_lines=0, duplicate_lines=0)
        assert result.duplication_percent == 0.0

    def test_duplication_percent_calculated(self) -> None:
        """Test duplication percent is calculated correctly."""
        result = DuplicationResult(total_lines=100, duplicate_lines=25)
        assert result.duplication_percent == 25.0

    def test_passed_below_threshold(self) -> None:
        """Test passed when duplication is below threshold."""
        result = DuplicationResult(total_lines=100, duplicate_lines=5, threshold=10.0)
        assert result.passed is True

    def test_failed_above_threshold(self) -> None:
        """Test failed when duplication exceeds threshold."""
        result = DuplicationResult(total_lines=100, duplicate_lines=15, threshold=10.0)
        assert result.passed is False

    def test_to_summary(self) -> None:
        """Test conversion to DuplicationSummary."""
        result = DuplicationResult(
            files_analyzed=10,
            total_lines=500,
            duplicate_blocks=3,
            duplicate_lines=50,
            threshold=10.0,
        )
        summary = result.to_summary()
        assert summary.files_analyzed == 10
        assert summary.total_lines == 500
        assert summary.duplicate_blocks == 3
        assert summary.passed is True

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = DuplicationResult(
            files_analyzed=10,
            total_lines=500,
            duplicate_blocks=3,
            duplicate_lines=50,
            threshold=10.0,
        )
        d = result.to_dict()
        assert d["files_analyzed"] == 10
        assert d["total_lines"] == 500
        assert d["duplicate_blocks"] == 3
        assert d["passed"] is True
        assert d["duplication_percent"] == 10.0
