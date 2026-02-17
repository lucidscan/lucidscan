"""Unit tests for Checkstyle linter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.checkstyle import (
    CheckstyleLinter,
    SEVERITY_MAP,
)


def make_completed_process(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestCheckstyleLinterProperties:
    """Tests for CheckstyleLinter basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        linter = CheckstyleLinter()
        assert linter.name == "checkstyle"

    def test_languages(self) -> None:
        """Test supported languages."""
        linter = CheckstyleLinter()
        assert linter.languages == ["java"]

    def test_domain(self) -> None:
        """Test domain is LINTING."""
        linter = CheckstyleLinter()
        assert linter.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        """Test supports_fix returns False."""
        linter = CheckstyleLinter()
        assert linter.supports_fix is False

    def test_get_version(self) -> None:
        """Test get_version returns configured version."""
        linter = CheckstyleLinter(version="10.12.0")
        assert linter.get_version() == "10.12.0"

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(project_root=Path(tmpdir))
            assert linter._project_root == Path(tmpdir)


class TestCheckstyleSeverityMapping:
    """Tests for Checkstyle severity mapping."""

    def test_error_maps_to_high(self) -> None:
        """Test error maps to HIGH."""
        assert SEVERITY_MAP["error"] == Severity.HIGH

    def test_warning_maps_to_medium(self) -> None:
        """Test warning maps to MEDIUM."""
        assert SEVERITY_MAP["warning"] == Severity.MEDIUM

    def test_info_maps_to_low(self) -> None:
        """Test info maps to LOW."""
        assert SEVERITY_MAP["info"] == Severity.LOW

    def test_ignore_maps_to_info(self) -> None:
        """Test ignore maps to INFO."""
        assert SEVERITY_MAP["ignore"] == Severity.INFO


class TestCheckstyleJavaDetection:
    """Tests for Java detection."""

    @patch("shutil.which")
    def test_java_available(self, mock_which) -> None:
        """Test Java detection when available."""
        mock_which.return_value = "/usr/bin/java"
        linter = CheckstyleLinter()
        java_path = linter._check_java_available()
        assert java_path == Path("/usr/bin/java")

    @patch("shutil.which")
    def test_java_not_available(self, mock_which) -> None:
        """Test Java detection when not available."""
        mock_which.return_value = None
        linter = CheckstyleLinter()
        java_path = linter._check_java_available()
        assert java_path is None

    @patch("shutil.which")
    def test_ensure_binary_no_java_raises(self, mock_which) -> None:
        """Test ensure_binary raises when Java not available."""
        mock_which.return_value = None
        linter = CheckstyleLinter()

        with pytest.raises(FileNotFoundError, match="Java is not installed"):
            linter.ensure_binary()


class TestCheckstyleEnsureBinary:
    """Tests for ensure_binary method."""

    def test_returns_existing_jar(self) -> None:
        """Test returns existing JAR when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="10.12.0", project_root=Path(tmpdir))

            with patch.object(linter, "_check_java_available", return_value=Path("/usr/bin/java")):
                with patch.object(linter, "_paths") as mock_paths:
                    jar_dir = Path(tmpdir) / "jars"
                    jar_dir.mkdir()
                    jar_file = jar_dir / "checkstyle-10.12.0-all.jar"
                    jar_file.touch()
                    mock_paths.plugin_bin_dir.return_value = jar_dir

                    result = linter.ensure_binary()
                    assert result == jar_file

    def test_downloads_jar_when_missing(self) -> None:
        """Test downloads JAR when not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="10.12.0", project_root=Path(tmpdir))

            with patch.object(linter, "_check_java_available", return_value=Path("/usr/bin/java")):
                with patch.object(linter, "_paths") as mock_paths:
                    jar_dir = Path(tmpdir) / "jars"
                    jar_dir.mkdir()
                    mock_paths.plugin_bin_dir.return_value = jar_dir

                    with patch.object(linter, "_download_jar") as mock_download:
                        # Simulate download creating the file
                        def create_jar(path):
                            path.touch()

                        mock_download.side_effect = create_jar

                        linter.ensure_binary()
                        mock_download.assert_called_once()


class TestCheckstyleFindConfigFile:
    """Tests for _find_config_file method."""

    def test_finds_checkstyle_xml(self) -> None:
        """Test finding checkstyle.xml in project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "checkstyle.xml"
            config_file.touch()

            linter = CheckstyleLinter()
            result = linter._find_config_file(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_dot_checkstyle_xml(self) -> None:
        """Test finding .checkstyle.xml in project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".checkstyle.xml"
            config_file.touch()

            linter = CheckstyleLinter()
            result = linter._find_config_file(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_config_subdirectory(self) -> None:
        """Test finding config/checkstyle/checkstyle.xml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config" / "checkstyle"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "checkstyle.xml"
            config_file.touch()

            linter = CheckstyleLinter()
            result = linter._find_config_file(Path(tmpdir))
            assert result == str(config_file)

    def test_defaults_to_google_checks(self) -> None:
        """Test defaults to Google checks when no config found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter()
            result = linter._find_config_file(Path(tmpdir))
            assert result == "/google_checks.xml"


class TestCheckstyleFindJavaFiles:
    """Tests for _find_java_files method."""

    def test_finds_java_files_in_paths(self) -> None:
        """Test finding Java files in context paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            java_file = src_dir / "Main.java"
            java_file.touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            linter = CheckstyleLinter()
            files = linter._find_java_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.java")

    def test_finds_java_files_in_standard_dirs(self) -> None:
        """Test finding Java files in standard directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src" / "main" / "java"
            src_dir.mkdir(parents=True)
            java_file = src_dir / "App.java"
            java_file.touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            linter = CheckstyleLinter()
            files = linter._find_java_files(context)
            assert len(files) >= 1
            assert any("App.java" in f for f in files)

    def test_no_java_files(self) -> None:
        """Test returns empty when no Java files found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            linter = CheckstyleLinter()
            files = linter._find_java_files(context)
            assert files == []

    def test_skips_nonexistent_directories(self) -> None:
        """Test skips nonexistent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "nonexistent"

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[nonexistent],
                enabled_domains=[],
            )

            linter = CheckstyleLinter()
            files = linter._find_java_files(context)
            assert files == []


class TestCheckstyleLint:
    """Tests for lint method."""

    def test_lint_no_java(self) -> None:
        """Test lint returns empty when Java not available."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", side_effect=FileNotFoundError("no java")):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_no_java_runtime(self) -> None:
        """Test lint returns empty when Java runtime disappears after binary check."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/path/to/jar")):
                with patch.object(linter, "_check_java_available", return_value=None):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_no_java_files(self) -> None:
        """Test lint returns empty when no Java files found."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/path/to/jar")):
                with patch.object(linter, "_check_java_available", return_value=Path("/usr/bin/java")):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_success(self) -> None:
        """Test successful linting with XML output."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            java_file = src_dir / "Main.java"
            java_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            xml_output = """<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="10.12.0">
    <file name="/project/src/Main.java">
        <error line="5" column="1" severity="warning"
               message="Missing Javadoc comment."
               source="com.puppycrawl.tools.checkstyle.checks.javadoc.MissingJavadocMethodCheck"/>
    </file>
</checkstyle>"""

            mock_result = make_completed_process(0, xml_output)

            with patch.object(linter, "ensure_binary", return_value=Path("/path/to/jar")):
                with patch.object(linter, "_check_java_available", return_value=Path("/usr/bin/java")):
                    with patch("lucidshark.plugins.linters.checkstyle.run_with_streaming", return_value=mock_result):
                        issues = linter.lint(context)

                        assert len(issues) == 1
                        assert issues[0].source_tool == "checkstyle"
                        assert issues[0].domain == ToolDomain.LINTING
                        assert issues[0].severity == Severity.MEDIUM
                        assert issues[0].line_start == 5

    def test_lint_timeout(self) -> None:
        """Test lint handles timeout."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            java_file = src_dir / "Main.java"
            java_file.touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/path/to/jar")):
                with patch.object(linter, "_check_java_available", return_value=Path("/usr/bin/java")):
                    with patch(
                        "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                        side_effect=subprocess.TimeoutExpired("java", 120),
                    ):
                        issues = linter.lint(context)
                        assert issues == []

    def test_lint_subprocess_error(self) -> None:
        """Test lint handles subprocess errors."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            java_file = src_dir / "Main.java"
            java_file.touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/path/to/jar")):
                with patch.object(linter, "_check_java_available", return_value=Path("/usr/bin/java")):
                    with patch(
                        "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                        side_effect=OSError("command failed"),
                    ):
                        issues = linter.lint(context)
                        assert issues == []


class TestCheckstyleParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        linter = CheckstyleLinter()
        issues = linter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_invalid_xml(self) -> None:
        """Test parsing invalid XML."""
        linter = CheckstyleLinter()
        issues = linter._parse_output("not xml at all", Path("/project"))
        assert issues == []

    def test_parse_no_errors(self) -> None:
        """Test parsing XML with no errors."""
        linter = CheckstyleLinter()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="10.12.0">
    <file name="/project/Main.java">
    </file>
</checkstyle>"""
        issues = linter._parse_output(xml, Path("/project"))
        assert issues == []

    def test_parse_multiple_files(self) -> None:
        """Test parsing XML with multiple files and errors."""
        linter = CheckstyleLinter()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="10.12.0">
    <file name="/project/A.java">
        <error line="1" severity="error" message="Error 1"
               source="com.example.Check1"/>
    </file>
    <file name="/project/B.java">
        <error line="10" severity="warning" message="Warning 1"
               source="com.example.Check2"/>
        <error line="20" severity="info" message="Info 1"
               source="com.example.Check3"/>
    </file>
</checkstyle>"""

        issues = linter._parse_output(xml, Path("/project"))
        assert len(issues) == 3
        assert issues[0].severity == Severity.HIGH
        assert issues[1].severity == Severity.MEDIUM
        assert issues[2].severity == Severity.LOW


class TestCheckstyleErrorToIssue:
    """Tests for _error_to_issue method."""

    def test_converts_error_correctly(self) -> None:
        """Test basic error conversion."""
        import xml.etree.ElementTree as ET

        linter = CheckstyleLinter()
        error_elem = ET.fromstring(
            '<error line="15" column="3" severity="warning" '
            'message="Missing Javadoc." '
            'source="com.puppycrawl.tools.checkstyle.checks.javadoc.MissingJavadocMethodCheck"/>'
        )

        issue = linter._error_to_issue(error_elem, "/project/Main.java", Path("/project"))

        assert issue is not None
        assert issue.source_tool == "checkstyle"
        assert issue.severity == Severity.MEDIUM
        assert issue.rule_id == "MissingJavadocMethodCheck"
        assert issue.line_start == 15
        assert issue.column_start == 3
        assert "Missing Javadoc." in issue.title

    def test_error_without_column(self) -> None:
        """Test error without column attribute."""
        import xml.etree.ElementTree as ET

        linter = CheckstyleLinter()
        error_elem = ET.fromstring(
            '<error line="5" severity="error" message="Tab character." '
            'source="com.puppycrawl.tools.checkstyle.checks.whitespace.FileTabCharacterCheck"/>'
        )

        issue = linter._error_to_issue(error_elem, "Main.java", Path("/project"))
        assert issue is not None
        assert issue.column_start is None

    def test_error_without_source(self) -> None:
        """Test error without source attribute."""
        import xml.etree.ElementTree as ET

        linter = CheckstyleLinter()
        error_elem = ET.fromstring(
            '<error line="1" severity="error" message="Parse error."/>'
        )

        issue = linter._error_to_issue(error_elem, "Main.java", Path("/project"))
        assert issue is not None
        assert issue.rule_id == "unknown"

    def test_error_with_relative_path(self) -> None:
        """Test error with relative file path."""
        import xml.etree.ElementTree as ET

        linter = CheckstyleLinter()
        error_elem = ET.fromstring(
            '<error line="1" severity="error" message="Error" source="com.Check"/>'
        )

        issue = linter._error_to_issue(error_elem, "src/Main.java", Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("/project/src/Main.java")

    def test_error_with_absolute_path(self) -> None:
        """Test error with absolute file path."""
        import xml.etree.ElementTree as ET

        linter = CheckstyleLinter()
        error_elem = ET.fromstring(
            '<error line="1" severity="error" message="Error" source="com.Check"/>'
        )

        issue = linter._error_to_issue(error_elem, "/abs/path/Main.java", Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("/abs/path/Main.java")

    def test_error_unknown_severity(self) -> None:
        """Test error with unknown severity defaults to MEDIUM."""
        import xml.etree.ElementTree as ET

        linter = CheckstyleLinter()
        error_elem = ET.fromstring(
            '<error line="1" severity="unknown" message="msg" source="com.Check"/>'
        )

        issue = linter._error_to_issue(error_elem, "file.java", Path("/project"))
        assert issue is not None
        assert issue.severity == Severity.MEDIUM


class TestCheckstyleIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        """Test same input produces same ID."""
        linter = CheckstyleLinter()
        id1 = linter._generate_issue_id("Check", "file.java", 10, 5, "msg")
        id2 = linter._generate_issue_id("Check", "file.java", 10, 5, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        """Test different inputs produce different IDs."""
        linter = CheckstyleLinter()
        id1 = linter._generate_issue_id("Check1", "file.java", 10, 5, "msg")
        id2 = linter._generate_issue_id("Check2", "file.java", 10, 5, "msg")
        assert id1 != id2

    def test_id_format_with_rule(self) -> None:
        """Test ID format includes rule."""
        linter = CheckstyleLinter()
        issue_id = linter._generate_issue_id("MissingJavadoc", "f.java", 1, 1, "msg")
        assert issue_id.startswith("checkstyle-MissingJavadoc-")

    def test_id_format_without_rule(self) -> None:
        """Test ID format without rule."""
        linter = CheckstyleLinter()
        issue_id = linter._generate_issue_id("", "f.java", 1, 1, "msg")
        assert issue_id.startswith("checkstyle-")
        assert "checkstyle--" not in issue_id

    def test_id_handles_none_values(self) -> None:
        """Test ID handles None line/column."""
        linter = CheckstyleLinter()
        issue_id = linter._generate_issue_id("Rule", "file.java", None, None, "msg")
        assert issue_id.startswith("checkstyle-Rule-")


class TestCheckstyleDownloadJar:
    """Tests for _download_jar method."""

    def test_download_url_format(self) -> None:
        """Test the download URL is correctly formed."""
        linter = CheckstyleLinter(version="10.12.0")

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "checkstyle.jar"

            with patch("lucidshark.plugins.linters.checkstyle.download_file") as mock_download:
                linter._download_jar(target_path)
                call_url = mock_download.call_args[0][0]
                assert "checkstyle-10.12.0" in call_url
                assert call_url.startswith("https://github.com/")

    def test_download_failure_raises(self) -> None:
        """Test download failure raises RuntimeError."""
        linter = CheckstyleLinter(version="10.12.0")

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "checkstyle.jar"

            with patch("lucidshark.plugins.linters.checkstyle.download_file", side_effect=Exception("network error")):
                with pytest.raises(RuntimeError, match="Failed to download Checkstyle"):
                    linter._download_jar(target_path)
