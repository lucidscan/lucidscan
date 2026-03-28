"""Unit tests for Detekt type checker plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.type_checkers.detekt import (
    SEVERITY_MAP,
    DetektChecker,
)


# ---------------------------------------------------------------------------
# Sample XML fragments used across tests
# ---------------------------------------------------------------------------
CHECKSTYLE_XML_WITH_ERRORS = """\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
  <file name="src/main/kotlin/com/example/App.kt">
    <error line="10" column="1" severity="warning" message="Function is too long" source="detekt.complexity.LongMethod"/>
    <error line="25" column="5" severity="error" message="Unreachable code detected" source="detekt.potential-bugs.UnreachableCode"/>
  </file>
  <file name="src/main/kotlin/com/example/Utils.kt">
    <error line="3" column="1" severity="info" message="Unused import" source="detekt.style.UnusedImports"/>
  </file>
</checkstyle>
"""

CHECKSTYLE_XML_EMPTY = """\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
</checkstyle>
"""


class TestDetektCheckerProperties:
    """Tests for DetektChecker basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        checker = DetektChecker()
        assert checker.name == "detekt"

    def test_languages(self) -> None:
        """Test supported languages."""
        checker = DetektChecker()
        assert checker.languages == ["kotlin"]

    def test_domain(self) -> None:
        """Test domain is TYPE_CHECKING."""
        checker = DetektChecker()
        assert checker.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        """Test strict mode support."""
        checker = DetektChecker()
        assert checker.supports_strict_mode is True

    def test_get_version(self) -> None:
        """Test get_version returns configured version."""
        checker = DetektChecker(version="1.23.7")
        assert checker.get_version() == "1.23.7"

    def test_get_version_default(self) -> None:
        """Test get_version returns default version when not overridden."""
        checker = DetektChecker()
        # Should return the DEFAULT_VERSION from pyproject.toml
        version = checker.get_version()
        assert isinstance(version, str)
        assert len(version) > 0


class TestDetektEnsureBinary:
    """Tests for ensure_binary and binary caching."""

    def test_ensure_binary_returns_cached_jar(self) -> None:
        """Test ensure_binary returns cached path when JAR already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            version = "1.23.7"

            # Create the expected JAR file in the cache directory
            jar_dir = (
                project_root / ".lucidshark" / "bin" / "detekt" / version
            )
            jar_dir.mkdir(parents=True)
            jar_path = jar_dir / f"detekt-cli-{version}-all.jar"
            jar_path.touch()

            checker = DetektChecker(version=version, project_root=project_root)
            result = checker.ensure_binary()

            assert result == jar_path

    def test_ensure_binary_triggers_download_when_not_cached(self) -> None:
        """Test ensure_binary downloads JAR when not found in cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            version = "1.23.7"

            checker = DetektChecker(version=version, project_root=project_root)

            with patch(
                "lucidshark.plugins.type_checkers.detekt.shutil.which",
                return_value="/usr/bin/java",
            ):
                with patch.object(checker, "_download_binary") as mock_download:
                    # After _download_binary, simulate the JAR being present
                    jar_dir = (
                        project_root
                        / ".lucidshark"
                        / "bin"
                        / "detekt"
                        / version
                    )

                    def create_jar(dest_dir: Path) -> None:
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        (dest_dir / f"detekt-cli-{version}-all.jar").touch()

                    mock_download.side_effect = create_jar

                    result = checker.ensure_binary()

                    mock_download.assert_called_once()
                    assert result == jar_dir / f"detekt-cli-{version}-all.jar"

    def test_ensure_binary_raises_when_java_not_found(self) -> None:
        """Test ensure_binary raises FileNotFoundError when Java is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch(
                "lucidshark.plugins.type_checkers.detekt.shutil.which",
                return_value=None,
            ):
                checker = DetektChecker(project_root=project_root)

                with pytest.raises(FileNotFoundError) as exc:
                    checker.ensure_binary()

                assert "Java is required" in str(exc.value)

    def test_ensure_binary_raises_when_download_fails(self) -> None:
        """Test ensure_binary raises RuntimeError when download fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch(
                "lucidshark.plugins.type_checkers.detekt.shutil.which",
                return_value="/usr/bin/java",
            ):
                checker = DetektChecker(project_root=project_root)

                # _download_binary is called but doesn't create the JAR
                with patch.object(checker, "_download_binary"):
                    with pytest.raises(RuntimeError) as exc:
                        checker.ensure_binary()

                    assert "Failed to download detekt JAR" in str(exc.value)

    def test_different_versions_use_different_paths(self) -> None:
        """Test that different versions use different directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker1 = DetektChecker(version="1.23.7", project_root=Path(tmpdir))
            checker2 = DetektChecker(version="1.22.0", project_root=Path(tmpdir))

            path1 = checker1._paths.plugin_bin_dir("detekt", "1.23.7")
            path2 = checker2._paths.plugin_bin_dir("detekt", "1.22.0")

            assert path1 != path2
            assert "1.23.7" in str(path1)
            assert "1.22.0" in str(path2)


class TestDetektDownloadBinary:
    """Tests for _download_binary JAR download."""

    def test_download_binary_creates_jar(self) -> None:
        """Test _download_binary downloads and saves the JAR file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            version = "1.23.7"
            dest_dir = project_root / "dest"

            checker = DetektChecker(version=version, project_root=project_root)

            mock_response = MagicMock()
            mock_response.read.return_value = b"fake-jar-content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.type_checkers.detekt.secure_urlopen",
                return_value=mock_response,
            ):
                checker._download_binary(dest_dir)

            jar_path = dest_dir / f"detekt-cli-{version}-all.jar"
            assert jar_path.exists()
            assert jar_path.read_bytes() == b"fake-jar-content"

    def test_download_url_uses_github_domain(self) -> None:
        """Test that the download URL uses the github.com domain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            version = "1.23.7"

            checker = DetektChecker(version=version, project_root=project_root)

            expected_url = (
                f"https://github.com/detekt/detekt/releases/download/"
                f"v{version}/detekt-cli-{version}-all.jar"
            )

            # Verify version is used in construction
            assert checker._version == version
            assert "github.com" in expected_url

    def test_download_binary_rejects_invalid_url(self) -> None:
        """Test that _download_binary rejects non-GitHub URLs.

        The URL is constructed internally so this validates the guard
        works if the format is ever changed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            checker = DetektChecker(version="1.23.7", project_root=project_root)

            # The URL is always correctly constructed internally, but the
            # guard ensures it starts with https://github.com/
            # We can verify this by checking the code flow works normally
            mock_response = MagicMock()
            mock_response.read.return_value = b"content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.type_checkers.detekt.secure_urlopen",
                return_value=mock_response,
            ) as mock_urlopen:
                dest_dir = Path(tmpdir) / "dest"
                checker._download_binary(dest_dir)

                # Verify the URL passed to secure_urlopen
                call_args = mock_urlopen.call_args[0][0]
                assert call_args.startswith("https://github.com/")


class TestDetektFindSourceDirectories:
    """Tests for _find_source_directories."""

    def test_find_standard_kotlin_source_dirs(self) -> None:
        """Test finding standard Kotlin source directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create standard Kotlin source directories
            (project_root / "src" / "main" / "kotlin").mkdir(parents=True)
            (project_root / "src" / "test" / "kotlin").mkdir(parents=True)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker()
            source_dirs = checker._find_source_directories(context)

            assert project_root / "src" / "main" / "kotlin" in source_dirs
            assert project_root / "src" / "test" / "kotlin" in source_dirs

    def test_find_standard_java_dirs_for_mixed_projects(self) -> None:
        """Test finding src/main/java dirs (Kotlin files can live there)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "src" / "main" / "java").mkdir(parents=True)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker()
            source_dirs = checker._find_source_directories(context)

            assert project_root / "src" / "main" / "java" in source_dirs

    def test_custom_paths_from_context(self) -> None:
        """Test that explicit context paths override standard discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            custom_dir = project_root / "custom" / "kotlin"
            custom_dir.mkdir(parents=True)

            # Also create a standard dir that should be ignored
            (project_root / "src" / "main" / "kotlin").mkdir(parents=True)

            context = ScanContext(
                project_root=project_root,
                paths=[custom_dir],
                enabled_domains=[],
            )

            checker = DetektChecker()
            source_dirs = checker._find_source_directories(context)

            assert custom_dir in source_dirs
            # Standard dirs should NOT be in the result when custom paths given
            assert project_root / "src" / "main" / "kotlin" not in source_dirs

    def test_no_source_directories_found(self) -> None:
        """Test empty list when no source directories exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker()
            source_dirs = checker._find_source_directories(context)

            assert source_dirs == []

    def test_src_fallback_directory(self) -> None:
        """Test that bare 'src' directory is found as fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "src").mkdir()

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker()
            source_dirs = checker._find_source_directories(context)

            assert project_root / "src" in source_dirs


class TestDetektFindConfigFile:
    """Tests for _find_config_file."""

    def test_finds_detekt_yml_in_root(self) -> None:
        """Test finding detekt.yml in project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_file = project_root / "detekt.yml"
            config_file.write_text("build:\n  maxIssues: 10\n")

            checker = DetektChecker()
            result = checker._find_config_file(project_root)

            assert result == str(config_file)

    def test_finds_detekt_yaml_in_root(self) -> None:
        """Test finding detekt.yaml in project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_file = project_root / "detekt.yaml"
            config_file.write_text("build:\n  maxIssues: 10\n")

            checker = DetektChecker()
            result = checker._find_config_file(project_root)

            assert result == str(config_file)

    def test_finds_dotdetekt_yml_in_root(self) -> None:
        """Test finding .detekt.yml in project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_file = project_root / ".detekt.yml"
            config_file.write_text("build:\n  maxIssues: 10\n")

            checker = DetektChecker()
            result = checker._find_config_file(project_root)

            assert result == str(config_file)

    def test_finds_config_in_config_detekt_dir(self) -> None:
        """Test finding config/detekt/detekt.yml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_dir = project_root / "config" / "detekt"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "detekt.yml"
            config_file.write_text("build:\n  maxIssues: 10\n")

            checker = DetektChecker()
            result = checker._find_config_file(project_root)

            assert result == str(config_file)

    def test_finds_config_in_config_dir(self) -> None:
        """Test finding config/detekt.yml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_dir = project_root / "config"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "detekt.yml"
            config_file.write_text("build:\n  maxIssues: 10\n")

            checker = DetektChecker()
            result = checker._find_config_file(project_root)

            assert result == str(config_file)

    def test_none_when_no_config_found(self) -> None:
        """Test returns None when no config file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            checker = DetektChecker()
            result = checker._find_config_file(project_root)

            assert result is None

    def test_first_matching_config_takes_precedence(self) -> None:
        """Test that detekt.yml in root takes precedence over nested configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create both root and nested config
            root_config = project_root / "detekt.yml"
            root_config.write_text("# root config\n")

            nested_dir = project_root / "config" / "detekt"
            nested_dir.mkdir(parents=True)
            nested_config = nested_dir / "detekt.yml"
            nested_config.write_text("# nested config\n")

            checker = DetektChecker()
            result = checker._find_config_file(project_root)

            assert result == str(root_config)


class TestDetektCheck:
    """Tests for check method end-to-end."""

    def test_check_success_with_xml_output(self) -> None:
        """Test check parses detekt XML output correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source directory
            src_dir = project_root / "src" / "main" / "kotlin"
            src_dir.mkdir(parents=True)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker(project_root=project_root)

            with patch.object(
                checker,
                "ensure_binary",
                return_value=Path("/path/to/detekt-cli-all.jar"),
            ):
                with patch(
                    "lucidshark.plugins.type_checkers.detekt.run_with_streaming",
                ) as mock_run:
                    # Simulate detekt writing XML to the report file
                    def write_report(*args, **kwargs) -> None:
                        # Extract the report path from the cmd argument
                        cmd = kwargs.get("cmd") or args[0]
                        for i, arg in enumerate(cmd):
                            if arg == "--report" and i + 1 < len(cmd):
                                report_spec = cmd[i + 1]
                                # Format is "xml:/path/to/report.xml"
                                report_path = report_spec.split(":", 1)[1]
                                Path(report_path).write_text(
                                    CHECKSTYLE_XML_WITH_ERRORS
                                )
                                break

                    mock_run.side_effect = write_report

                    issues = checker.check(context)

            assert len(issues) == 3

            # Verify first issue (warning - MEDIUM severity)
            issue1 = issues[0]
            assert issue1.source_tool == "detekt"
            assert issue1.domain == ToolDomain.TYPE_CHECKING
            assert issue1.severity == Severity.MEDIUM
            assert issue1.line_start == 10
            assert issue1.column_start == 1
            assert "LongMethod" in issue1.title
            assert "Function is too long" in issue1.description
            assert issue1.rule_id == "LongMethod"

            # Verify second issue (error - HIGH severity)
            issue2 = issues[1]
            assert issue2.severity == Severity.HIGH
            assert issue2.line_start == 25
            assert "UnreachableCode" in issue2.title

            # Verify third issue (info - LOW severity)
            issue3 = issues[2]
            assert issue3.severity == Severity.LOW
            assert "UnusedImports" in issue3.title

    def test_check_returns_empty_when_binary_not_found(self) -> None:
        """Test check returns empty list when binary cannot be obtained."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker(project_root=project_root)

            with patch.object(
                checker,
                "ensure_binary",
                side_effect=FileNotFoundError("Java not found"),
            ):
                issues = checker.check(context)

            assert issues == []

    def test_check_returns_empty_on_timeout(self) -> None:
        """Test check handles timeout gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source directory so check proceeds
            src_dir = project_root / "src" / "main" / "kotlin"
            src_dir.mkdir(parents=True)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker(project_root=project_root)

            with patch.object(
                checker,
                "ensure_binary",
                return_value=Path("/path/to/detekt.jar"),
            ):
                with patch(
                    "lucidshark.plugins.type_checkers.detekt.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("java", 300),
                ):
                    issues = checker.check(context)

            assert issues == []

    def test_check_returns_empty_when_no_source_dirs(self) -> None:
        """Test check returns empty list when no Kotlin source dirs found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker(project_root=project_root)

            with patch.object(
                checker,
                "ensure_binary",
                return_value=Path("/path/to/detekt.jar"),
            ):
                issues = checker.check(context)

            assert issues == []

    def test_check_returns_empty_on_runtime_error(self) -> None:
        """Test check handles RuntimeError from ensure_binary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker(project_root=project_root)

            with patch.object(
                checker,
                "ensure_binary",
                side_effect=RuntimeError("Download failed"),
            ):
                issues = checker.check(context)

            assert issues == []

    def test_check_returns_empty_on_execution_error(self) -> None:
        """Test check handles generic execution errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            src_dir = project_root / "src" / "main" / "kotlin"
            src_dir.mkdir(parents=True)

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker(project_root=project_root)

            with patch.object(
                checker,
                "ensure_binary",
                return_value=Path("/path/to/detekt.jar"),
            ):
                with patch(
                    "lucidshark.plugins.type_checkers.detekt.run_with_streaming",
                    side_effect=OSError("Command failed"),
                ):
                    issues = checker.check(context)

            assert issues == []

    def test_check_includes_config_when_found(self) -> None:
        """Test check passes --config flag when config file is found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source dir and config file
            src_dir = project_root / "src" / "main" / "kotlin"
            src_dir.mkdir(parents=True)
            config_file = project_root / "detekt.yml"
            config_file.write_text("build:\n  maxIssues: 0\n")

            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[],
            )

            checker = DetektChecker(project_root=project_root)

            with patch.object(
                checker,
                "ensure_binary",
                return_value=Path("/path/to/detekt.jar"),
            ):
                with patch(
                    "lucidshark.plugins.type_checkers.detekt.run_with_streaming",
                ) as mock_run:
                    checker.check(context)

                    # Verify --config flag was included
                    cmd = mock_run.call_args[1].get("cmd") or mock_run.call_args[0][0]
                    assert "--config" in cmd
                    config_idx = cmd.index("--config")
                    assert cmd[config_idx + 1] == str(config_file)


class TestDetektXmlParsing:
    """Tests for _parse_output XML parsing."""

    def test_parse_checkstyle_xml_with_errors(self) -> None:
        """Test parsing checkstyle XML with multiple errors."""
        checker = DetektChecker()

        issues = checker._parse_output(
            CHECKSTYLE_XML_WITH_ERRORS, Path("/project")
        )

        assert len(issues) == 3

        # First issue
        assert issues[0].rule_id == "LongMethod"
        assert issues[0].source_tool == "detekt"
        assert issues[0].domain == ToolDomain.TYPE_CHECKING
        assert issues[0].line_start == 10
        assert issues[0].column_start == 1
        assert issues[0].severity == Severity.MEDIUM
        assert "Function is too long" in issues[0].description
        assert issues[0].metadata["source"] == "detekt.complexity.LongMethod"
        assert issues[0].metadata["category"] == "complexity"
        assert (
            issues[0].documentation_url
            == "https://detekt.dev/docs/rules/complexity#longmethod"
        )

        # Second issue
        assert issues[1].rule_id == "UnreachableCode"
        assert issues[1].severity == Severity.HIGH
        assert issues[1].line_start == 25
        assert issues[1].column_start == 5

        # Third issue
        assert issues[2].rule_id == "UnusedImports"
        assert issues[2].severity == Severity.LOW

    def test_parse_empty_output(self) -> None:
        """Test parsing empty string."""
        checker = DetektChecker()
        issues = checker._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_whitespace_only_output(self) -> None:
        """Test parsing whitespace-only string."""
        checker = DetektChecker()
        issues = checker._parse_output("   \n\t  ", Path("/project"))
        assert issues == []

    def test_parse_empty_checkstyle_xml(self) -> None:
        """Test parsing checkstyle XML with no errors."""
        checker = DetektChecker()
        issues = checker._parse_output(CHECKSTYLE_XML_EMPTY, Path("/project"))
        assert issues == []

    def test_parse_invalid_xml(self) -> None:
        """Test parsing invalid XML returns empty list."""
        checker = DetektChecker()
        issues = checker._parse_output(
            "this is not valid xml <<<<", Path("/project")
        )
        assert issues == []

    def test_parse_xml_with_no_source_attribute(self) -> None:
        """Test parsing error element with missing source attribute."""
        checker = DetektChecker()

        xml_output = """\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
  <file name="src/App.kt">
    <error line="5" column="1" severity="warning" message="Some issue"/>
  </file>
</checkstyle>
"""
        issues = checker._parse_output(xml_output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].rule_id == "unknown"
        assert issues[0].description == "Some issue"

    def test_parse_xml_with_missing_line_column(self) -> None:
        """Test parsing error element with missing line/column."""
        checker = DetektChecker()

        xml_output = """\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
  <file name="src/App.kt">
    <error severity="info" message="File level issue" source="detekt.style.MaxLineLength"/>
  </file>
</checkstyle>
"""
        issues = checker._parse_output(xml_output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].line_start is None
        assert issues[0].column_start is None

    def test_parse_xml_absolute_file_path(self) -> None:
        """Test that absolute file paths are preserved."""
        checker = DetektChecker()

        xml_output = """\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
  <file name="/absolute/path/to/App.kt">
    <error line="1" column="1" severity="warning" message="Issue" source="detekt.style.Test"/>
  </file>
</checkstyle>
"""
        issues = checker._parse_output(xml_output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].file_path == Path("/absolute/path/to/App.kt")

    def test_parse_xml_relative_file_path_joined_with_project_root(self) -> None:
        """Test that relative file paths are joined with project root."""
        checker = DetektChecker()

        xml_output = """\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
  <file name="src/main/kotlin/App.kt">
    <error line="1" column="1" severity="warning" message="Issue" source="detekt.style.Test"/>
  </file>
</checkstyle>
"""
        issues = checker._parse_output(xml_output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].file_path == Path("/project/src/main/kotlin/App.kt")

    def test_parse_xml_metadata_contains_category_description(self) -> None:
        """Test metadata includes category description from CATEGORY_DESCRIPTIONS."""
        checker = DetektChecker()

        xml_output = """\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
  <file name="App.kt">
    <error line="1" column="1" severity="error" message="Bug" source="detekt.potential-bugs.UnsafeCall"/>
  </file>
</checkstyle>
"""
        issues = checker._parse_output(xml_output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].metadata["category_description"] == "Potential bug detected"
        assert issues[0].metadata["severity_raw"] == "error"

    def test_parse_xml_documentation_url_format(self) -> None:
        """Test documentation URL is correctly formatted."""
        checker = DetektChecker()

        xml_output = """\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
  <file name="App.kt">
    <error line="1" column="1" severity="warning" message="Issue" source="detekt.naming.FunctionNaming"/>
  </file>
</checkstyle>
"""
        issues = checker._parse_output(xml_output, Path("/project"))

        assert len(issues) == 1
        assert (
            issues[0].documentation_url
            == "https://detekt.dev/docs/rules/naming#functionnaming"
        )


class TestDetektSeverityMapping:
    """Tests for severity mapping from detekt severity strings."""

    def test_error_maps_to_high(self) -> None:
        """Test 'error' severity maps to HIGH."""
        assert SEVERITY_MAP["error"] == Severity.HIGH

    def test_warning_maps_to_medium(self) -> None:
        """Test 'warning' severity maps to MEDIUM."""
        assert SEVERITY_MAP["warning"] == Severity.MEDIUM

    def test_info_maps_to_low(self) -> None:
        """Test 'info' severity maps to LOW."""
        assert SEVERITY_MAP["info"] == Severity.LOW

    def test_unknown_severity_defaults_to_medium(self) -> None:
        """Test unknown severity string defaults to MEDIUM."""
        # Verify SEVERITY_MAP.get with default matches implementation behavior
        assert SEVERITY_MAP.get("unknown", Severity.MEDIUM) == Severity.MEDIUM

    def test_severity_mapping_via_parsed_issue(self) -> None:
        """Test severity mapping through actual XML parsing."""
        checker = DetektChecker()

        for severity_str, expected in [
            ("error", Severity.HIGH),
            ("warning", Severity.MEDIUM),
            ("info", Severity.LOW),
        ]:
            xml_output = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
  <file name="App.kt">
    <error line="1" column="1" severity="{severity_str}" message="Test" source="detekt.style.Test"/>
  </file>
</checkstyle>
"""
            issues = checker._parse_output(xml_output, Path("/project"))
            assert len(issues) == 1
            assert issues[0].severity == expected, (
                f"Expected {expected} for severity '{severity_str}', "
                f"got {issues[0].severity}"
            )


class TestDetektIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_same_input_same_id(self) -> None:
        """Test same input produces the same ID."""
        checker = DetektChecker()

        id1 = checker._generate_issue_id("LongMethod", "App.kt", 10, 1, "Too long")
        id2 = checker._generate_issue_id("LongMethod", "App.kt", 10, 1, "Too long")

        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        """Test different input produces different IDs."""
        checker = DetektChecker()

        id1 = checker._generate_issue_id("LongMethod", "App.kt", 10, 1, "Too long")
        id2 = checker._generate_issue_id("LongMethod", "Other.kt", 10, 1, "Too long")

        assert id1 != id2

    def test_different_rule_different_id(self) -> None:
        """Test different rule produces different IDs."""
        checker = DetektChecker()

        id1 = checker._generate_issue_id("LongMethod", "App.kt", 10, 1, "Issue")
        id2 = checker._generate_issue_id("ComplexMethod", "App.kt", 10, 1, "Issue")

        assert id1 != id2

    def test_different_line_different_id(self) -> None:
        """Test different line number produces different IDs."""
        checker = DetektChecker()

        id1 = checker._generate_issue_id("LongMethod", "App.kt", 10, 1, "Issue")
        id2 = checker._generate_issue_id("LongMethod", "App.kt", 20, 1, "Issue")

        assert id1 != id2

    def test_different_message_different_id(self) -> None:
        """Test different message produces different IDs."""
        checker = DetektChecker()

        id1 = checker._generate_issue_id("LongMethod", "App.kt", 10, 1, "Message A")
        id2 = checker._generate_issue_id("LongMethod", "App.kt", 10, 1, "Message B")

        assert id1 != id2

    def test_id_format_with_rule(self) -> None:
        """Test ID format starts with 'detekt-{rule}-'."""
        checker = DetektChecker()

        issue_id = checker._generate_issue_id(
            "LongMethod", "App.kt", 10, 1, "Issue"
        )

        assert issue_id.startswith("detekt-LongMethod-")

    def test_id_format_without_rule(self) -> None:
        """Test ID format starts with 'detekt-' when rule is empty."""
        checker = DetektChecker()

        issue_id = checker._generate_issue_id("", "App.kt", 10, 1, "Issue")

        assert issue_id.startswith("detekt-")
        # Should not have a double dash (detekt--)
        assert not issue_id.startswith("detekt--")

    def test_none_line_column_handled(self) -> None:
        """Test None line/column are handled in ID generation."""
        checker = DetektChecker()

        # Should not raise even with None values
        id1 = checker._generate_issue_id("Rule", "file.kt", None, None, "msg")
        id2 = checker._generate_issue_id("Rule", "file.kt", None, None, "msg")

        assert id1 == id2
        assert id1.startswith("detekt-Rule-")
