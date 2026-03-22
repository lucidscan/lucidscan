"""Unit tests for Checkstyle linter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.checkstyle import (
    DEFAULT_VERSION,
    SEVERITY_MAP,
    CheckstyleLinter,
)


def make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


SAMPLE_CHECKSTYLE_OUTPUT = """<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="13.3.0">
    <file name="/project/src/Main.java">
        <error line="5" column="1" severity="warning"
               message="Missing Javadoc comment."
               source="com.puppycrawl.tools.checkstyle.checks.javadoc.MissingJavadocMethodCheck"/>
    </file>
</checkstyle>"""


SAMPLE_CHECKSTYLE_MULTI_FILE = """<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="13.3.0">
    <file name="/project/src/A.java">
        <error line="1" severity="error" message="Tab character detected."
               source="com.puppycrawl.tools.checkstyle.checks.whitespace.FileTabCharacterCheck"/>
    </file>
    <file name="/project/src/B.java">
        <error line="10" column="5" severity="warning" message="Line too long."
               source="com.puppycrawl.tools.checkstyle.checks.sizes.LineLengthCheck"/>
        <error line="20" column="3" severity="info" message="Missing @param tag."
               source="com.puppycrawl.tools.checkstyle.checks.javadoc.JavadocMethodCheck"/>
    </file>
</checkstyle>"""


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
        linter = CheckstyleLinter(version="13.3.0")
        assert linter.get_version() == "13.3.0"

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(project_root=Path(tmpdir))
            assert linter._project_root == Path(tmpdir)

    def test_init_default_version(self) -> None:
        """Test default version is loaded from pyproject.toml."""
        linter = CheckstyleLinter()
        assert linter._version == DEFAULT_VERSION
        assert isinstance(linter._version, str)


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


class TestCheckstyleEnsureBinary:
    """Tests for ensure_binary method."""

    def test_cached_jar_found(self) -> None:
        """Test finds cached JAR."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="13.3.0", project_root=Path(tmpdir))

            # Create fake cached JAR
            jar_dir = Path(tmpdir) / ".lucidshark" / "bin" / "checkstyle" / "13.3.0"
            jar_dir.mkdir(parents=True)
            jar_path = jar_dir / "checkstyle-13.3.0-all.jar"
            jar_path.touch()

            result = linter.ensure_binary()
            assert result == jar_path

    def test_download_triggered_when_not_cached(self) -> None:
        """Test download is triggered when JAR not cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="13.3.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value="/usr/bin/java"):
                with patch.object(linter, "_download_binary") as mock_download:
                    # After download, create the JAR
                    def create_jar(dest_dir):
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        (dest_dir / "checkstyle-13.3.0-all.jar").touch()

                    mock_download.side_effect = create_jar

                    result = linter.ensure_binary()
                    mock_download.assert_called_once()
                    assert result.name == "checkstyle-13.3.0-all.jar"

    def test_java_not_found_raises(self) -> None:
        """Test raises FileNotFoundError when Java not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="13.3.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value=None):
                with pytest.raises(FileNotFoundError, match="Java is required"):
                    linter.ensure_binary()

    def test_download_fails_raises_runtime_error(self) -> None:
        """Test raises RuntimeError when download fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="13.3.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value="/usr/bin/java"):
                with patch.object(linter, "_download_binary"):
                    # Don't create the JAR  -  simulate failed download
                    with pytest.raises(RuntimeError, match="Failed to download"):
                        linter.ensure_binary()


class TestCheckstyleDownloadBinary:
    """Tests for _download_binary method."""

    def test_download_jar(self) -> None:
        """Test downloading JAR file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="13.3.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            # Create mock JAR content
            jar_content = b"PK\x03\x04fake jar content"

            mock_response = MagicMock()
            mock_response.read.return_value = jar_content
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.linters.checkstyle.secure_urlopen",
                return_value=mock_response,
            ):
                linter._download_binary(dest_dir)

            # Verify JAR was created
            jar_path = dest_dir / "checkstyle-13.3.0-all.jar"
            assert jar_path.exists()

    def test_download_cleans_up_temp_on_network_error(self) -> None:
        """Verify temp file is cleaned up when secure_urlopen raises."""
        from urllib.error import URLError

        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="13.3.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            with patch(
                "lucidshark.plugins.linters.checkstyle.secure_urlopen",
                side_effect=URLError("connection refused"),
            ):
                with pytest.raises(URLError):
                    linter._download_binary(dest_dir)

    def test_download_validates_url_domain(self) -> None:
        """Verify URL domain validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(version="13.3.0", project_root=Path(tmpdir))
            # URL validation happens in _download_binary - the URL is constructed
            # internally so this test just verifies the download attempt uses HTTPS
            dest_dir = Path(tmpdir) / "dest"

            mock_response = MagicMock()
            mock_response.read.return_value = b"content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.linters.checkstyle.secure_urlopen",
                return_value=mock_response,
            ) as mock_urlopen:
                linter._download_binary(dest_dir)

            # Verify called with HTTPS URL
            call_args = mock_urlopen.call_args[0][0]
            assert call_args.startswith("https://github.com/")


class TestCheckstyleFindConfigFile:
    """Tests for _find_config_file method."""

    def test_finds_checkstyle_xml(self) -> None:
        """Test finding checkstyle.xml in project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "checkstyle.xml"
            config_file.touch()

            linter = CheckstyleLinter(project_root=Path(tmpdir))
            result = linter._find_config_file(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_dot_checkstyle_xml(self) -> None:
        """Test finding .checkstyle.xml in project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / ".checkstyle.xml"
            config_file.touch()

            linter = CheckstyleLinter(project_root=Path(tmpdir))
            result = linter._find_config_file(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_config_subdirectory(self) -> None:
        """Test finding config/checkstyle/checkstyle.xml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config" / "checkstyle"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "checkstyle.xml"
            config_file.touch()

            linter = CheckstyleLinter(project_root=Path(tmpdir))
            result = linter._find_config_file(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_config_checkstyle_xml(self) -> None:
        """Test finding config/checkstyle.xml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "checkstyle.xml"
            config_file.touch()

            linter = CheckstyleLinter(project_root=Path(tmpdir))
            result = linter._find_config_file(Path(tmpdir))
            assert result == str(config_file)

    def test_defaults_to_bundled_config(self) -> None:
        """Test defaults to bundled google config when no custom config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(project_root=Path(tmpdir))
            result = linter._find_config_file(Path(tmpdir))
            # Should use bundled config cached to .lucidshark/config
            assert result.endswith("checkstyle-google.xml")
            assert "lucidshark" in result.lower()

    def test_priority_ordering_with_multiple_configs(self) -> None:
        """Verify checkstyle.xml takes priority over config/checkstyle.xml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "checkstyle.xml").touch()
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            (config_dir / "checkstyle.xml").touch()

            linter = CheckstyleLinter(project_root=Path(tmpdir))
            result = linter._find_config_file(Path(tmpdir))
            assert result == str(Path(tmpdir) / "checkstyle.xml")


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

    def test_ignore_patterns_excludes_matching_files(self) -> None:
        """Verify ignore_patterns filtering excludes matching files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.java").touch()
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            (build_dir / "Generated.java").touch()

            mock_patterns = MagicMock()
            mock_patterns.matches = MagicMock(
                side_effect=lambda f, root: "build" in str(f)
            )

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir, build_dir],
                enabled_domains=[],
                ignore_patterns=mock_patterns,
            )

            linter = CheckstyleLinter()
            files = linter._find_java_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.java")

    def test_ignore_patterns_none_includes_all(self) -> None:
        """Verify ignore_patterns=None includes all Java files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "A.java").touch()
            (src_dir / "B.java").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
                ignore_patterns=None,
            )

            linter = CheckstyleLinter()
            files = linter._find_java_files(context)
            assert len(files) == 2

    def test_fallback_to_project_root(self) -> None:
        """Verify fallback to project_root when no paths and no standard dirs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "Main.java").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            linter = CheckstyleLinter()
            files = linter._find_java_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.java")

    def test_excludes_non_java_files(self) -> None:
        """Verify non-.java files are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.java").touch()
            (src_dir / "Main.kt").touch()
            (src_dir / "Main.py").touch()
            (src_dir / "Main.class").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            linter = CheckstyleLinter()
            files = linter._find_java_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.java")


class TestCheckstyleLint:
    """Tests for lint method."""

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

            mock_result = make_completed_process(0, SAMPLE_CHECKSTYLE_OUTPUT)

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = linter.lint(context)

                    assert len(issues) == 1
                    assert issues[0].source_tool == "checkstyle"
                    assert issues[0].domain == ToolDomain.LINTING
                    assert issues[0].severity == Severity.MEDIUM
                    assert issues[0].line_start == 5

    def test_lint_uses_java_jar_command(self) -> None:
        """Verify command uses java -jar."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.java").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(
                0, '<?xml version="1.0"?><checkstyle/>'
            )
            captured_cmd = []

            def capture_cmd(**kwargs):
                captured_cmd.extend(kwargs.get("cmd", []))
                return mock_result

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                    side_effect=capture_cmd,
                ):
                    linter.lint(context)

            assert "java" in captured_cmd
            assert "-jar" in captured_cmd
            assert "/opt/checkstyle.jar" in captured_cmd

    def test_lint_passes_correct_kwargs_to_runner(self) -> None:
        """Verify correct cwd, tool_name, timeout passed to run_with_streaming."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.java").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(
                0, '<?xml version="1.0"?><checkstyle/>'
            )
            captured_kwargs = {}

            def capture_kwargs(**kwargs):
                captured_kwargs.update(kwargs)
                return mock_result

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                    side_effect=capture_kwargs,
                ):
                    linter.lint(context)

            assert captured_kwargs["cwd"] == tmpdir_path
            assert captured_kwargs["tool_name"] == "checkstyle"
            assert captured_kwargs["timeout"] == 120

    def test_lint_no_binary(self) -> None:
        """Test lint returns empty when binary not available."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(
                linter,
                "ensure_binary",
                side_effect=FileNotFoundError("Java not found"),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_runtime_error_from_ensure_binary(self) -> None:
        """Verify RuntimeError from ensure_binary is caught and returns []."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(
                linter,
                "ensure_binary",
                side_effect=RuntimeError("Failed to download Checkstyle"),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_no_files(self) -> None:
        """Test lint returns empty when no Java files found."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_timeout(self) -> None:
        """Test lint handles timeout."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.java").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
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
            (src_dir / "Main.java").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                    side_effect=OSError("command failed"),
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_nonzero_exit_code_with_valid_xml(self) -> None:
        """Verify issues are parsed even when Checkstyle returns non-zero exit code."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.java").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            # Checkstyle returns non-zero when violations are found
            mock_result = make_completed_process(1, SAMPLE_CHECKSTYLE_OUTPUT)

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = linter.lint(context)
                    assert len(issues) == 1
                    assert issues[0].rule_id == "MissingJavadocMethodCheck"

    def test_lint_temp_file_cleaned_up_on_success(self) -> None:
        """Verify temp file is deleted after successful lint."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.java").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(
                0, '<?xml version="1.0"?><checkstyle/>'
            )
            created_files = []
            original_named_temp = tempfile.NamedTemporaryFile

            def tracking_temp(*args, **kwargs):
                f = original_named_temp(*args, **kwargs)
                created_files.append(Path(f.name))
                return f

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                    return_value=mock_result,
                ):
                    with patch(
                        "lucidshark.plugins.linters.checkstyle.tempfile.NamedTemporaryFile",
                        side_effect=tracking_temp,
                    ):
                        linter.lint(context)

            for f in created_files:
                assert not f.exists(), f"Temp file {f} should be cleaned up"

    def test_lint_temp_file_cleaned_up_on_timeout(self) -> None:
        """Verify temp file is deleted when run_with_streaming times out."""
        linter = CheckstyleLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.java").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            created_files = []
            original_named_temp = tempfile.NamedTemporaryFile

            def tracking_temp(*args, **kwargs):
                f = original_named_temp(*args, **kwargs)
                created_files.append(Path(f.name))
                return f

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/checkstyle.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.checkstyle.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("java", 120),
                ):
                    with patch(
                        "lucidshark.plugins.linters.checkstyle.tempfile.NamedTemporaryFile",
                        side_effect=tracking_temp,
                    ):
                        issues = linter.lint(context)

            assert issues == []
            for f in created_files:
                assert not f.exists(), f"Temp file {f} should be cleaned up"


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
<checkstyle version="13.3.0">
    <file name="/project/Main.java">
    </file>
</checkstyle>"""
        issues = linter._parse_output(xml, Path("/project"))
        assert issues == []

    def test_parse_single_error(self) -> None:
        """Test parsing XML with single error."""
        linter = CheckstyleLinter()
        issues = linter._parse_output(SAMPLE_CHECKSTYLE_OUTPUT, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "MissingJavadocMethodCheck"
        assert issues[0].severity == Severity.MEDIUM
        assert issues[0].line_start == 5

    def test_parse_multiple_files_and_errors(self) -> None:
        """Test parsing XML with multiple files and errors."""
        linter = CheckstyleLinter()
        issues = linter._parse_output(SAMPLE_CHECKSTYLE_MULTI_FILE, Path("/project"))
        assert len(issues) == 3
        assert issues[0].severity == Severity.HIGH
        assert issues[1].severity == Severity.MEDIUM
        assert issues[2].severity == Severity.LOW

    def test_parse_whitespace_only_output(self) -> None:
        """Verify whitespace-only output returns empty list."""
        linter = CheckstyleLinter()
        issues = linter._parse_output("   \n\t  ", Path("/project"))
        assert issues == []


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

        issue = linter._error_to_issue(
            error_elem, "/project/Main.java", Path("/project")
        )

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

        issue = linter._error_to_issue(
            error_elem, "/abs/path/Main.java", Path("/project")
        )
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
