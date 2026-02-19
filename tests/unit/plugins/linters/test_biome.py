"""Unit tests for Biome linter plugin."""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.biome import (
    BiomeLinter,
    SEVERITY_MAP,
)

_BIOME_BINARY = "biome.exe" if platform.system() == "Windows" else "biome"


def make_completed_process(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestBiomeLinterProperties:
    """Tests for BiomeLinter basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        linter = BiomeLinter()
        assert linter.name == "biome"

    def test_languages(self) -> None:
        """Test supported languages."""
        linter = BiomeLinter()
        assert "javascript" in linter.languages
        assert "typescript" in linter.languages
        assert "json" in linter.languages

    def test_domain(self) -> None:
        """Test domain is LINTING."""
        linter = BiomeLinter()
        assert linter.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        """Test supports_fix returns True."""
        linter = BiomeLinter()
        assert linter.supports_fix is True

    def test_get_version(self) -> None:
        """Test get_version returns configured version."""
        linter = BiomeLinter(version="1.5.0")
        assert linter.get_version() == "1.5.0"

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = BiomeLinter(project_root=Path(tmpdir))
            assert linter._project_root == Path(tmpdir)

    def test_init_without_project_root(self) -> None:
        """Test initialization without project root."""
        linter = BiomeLinter()
        assert linter._project_root is None


class TestBiomeSeverityMapping:
    """Tests for Biome severity mapping."""

    def test_error_maps_to_high(self) -> None:
        """Test error maps to HIGH."""
        assert SEVERITY_MAP["error"] == Severity.HIGH

    def test_warning_maps_to_medium(self) -> None:
        """Test warning maps to MEDIUM."""
        assert SEVERITY_MAP["warning"] == Severity.MEDIUM

    def test_info_maps_to_low(self) -> None:
        """Test info maps to LOW."""
        assert SEVERITY_MAP["info"] == Severity.LOW


class TestBiomeResolveTargetPaths:
    """Tests for _resolve_target_paths method."""

    def test_uses_context_paths_when_provided(self) -> None:
        """Test using context paths."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_file = tmpdir_path / "app.js"
            src_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_file],
                enabled_domains=[],
            )

            paths = linter._resolve_target_paths(context)
            assert len(paths) == 1
            assert paths[0] == src_file.as_posix()

    def test_uses_src_dir_when_no_paths(self) -> None:
        """Test using src directory when no paths provided."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[],
                enabled_domains=[],
            )

            paths = linter._resolve_target_paths(context)
            assert len(paths) == 1
            assert paths[0] == src_dir.as_posix()

    def test_uses_dot_as_fallback(self) -> None:
        """Test using '.' when no paths and no src dir."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            paths = linter._resolve_target_paths(context)
            assert paths == ["."]


class TestBiomeEnsureBinary:
    """Tests for ensure_binary method."""

    def test_finds_node_modules_biome(self) -> None:
        """Test finding biome in project node_modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = BiomeLinter(project_root=Path(tmpdir))
            node_biome = Path(tmpdir) / "node_modules" / ".bin" / "biome"

            with patch("lucidshark.plugins.linters.biome.resolve_node_bin", return_value=node_biome):
                binary = linter.ensure_binary()
                assert binary == node_biome

    def test_finds_system_biome(self) -> None:
        """Test finding biome in system PATH."""
        linter = BiomeLinter()

        with patch("shutil.which", return_value="/usr/local/bin/biome"):
            binary = linter.ensure_binary()
            assert binary == Path("/usr/local/bin/biome")

    def test_downloads_when_not_found(self) -> None:
        """Test downloading biome when not found."""
        linter = BiomeLinter()

        with patch("shutil.which", return_value=None):
            with patch("lucidshark.plugins.linters.biome.resolve_node_bin", return_value=None):
                with patch.object(linter, "_paths") as mock_paths:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        bin_dir = Path(tmpdir) / "bin"
                        bin_dir.mkdir()
                        binary = bin_dir / _BIOME_BINARY
                        binary.touch()
                        mock_paths.plugin_bin_dir.return_value = bin_dir

                        result = linter.ensure_binary()
                        assert result == binary


class TestBiomeLint:
    """Tests for lint method."""

    def test_lint_success(self) -> None:
        """Test successful linting."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            biome_output = json.dumps({
                "diagnostics": [
                    {
                        "severity": "error",
                        "message": "Avoid using var",
                        "category": "lint/style/noVar",
                        "location": {
                            "path": {"file": "src/app.js"},
                            "lineStart": 5,
                            "lineEnd": 5,
                            "columnStart": 1,
                            "columnEnd": 10,
                        },
                        "fixable": True,
                    }
                ]
            })

            mock_result = make_completed_process(1, biome_output)

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/biome")):
                with patch("lucidshark.plugins.linters.biome.run_with_streaming", return_value=mock_result):
                    issues = linter.lint(context)

                    assert len(issues) == 1
                    assert issues[0].source_tool == "biome"
                    assert issues[0].domain == ToolDomain.LINTING
                    assert issues[0].severity == Severity.HIGH
                    assert issues[0].fixable is True

    def test_lint_timeout(self) -> None:
        """Test lint handles timeout."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/biome")):
                with patch(
                    "lucidshark.plugins.linters.biome.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("biome", 120),
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_subprocess_error(self) -> None:
        """Test lint handles subprocess errors."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/biome")):
                with patch(
                    "lucidshark.plugins.linters.biome.run_with_streaming",
                    side_effect=OSError("command failed"),
                ):
                    issues = linter.lint(context)
                    assert issues == []


class TestBiomeFix:
    """Tests for fix method."""

    def test_fix_success(self) -> None:
        """Test successful fix operation."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            # Pre-fix lint: 2 issues
            pre_output = json.dumps({
                "diagnostics": [
                    {"severity": "error", "message": "Issue 1", "category": "cat1",
                     "location": {"path": {"file": "a.js"}, "lineStart": 1}},
                    {"severity": "error", "message": "Issue 2", "category": "cat2",
                     "location": {"path": {"file": "a.js"}, "lineStart": 2}},
                ]
            })
            # Fix run: no output needed
            fix_result = make_completed_process(0, "")
            # Post-fix lint: 1 issue remaining
            post_output = json.dumps({
                "diagnostics": [
                    {"severity": "error", "message": "Issue 2", "category": "cat2",
                     "location": {"path": {"file": "a.js"}, "lineStart": 2}},
                ]
            })

            pre_result = make_completed_process(1, pre_output)
            post_result = make_completed_process(1, post_output)

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/biome")):
                with patch("lucidshark.plugins.linters.biome.run_with_streaming") as mock_run:
                    # lint(pre) -> fix -> lint(post)
                    mock_run.side_effect = [pre_result, fix_result, post_result]
                    result = linter.fix(context)
                    assert result.issues_fixed == 1
                    assert result.issues_remaining == 1

    def test_fix_timeout(self) -> None:
        """Test fix handles timeout during fix step."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            pre_output = json.dumps({
                "diagnostics": [
                    {"severity": "error", "message": "Issue", "category": "cat",
                     "location": {"path": {"file": "a.js"}, "lineStart": 1}},
                ]
            })
            pre_result = make_completed_process(1, pre_output)

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/biome")):
                with patch("lucidshark.plugins.linters.biome.run_with_streaming") as mock_run:
                    mock_run.side_effect = [
                        pre_result,  # lint (pre)
                        subprocess.TimeoutExpired("biome", 120),  # fix
                    ]
                    result = linter.fix(context)
                    assert result.issues_fixed == 0


class TestBiomeParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        linter = BiomeLinter()
        issues = linter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON."""
        linter = BiomeLinter()
        issues = linter._parse_output("not json", Path("/project"))
        assert issues == []

    def test_parse_no_diagnostics(self) -> None:
        """Test parsing output with no diagnostics."""
        linter = BiomeLinter()
        output = json.dumps({"diagnostics": []})
        issues = linter._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_multiple_diagnostics(self) -> None:
        """Test parsing output with multiple diagnostics."""
        linter = BiomeLinter()
        output = json.dumps({
            "diagnostics": [
                {"severity": "error", "message": "Error 1", "category": "cat1",
                 "location": {"path": {"file": "a.js"}, "lineStart": 1, "columnStart": 1}},
                {"severity": "warning", "message": "Warning 1", "category": "cat2",
                 "location": {"path": {"file": "b.js"}, "lineStart": 5, "columnStart": 3}},
            ]
        })

        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 2
        assert issues[0].severity == Severity.HIGH
        assert issues[1].severity == Severity.MEDIUM


class TestBiomeDiagnosticToIssue:
    """Tests for _diagnostic_to_issue method."""

    def test_converts_diagnostic_correctly(self) -> None:
        """Test basic diagnostic conversion."""
        linter = BiomeLinter()
        diagnostic = {
            "severity": "error",
            "message": "Avoid using var",
            "category": "lint/style/noVar",
            "location": {
                "path": {"file": "src/app.js"},
                "lineStart": 5,
                "lineEnd": 5,
                "columnStart": 1,
                "columnEnd": 10,
            },
            "fixable": True,
        }

        issue = linter._diagnostic_to_issue(diagnostic, Path("/project"))

        assert issue is not None
        assert issue.source_tool == "biome"
        assert issue.severity == Severity.HIGH
        assert issue.rule_id == "lint/style/noVar"
        assert issue.line_start == 5
        assert issue.line_end == 5
        assert issue.column_start == 1
        assert issue.column_end == 10
        assert issue.fixable is True
        assert issue.file_path == Path("/project/src/app.js")

    def test_diagnostic_with_structured_message(self) -> None:
        """Test diagnostic with structured message format (list)."""
        linter = BiomeLinter()
        diagnostic = {
            "severity": "warning",
            "message": [
                {"content": "Avoid "},
                {"content": "var"},
            ],
            "category": "style",
            "location": {
                "path": {"file": "file.js"},
                "lineStart": 1,
                "columnStart": 1,
            },
        }

        issue = linter._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert "Avoid" in issue.description
        assert "var" in issue.description

    def test_diagnostic_without_category(self) -> None:
        """Test diagnostic without category field."""
        linter = BiomeLinter()
        diagnostic = {
            "severity": "error",
            "message": "Parse error",
            "location": {
                "path": {"file": "file.js"},
                "lineStart": 1,
                "columnStart": 1,
            },
        }

        issue = linter._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert issue.rule_id == "unknown"
        assert issue.title == "Parse error"

    def test_diagnostic_without_file_path(self) -> None:
        """Test diagnostic without file path."""
        linter = BiomeLinter()
        diagnostic = {
            "severity": "error",
            "message": "msg",
            "category": "cat",
            "location": {
                "path": {},
                "lineStart": 1,
                "columnStart": 1,
            },
        }

        issue = linter._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("unknown")

    def test_diagnostic_with_absolute_path(self) -> None:
        """Test diagnostic with absolute file path."""
        linter = BiomeLinter()
        diagnostic = {
            "severity": "error",
            "message": "msg",
            "category": "cat",
            "location": {
                "path": {"file": "/abs/path/file.js"},
                "lineStart": 1,
                "columnStart": 1,
            },
        }

        issue = linter._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("/abs/path/file.js")

    def test_diagnostic_unknown_severity(self) -> None:
        """Test diagnostic with unknown severity defaults to MEDIUM."""
        linter = BiomeLinter()
        diagnostic = {
            "severity": "unknown",
            "message": "msg",
            "category": "cat",
            "location": {
                "path": {"file": "file.js"},
                "lineStart": 1,
                "columnStart": 1,
            },
        }

        issue = linter._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert issue.severity == Severity.MEDIUM


class TestBiomeIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        """Test same input produces same ID."""
        linter = BiomeLinter()
        id1 = linter._generate_issue_id("cat", "file.js", 1, 1, "msg")
        id2 = linter._generate_issue_id("cat", "file.js", 1, 1, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        """Test different inputs produce different IDs."""
        linter = BiomeLinter()
        id1 = linter._generate_issue_id("cat1", "file.js", 1, 1, "msg")
        id2 = linter._generate_issue_id("cat2", "file.js", 1, 1, "msg")
        assert id1 != id2

    def test_id_format_with_category(self) -> None:
        """Test ID format includes category."""
        linter = BiomeLinter()
        issue_id = linter._generate_issue_id("noVar", "f.js", 1, 1, "msg")
        assert issue_id.startswith("biome-noVar-")

    def test_id_format_without_category(self) -> None:
        """Test ID format without category."""
        linter = BiomeLinter()
        issue_id = linter._generate_issue_id("", "f.js", 1, 1, "msg")
        assert issue_id.startswith("biome-")
        assert "biome--" not in issue_id


class TestBiomeDownloadRelease:
    """Tests for _download_release method."""

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    def test_download_url_v2(self, mock_machine, mock_system) -> None:
        """Test download URL generation for Biome 2.x."""
        linter = BiomeLinter(version="2.0.0")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lucidshark.plugins.linters.biome.download_file") as mock_download:
                linter._download_release(Path(tmpdir))
                call_url = mock_download.call_args[0][0]
                assert "@biomejs/biome@2.0.0" in call_url
                assert "biome-darwin-arm64" in call_url

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="x86_64")
    def test_download_url_v1(self, mock_machine, mock_system) -> None:
        """Test download URL generation for Biome 1.x."""
        linter = BiomeLinter(version="1.5.0")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lucidshark.plugins.linters.biome.download_file") as mock_download:
                linter._download_release(Path(tmpdir))
                call_url = mock_download.call_args[0][0]
                assert "cli/v1.5.0" in call_url
                assert "biome-darwin-x64" in call_url


class TestBiomeExtractBinary:
    """Tests for _extract_binary method."""

    def test_rename_when_different_names(self) -> None:
        """Test binary is renamed when archive_path differs from target."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "biome-darwin-arm64"
            archive_path.touch()
            target_name = "biome"

            linter._extract_binary(archive_path, Path(tmpdir), target_name)
            assert (Path(tmpdir) / target_name).exists()

    def test_no_rename_when_same_name(self) -> None:
        """Test no action when archive_path equals target."""
        linter = BiomeLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "biome"
            binary_path.touch()

            # Should not raise
            linter._extract_binary(binary_path, Path(tmpdir), "biome")
            assert binary_path.exists()
