"""Unit tests for lcov coverage plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.coverage.lcov import LcovPlugin


SAMPLE_LCOV_INFO = """\
TN:
SF:/tmp/test/src/main.cpp
DA:1,1
DA:2,1
DA:3,1
DA:4,0
DA:5,0
LF:5
LH:3
end_of_record
SF:/tmp/test/src/utils.cpp
DA:1,1
DA:2,1
DA:3,1
DA:4,1
DA:5,1
DA:6,0
DA:7,0
DA:8,0
LF:8
LH:5
end_of_record
"""

SAMPLE_LCOV_100_PERCENT = """\
TN:
SF:/tmp/test/src/main.cpp
DA:1,1
DA:2,1
DA:3,1
LF:3
LH:3
end_of_record
"""


class TestLcovProperties:
    """Basic property tests for LcovPlugin."""

    def test_name(self) -> None:
        plugin = LcovPlugin()
        assert plugin.name == "lcov"

    def test_languages(self) -> None:
        plugin = LcovPlugin()
        assert plugin.languages == ["c++"]

    def test_domain(self) -> None:
        plugin = LcovPlugin()
        assert plugin.domain == ToolDomain.COVERAGE


class TestParseLcovInfo:
    """Tests for _parse_lcov_info."""

    def test_parse_sample_coverage(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            coverage_file = tmpdir_path / "coverage.info"
            coverage_file.write_text(SAMPLE_LCOV_INFO)

            result = plugin._parse_lcov_info(
                coverage_file, Path("/tmp/test"), threshold=80.0
            )

            # Total: 5 + 8 = 13 lines, 3 + 5 = 8 covered
            assert result.total_lines == 13
            assert result.covered_lines == 8
            assert result.missing_lines == 5
            assert result.tool == "lcov"

    def test_parse_per_file_coverage(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            coverage_file = tmpdir_path / "coverage.info"
            coverage_file.write_text(SAMPLE_LCOV_INFO)

            result = plugin._parse_lcov_info(
                coverage_file, Path("/tmp/test"), threshold=80.0
            )

            assert len(result.files) == 2

    def test_parse_missing_lines_tracked(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            coverage_file = tmpdir_path / "coverage.info"
            coverage_file.write_text(SAMPLE_LCOV_INFO)

            result = plugin._parse_lcov_info(
                coverage_file, Path("/tmp/test"), threshold=80.0
            )

            # main.cpp has 2 missing lines (4, 5)
            main_file = None
            for path, cov in result.files.items():
                if "main.cpp" in path:
                    main_file = cov
                    break

            assert main_file is not None
            assert 4 in main_file.missing_lines
            assert 5 in main_file.missing_lines

    def test_below_threshold_creates_issue(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            coverage_file = tmpdir_path / "coverage.info"
            coverage_file.write_text(SAMPLE_LCOV_INFO)

            result = plugin._parse_lcov_info(
                coverage_file, Path("/tmp/test"), threshold=80.0
            )

            # Coverage is ~61.5%, below 80% threshold
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "coverage_below_threshold"

    def test_above_threshold_no_issue(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            coverage_file = tmpdir_path / "coverage.info"
            coverage_file.write_text(SAMPLE_LCOV_100_PERCENT)

            result = plugin._parse_lcov_info(
                coverage_file, Path("/tmp/test"), threshold=80.0
            )

            assert result.total_lines == 3
            assert result.covered_lines == 3
            assert len(result.issues) == 0

    def test_parse_empty_file(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            coverage_file = tmpdir_path / "coverage.info"
            coverage_file.write_text("")

            result = plugin._parse_lcov_info(
                coverage_file, Path("/tmp"), threshold=80.0
            )

            assert result.total_lines == 0
            assert result.covered_lines == 0

    def test_percentage_calculation(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            coverage_file = tmpdir_path / "coverage.info"
            coverage_file.write_text(SAMPLE_LCOV_INFO)

            result = plugin._parse_lcov_info(
                coverage_file, Path("/tmp/test"), threshold=80.0
            )

            # 8/13 ≈ 61.5%
            assert 61.0 < result.percentage < 62.0


class TestFindCoverageFile:
    """Tests for _find_coverage_file."""

    def test_finds_coverage_info(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "coverage.info").write_text("SF:test\nend_of_record\n")
            result = plugin._find_coverage_file(tmpdir_path)
            assert result == tmpdir_path / "coverage.info"

    def test_finds_lcov_info(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "lcov.info").write_text("SF:test\nend_of_record\n")
            result = plugin._find_coverage_file(tmpdir_path)
            assert result == tmpdir_path / "lcov.info"

    def test_finds_in_build_dir(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            build_dir = tmpdir_path / "build"
            build_dir.mkdir()
            (build_dir / "coverage.info").write_text("SF:test\nend_of_record\n")
            result = plugin._find_coverage_file(tmpdir_path)
            assert result == build_dir / "coverage.info"

    def test_returns_none_when_not_found(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = plugin._find_coverage_file(Path(tmpdir))
            assert result is None


class TestMeasureCoverage:
    """Tests for measure_coverage method."""

    def test_no_coverage_file_creates_issue(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            result = plugin.measure_coverage(context, threshold=80.0)
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"

    def test_with_valid_coverage_file(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "coverage.info").write_text(SAMPLE_LCOV_100_PERCENT)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 3
            assert result.covered_lines == 3
            assert result.tool == "lcov"


class TestMakeRelative:
    """Tests for _make_relative."""

    def test_absolute_path_made_relative(self) -> None:
        plugin = LcovPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            abs_path = str(tmpdir_path / "src" / "main.cpp")
            result = plugin._make_relative(abs_path, tmpdir_path)
            assert result == "src/main.cpp"

    def test_already_relative_path(self) -> None:
        plugin = LcovPlugin()
        result = plugin._make_relative("src/main.cpp", Path("/tmp"))
        assert result == "src/main.cpp"

    def test_path_outside_project(self) -> None:
        plugin = LcovPlugin()
        result = plugin._make_relative("/other/path/main.cpp", Path("/tmp"))
        assert result == "/other/path/main.cpp"
