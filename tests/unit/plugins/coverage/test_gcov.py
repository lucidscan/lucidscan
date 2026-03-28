"""Unit tests for gcov/lcov coverage plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.coverage.base import CoverageResult, FileCoverage
from lucidshark.plugins.coverage.gcov import GcovPlugin


FAKE_BINARY = Path("/usr/bin/gcov")


# ---------------------------------------------------------------------------
# GcovPlugin properties
# ---------------------------------------------------------------------------


class TestGcovPluginProperties:
    """Tests for GcovPlugin basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        plugin = GcovPlugin()
        assert plugin.name == "gcov"

    def test_languages(self) -> None:
        """Test supported languages."""
        plugin = GcovPlugin()
        assert plugin.languages == ["c"]

    def test_domain(self) -> None:
        """Test domain is COVERAGE."""
        plugin = GcovPlugin()
        assert plugin.domain == ToolDomain.COVERAGE

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = GcovPlugin(project_root=Path(tmpdir))
            assert plugin._project_root == Path(tmpdir)


# ---------------------------------------------------------------------------
# GcovPlugin binary finding
# ---------------------------------------------------------------------------


class TestGcovBinaryFinding:
    """Tests for binary finding logic."""

    def test_ensure_binary(self) -> None:
        """Test ensure_binary delegates to find_gcov."""
        plugin = GcovPlugin()
        with patch(
            "lucidshark.plugins.coverage.gcov.find_gcov",
            return_value=FAKE_BINARY,
        ):
            binary = plugin.ensure_binary()
            assert binary == FAKE_BINARY

    def test_ensure_binary_raises_when_not_found(self) -> None:
        """Test ensure_binary raises FileNotFoundError."""
        plugin = GcovPlugin()
        with patch(
            "lucidshark.plugins.coverage.gcov.find_gcov",
            side_effect=FileNotFoundError("not found"),
        ):
            with pytest.raises(FileNotFoundError):
                plugin.ensure_binary()


# ---------------------------------------------------------------------------
# GcovPlugin version
# ---------------------------------------------------------------------------


class TestGcovGetVersion:
    """Tests for version detection."""

    def test_get_version_success(self) -> None:
        """Test getting gcov version."""
        plugin = GcovPlugin()
        with patch(
            "lucidshark.plugins.coverage.gcov.get_gcov_version",
            return_value="gcov (GCC) 13.2.0",
        ):
            version = plugin.get_version()
            assert version == "gcov (GCC) 13.2.0"

    def test_get_version_unknown_when_not_found(self) -> None:
        """Test version returns 'unknown' when gcov not found."""
        plugin = GcovPlugin()
        with patch(
            "lucidshark.plugins.coverage.gcov.get_gcov_version",
            return_value="unknown",
        ):
            version = plugin.get_version()
            assert version == "unknown"


# ---------------------------------------------------------------------------
# measure_coverage
# ---------------------------------------------------------------------------


class TestGcovMeasureCoverage:
    """Tests for measure_coverage flow."""

    def test_measure_coverage_no_data_returns_issue(self) -> None:
        """Test measure_coverage when no coverage data found."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.threshold == 80.0
            assert result.tool == "gcov"
            assert result.total_lines == 0
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"

    def test_measure_coverage_finds_coverage_info(self) -> None:
        """Test measure_coverage when coverage.info exists."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            lcov_content = (
                "SF:/project/src/main.c\n"
                "DA:1,1\n"
                "DA:2,1\n"
                "DA:3,0\n"
                "DA:4,1\n"
                "DA:5,0\n"
                "LF:5\n"
                "LH:3\n"
                "end_of_record\n"
            )
            (project_root / "coverage.info").write_text(lcov_content)

            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 5
            assert result.covered_lines == 3
            assert result.missing_lines == 2

    def test_measure_coverage_finds_lcov_info(self) -> None:
        """Test measure_coverage when lcov.info exists."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            lcov_content = (
                "SF:/project/src/lib.c\n"
                "DA:1,1\n"
                "DA:2,1\n"
                "LF:2\n"
                "LH:2\n"
                "end_of_record\n"
            )
            (project_root / "lcov.info").write_text(lcov_content)

            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 2
            assert result.covered_lines == 2

    def test_measure_coverage_checks_build_dir(self) -> None:
        """Test measure_coverage checks build directory for coverage data."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create build dir with CMakeCache.txt and coverage.info
            build_dir = project_root / "build"
            build_dir.mkdir()
            (build_dir / "CMakeCache.txt").touch()

            lcov_content = (
                "SF:/project/src/main.c\n"
                "DA:1,1\n"
                "LF:1\n"
                "LH:1\n"
                "end_of_record\n"
            )
            (build_dir / "coverage.info").write_text(lcov_content)

            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 1
            assert result.covered_lines == 1

    def test_measure_coverage_prefers_root_over_build_dir(self) -> None:
        """Test measure_coverage prefers coverage.info in project root."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create coverage.info in both root and build dir
            root_content = (
                "SF:/project/src/main.c\n"
                "DA:1,1\n"
                "DA:2,1\n"
                "LF:2\n"
                "LH:2\n"
                "end_of_record\n"
            )
            (project_root / "coverage.info").write_text(root_content)

            build_dir = project_root / "build"
            build_dir.mkdir()
            (build_dir / "CMakeCache.txt").touch()
            build_content = (
                "SF:/project/src/main.c\n"
                "DA:1,1\n"
                "LF:1\n"
                "LH:1\n"
                "end_of_record\n"
            )
            (build_dir / "coverage.info").write_text(build_content)

            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            # Should use root coverage.info (2 lines) not build dir (1 line)
            assert result.total_lines == 2


# ---------------------------------------------------------------------------
# _parse_lcov_info
# ---------------------------------------------------------------------------


class TestParseLcovInfo:
    """Tests for _parse_lcov_info method."""

    def test_parse_empty_file(self) -> None:
        """Test parsing empty lcov info file."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            info_file.write_text("")

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert result.total_lines == 0
            assert result.covered_lines == 0
            assert result.tool == "gcov"

    def test_parse_single_file_coverage(self) -> None:
        """Test parsing lcov info with one source file."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            content = (
                f"SF:{project_root}/src/main.c\n"
                "DA:1,1\n"
                "DA:2,1\n"
                "DA:3,0\n"
                "DA:4,1\n"
                "DA:5,0\n"
                "LF:5\n"
                "LH:3\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert result.total_lines == 5
            assert result.covered_lines == 3
            assert result.missing_lines == 2
            assert len(result.files) == 1
            assert result.threshold == 80.0

    def test_parse_multiple_files(self) -> None:
        """Test parsing lcov info with multiple source files."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            content = (
                f"SF:{project_root}/src/a.c\n"
                "DA:1,1\n"
                "DA:2,0\n"
                "end_of_record\n"
                f"SF:{project_root}/src/b.c\n"
                "DA:1,1\n"
                "DA:2,1\n"
                "DA:3,1\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert result.total_lines == 5
            assert result.covered_lines == 4
            assert result.missing_lines == 1
            assert len(result.files) == 2

    def test_parse_below_threshold_creates_issue(self) -> None:
        """Test that coverage below threshold creates an issue."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            content = (
                f"SF:{project_root}/src/main.c\n"
                "DA:1,1\n"
                "DA:2,0\n"
                "DA:3,0\n"
                "DA:4,0\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert result.percentage == 25.0
            assert len(result.issues) == 1
            assert "25.0%" in result.issues[0].title
            assert "80.0%" in result.issues[0].title

    def test_parse_above_threshold_no_issue(self) -> None:
        """Test that coverage above threshold creates no issue."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            content = (
                f"SF:{project_root}/src/main.c\n"
                "DA:1,1\n"
                "DA:2,1\n"
                "DA:3,1\n"
                "DA:4,1\n"
                "DA:5,1\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert result.percentage == 100.0
            assert len(result.issues) == 0

    def test_parse_exactly_at_threshold(self) -> None:
        """Test that coverage exactly at threshold creates no issue."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            # 4 out of 5 = 80%
            content = (
                f"SF:{project_root}/src/main.c\n"
                "DA:1,1\n"
                "DA:2,1\n"
                "DA:3,1\n"
                "DA:4,1\n"
                "DA:5,0\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert result.percentage == 80.0
            assert len(result.issues) == 0

    def test_parse_file_coverage_missing_lines(self) -> None:
        """Test that missing lines are correctly tracked per file."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            content = (
                f"SF:{project_root}/src/main.c\n"
                "DA:10,0\n"
                "DA:20,1\n"
                "DA:30,0\n"
                "DA:40,1\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert len(result.files) == 1
            file_cov = list(result.files.values())[0]
            assert file_cov.total_lines == 4
            assert file_cov.covered_lines == 2
            assert file_cov.missing_lines == [10, 30]

    def test_parse_handles_malformed_da_lines(self) -> None:
        """Test that malformed DA lines are gracefully skipped."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            content = (
                f"SF:{project_root}/src/main.c\n"
                "DA:1,1\n"
                "DA:bad,data\n"
                "DA:3,1\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert result.total_lines == 2
            assert result.covered_lines == 2

    def test_parse_handles_read_error(self) -> None:
        """Test that read errors return empty result."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # File doesn't exist
            info_file = project_root / "nonexistent.info"

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert result.total_lines == 0
            assert result.tool == "gcov"

    def test_parse_relative_path_computation(self) -> None:
        """Test that file paths are correctly made relative to project root."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            content = (
                f"SF:{project_root}/src/main.c\n"
                "DA:1,1\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            assert "src/main.c" in result.files

    def test_parse_external_file_path(self) -> None:
        """Test handling of file paths outside project root."""
        plugin = GcovPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            info_file = project_root / "coverage.info"
            content = (
                "SF:/external/path/lib.c\n"
                "DA:1,1\n"
                "end_of_record\n"
            )
            info_file.write_text(content)

            result = plugin._parse_lcov_info(info_file, project_root, 80.0)
            # When file is external, the raw path is used
            assert len(result.files) == 1


# ---------------------------------------------------------------------------
# No data issue
# ---------------------------------------------------------------------------


class TestGcovNoDataIssue:
    """Tests for _create_no_data_issue."""

    def test_no_data_issue_fields(self) -> None:
        """Test no-data issue has correct fields."""
        plugin = GcovPlugin()
        issue = plugin._create_no_data_issue()
        assert issue.id == "no-coverage-data-gcov"
        assert issue.rule_id == "no_coverage_data"
        assert issue.source_tool == "gcov"
        assert issue.severity == Severity.HIGH
        assert issue.domain == ToolDomain.COVERAGE
        assert "gcov" in issue.description.lower()


# ---------------------------------------------------------------------------
# Coverage issue creation
# ---------------------------------------------------------------------------


class TestGcovCoverageIssueCreation:
    """Tests for coverage issue creation (inherited from base)."""

    def test_create_issue_high_severity(self) -> None:
        """Test creating issue with HIGH severity (< 50%)."""
        plugin = GcovPlugin()
        issue = plugin._create_coverage_issue(
            percentage=40.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=40,
        )
        assert issue.severity == Severity.HIGH
        assert "40.0%" in issue.title
        assert "80.0%" in issue.title

    def test_create_issue_medium_severity(self) -> None:
        """Test creating issue with MEDIUM severity (< threshold - 10)."""
        plugin = GcovPlugin()
        issue = plugin._create_coverage_issue(
            percentage=65.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=65,
        )
        assert issue.severity == Severity.MEDIUM

    def test_create_issue_low_severity(self) -> None:
        """Test creating issue with LOW severity (close to threshold)."""
        plugin = GcovPlugin()
        issue = plugin._create_coverage_issue(
            percentage=78.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=78,
        )
        assert issue.severity == Severity.LOW

    def test_issue_metadata(self) -> None:
        """Test issue contains correct metadata."""
        plugin = GcovPlugin()
        issue = plugin._create_coverage_issue(
            percentage=75.0,
            threshold=80.0,
            total_lines=200,
            covered_lines=150,
        )
        metadata = issue.metadata
        assert metadata["coverage_percentage"] == 75.0
        assert metadata["threshold"] == 80.0
        assert metadata["total_lines"] == 200
        assert metadata["covered_lines"] == 150
        assert metadata["missing_lines"] == 50
        assert metadata["gap_percentage"] == 5.0


# ---------------------------------------------------------------------------
# Coverage threshold boundary
# ---------------------------------------------------------------------------


class TestGcovCoverageThresholdBoundary:
    """Tests for coverage threshold comparison at boundary values."""

    def test_exactly_at_threshold_passes(self) -> None:
        """Coverage exactly equal to threshold should pass."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            missing_lines=20,
            threshold=80.0,
        )
        assert result.percentage == 80.0
        assert result.passed is True

    def test_one_line_below_threshold_fails(self) -> None:
        """Coverage just below threshold should fail."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=79,
            missing_lines=21,
            threshold=80.0,
        )
        assert result.percentage == 79.0
        assert result.passed is False

    def test_one_line_above_threshold_passes(self) -> None:
        """Coverage just above threshold should pass."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=81,
            missing_lines=19,
            threshold=80.0,
        )
        assert result.percentage == 81.0
        assert result.passed is True

    def test_zero_total_lines_fails(self) -> None:
        """Zero total lines means no data, should fail."""
        result = CoverageResult(
            total_lines=0,
            covered_lines=0,
            missing_lines=0,
            threshold=80.0,
        )
        assert result.percentage == 0.0
        assert result.passed is False

    def test_100_percent_coverage(self) -> None:
        """100% coverage should pass."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=100,
            missing_lines=0,
            threshold=80.0,
        )
        assert result.percentage == 100.0
        assert result.passed is True


# ---------------------------------------------------------------------------
# FileCoverage
# ---------------------------------------------------------------------------


class TestFileCoverage:
    """Tests for FileCoverage dataclass."""

    def test_percentage_calculation(self) -> None:
        """Test percentage is computed correctly."""
        fc = FileCoverage(
            file_path=Path("/project/src/main.c"),
            total_lines=100,
            covered_lines=75,
            missing_lines=[10, 20, 30],
        )
        assert fc.percentage == 75.0

    def test_percentage_zero_lines(self) -> None:
        """Test percentage returns 0.0 for zero total lines."""
        fc = FileCoverage(
            file_path=Path("/project/src/empty.c"),
            total_lines=0,
            covered_lines=0,
        )
        assert fc.percentage == 0.0

    def test_percentage_full_coverage(self) -> None:
        """Test percentage returns 100.0 for full coverage."""
        fc = FileCoverage(
            file_path=Path("/project/src/main.c"),
            total_lines=50,
            covered_lines=50,
        )
        assert fc.percentage == 100.0
