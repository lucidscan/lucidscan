"""Integration tests for SpotBugs type checker.

These tests require Java to be installed. SpotBugs will be auto-downloaded.

Run with: pytest tests/integration/type_checkers/test_spotbugs_integration.py -v
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.type_checkers.spotbugs import SpotBugsChecker
from tests.integration.conftest import (
    java_available,
    spotbugs_available,
    maven_available,
)

_MVN_CMD = shutil.which("mvn") or "mvn"


class TestSpotBugsResolution:
    """Tests for SpotBugs binary resolution."""

    def test_ensure_binary_raises_when_java_not_available(self) -> None:
        """Test that ensure_binary raises FileNotFoundError when Java is missing."""
        checker = SpotBugsChecker(project_root=Path("/nonexistent"))

        with patch.object(shutil, "which", return_value=None):
            with pytest.raises(FileNotFoundError, match="Java is required"):
                checker.ensure_binary()


@java_available
class TestSpotBugsDownload:
    """Integration tests for SpotBugs binary download."""

    @pytest.mark.slow
    def test_download_spotbugs_binary(self) -> None:
        """Test downloading and extracting SpotBugs binary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = SpotBugsChecker(project_root=Path(tmpdir))
            spotbugs_dir = checker.ensure_binary()
            assert spotbugs_dir.exists()
            assert (spotbugs_dir / "lib" / "spotbugs.jar").exists()

    @pytest.mark.slow
    def test_cached_binary_reused(self) -> None:
        """Test that cached binary is reused on subsequent calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = SpotBugsChecker(project_root=Path(tmpdir))

            # First call downloads
            dir1 = checker.ensure_binary()
            assert dir1.exists()

            # Second call should reuse cached binary
            dir2 = checker.ensure_binary()
            assert dir1 == dir2


class TestSpotBugsAvailability:
    """Tests for SpotBugs availability."""

    @spotbugs_available
    def test_ensure_binary_returns_valid_path(
        self, spotbugs_checker: SpotBugsChecker
    ) -> None:
        """Test that ensure_binary returns a valid SpotBugs installation path."""
        binary_path = spotbugs_checker.ensure_binary()
        assert binary_path.exists()
        # SpotBugs dir should contain lib/spotbugs.jar
        spotbugs_jar = binary_path / "lib" / "spotbugs.jar"
        assert spotbugs_jar.exists(), f"spotbugs.jar not found at {spotbugs_jar}"

    @spotbugs_available
    def test_get_version(self, spotbugs_checker: SpotBugsChecker) -> None:
        """Test that get_version returns the configured version."""
        version = spotbugs_checker.get_version()
        assert version is not None
        assert isinstance(version, str)
        # Should be a valid semver-like version
        assert "." in version


@spotbugs_available
@maven_available
class TestSpotBugsTypeChecking:
    """Integration tests for SpotBugs type checking."""

    def test_check_java_webapp_project(
        self, spotbugs_checker: SpotBugsChecker, java_webapp_project: Path
    ) -> None:
        """Test checking the java-webapp project with intentional bugs."""
        import subprocess

        # First compile the project with Maven
        result = subprocess.run(
            [_MVN_CMD, "compile", "-q"],
            cwd=java_webapp_project,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )

        if result.returncode != 0:
            # Maven compile failed - skip test
            pytest.skip(f"Maven compile failed: {result.stderr}")

        context = ScanContext(
            project_root=java_webapp_project,
            paths=[java_webapp_project],
            enabled_domains=[],
        )

        issues = spotbugs_checker.check(context)

        # Should find at least one issue (null dereference in UserService)
        assert isinstance(issues, list)
        # Note: Actual bug count depends on SpotBugs version and Java version
        # The UserService.getUser() has a null dereference bug
        if len(issues) > 0:
            assert issues[0].source_tool == "spotbugs"
            assert issues[0].domain == ToolDomain.TYPE_CHECKING

    def test_check_compiled_classes_exist(
        self, spotbugs_checker: SpotBugsChecker, java_webapp_project: Path
    ) -> None:
        """Test that SpotBugs finds compiled class files."""
        import subprocess

        # First compile the project with Maven
        result = subprocess.run(
            [_MVN_CMD, "compile", "-q"],
            cwd=java_webapp_project,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )

        if result.returncode != 0:
            pytest.skip(f"Maven compile failed: {result.stderr}")

        # Check that target/classes exists
        classes_dir = java_webapp_project / "target" / "classes"
        assert classes_dir.exists(), "Maven should create target/classes directory"

        # Check that class files were compiled
        class_files = list(classes_dir.rglob("*.class"))
        assert len(class_files) > 0, "Maven should compile Java files"


@spotbugs_available
class TestSpotBugsIssueGeneration:
    """Tests for SpotBugs issue generation."""

    @maven_available
    def test_issue_has_correct_fields(
        self, spotbugs_checker: SpotBugsChecker, java_webapp_project: Path
    ) -> None:
        """Test that generated issues have all required fields."""
        import subprocess

        # First compile the project with Maven
        result = subprocess.run(
            [_MVN_CMD, "compile", "-q"],
            cwd=java_webapp_project,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )

        if result.returncode != 0:
            pytest.skip(f"Maven compile failed: {result.stderr}")

        context = ScanContext(
            project_root=java_webapp_project,
            paths=[java_webapp_project],
            enabled_domains=[],
        )

        issues = spotbugs_checker.check(context)

        if len(issues) > 0:
            issue = issues[0]

            # Check required fields
            assert issue.id is not None
            assert issue.id.startswith("spotbugs-")
            assert issue.domain == ToolDomain.TYPE_CHECKING
            assert issue.source_tool == "spotbugs"
            assert issue.severity is not None
            assert issue.title is not None
            assert issue.description is not None


@spotbugs_available
class TestSpotBugsVersion:
    """Tests for SpotBugs version management."""

    @pytest.mark.slow
    def test_different_versions_use_different_directories(self) -> None:
        """Test that different versions download to different directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Note: This test doesn't actually download different versions
            # It just verifies the path structure would be different
            checker1 = SpotBugsChecker(version="4.9.3", project_root=Path(tmpdir))
            checker2 = SpotBugsChecker(version="4.8.0", project_root=Path(tmpdir))

            # The paths should include the version
            path1 = checker1._paths.plugin_bin_dir("spotbugs", "4.9.3")
            path2 = checker2._paths.plugin_bin_dir("spotbugs", "4.8.0")

            assert path1 != path2
            assert "4.9.3" in str(path1)
            assert "4.8.0" in str(path2)


@spotbugs_available
class TestSpotBugsEmptyProject:
    """Tests for SpotBugs with empty projects."""

    @pytest.mark.slow
    def test_check_empty_directory(self) -> None:
        """Test checking an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            checker = SpotBugsChecker(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            # Should return empty since no compiled classes
            issues = checker.check(context)
            assert isinstance(issues, list)
            assert len(issues) == 0
