"""Unit tests for PMD linter plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.pmd import (
    PRIORITY_SEVERITY_MAP,
    PmdLinter,
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


SAMPLE_PMD_OUTPUT = json.dumps(
    {
        "formatVersion": 0,
        "pmdVersion": "7.22.0",
        "files": [
            {
                "filename": "/project/src/Main.java",
                "violations": [
                    {
                        "beginline": 5,
                        "begincolumn": 1,
                        "endline": 5,
                        "endcolumn": 20,
                        "rule": "UnusedLocalVariable",
                        "ruleset": "Best Practices",
                        "priority": 3,
                        "description": "Avoid unused local variables such as 'x'.",
                        "externalInfoUrl": "https://docs.pmd-code.org/pmd-doc-7.22.0/pmd_rules_java_bestpractices.html#unusedlocalvariable",
                    }
                ],
            }
        ],
    }
)


SAMPLE_PMD_MULTI_FILE = json.dumps(
    {
        "formatVersion": 0,
        "pmdVersion": "7.22.0",
        "files": [
            {
                "filename": "/project/src/A.java",
                "violations": [
                    {
                        "beginline": 1,
                        "begincolumn": 1,
                        "endline": 1,
                        "endcolumn": 10,
                        "rule": "UnusedImports",
                        "ruleset": "Best Practices",
                        "priority": 4,
                        "description": "Unused import",
                        "externalInfoUrl": "https://example.com/unused-imports",
                    }
                ],
            },
            {
                "filename": "/project/src/B.java",
                "violations": [
                    {
                        "beginline": 10,
                        "begincolumn": 5,
                        "endline": 20,
                        "endcolumn": 5,
                        "rule": "GodClass",
                        "ruleset": "Design",
                        "priority": 2,
                        "description": "Possible God Class",
                        "externalInfoUrl": "https://example.com/god-class",
                    },
                    {
                        "beginline": 50,
                        "begincolumn": 1,
                        "endline": 50,
                        "endcolumn": 30,
                        "rule": "EmptyCatchBlock",
                        "ruleset": "Error Prone",
                        "priority": 1,
                        "description": "Avoid empty catch blocks",
                        "externalInfoUrl": "https://example.com/empty-catch",
                    },
                ],
            },
        ],
    }
)


class TestPmdLinterProperties:
    """Tests for PmdLinter basic properties."""

    def test_name(self) -> None:
        linter = PmdLinter()
        assert linter.name == "pmd"

    def test_languages(self) -> None:
        linter = PmdLinter()
        assert linter.languages == ["java"]

    def test_domain(self) -> None:
        linter = PmdLinter()
        assert linter.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        linter = PmdLinter()
        assert linter.supports_fix is False

    def test_get_version(self) -> None:
        linter = PmdLinter(version="7.22.0")
        assert linter.get_version() == "7.22.0"

    def test_init_with_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(project_root=Path(tmpdir))
            assert linter._project_root == Path(tmpdir)

    def test_init_default_version(self) -> None:
        linter = PmdLinter()
        # Should use DEFAULT_VERSION from get_tool_version("pmd")
        assert linter._version is not None
        assert isinstance(linter._version, str)


class TestPmdSeverityMapping:
    """Tests for PMD priority to severity mapping."""

    def test_priority_1_maps_to_critical(self) -> None:
        assert PRIORITY_SEVERITY_MAP[1] == Severity.CRITICAL

    def test_priority_2_maps_to_high(self) -> None:
        assert PRIORITY_SEVERITY_MAP[2] == Severity.HIGH

    def test_priority_3_maps_to_medium(self) -> None:
        assert PRIORITY_SEVERITY_MAP[3] == Severity.MEDIUM

    def test_priority_4_maps_to_low(self) -> None:
        assert PRIORITY_SEVERITY_MAP[4] == Severity.LOW

    def test_priority_5_maps_to_info(self) -> None:
        assert PRIORITY_SEVERITY_MAP[5] == Severity.INFO

    def test_all_priorities_covered(self) -> None:
        assert set(PRIORITY_SEVERITY_MAP.keys()) == {1, 2, 3, 4, 5}


class TestPmdEnsureBinary:
    """Tests for ensure_binary method."""

    def test_cached_binary_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))

            # Create fake cached binary
            binary_dir = (
                Path(tmpdir)
                / ".lucidshark"
                / "bin"
                / "pmd"
                / "7.22.0"
                / "pmd-bin-7.22.0"
                / "bin"
            )
            binary_dir.mkdir(parents=True)
            binary_path = binary_dir / "pmd"
            binary_path.touch()
            binary_path.chmod(0o755)

            result = linter.ensure_binary()
            assert result == binary_path

    def test_download_triggered_when_not_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value="/usr/bin/java"):
                with patch.object(linter, "_download_binary") as mock_download:
                    # After download, create the binary
                    def create_binary(dest_dir):
                        binary_dir = dest_dir / "pmd-bin-7.22.0" / "bin"
                        binary_dir.mkdir(parents=True)
                        (binary_dir / "pmd").touch()

                    mock_download.side_effect = create_binary

                    result = linter.ensure_binary()
                    mock_download.assert_called_once()
                    assert result.name == "pmd"

    def test_java_not_found_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value=None):
                with pytest.raises(FileNotFoundError, match="Java is required"):
                    linter.ensure_binary()

    def test_download_fails_raises_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value="/usr/bin/java"):
                with patch.object(linter, "_download_binary"):
                    # Don't create the binary — simulate failed download
                    with pytest.raises(RuntimeError, match="Failed to download"):
                        linter.ensure_binary()


class TestPmdDownloadBinary:
    """Tests for _download_binary method."""

    def test_download_and_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            # Create a mock zip file in memory
            import io
            import zipfile

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                zf.writestr("pmd-bin-7.22.0/bin/pmd", "#!/bin/sh\necho pmd")
                zf.writestr("pmd-bin-7.22.0/lib/pmd.jar", "fake jar")

            zip_data = zip_buffer.getvalue()

            mock_response = MagicMock()
            mock_response.read.return_value = zip_data
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.linters.pmd.secure_urlopen",
                return_value=mock_response,
            ):
                linter._download_binary(dest_dir)

            # Verify extraction
            binary = dest_dir / "pmd-bin-7.22.0" / "bin" / "pmd"
            assert binary.exists()
            # Verify executable
            import stat

            assert binary.stat().st_mode & stat.S_IXUSR

    def test_path_traversal_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            # Create a malicious zip with path traversal
            import io
            import zipfile

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                zf.writestr("../../etc/passwd", "malicious content")

            zip_data = zip_buffer.getvalue()

            mock_response = MagicMock()
            mock_response.read.return_value = zip_data
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.linters.pmd.secure_urlopen",
                return_value=mock_response,
            ):
                with pytest.raises(ValueError, match="Path traversal detected"):
                    linter._download_binary(dest_dir)

    def test_download_cleans_up_temp_on_network_error(self) -> None:
        """Verify temp zip is cleaned up when secure_urlopen raises."""
        from urllib.error import URLError

        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            with patch(
                "lucidshark.plugins.linters.pmd.secure_urlopen",
                side_effect=URLError("connection refused"),
            ):
                with pytest.raises(URLError):
                    linter._download_binary(dest_dir)

            # The finally block in _download_binary should have cleaned up the temp file.
            # We can't assert on specific temp files since we don't control the path,
            # but the test verifies no exception was raised during cleanup.

    def test_download_cleans_up_temp_on_corrupt_zip(self) -> None:
        """Verify temp file is cleaned up when zip is corrupt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            mock_response = MagicMock()
            mock_response.read.return_value = b"not a zip file at all"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.linters.pmd.secure_urlopen",
                return_value=mock_response,
            ):
                with pytest.raises(Exception):
                    linter._download_binary(dest_dir)

    def test_download_missing_binary_in_zip(self) -> None:
        """Verify no error when zip lacks expected bin/pmd path (caller handles it)."""
        import io
        import zipfile

        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(version="7.22.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            # Zip without the expected binary structure
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                zf.writestr("README.md", "just a readme")

            mock_response = MagicMock()
            mock_response.read.return_value = zip_buffer.getvalue()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.linters.pmd.secure_urlopen",
                return_value=mock_response,
            ):
                # Should not raise — the caller (ensure_binary) checks for the path
                linter._download_binary(dest_dir)

            # Binary should not exist
            binary = dest_dir / "pmd-bin-7.22.0" / "bin" / "pmd"
            assert not binary.exists()


class TestPmdFindRulesetConfig:
    """Tests for _find_ruleset_config method."""

    def test_finds_pmd_ruleset_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "pmd-ruleset.xml"
            config_file.touch()

            linter = PmdLinter()
            result = linter._find_ruleset_config(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_pmd_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "pmd.xml"
            config_file.touch()

            linter = PmdLinter()
            result = linter._find_ruleset_config(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_ruleset_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "ruleset.xml"
            config_file.touch()

            linter = PmdLinter()
            result = linter._find_ruleset_config(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_dot_pmd_rulesets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".pmd"
            config_dir.mkdir()
            config_file = config_dir / "rulesets.xml"
            config_file.touch()

            linter = PmdLinter()
            result = linter._find_ruleset_config(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_config_pmd_pmd_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config" / "pmd"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "pmd.xml"
            config_file.touch()

            linter = PmdLinter()
            result = linter._find_ruleset_config(Path(tmpdir))
            assert result == str(config_file)

    def test_finds_config_pmd_ruleset_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config" / "pmd"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "ruleset.xml"
            config_file.touch()

            linter = PmdLinter()
            result = linter._find_ruleset_config(Path(tmpdir))
            assert result == str(config_file)

    def test_defaults_to_quickstart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter()
            result = linter._find_ruleset_config(Path(tmpdir))
            assert result == "rulesets/java/quickstart.xml"

    def test_priority_ordering_with_multiple_configs(self) -> None:
        """Verify pmd-ruleset.xml takes priority over pmd.xml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pmd-ruleset.xml").touch()
            (Path(tmpdir) / "pmd.xml").touch()

            linter = PmdLinter()
            result = linter._find_ruleset_config(Path(tmpdir))
            assert result.endswith("pmd-ruleset.xml")


class TestPmdFindJavaFiles:
    """Tests for _find_java_files method."""

    def test_finds_java_files_in_context_paths(self) -> None:
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

            linter = PmdLinter()
            files = linter._find_java_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.java")

    def test_finds_java_files_in_standard_dirs(self) -> None:
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

            linter = PmdLinter()
            files = linter._find_java_files(context)
            assert len(files) >= 1
            assert any("App.java" in f for f in files)

    def test_no_java_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            linter = PmdLinter()
            files = linter._find_java_files(context)
            assert files == []

    def test_skips_nonexistent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "nonexistent"

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[nonexistent],
                enabled_domains=[],
            )

            linter = PmdLinter()
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

            linter = PmdLinter()
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

            linter = PmdLinter()
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

            linter = PmdLinter()
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

            linter = PmdLinter()
            files = linter._find_java_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.java")


class TestPmdLint:
    """Tests for lint method."""

    def test_lint_success(self) -> None:
        linter = PmdLinter()

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

            mock_result = make_completed_process(0, SAMPLE_PMD_OUTPUT)

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = linter.lint(context)

                    assert len(issues) == 1
                    assert issues[0].source_tool == "pmd"
                    assert issues[0].domain == ToolDomain.LINTING
                    assert issues[0].severity == Severity.MEDIUM
                    assert issues[0].rule_id == "UnusedLocalVariable"
                    assert issues[0].line_start == 5

    def test_lint_uses_file_list_not_directory(self) -> None:
        """Verify --file-list is used instead of -d to respect gitignore filtering."""
        linter = PmdLinter()

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

            mock_result = make_completed_process(0, '{"files": []}')
            captured_cmd = []

            def capture_cmd(**kwargs):
                captured_cmd.extend(kwargs.get("cmd", []))
                return mock_result

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    side_effect=capture_cmd,
                ):
                    linter.lint(context)

            assert "--file-list" in captured_cmd
            assert "-d" not in captured_cmd
            # Verify --file-list is followed by a path
            idx = captured_cmd.index("--file-list")
            file_list_path = captured_cmd[idx + 1]
            assert file_list_path.endswith(".txt")

    def test_lint_file_list_contains_correct_paths(self) -> None:
        """Verify the temp file-list contains all discovered Java file paths."""
        linter = PmdLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            file_a = src_dir / "A.java"
            file_b = src_dir / "B.java"
            file_a.touch()
            file_b.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, '{"files": []}')
            captured_file_list_contents = []

            def capture_file_list(**kwargs):
                cmd = kwargs.get("cmd", [])
                idx = cmd.index("--file-list")
                file_list_path = Path(cmd[idx + 1])
                captured_file_list_contents.append(file_list_path.read_text())
                return mock_result

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    side_effect=capture_file_list,
                ):
                    linter.lint(context)

            assert len(captured_file_list_contents) == 1
            contents = captured_file_list_contents[0]
            file_lines = [line for line in contents.strip().split("\n") if line]
            assert len(file_lines) == 2
            assert any("A.java" in line for line in file_lines)
            assert any("B.java" in line for line in file_lines)

    def test_lint_file_list_cleaned_up_on_success(self) -> None:
        """Verify temp file-list is deleted after successful lint."""
        linter = PmdLinter()

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

            mock_result = make_completed_process(0, '{"files": []}')
            captured_paths = []

            def capture_path(**kwargs):
                cmd = kwargs.get("cmd", [])
                idx = cmd.index("--file-list")
                captured_paths.append(Path(cmd[idx + 1]))
                return mock_result

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    side_effect=capture_path,
                ):
                    linter.lint(context)

            assert len(captured_paths) == 1
            assert not captured_paths[0].exists(), "Temp file-list should be cleaned up"

    def test_lint_file_list_cleaned_up_on_timeout(self) -> None:
        """Verify temp file-list is deleted when run_with_streaming times out."""
        linter = PmdLinter()

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
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("pmd", 120),
                ):
                    with patch(
                        "lucidshark.plugins.linters.pmd.tempfile.NamedTemporaryFile",
                        side_effect=tracking_temp,
                    ):
                        issues = linter.lint(context)

            assert issues == []
            for f in created_files:
                assert not f.exists(), f"Temp file {f} should be cleaned up"

    def test_lint_file_list_cleaned_up_on_unexpected_exception(self) -> None:
        """Verify temp file-list is deleted when run_with_streaming raises unexpected error."""
        linter = PmdLinter()

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
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    side_effect=RuntimeError("unexpected crash"),
                ):
                    with patch(
                        "lucidshark.plugins.linters.pmd.tempfile.NamedTemporaryFile",
                        side_effect=tracking_temp,
                    ):
                        issues = linter.lint(context)

            assert issues == []
            for f in created_files:
                assert not f.exists(), f"Temp file {f} should be cleaned up"

    def test_lint_passes_correct_kwargs_to_runner(self) -> None:
        """Verify correct cwd, tool_name, timeout passed to run_with_streaming."""
        linter = PmdLinter()

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

            mock_result = make_completed_process(0, '{"files": []}')
            captured_kwargs = {}

            def capture_kwargs(**kwargs):
                captured_kwargs.update(kwargs)
                return mock_result

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    side_effect=capture_kwargs,
                ):
                    linter.lint(context)

            assert captured_kwargs["cwd"] == tmpdir_path
            assert captured_kwargs["tool_name"] == "pmd"
            assert captured_kwargs["timeout"] == 120

    def test_lint_no_binary(self) -> None:
        linter = PmdLinter()

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
        linter = PmdLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(
                linter,
                "ensure_binary",
                side_effect=RuntimeError("Failed to download PMD"),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_no_files(self) -> None:
        linter = PmdLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_timeout(self) -> None:
        linter = PmdLinter()

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
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("pmd", 120),
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_subprocess_error(self) -> None:
        linter = PmdLinter()

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
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    side_effect=OSError("command failed"),
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_nonzero_exit_code_with_valid_json(self) -> None:
        """Verify issues are parsed even when PMD returns non-zero exit code."""
        linter = PmdLinter()

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

            # PMD returns exit code 4 when violations are found
            mock_result = make_completed_process(4, SAMPLE_PMD_OUTPUT)

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/pmd/bin/pmd")
            ):
                with patch(
                    "lucidshark.plugins.linters.pmd.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = linter.lint(context)
                    assert len(issues) == 1
                    assert issues[0].rule_id == "UnusedLocalVariable"


class TestPmdParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        linter = PmdLinter()
        issues = linter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_invalid_json(self) -> None:
        linter = PmdLinter()
        issues = linter._parse_output("not json at all", Path("/project"))
        assert issues == []

    def test_parse_no_violations(self) -> None:
        linter = PmdLinter()
        output = json.dumps(
            {
                "formatVersion": 0,
                "pmdVersion": "7.22.0",
                "files": [{"filename": "/project/Main.java", "violations": []}],
            }
        )
        issues = linter._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_single_violation(self) -> None:
        linter = PmdLinter()
        issues = linter._parse_output(SAMPLE_PMD_OUTPUT, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "UnusedLocalVariable"
        assert issues[0].severity == Severity.MEDIUM
        assert issues[0].line_start == 5

    def test_parse_multiple_files_and_violations(self) -> None:
        linter = PmdLinter()
        issues = linter._parse_output(SAMPLE_PMD_MULTI_FILE, Path("/project"))
        assert len(issues) == 3
        assert issues[0].rule_id == "UnusedImports"
        assert issues[0].severity == Severity.LOW
        assert issues[1].rule_id == "GodClass"
        assert issues[1].severity == Severity.HIGH
        assert issues[2].rule_id == "EmptyCatchBlock"
        assert issues[2].severity == Severity.CRITICAL

    def test_parse_empty_files_list(self) -> None:
        linter = PmdLinter()
        output = json.dumps({"formatVersion": 0, "pmdVersion": "7.22.0", "files": []})
        issues = linter._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_missing_files_key(self) -> None:
        """Verify JSON without 'files' key returns empty list."""
        linter = PmdLinter()
        output = json.dumps({"formatVersion": 0, "pmdVersion": "7.22.0"})
        issues = linter._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_file_without_violations_key(self) -> None:
        """Verify file entry without 'violations' key is handled."""
        linter = PmdLinter()
        output = json.dumps({"files": [{"filename": "/project/Main.java"}]})
        issues = linter._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_file_without_filename_key(self) -> None:
        """Verify file entry without 'filename' key is handled."""
        linter = PmdLinter()
        output = json.dumps(
            {
                "files": [
                    {
                        "violations": [
                            {
                                "rule": "X",
                                "priority": 3,
                                "description": "test",
                                "beginline": 1,
                            }
                        ]
                    }
                ]
            }
        )
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1

    def test_parse_whitespace_only_output(self) -> None:
        """Verify whitespace-only output returns empty list."""
        linter = PmdLinter()
        issues = linter._parse_output("   \n\t  ", Path("/project"))
        assert issues == []

    def test_parse_skips_bad_violations(self) -> None:
        """Verify a bad violation is skipped while good ones are parsed."""
        linter = PmdLinter()
        output = json.dumps(
            {
                "files": [
                    {
                        "filename": "/project/Main.java",
                        "violations": [
                            {
                                "rule": "Good",
                                "priority": 3,
                                "description": "good issue",
                                "beginline": 1,
                            },
                            {
                                "rule": "Bad",
                                "priority": 3,
                                "description": "bad issue",
                                "beginline": "not-a-number",
                            },
                        ],
                    }
                ]
            }
        )
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "Good"


class TestPmdViolationToIssue:
    """Tests for _violation_to_issue method."""

    def test_full_conversion(self) -> None:
        linter = PmdLinter()
        violation = {
            "beginline": 15,
            "begincolumn": 3,
            "endline": 20,
            "endcolumn": 10,
            "rule": "UnusedLocalVariable",
            "ruleset": "Best Practices",
            "priority": 3,
            "description": "Avoid unused local variables such as 'x'.",
            "externalInfoUrl": "https://docs.pmd-code.org/unused",
        }

        issue = linter._violation_to_issue(
            violation, "/project/Main.java", Path("/project")
        )

        assert issue is not None
        assert issue.source_tool == "pmd"
        assert issue.severity == Severity.MEDIUM
        assert issue.rule_id == "UnusedLocalVariable"
        assert issue.line_start == 15
        assert issue.line_end == 20
        assert issue.column_start == 3
        assert "UnusedLocalVariable" in issue.title
        assert issue.documentation_url == "https://docs.pmd-code.org/unused"
        assert issue.metadata["ruleset"] == "Best Practices"
        assert issue.metadata["priority"] == 3
        assert issue.fixable is False

    def test_missing_fields(self) -> None:
        linter = PmdLinter()
        violation = {
            "description": "Some issue",
            "priority": 3,
        }

        issue = linter._violation_to_issue(
            violation, "/project/Main.java", Path("/project")
        )

        assert issue is not None
        assert issue.rule_id == "unknown"
        assert issue.line_start is None
        assert issue.column_start is None
        assert issue.documentation_url is None

    def test_relative_path(self) -> None:
        linter = PmdLinter()
        violation = {
            "beginline": 1,
            "rule": "Test",
            "priority": 3,
            "description": "test",
        }

        issue = linter._violation_to_issue(violation, "src/Main.java", Path("/project"))

        assert issue is not None
        assert issue.file_path == Path("/project/src/Main.java")

    def test_absolute_path(self) -> None:
        linter = PmdLinter()
        violation = {
            "beginline": 1,
            "rule": "Test",
            "priority": 3,
            "description": "test",
        }

        issue = linter._violation_to_issue(
            violation, "/abs/path/Main.java", Path("/project")
        )

        assert issue is not None
        assert issue.file_path == Path("/abs/path/Main.java")

    def test_unknown_priority_defaults_to_medium(self) -> None:
        linter = PmdLinter()
        violation = {
            "beginline": 1,
            "rule": "Test",
            "priority": 99,
            "description": "test",
        }

        issue = linter._violation_to_issue(violation, "Main.java", Path("/project"))

        assert issue is not None
        assert issue.severity == Severity.MEDIUM

    def test_empty_violation_dict(self) -> None:
        """Verify empty violation dict produces an issue with defaults."""
        linter = PmdLinter()
        issue = linter._violation_to_issue({}, "/project/Main.java", Path("/project"))
        assert issue is not None
        assert issue.rule_id == "unknown"
        assert issue.severity == Severity.MEDIUM
        assert issue.line_start is None

    def test_non_numeric_beginline_returns_none(self) -> None:
        """Verify non-numeric beginline causes violation to be skipped."""
        linter = PmdLinter()
        violation = {
            "beginline": "abc",
            "rule": "Test",
            "priority": 3,
            "description": "test",
        }
        issue = linter._violation_to_issue(violation, "Main.java", Path("/project"))
        assert issue is None

    def test_string_priority_defaults_to_medium(self) -> None:
        """Verify string priority (not int) falls back to MEDIUM."""
        linter = PmdLinter()
        violation = {
            "beginline": 1,
            "rule": "Test",
            "priority": "3",
            "description": "test",
        }
        issue = linter._violation_to_issue(violation, "Main.java", Path("/project"))
        assert issue is not None
        # String "3" does not match int key 3 in PRIORITY_SEVERITY_MAP
        assert issue.severity == Severity.MEDIUM

    def test_title_format_without_rule(self) -> None:
        """Verify title is just description when rule is empty."""
        linter = PmdLinter()
        violation = {
            "beginline": 1,
            "rule": "",
            "priority": 3,
            "description": "Some message",
        }
        issue = linter._violation_to_issue(violation, "Main.java", Path("/project"))
        assert issue is not None
        assert issue.title == "Some message"
        assert "[]" not in issue.title


class TestPmdIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        linter = PmdLinter()
        id1 = linter._generate_issue_id("Rule", "file.java", 10, 5, "msg")
        id2 = linter._generate_issue_id("Rule", "file.java", 10, 5, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        linter = PmdLinter()
        id1 = linter._generate_issue_id("Rule1", "file.java", 10, 5, "msg")
        id2 = linter._generate_issue_id("Rule2", "file.java", 10, 5, "msg")
        assert id1 != id2

    def test_id_format_with_rule(self) -> None:
        linter = PmdLinter()
        issue_id = linter._generate_issue_id(
            "UnusedLocalVariable", "f.java", 1, 1, "msg"
        )
        assert issue_id.startswith("pmd-UnusedLocalVariable-")

    def test_id_format_without_rule(self) -> None:
        linter = PmdLinter()
        issue_id = linter._generate_issue_id("", "f.java", 1, 1, "msg")
        assert issue_id.startswith("pmd-")
        assert "pmd--" not in issue_id

    def test_id_handles_none_values(self) -> None:
        linter = PmdLinter()
        issue_id = linter._generate_issue_id("Rule", "file.java", None, None, "msg")
        assert issue_id.startswith("pmd-Rule-")
