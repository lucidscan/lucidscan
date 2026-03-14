"""Integration tests for go cover coverage plugin.

NOTE: The go_cover plugin (src/lucidshark/plugins/coverage/go_cover.py) is
not yet implemented. These tests document the expected behaviour and will
serve as a specification once the plugin is created.

Tests that require the plugin import are conditionally skipped.

Run with: pytest tests/integration/coverage/test_go_cover_integration.py -v
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from lucidshark.core.models import ScanContext, ToolDomain
from tests.integration.conftest import go_available

# Conditionally import the plugin; skip tests if it does not exist yet.
try:
    from lucidshark.plugins.coverage.go_cover import GoCoverPlugin

    _go_cover_importable = True
except ImportError:
    _go_cover_importable = False

go_cover_plugin_available = pytest.mark.skipif(
    not _go_cover_importable,
    reason="go_cover plugin not yet implemented",
)


def _create_temp_go_project(
    tmp_path: Path, module_name: str = "example.com/testproject"
) -> Path:
    """Create a minimal Go project in tmp_path."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(f"module {module_name}\n\ngo 1.21\n")
    return tmp_path


def _create_go_project_with_tests(tmp_path: Path) -> Path:
    """Create a Go project with a function and test for coverage measurement."""
    _create_temp_go_project(tmp_path)

    main_go = tmp_path / "main.go"
    main_go.write_text(
        "package main\n\n"
        "func Add(a, b int) int { return a + b }\n\n"
        "func Subtract(a, b int) int { return a - b }\n\n"
        "func main() {}\n"
    )

    test_go = tmp_path / "main_test.go"
    test_go.write_text(
        'package main\n\nimport "testing"\n\n'
        "func TestAdd(t *testing.T) {\n"
        "\tif Add(1, 2) != 3 {\n"
        '\t\tt.Error("expected 3")\n'
        "\t}\n}\n"
    )

    subprocess.run(
        ["go", "mod", "tidy"],
        cwd=tmp_path,
        capture_output=True,
        timeout=60,
    )

    return tmp_path


def _generate_coverage_out(project_path: Path) -> Path:
    """Run go test -coverprofile to generate a coverage.out file."""
    subprocess.run(
        ["go", "test", "-coverprofile=coverage.out", "./..."],
        cwd=project_path,
        capture_output=True,
        timeout=120,
    )
    return project_path / "coverage.out"


# =============================================================================
# Tests that exercise the coverage profile format parsing.
# These work even if the plugin is not yet implemented, by testing
# the raw Go coverage.out file format that the plugin must parse.
# =============================================================================


@go_available
class TestGoCoverProfileFormat:
    """Tests validating Go coverage profile format and generation."""

    def test_go_test_generates_coverprofile(self) -> None:
        """Test that go test -coverprofile creates a coverage.out file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_go_project_with_tests(tmpdir_path)

            coverage_file = _generate_coverage_out(tmpdir_path)

            assert coverage_file.exists()

            content = coverage_file.read_text()
            # Go coverage files start with "mode: "
            assert content.startswith("mode: ")

    def test_coverprofile_contains_file_entries(self) -> None:
        """Test that coverage.out contains entries for covered files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_go_project_with_tests(tmpdir_path)

            coverage_file = _generate_coverage_out(tmpdir_path)

            content = coverage_file.read_text()
            lines = content.strip().splitlines()

            # First line is mode line, rest are coverage entries
            assert len(lines) >= 2
            # Entries follow format: module/file.go:startLine.startCol,endLine.endCol count numStmts
            for line in lines[1:]:
                assert ".go:" in line


# =============================================================================
# Tests that require the go_cover plugin to be implemented.
# =============================================================================


@go_cover_plugin_available
@go_available
class TestGoCoverFunctional:
    """Functional integration tests for go cover plugin."""

    def test_measure_coverage_parses_coverprofile(self) -> None:
        """Test that the plugin correctly parses a coverage.out file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_go_project_with_tests(tmpdir_path)

            _generate_coverage_out(tmpdir_path)

            plugin = GoCoverPlugin(project_root=tmpdir_path)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = plugin.measure_coverage(context, threshold=50.0)

            assert result.has_data
            assert result.total_lines > 0
            assert result.covered_lines >= 0
            assert 0 <= result.percentage <= 100
            assert result.tool == "go_cover"

    def test_measure_coverage_no_data(self) -> None:
        """Test that missing coverage.out produces a no-data issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_temp_go_project(tmpdir_path)

            plugin = GoCoverPlugin(project_root=tmpdir_path)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = plugin.measure_coverage(context, threshold=80.0)

            # No coverage.out means no data
            assert not result.has_data
            assert len(result.issues) >= 1
            assert any(issue.rule_id == "no_coverage_data" for issue in result.issues)

    def test_coverage_below_threshold_creates_issue(self) -> None:
        """Test that coverage below threshold creates an issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_go_project_with_tests(tmpdir_path)

            _generate_coverage_out(tmpdir_path)

            plugin = GoCoverPlugin(project_root=tmpdir_path)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            # Use very high threshold to force failure
            result = plugin.measure_coverage(context, threshold=99.0)

            if result.has_data and result.percentage < 99.0:
                assert result.passed is False
                assert len(result.issues) >= 1
                issue = result.issues[0]
                assert issue.domain == ToolDomain.COVERAGE
                assert issue.source_tool == "go_cover"

    def test_coverage_above_threshold_no_issues(self) -> None:
        """Test that coverage above threshold creates no threshold issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_go_project_with_tests(tmpdir_path)

            _generate_coverage_out(tmpdir_path)

            plugin = GoCoverPlugin(project_root=tmpdir_path)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            # Use very low threshold
            result = plugin.measure_coverage(context, threshold=1.0)

            if result.has_data and result.percentage >= 1.0:
                assert result.passed is True
                # No threshold issues (there may be per-file issues)
                threshold_issues = [
                    i for i in result.issues if i.rule_id == "coverage_below_threshold"
                ]
                assert len(threshold_issues) == 0

    def test_module_path_stripping(self) -> None:
        """Test that module path is stripped from file paths in results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_go_project_with_tests(tmpdir_path)

            _generate_coverage_out(tmpdir_path)

            plugin = GoCoverPlugin(project_root=tmpdir_path)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = plugin.measure_coverage(context, threshold=0.0)

            if result.files:
                for file_key in result.files:
                    # File keys should not contain the full module path
                    assert not file_key.startswith("example.com/"), (
                        f"File key '{file_key}' should have module path stripped"
                    )


# =============================================================================
# New unit tests — NO Go binary required
# =============================================================================


@go_cover_plugin_available
class TestGoCoverProperties:
    """Tests for GoCoverPlugin property accessors."""

    def test_name(self) -> None:
        """Test that plugin name is 'go_cover'."""
        plugin = GoCoverPlugin()
        assert plugin.name == "go_cover"

    def test_languages(self) -> None:
        """Test that supported languages includes 'go'."""
        plugin = GoCoverPlugin()
        assert plugin.languages == ["go"]

    def test_domain(self) -> None:
        """Test that domain is COVERAGE."""
        plugin = GoCoverPlugin()
        assert plugin.domain == ToolDomain.COVERAGE


@go_cover_plugin_available
class TestGoCoverProfileParsing:
    """Tests for _parse_coverprofile — NO Go binary needed.

    Each test writes a synthetic coverage.out file and calls
    _parse_coverprofile directly.
    """

    def test_parse_mode_set(self, tmp_path: Path) -> None:
        """Standard coverprofile with 'mode: set' parses correctly."""
        (tmp_path / "go.mod").write_text("module example.com/pkg\n\ngo 1.21\n")
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:3.14,5.2 1 1\n"
            "example.com/pkg/main.go:7.14,9.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 2
        assert result.covered_lines == 1

    def test_parse_mode_count(self, tmp_path: Path) -> None:
        """'mode: count' with count>1 values counts as covered."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: count\n"
            "example.com/pkg/main.go:3.14,5.2 1 5\n"
            "example.com/pkg/main.go:7.14,9.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 2
        assert result.covered_lines == 1

    def test_parse_mode_atomic(self, tmp_path: Path) -> None:
        """'mode: atomic' behaves the same as count."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: atomic\n"
            "example.com/pkg/main.go:3.14,5.2 1 3\n"
            "example.com/pkg/main.go:7.14,9.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 2
        assert result.covered_lines == 1

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty coverage.out results in total_lines=0."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text("")
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 0

    def test_only_mode_line(self, tmp_path: Path) -> None:
        """'mode: set' with no data lines results in total_lines=0."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text("mode: set\n")
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 0

    def test_single_file_fully_covered(self, tmp_path: Path) -> None:
        """All blocks with count>0 results in 100% coverage."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:3.14,5.2 2 1\n"
            "example.com/pkg/main.go:7.14,9.2 3 1\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 5
        assert result.covered_lines == 5
        assert result.percentage == 100.0

    def test_single_file_fully_uncovered(self, tmp_path: Path) -> None:
        """All blocks with count=0 results in 0% coverage."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:3.14,5.2 2 0\n"
            "example.com/pkg/main.go:7.14,9.2 3 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 5
        assert result.covered_lines == 0
        assert result.percentage == 0.0

    def test_multiple_files(self, tmp_path: Path) -> None:
        """Blocks from 3 files produce correct per-file stats and totals."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/a.go:3.14,5.2 2 1\n"
            "example.com/pkg/b.go:3.14,5.2 3 0\n"
            "example.com/pkg/c.go:3.14,5.2 4 1\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 9
        assert result.covered_lines == 6  # 2 + 0 + 4
        assert len(result.files) == 3
        assert result.files["a.go"].total_lines == 2
        assert result.files["a.go"].covered_lines == 2
        assert result.files["b.go"].total_lines == 3
        assert result.files["b.go"].covered_lines == 0
        assert result.files["c.go"].total_lines == 4
        assert result.files["c.go"].covered_lines == 4

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        """Mix of valid and malformed lines — only valid lines parsed."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:3.14,5.2 1 1\n"
            "bad_line\n"
            "another bad line with no match\n"
            "example.com/pkg/main.go:7.14,9.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        assert result.total_lines == 2

    def test_zero_statements_block(self, tmp_path: Path) -> None:
        """Block with num_statements=0 does not cause division by zero."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:3.14,5.2 0 1\n"
            "example.com/pkg/main.go:7.14,9.2 1 1\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        # 0 + 1 = 1 total, 0 + 1 = 1 covered
        assert result.total_lines == 1
        assert result.covered_lines == 1

    def test_missing_lines_populated(self, tmp_path: Path) -> None:
        """Blocks with count=0 have their start lines in missing_lines."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:3.14,5.2 1 1\n"
            "example.com/pkg/main.go:10.14,15.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        file_cov = result.files["main.go"]
        assert 10 in file_cov.missing_lines

    def test_missing_lines_sorted(self, tmp_path: Path) -> None:
        """Uncovered blocks at lines 20, 5, 12 produce sorted missing_lines."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:20.1,22.2 1 0\n"
            "example.com/pkg/main.go:5.1,7.2 1 0\n"
            "example.com/pkg/main.go:12.1,14.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        file_cov = result.files["main.go"]
        assert file_cov.missing_lines == [5, 12, 20]

    def test_file_path_resolution(self, tmp_path: Path) -> None:
        """File paths in result are resolved against project_root."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text("mode: set\nexample.com/pkg/main.go:3.14,5.2 1 1\n")
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        file_cov = result.files["main.go"]
        assert file_cov.file_path == tmp_path / "main.go"


@go_cover_plugin_available
class TestGoCoverModulePath:
    """Tests for _read_module_path and _strip_module_prefix."""

    def test_read_standard_go_mod(self, tmp_path: Path) -> None:
        """'module example.com/pkg' is extracted correctly."""
        (tmp_path / "go.mod").write_text("module example.com/pkg\n\ngo 1.21\n")
        plugin = GoCoverPlugin()
        assert plugin._read_module_path(tmp_path) == "example.com/pkg"

    def test_read_go_mod_with_comments(self, tmp_path: Path) -> None:
        """Comments before module line do not interfere."""
        (tmp_path / "go.mod").write_text(
            "// This is a comment\n"
            "// Another comment\n"
            "module example.com/mymod\n\ngo 1.21\n"
        )
        plugin = GoCoverPlugin()
        assert plugin._read_module_path(tmp_path) == "example.com/mymod"

    def test_read_go_mod_with_replace_directives(self, tmp_path: Path) -> None:
        """Complex go.mod with replace directives still finds module path."""
        (tmp_path / "go.mod").write_text(
            "module example.com/complex\n\n"
            "go 1.21\n\n"
            "require (\n"
            "\tgithub.com/some/dep v1.0.0\n"
            ")\n\n"
            "replace github.com/some/dep => ../local\n"
        )
        plugin = GoCoverPlugin()
        assert plugin._read_module_path(tmp_path) == "example.com/complex"

    def test_read_go_mod_missing(self, tmp_path: Path) -> None:
        """No go.mod returns empty string."""
        plugin = GoCoverPlugin()
        assert plugin._read_module_path(tmp_path) == ""

    def test_strip_module_prefix_standard(self) -> None:
        """'example.com/pkg/main.go' with module 'example.com/pkg' becomes 'main.go'."""
        plugin = GoCoverPlugin()
        assert (
            plugin._strip_module_prefix("example.com/pkg/main.go", "example.com/pkg")
            == "main.go"
        )

    def test_strip_nested_subpackage(self) -> None:
        """'example.com/pkg/handlers/auth.go' becomes 'handlers/auth.go'."""
        plugin = GoCoverPlugin()
        result = plugin._strip_module_prefix(
            "example.com/pkg/handlers/auth.go", "example.com/pkg"
        )
        assert result == "handlers/auth.go"

    def test_strip_no_match(self) -> None:
        """'other.com/pkg/main.go' with module 'example.com/pkg' is unchanged."""
        plugin = GoCoverPlugin()
        result = plugin._strip_module_prefix("other.com/pkg/main.go", "example.com/pkg")
        assert result == "other.com/pkg/main.go"

    def test_strip_empty_module_path(self) -> None:
        """Module='' leaves file path unchanged."""
        plugin = GoCoverPlugin()
        result = plugin._strip_module_prefix("example.com/pkg/main.go", "")
        assert result == "example.com/pkg/main.go"

    def test_strip_partial_match_not_directory(self) -> None:
        """'example.com/pkgextra/main.go' with module 'example.com/pkg' is unchanged.

        The '/' check in _strip_module_prefix prevents false partial matches.
        """
        plugin = GoCoverPlugin()
        result = plugin._strip_module_prefix(
            "example.com/pkgextra/main.go", "example.com/pkg"
        )
        assert result == "example.com/pkgextra/main.go"


@go_cover_plugin_available
class TestGoCoverThresholdEdgeCases:
    """Tests for threshold edge cases — synthetic coverage files, no Go needed."""

    def test_exactly_at_threshold_passes(self, tmp_path: Path) -> None:
        """80.0% coverage with threshold=80.0 produces no coverage issue (strict <)."""
        coverfile = tmp_path / "coverage.out"
        # 4 covered, 1 uncovered out of 5 = 80%
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:1.1,2.2 4 1\n"
            "example.com/pkg/main.go:3.1,4.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        threshold_issues = [
            i for i in result.issues if i.rule_id == "coverage_below_threshold"
        ]
        assert len(threshold_issues) == 0

    def test_just_below_threshold(self, tmp_path: Path) -> None:
        """79.99% coverage with threshold=80.0 creates an issue."""
        coverfile = tmp_path / "coverage.out"
        # We need coverage just under 80%. Use 7999/10000 ~ 79.99%
        # 7999 covered statements, 2001 uncovered — but simpler:
        # 3 covered out of 4 = 75%, which is below 80
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:1.1,2.2 3 1\n"
            "example.com/pkg/main.go:3.1,4.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        threshold_issues = [
            i for i in result.issues if i.rule_id == "coverage_below_threshold"
        ]
        assert len(threshold_issues) == 1

    def test_zero_percent_coverage(self, tmp_path: Path) -> None:
        """All uncovered produces severity HIGH."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:1.1,2.2 5 0\n"
            "example.com/pkg/main.go:3.1,4.2 5 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        threshold_issues = [
            i for i in result.issues if i.rule_id == "coverage_below_threshold"
        ]
        assert len(threshold_issues) == 1
        from lucidshark.core.models import Severity

        assert threshold_issues[0].severity == Severity.HIGH

    def test_100_percent_coverage(self, tmp_path: Path) -> None:
        """100% covered produces no issue."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:1.1,2.2 5 1\n"
            "example.com/pkg/main.go:3.1,4.2 5 1\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 80.0
        )
        threshold_issues = [
            i for i in result.issues if i.rule_id == "coverage_below_threshold"
        ]
        assert len(threshold_issues) == 0

    def test_threshold_zero_always_passes(self, tmp_path: Path) -> None:
        """threshold=0.0 never produces a threshold issue."""
        coverfile = tmp_path / "coverage.out"
        coverfile.write_text("mode: set\nexample.com/pkg/main.go:1.1,2.2 5 0\n")
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(coverfile, tmp_path, "example.com/pkg", 0.0)
        threshold_issues = [
            i for i in result.issues if i.rule_id == "coverage_below_threshold"
        ]
        assert len(threshold_issues) == 0

    def test_threshold_100_almost_always_fails(self, tmp_path: Path) -> None:
        """99% coverage with threshold=100 produces an issue."""
        coverfile = tmp_path / "coverage.out"
        # 99 covered, 1 uncovered out of 100 = 99%
        coverfile.write_text(
            "mode: set\n"
            "example.com/pkg/main.go:1.1,2.2 99 1\n"
            "example.com/pkg/main.go:3.1,4.2 1 0\n"
        )
        plugin = GoCoverPlugin()
        result = plugin._parse_coverprofile(
            coverfile, tmp_path, "example.com/pkg", 100.0
        )
        threshold_issues = [
            i for i in result.issues if i.rule_id == "coverage_below_threshold"
        ]
        assert len(threshold_issues) == 1


@go_cover_plugin_available
class TestGoCoverErrorHandling:
    """Tests for measure_coverage error paths — uses mocks, no Go needed."""

    def test_measure_coverage_no_go_mod(self, tmp_path: Path) -> None:
        """No go.mod results in empty CoverageResult."""
        plugin = GoCoverPlugin()
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        result = plugin.measure_coverage(context, threshold=80.0)
        assert result.total_lines == 0
        assert result.tool == "go_cover"

    def test_measure_coverage_empty_coverage_file(self, tmp_path: Path) -> None:
        """Empty coverage.out with threshold=0 produces a no_data issue.

        When threshold > 0, _parse_coverprofile creates a coverage_below_threshold
        issue (since 0% < threshold), which prevents the no_data_issue from being
        appended. Using threshold=0.0 avoids the threshold issue so we can verify
        the no_data fallback path.
        """
        _create_temp_go_project(tmp_path)
        (tmp_path / "coverage.out").write_text("")
        plugin = GoCoverPlugin()
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        result = plugin.measure_coverage(context, threshold=0.0)
        assert result.total_lines == 0
        no_data_issues = [i for i in result.issues if i.rule_id == "no_coverage_data"]
        assert len(no_data_issues) >= 1

    def test_measure_coverage_only_mode_line(self, tmp_path: Path) -> None:
        """Just 'mode: set' with no data and threshold=0 produces a no_data issue.

        Same rationale as test_measure_coverage_empty_coverage_file: threshold=0.0
        avoids a coverage_below_threshold issue blocking the no_data path.
        """
        _create_temp_go_project(tmp_path)
        (tmp_path / "coverage.out").write_text("mode: set\n")
        plugin = GoCoverPlugin()
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        result = plugin.measure_coverage(context, threshold=0.0)
        assert result.total_lines == 0
        no_data_issues = [i for i in result.issues if i.rule_id == "no_coverage_data"]
        assert len(no_data_issues) >= 1
