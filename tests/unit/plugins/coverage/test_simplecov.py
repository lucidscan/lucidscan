"""Unit tests for SimpleCov coverage plugin."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.coverage.base import CoverageResult
from lucidshark.plugins.coverage.simplecov import SimpleCovPlugin


class TestSimpleCovPlugin:
    """Tests for SimpleCovPlugin class."""

    def test_name(self) -> None:
        plugin = SimpleCovPlugin()
        assert plugin.name == "simplecov"

    def test_languages(self) -> None:
        plugin = SimpleCovPlugin()
        assert plugin.languages == ["ruby"]

    def test_domain(self) -> None:
        plugin = SimpleCovPlugin()
        assert plugin.domain == ToolDomain.COVERAGE


class TestSimpleCovBinaryFinding:
    """Tests for binary finding logic."""

    @patch("shutil.which")
    def test_find_ruby_in_path(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/bin/ruby"
        plugin = SimpleCovPlugin()
        binary = plugin.ensure_binary()
        assert binary == Path("/usr/bin/ruby")

    @patch("shutil.which")
    def test_ruby_not_found_raises_error(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        plugin = SimpleCovPlugin()
        with pytest.raises(FileNotFoundError) as exc:
            plugin.ensure_binary()
        assert "Ruby is not installed" in str(exc.value)


class TestSimpleCovGetVersion:
    """Tests for version detection."""

    @patch("shutil.which", return_value="/usr/bin/ruby")
    def test_get_version_installed(self, mock_which: MagicMock) -> None:
        plugin = SimpleCovPlugin()
        version = plugin.get_version()
        assert version == "installed"

    @patch("shutil.which", return_value=None)
    def test_get_version_unknown(self, mock_which: MagicMock) -> None:
        plugin = SimpleCovPlugin()
        version = plugin.get_version()
        assert version == "unknown"


class TestSimpleCovFindResultset:
    """Tests for finding coverage resultset files."""

    def test_find_resultset_in_coverage_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            coverage_dir = project_root / "coverage"
            coverage_dir.mkdir()
            resultset = coverage_dir / ".resultset.json"
            resultset.write_text("{}")

            plugin = SimpleCovPlugin(project_root=project_root)
            found = plugin._find_resultset(project_root)
            assert found == resultset

    def test_find_resultset_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            plugin = SimpleCovPlugin(project_root=project_root)
            found = plugin._find_resultset(project_root)
            assert found is None


class TestSimpleCovMeasureCoverage:
    """Tests for coverage measurement."""

    def test_no_resultset_returns_no_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            from lucidshark.core.models import ScanContext

            plugin = SimpleCovPlugin(project_root=project_root)
            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[ToolDomain.COVERAGE],
            )
            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 0
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"


class TestSimpleCovParseResultset:
    """Tests for resultset JSON parsing."""

    def test_parse_modern_format(self) -> None:
        """Test parsing modern SimpleCov format with nested lines dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            resultset = Path(tmpdir) / "resultset.json"
            data = {
                "RSpec": {
                    "coverage": {
                        f"{tmpdir}/lib/example.rb": {
                            "lines": [None, 1, 1, 0, None, 1, 0, 1]
                        }
                    },
                    "timestamp": 1234567890,
                }
            }
            resultset.write_text(json.dumps(data))

            plugin = SimpleCovPlugin(project_root=project_root)
            result = plugin._parse_resultset(resultset, project_root, threshold=80.0)

            # Lines: [None, 1, 1, 0, None, 1, 0, 1]
            # Relevant lines (non-None): [1, 1, 0, 1, 0, 1] = 6 total
            # Covered (>0): [1, 1, 1, 1] = 4 covered
            assert result.total_lines == 6
            assert result.covered_lines == 4
            assert result.has_data is True

    def test_parse_legacy_format(self) -> None:
        """Test parsing legacy SimpleCov format with direct array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            resultset = Path(tmpdir) / "resultset.json"
            data = {
                "RSpec": {
                    "coverage": {
                        f"{tmpdir}/lib/example.rb": [None, 1, 1, 0, None, 1]
                    }
                }
            }
            resultset.write_text(json.dumps(data))

            plugin = SimpleCovPlugin(project_root=project_root)
            result = plugin._parse_resultset(resultset, project_root, threshold=80.0)

            # Relevant: [1, 1, 0, 1] = 4 total, 3 covered
            assert result.total_lines == 4
            assert result.covered_lines == 3

    def test_parse_multiple_suites(self) -> None:
        """Test merging coverage from multiple test suites."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            resultset = Path(tmpdir) / "resultset.json"
            data = {
                "RSpec": {
                    "coverage": {
                        f"{tmpdir}/lib/example.rb": [None, 1, 0, 0]
                    }
                },
                "Minitest": {
                    "coverage": {
                        f"{tmpdir}/lib/example.rb": [None, 0, 1, 0]
                    }
                },
            }
            resultset.write_text(json.dumps(data))

            plugin = SimpleCovPlugin(project_root=project_root)
            result = plugin._parse_resultset(resultset, project_root, threshold=80.0)

            # Merged: [None, max(1,0)=1, max(0,1)=1, max(0,0)=0] = [None, 1, 1, 0]
            # Relevant: [1, 1, 0] = 3 total, 2 covered
            assert result.total_lines == 3
            assert result.covered_lines == 2

    def test_parse_empty_resultset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            resultset = Path(tmpdir) / "resultset.json"
            resultset.write_text("{}")

            plugin = SimpleCovPlugin()
            result = plugin._parse_resultset(
                resultset, Path(tmpdir), threshold=80.0
            )
            assert result.total_lines == 0
            assert result.covered_lines == 0

    def test_parse_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            resultset = Path(tmpdir) / "resultset.json"
            resultset.write_text("not json")

            plugin = SimpleCovPlugin()
            result = plugin._parse_resultset(
                resultset, Path(tmpdir), threshold=80.0
            )
            assert result.total_lines == 0


class TestSimpleCovCoverageThreshold:
    """Tests for coverage threshold behavior."""

    def test_below_threshold_creates_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            resultset = Path(tmpdir) / "resultset.json"
            # 50% coverage (2 of 4 lines covered)
            data = {
                "RSpec": {
                    "coverage": {
                        f"{tmpdir}/lib/example.rb": [None, 1, 1, 0, 0]
                    }
                }
            }
            resultset.write_text(json.dumps(data))

            plugin = SimpleCovPlugin(project_root=project_root)
            result = plugin._parse_resultset(resultset, project_root, threshold=80.0)

            assert result.percentage < 80.0
            assert len(result.issues) == 1
            assert "below threshold" in result.issues[0].title

    def test_above_threshold_no_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            resultset = Path(tmpdir) / "resultset.json"
            # 100% coverage
            data = {
                "RSpec": {
                    "coverage": {
                        f"{tmpdir}/lib/example.rb": [None, 1, 1, 1, 1]
                    }
                }
            }
            resultset.write_text(json.dumps(data))

            plugin = SimpleCovPlugin(project_root=project_root)
            result = plugin._parse_resultset(resultset, project_root, threshold=80.0)

            assert result.percentage == 100.0
            assert len(result.issues) == 0


class TestSimpleCovMissingLines:
    """Tests for missing line tracking."""

    def test_missing_lines_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            resultset = Path(tmpdir) / "resultset.json"
            data = {
                "RSpec": {
                    "coverage": {
                        f"{tmpdir}/lib/example.rb": [None, 1, 0, 1, 0, None]
                    }
                }
            }
            resultset.write_text(json.dumps(data))

            plugin = SimpleCovPlugin(project_root=project_root)
            result = plugin._parse_resultset(resultset, project_root, threshold=80.0)

            # Lines 3 and 5 are uncovered (1-indexed)
            file_key = list(result.files.keys())[0]
            file_coverage = result.files[file_key]
            assert 3 in file_coverage.missing_lines
            assert 5 in file_coverage.missing_lines
            assert len(file_coverage.missing_lines) == 2
