"""Unit tests for Swift coverage plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.coverage.swift_coverage import SwiftCoveragePlugin


def _make_context(
    project_root: Path,
    paths: list[Path] | None = None,
    enabled_domains: list | None = None,
) -> ScanContext:
    """Create a minimal ScanContext for testing."""
    return ScanContext(
        project_root=project_root,
        paths=paths or [],
        enabled_domains=enabled_domains or [ToolDomain.COVERAGE],
    )


FAKE_BINARY = Path("/usr/bin/swift")


class TestSwiftCoverageProperties:
    """Tests for SwiftCoveragePlugin basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        plugin = SwiftCoveragePlugin()
        assert plugin.name == "swift_coverage"

    def test_languages(self) -> None:
        """Test supported languages."""
        plugin = SwiftCoveragePlugin()
        assert plugin.languages == ["swift"]

    def test_domain(self) -> None:
        """Test domain is COVERAGE."""
        plugin = SwiftCoveragePlugin()
        assert plugin.domain == ToolDomain.COVERAGE

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = SwiftCoveragePlugin(project_root=Path(tmpdir))
            assert plugin._project_root == Path(tmpdir)


class TestSwiftCoverageEnsureBinary:
    """Tests for ensure_binary method."""

    def test_found(self) -> None:
        """Test finding swift in system PATH."""
        plugin = SwiftCoveragePlugin()
        with patch(
            "lucidshark.plugins.swift_utils.shutil.which",
            return_value="/usr/bin/swift",
        ):
            binary = plugin.ensure_binary()
            assert binary == Path("/usr/bin/swift")

    def test_not_found(self) -> None:
        """Test FileNotFoundError when swift not found."""
        plugin = SwiftCoveragePlugin()
        with patch(
            "lucidshark.plugins.swift_utils.shutil.which",
            return_value=None,
        ):
            with pytest.raises(FileNotFoundError, match="swift is not installed"):
                plugin.ensure_binary()


class TestSwiftCoverageGetVersion:
    """Tests for get_version method."""

    def test_returns_version(self) -> None:
        """Test get_version returns a version string."""
        plugin = SwiftCoveragePlugin()
        mock_result = subprocess.CompletedProcess(
            args=["swift", "--version"],
            returncode=0,
            stdout="Swift version 5.9.0 (swift-5.9-RELEASE)",
            stderr="",
        )
        with patch(
            "lucidshark.plugins.swift_utils.subprocess.run",
            return_value=mock_result,
        ):
            version = plugin.get_version()
            assert version == "5.9.0"

    def test_returns_unknown_on_error(self) -> None:
        """Test get_version returns 'unknown' when binary not found."""
        plugin = SwiftCoveragePlugin()
        with patch(
            "lucidshark.plugins.swift_utils.subprocess.run",
            side_effect=FileNotFoundError("not found"),
        ):
            version = plugin.get_version()
            assert version == "unknown"


class TestSwiftCoverageMeasure:
    """Tests for measure_coverage method."""

    def test_no_package_swift(self) -> None:
        """Test measure_coverage returns empty when no Package.swift exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            plugin = SwiftCoveragePlugin(project_root=project_root)
            context = _make_context(project_root, [project_root])

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.threshold == 80.0
            assert result.tool == "swift_coverage"
            assert result.total_lines == 0

    def test_no_coverage_data(self) -> None:
        """Test measure_coverage when no coverage data is found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            plugin = SwiftCoveragePlugin(project_root=project_root)
            context = _make_context(project_root, [project_root])

            with patch.object(plugin, "_export_coverage", return_value=None):
                result = plugin.measure_coverage(context, threshold=80.0)
                assert result.total_lines == 0
                assert len(result.issues) == 1
                assert result.issues[0].rule_id == "no_coverage_data"
                assert result.issues[0].source_tool == "swift_coverage"

    def test_parse_codecov_json(self) -> None:
        """Test measure_coverage correctly parses llvm-cov JSON export format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            coverage_data = {
                "data": [
                    {
                        "totals": {
                            "lines": {"count": 100, "covered": 80, "percent": 80.0}
                        },
                        "files": [
                            {
                                "filename": "Sources/MyLib/Calculator.swift",
                                "summary": {
                                    "lines": {
                                        "count": 50,
                                        "covered": 40,
                                        "percent": 80.0,
                                    }
                                },
                                "segments": [
                                    [1, 1, 1, True, True],
                                    [10, 1, 0, True, False],
                                ],
                            }
                        ],
                    }
                ],
            }

            plugin = SwiftCoveragePlugin(project_root=project_root)
            context = _make_context(project_root, [project_root])

            with patch.object(plugin, "_export_coverage", return_value=coverage_data):
                result = plugin.measure_coverage(context, threshold=80.0)
                assert result.total_lines == 100
                assert result.covered_lines == 80
                assert result.percentage == 80.0
                # At exactly threshold: no coverage_below_threshold issue
                assert result.passed is True

    def test_coverage_below_threshold(self) -> None:
        """Test measure_coverage creates issue when below threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            coverage_data = {
                "data": [
                    {
                        "totals": {
                            "lines": {"count": 100, "covered": 50, "percent": 50.0}
                        },
                        "files": [],
                    }
                ],
            }

            plugin = SwiftCoveragePlugin(project_root=project_root)
            context = _make_context(project_root, [project_root])

            with patch.object(plugin, "_export_coverage", return_value=coverage_data):
                result = plugin.measure_coverage(context, threshold=80.0)
                assert result.total_lines == 100
                assert result.covered_lines == 50
                assert result.percentage == 50.0
                assert result.passed is False
                assert len(result.issues) == 1
                assert "50.0%" in result.issues[0].title
                assert "80.0%" in result.issues[0].title

    def test_per_file_coverage(self) -> None:
        """Test per-file coverage data is parsed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            coverage_data = {
                "data": [
                    {
                        "totals": {
                            "lines": {"count": 200, "covered": 180, "percent": 90.0}
                        },
                        "files": [
                            {
                                "filename": "Sources/App/Main.swift",
                                "summary": {
                                    "lines": {
                                        "count": 100,
                                        "covered": 90,
                                        "percent": 90.0,
                                    }
                                },
                                "segments": [],
                            },
                            {
                                "filename": "Sources/App/Utils.swift",
                                "summary": {
                                    "lines": {
                                        "count": 100,
                                        "covered": 90,
                                        "percent": 90.0,
                                    }
                                },
                                "segments": [],
                            },
                        ],
                    }
                ],
            }

            plugin = SwiftCoveragePlugin(project_root=project_root)
            context = _make_context(project_root, [project_root])

            with patch.object(plugin, "_export_coverage", return_value=coverage_data):
                result = plugin.measure_coverage(context, threshold=80.0)
                assert len(result.files) == 2


class TestSwiftCoverageExportCoverage:
    """Tests for _export_coverage method."""

    def test_returns_none_when_binary_not_found(self) -> None:
        """Test _export_coverage returns None when swift not found."""
        plugin = SwiftCoveragePlugin()
        context = _make_context(Path("/tmp"))

        with patch.object(
            plugin, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            result = plugin._export_coverage(context)
            assert result is None

    def test_returns_codecov_json(self) -> None:
        """Test _export_coverage returns parsed codecov JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            codecov_json = {
                "data": [
                    {
                        "totals": {"lines": {"count": 10, "covered": 8}},
                        "files": [],
                    }
                ]
            }

            # Create the codecov file
            codecov_path = project_root / ".build" / "debug" / "codecov.json"
            codecov_path.parent.mkdir(parents=True)
            codecov_path.write_text(json.dumps(codecov_json))

            plugin = SwiftCoveragePlugin(project_root=project_root)
            context = _make_context(project_root, [project_root])

            # Mock subprocess.run to return the codecov path
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = str(codecov_path)

            with (
                patch.object(plugin, "ensure_binary", return_value=FAKE_BINARY),
                patch("subprocess.run", return_value=mock_result),
            ):
                result = plugin._export_coverage(context)
                assert result is not None
                assert "data" in result

    def test_returns_none_on_timeout(self) -> None:
        """Test _export_coverage returns None on timeout."""
        plugin = SwiftCoveragePlugin()
        context = _make_context(Path("/tmp"))

        with (
            patch.object(plugin, "ensure_binary", return_value=FAKE_BINARY),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="swift", timeout=30),
            ),
        ):
            result = plugin._export_coverage(context)
            assert result is None


class TestSwiftCoverageParseLlvmCovExport:
    """Tests for _parse_llvm_cov_export method."""

    def test_empty_data(self) -> None:
        """Test parsing with empty data array."""
        plugin = SwiftCoveragePlugin()
        result = plugin._parse_llvm_cov_export({}, Path("/project"), 80.0)
        assert result.total_lines == 0
        assert result.covered_lines == 0

    def test_missing_data_key(self) -> None:
        """Test parsing with missing 'data' key."""
        plugin = SwiftCoveragePlugin()
        result = plugin._parse_llvm_cov_export(
            {"other": "value"}, Path("/project"), 80.0
        )
        assert result.total_lines == 0

    def test_full_parse(self) -> None:
        """Test parsing full llvm-cov JSON export."""
        plugin = SwiftCoveragePlugin()
        data = {
            "data": [
                {
                    "totals": {"lines": {"count": 100, "covered": 80, "percent": 80.0}},
                    "files": [
                        {
                            "filename": "Sources/MyLib/Calculator.swift",
                            "summary": {
                                "lines": {"count": 50, "covered": 40, "percent": 80.0}
                            },
                            "segments": [
                                [1, 1, 1, True, True],
                                [10, 1, 0, True, False],
                            ],
                        }
                    ],
                }
            ],
        }

        result = plugin._parse_llvm_cov_export(data, Path("/project"), 80.0)
        assert result.total_lines == 100
        assert result.covered_lines == 80
        assert result.missing_lines == 20
        assert result.tool == "swift_coverage"
        assert len(result.files) == 1

    def test_below_threshold_creates_issue(self) -> None:
        """Test that coverage below threshold creates an issue."""
        plugin = SwiftCoveragePlugin()
        data = {
            "data": [
                {
                    "totals": {"lines": {"count": 100, "covered": 60, "percent": 60.0}},
                    "files": [],
                }
            ],
        }

        result = plugin._parse_llvm_cov_export(data, Path("/project"), 80.0)
        assert len(result.issues) == 1
        assert "60.0%" in result.issues[0].title
        assert result.issues[0].domain == ToolDomain.COVERAGE
        assert result.issues[0].source_tool == "swift_coverage"


class TestSwiftCoverageExtractMissingLines:
    """Tests for _extract_missing_lines method."""

    def test_extracts_missing_lines(self) -> None:
        """Test extracting uncovered line numbers from segments."""
        plugin = SwiftCoveragePlugin()
        file_entry = {
            "segments": [
                [1, 1, 1, True, True],  # line 1: covered
                [5, 1, 0, True, False],  # line 5: not covered
                [10, 1, 0, True, False],  # line 10: not covered
                [15, 1, 3, True, True],  # line 15: covered
            ]
        }
        missing = plugin._extract_missing_lines(file_entry)
        assert missing == [5, 10]

    def test_no_segments(self) -> None:
        """Test with no segments."""
        plugin = SwiftCoveragePlugin()
        file_entry: dict = {"segments": []}
        missing = plugin._extract_missing_lines(file_entry)
        assert missing == []

    def test_all_covered(self) -> None:
        """Test when all segments are covered."""
        plugin = SwiftCoveragePlugin()
        file_entry = {
            "segments": [
                [1, 1, 1, True, True],
                [10, 1, 5, True, True],
            ]
        }
        missing = plugin._extract_missing_lines(file_entry)
        assert missing == []

    def test_deduplicates_lines(self) -> None:
        """Test that duplicate line numbers are deduplicated."""
        plugin = SwiftCoveragePlugin()
        file_entry = {
            "segments": [
                [5, 1, 0, True, False],
                [5, 10, 0, True, False],
            ]
        }
        missing = plugin._extract_missing_lines(file_entry)
        assert missing == [5]


class TestSwiftCoverageNoDataIssue:
    """Tests for _create_no_data_issue."""

    def test_no_data_issue_fields(self) -> None:
        """Test no-data issue has correct fields."""
        plugin = SwiftCoveragePlugin()
        issue = plugin._create_no_data_issue()
        assert issue.id == "no-coverage-data-swift_coverage"
        assert issue.rule_id == "no_coverage_data"
        assert issue.source_tool == "swift_coverage"
        assert issue.severity == Severity.HIGH
        assert issue.domain == ToolDomain.COVERAGE
        assert "swift_coverage" in issue.description.lower()


class TestSwiftCoverageIssueCreation:
    """Tests for coverage issue creation."""

    def test_high_severity_below_50(self) -> None:
        """Test HIGH severity when coverage is below 50%."""
        plugin = SwiftCoveragePlugin()
        issue = plugin._create_coverage_issue(
            percentage=30.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=30,
        )
        assert issue.severity == Severity.HIGH

    def test_medium_severity_below_threshold_minus_10(self) -> None:
        """Test MEDIUM severity when coverage is below threshold - 10."""
        plugin = SwiftCoveragePlugin()
        issue = plugin._create_coverage_issue(
            percentage=65.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=65,
        )
        assert issue.severity == Severity.MEDIUM

    def test_low_severity_close_to_threshold(self) -> None:
        """Test LOW severity when coverage is close to threshold."""
        plugin = SwiftCoveragePlugin()
        issue = plugin._create_coverage_issue(
            percentage=78.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=78,
        )
        assert issue.severity == Severity.LOW

    def test_issue_metadata(self) -> None:
        """Test issue contains correct metadata."""
        plugin = SwiftCoveragePlugin()
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
