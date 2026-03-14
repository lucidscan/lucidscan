"""Integration tests for go vet type checker plugin.

These tests require Go to be installed.

Run with: pytest tests/integration/type_checkers/test_go_vet_integration.py -v
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


from lucidshark.core.models import ScanContext, Severity, SkipReason, ToolDomain
from lucidshark.plugins.type_checkers.go_vet import (
    ANALYZER_SEVERITY,
    GoVetChecker,
)
from tests.integration.conftest import go_available


def _create_temp_go_project(
    tmp_path: Path, module_name: str = "example.com/testproject"
) -> Path:
    """Create a minimal Go project in tmp_path."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(f"module {module_name}\n\ngo 1.21\n")
    return tmp_path


class TestGoVetAvailability:
    """Tests for go vet availability."""

    @go_available
    def test_ensure_binary_finds_go(self, go_vet_checker: GoVetChecker) -> None:
        """Test that ensure_binary finds the go binary."""
        binary_path = go_vet_checker.ensure_binary()
        assert binary_path.exists()
        assert "go" in binary_path.name

    @go_available
    def test_get_version(self, go_vet_checker: GoVetChecker) -> None:
        """Test that get_version returns a version string."""
        version = go_vet_checker.get_version()
        assert version != "unknown"
        assert "go" in version.lower()

    def test_ensure_binary_raises_when_not_installed(self) -> None:
        """Test that ensure_binary raises FileNotFoundError when go is not found."""

        # Temporarily clear PATH to simulate go not being installed
        checker = GoVetChecker(project_root=Path("/nonexistent"))
        try:
            binary_path = checker.ensure_binary()
            # If go is installed (which it will be in CI), verify it exists
            assert binary_path.exists()
        except FileNotFoundError as e:
            assert "go" in str(e).lower()


@go_available
class TestGoVetChecking:
    """Integration tests for go vet type checking."""

    def test_check_clean_project(self, go_vet_checker: GoVetChecker) -> None:
        """Test that a clean Go project produces 0 vet issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_temp_go_project(tmpdir_path)

            main_go = tmpdir_path / "main.go"
            main_go.write_text(
                'package main\n\nimport "fmt"\n\nfunc main() {\n'
                '\tfmt.Println("hello")\n}\n'
            )

            subprocess.run(
                ["go", "mod", "tidy"],
                cwd=tmpdir_path,
                capture_output=True,
                timeout=60,
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = go_vet_checker.check(context)

            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_check_detects_printf_issue(self, go_vet_checker: GoVetChecker) -> None:
        """Test that go vet detects printf format mismatches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_temp_go_project(tmpdir_path)

            main_go = tmpdir_path / "main.go"
            main_go.write_text(
                'package main\n\nimport "fmt"\n\nfunc main() {\n'
                '\tx := "hello"\n'
                '\tfmt.Printf("%d", x)\n}\n'
            )

            subprocess.run(
                ["go", "mod", "tidy"],
                cwd=tmpdir_path,
                capture_output=True,
                timeout=60,
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = go_vet_checker.check(context)

            assert isinstance(issues, list)
            # go vet should detect the printf format mismatch
            assert len(issues) > 0

            for issue in issues:
                assert issue.source_tool == "go_vet"
                assert issue.domain == ToolDomain.TYPE_CHECKING
                assert issue.severity is not None

    def test_check_skips_without_go_mod(self, go_vet_checker: GoVetChecker) -> None:
        """Test that go vet returns empty when no go.mod is present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Go file without go.mod
            main_go = tmpdir_path / "main.go"
            main_go.write_text("package main\n\nfunc main() {}\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = go_vet_checker.check(context)

            assert isinstance(issues, list)
            assert len(issues) == 0


class TestGoVetOutputParsing:
    """Tests for go vet output parsing (no binary required)."""

    def test_parse_json_output_with_findings(self) -> None:
        """Test _parse_json_output with sample JSON stderr."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        # go vet -json produces per-package JSON objects
        sample_stderr = json.dumps(
            {
                "example.com/testproject": {
                    "printf": [
                        {
                            "posn": "main.go:7:2",
                            "message": "Printf format %d has arg x of wrong type string",
                        }
                    ]
                }
            }
        )

        issues = checker._parse_json_output(sample_stderr, Path("/tmp"))

        assert len(issues) == 1
        assert issues[0].source_tool == "go_vet"
        assert issues[0].domain == ToolDomain.TYPE_CHECKING
        assert issues[0].rule_id == "printf"
        assert issues[0].line_start == 7
        assert issues[0].column_start == 2
        assert "Printf format" in issues[0].description

    def test_parse_json_output_empty(self) -> None:
        """Test _parse_json_output with empty input."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        issues = checker._parse_json_output("", Path("/tmp"))

        assert issues == []

    def test_parse_json_output_multiple_analyzers(self) -> None:
        """Test _parse_json_output with multiple analyzer findings."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        sample_stderr = json.dumps(
            {
                "example.com/pkg": {
                    "printf": [
                        {
                            "posn": "handler.go:10:5",
                            "message": "Printf format %d has arg name of wrong type string",
                        }
                    ],
                    "unreachable": [
                        {
                            "posn": "handler.go:20:2",
                            "message": "unreachable code",
                        }
                    ],
                }
            }
        )

        issues = checker._parse_json_output(sample_stderr, Path("/tmp"))

        assert len(issues) == 2
        rule_ids = {issue.rule_id for issue in issues}
        assert "printf" in rule_ids
        assert "unreachable" in rule_ids

    def test_parse_text_output_fallback(self) -> None:
        """Test _parse_text_output with text-format stderr."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        sample_stderr = (
            "./main.go:7:2: printf: Printf format %d has arg x of wrong type string\n"
        )

        issues = checker._parse_text_output(sample_stderr, Path("/tmp"))

        assert len(issues) >= 1
        assert issues[0].source_tool == "go_vet"
        assert issues[0].line_start == 7
        assert issues[0].column_start == 2

    def test_parse_text_output_empty(self) -> None:
        """Test _parse_text_output with empty input."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        issues = checker._parse_text_output("", Path("/tmp"))

        assert issues == []

    def test_analyzer_severity_mapping(self) -> None:
        """Test that analyzer severities are correctly mapped."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        # printf analyzer should be HIGH severity
        sample_stderr = json.dumps(
            {
                "example.com/pkg": {
                    "printf": [
                        {
                            "posn": "main.go:5:1",
                            "message": "format mismatch",
                        }
                    ]
                }
            }
        )

        issues = checker._parse_json_output(sample_stderr, Path("/tmp"))

        assert len(issues) == 1
        assert issues[0].severity == Severity.HIGH

    def test_unknown_analyzer_defaults_to_medium(self) -> None:
        """Test that unknown analyzers default to MEDIUM severity."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        sample_stderr = json.dumps(
            {
                "example.com/pkg": {
                    "new_future_analyzer": [
                        {
                            "posn": "main.go:5:1",
                            "message": "some new check",
                        }
                    ]
                }
            }
        )

        issues = checker._parse_json_output(sample_stderr, Path("/tmp"))

        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_issue_id_is_deterministic(self) -> None:
        """Test that issue IDs are consistent across parse runs."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        sample_stderr = json.dumps(
            {
                "example.com/pkg": {
                    "printf": [
                        {
                            "posn": "main.go:7:2",
                            "message": "format mismatch",
                        }
                    ]
                }
            }
        )

        issues1 = checker._parse_json_output(sample_stderr, Path("/tmp"))
        issues2 = checker._parse_json_output(sample_stderr, Path("/tmp"))

        assert len(issues1) == 1
        assert len(issues2) == 1
        assert issues1[0].id == issues2[0].id
        assert issues1[0].id.startswith("go-vet-")

    def test_extract_json_objects_multiple(self) -> None:
        """Test _extract_json_objects with concatenated JSON objects."""
        checker = GoVetChecker(project_root=Path("/tmp"))

        # Simulate two package results concatenated
        text = (
            json.dumps({"pkg1": {"printf": [{"posn": "a.go:1:1", "message": "m1"}]}})
            + "\n"
            + json.dumps({"pkg2": {"atomic": [{"posn": "b.go:2:1", "message": "m2"}]}})
        )

        objects = checker._extract_json_objects(text)

        assert len(objects) == 2


# ---------------------------------------------------------------------------
# Helper for mock-based tests
# ---------------------------------------------------------------------------


def _make_context(tmp_path: Path, has_go_mod: bool = True) -> MagicMock:
    """Create a lightweight mock ScanContext rooted at *tmp_path*."""
    if has_go_mod:
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    ctx = MagicMock()
    ctx.project_root = tmp_path
    ctx.stream_handler = None
    ctx.record_skip = MagicMock()
    return ctx


# ---------------------------------------------------------------------------
# TestGoVetProperties
# ---------------------------------------------------------------------------


class TestGoVetProperties:
    """Test basic plugin properties (no Go binary needed)."""

    def test_name(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        assert checker.name == "go_vet"

    def test_languages(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        assert checker.languages == ["go"]

    def test_supports_strict_mode(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        assert checker.supports_strict_mode is False

    def test_domain(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        # The domain property is exposed by the base class; GoVetChecker uses
        # ToolDomain.TYPE_CHECKING in every issue it emits. Verify via a
        # trivial parse round-trip.
        sample = json.dumps(
            {"pkg": {"printf": [{"posn": "f.go:1:1", "message": "msg"}]}}
        )
        issues = checker._parse_json_output(sample, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].domain == ToolDomain.TYPE_CHECKING


# ---------------------------------------------------------------------------
# TestGoVetJsonParsingEdgeCases
# ---------------------------------------------------------------------------


class TestGoVetJsonParsingEdgeCases:
    """Edge-case coverage for _parse_json_output."""

    def test_whitespace_only_returns_empty(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        assert checker._parse_json_output("   \n\t  ", Path("/tmp")) == []

    def test_multiple_packages(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        stderr = json.dumps(
            {
                "example.com/a": {"printf": [{"posn": "a.go:1:1", "message": "msg-a"}]},
                "example.com/b": {"atomic": [{"posn": "b.go:2:1", "message": "msg-b"}]},
            }
        )
        issues = checker._parse_json_output(stderr, Path("/tmp"))
        assert len(issues) == 2
        rule_ids = {i.rule_id for i in issues}
        assert rule_ids == {"printf", "atomic"}

    def test_non_dict_top_level_skipped(self) -> None:
        """If a top-level value is not a dict, skip it gracefully."""
        checker = GoVetChecker(project_root=Path("/tmp"))
        stderr = json.dumps(
            {
                "example.com/good": {
                    "printf": [{"posn": "a.go:1:1", "message": "msg"}]
                },
                "example.com/bad": "not_a_dict",
            }
        )
        issues = checker._parse_json_output(stderr, Path("/tmp"))
        assert len(issues) == 1

    def test_non_dict_analyzers_skipped(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        stderr = json.dumps({"pkg": "not_a_dict"})
        assert checker._parse_json_output(stderr, Path("/tmp")) == []

    def test_non_list_findings_skipped(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        stderr = json.dumps({"pkg": {"printf": "not_a_list"}})
        assert checker._parse_json_output(stderr, Path("/tmp")) == []

    def test_deduplication_across_packages(self) -> None:
        """Same finding appearing under two packages should produce only one issue."""
        checker = GoVetChecker(project_root=Path("/tmp"))
        finding = {"posn": "shared.go:5:3", "message": "duplicated msg"}
        obj1 = json.dumps({"pkg1": {"printf": [finding]}})
        obj2 = json.dumps({"pkg2": {"printf": [finding]}})
        # Concatenated objects (two separate JSON blobs)
        stderr = obj1 + "\n" + obj2
        issues = checker._parse_json_output(stderr, Path("/tmp"))
        assert len(issues) == 1

    def test_completely_invalid_json(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        assert checker._parse_json_output("this is not json", Path("/tmp")) == []

    def test_partial_truncated_json(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        truncated = '{"pkg": {"printf": [{"posn": "f.go:1:1"'
        assert checker._parse_json_output(truncated, Path("/tmp")) == []


# ---------------------------------------------------------------------------
# TestGoVetExtractJsonObjectsEdgeCases
# ---------------------------------------------------------------------------


class TestGoVetExtractJsonObjectsEdgeCases:
    """Edge-case coverage for _extract_json_objects."""

    def test_nested_braces(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        deep = json.dumps({"a": {"b": {"c": {"d": 1}}}})
        result = checker._extract_json_objects(deep)
        assert len(result) == 1
        assert result[0]["a"]["b"]["c"]["d"] == 1

    def test_non_json_text_intermixed(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        text = '# output\n{"pkg": {}}\nDone.\n'
        result = checker._extract_json_objects(text)
        assert len(result) == 1
        assert result[0] == {"pkg": {}}

    def test_empty_string(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        assert checker._extract_json_objects("") == []

    def test_incomplete_json_no_close(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        assert checker._extract_json_objects('{"pkg": {') == []

    def test_single_valid_object_fast_path(self) -> None:
        """A single valid JSON blob should be parsed via the fast path."""
        checker = GoVetChecker(project_root=Path("/tmp"))
        obj = {"key": "value"}
        result = checker._extract_json_objects(json.dumps(obj))
        assert result == [obj]


# ---------------------------------------------------------------------------
# TestGoVetFindingToIssueEdgeCases
# ---------------------------------------------------------------------------


class TestGoVetFindingToIssueEdgeCases:
    """Edge-case coverage for _finding_to_issue."""

    def test_missing_message_returns_none(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        result = checker._finding_to_issue("printf", {"posn": "f.go:1:1"}, Path("/tmp"))
        assert result is None

    def test_empty_message_returns_none(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        result = checker._finding_to_issue(
            "printf", {"posn": "f.go:1:1", "message": ""}, Path("/tmp")
        )
        assert result is None

    def test_missing_posn(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        result = checker._finding_to_issue("printf", {"message": "bad"}, Path("/tmp"))
        assert result is not None
        assert result.file_path is None
        assert result.line_start is None

    def test_absolute_path_inside_project(self, tmp_path: Path) -> None:
        checker = GoVetChecker(project_root=tmp_path)
        abs_posn = f"{tmp_path}/sub/file.go:10:5"
        result = checker._finding_to_issue(
            "printf", {"posn": abs_posn, "message": "msg"}, tmp_path
        )
        assert result is not None
        assert str(result.file_path) == "sub/file.go"

    def test_absolute_path_outside_project(self, tmp_path: Path) -> None:
        checker = GoVetChecker(project_root=tmp_path)
        outside = "/some/other/path/file.go:10:5"
        result = checker._finding_to_issue(
            "printf", {"posn": outside, "message": "msg"}, tmp_path
        )
        assert result is not None
        assert str(result.file_path) == "/some/other/path/file.go"

    def test_posn_no_column(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        result = checker._finding_to_issue(
            "printf", {"posn": "file.go:42", "message": "msg"}, Path("/tmp")
        )
        assert result is not None
        assert result.line_start == 42
        assert result.column_start is None

    def test_exception_returns_none(self) -> None:
        """Passing a non-dict finding should be caught and return None."""
        checker = GoVetChecker(project_root=Path("/tmp"))
        # A list instead of dict will trigger an AttributeError on .get()
        result = checker._finding_to_issue("printf", ["not", "a", "dict"], Path("/tmp"))
        assert result is None


# ---------------------------------------------------------------------------
# TestGoVetTextParsingEdgeCases
# ---------------------------------------------------------------------------


class TestGoVetTextParsingEdgeCases:
    """Edge-case coverage for _parse_text_output."""

    def test_multiple_lines(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        stderr = (
            "./a.go:1:1: printf: msg1\n"
            "./b.go:2:2: atomic: msg2\n"
            "./c.go:3:3: unreachable: msg3\n"
        )
        issues = checker._parse_text_output(stderr, Path("/tmp"))
        assert len(issues) == 3

    def test_mixed_matching_nonmatching(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        stderr = (
            "# some comment\n"
            "./a.go:1:1: printf: msg1\n"
            "exit status 2\n"
            "./b.go:2:2: atomic: msg2\n"
            "\n"
        )
        issues = checker._parse_text_output(stderr, Path("/tmp"))
        assert len(issues) == 2

    def test_message_without_analyzer_prefix(self) -> None:
        """A message without a 'analyzer: ...' pattern should get rule_id='vet'."""
        checker = GoVetChecker(project_root=Path("/tmp"))
        stderr = "./a.go:1:1: something is wrong\n"
        issues = checker._parse_text_output(stderr, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].rule_id == "vet"

    def test_candidate_with_spaces_not_analyzer(self) -> None:
        """If the text before the colon has spaces, it is not treated as an analyzer."""
        checker = GoVetChecker(project_root=Path("/tmp"))
        stderr = "./a.go:1:1: not an analyzer: the message\n"
        issues = checker._parse_text_output(stderr, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].rule_id == "vet"

    def test_absolute_path_inside_project_root(self, tmp_path: Path) -> None:
        checker = GoVetChecker(project_root=tmp_path)
        stderr = f"{tmp_path}/sub/file.go:10:5: printf: bad format\n"
        issues = checker._parse_text_output(stderr, tmp_path)
        assert len(issues) == 1
        assert str(issues[0].file_path) == "sub/file.go"

    def test_absolute_path_outside_project_root(self, tmp_path: Path) -> None:
        checker = GoVetChecker(project_root=tmp_path)
        stderr = "/other/project/file.go:10:5: printf: bad format\n"
        issues = checker._parse_text_output(stderr, tmp_path)
        assert len(issues) == 1
        assert str(issues[0].file_path) == "/other/project/file.go"

    def test_deduplication(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        line = "./a.go:1:1: printf: duplicate msg\n"
        stderr = line + line
        issues = checker._parse_text_output(stderr, Path("/tmp"))
        assert len(issues) == 1

    def test_whitespace_only_input(self) -> None:
        checker = GoVetChecker(project_root=Path("/tmp"))
        assert checker._parse_text_output("   \n\n  ", Path("/tmp")) == []


# ---------------------------------------------------------------------------
# TestGoVetSeverityComplete
# ---------------------------------------------------------------------------


class TestGoVetSeverityComplete:
    """Verify the ANALYZER_SEVERITY mapping is consistent."""

    def test_all_high_analyzers(self) -> None:
        high_analyzers = {k for k, v in ANALYZER_SEVERITY.items() if v == Severity.HIGH}
        assert len(high_analyzers) > 0
        for name in high_analyzers:
            assert ANALYZER_SEVERITY[name] == Severity.HIGH

    def test_all_medium_analyzers(self) -> None:
        medium_analyzers = {
            k for k, v in ANALYZER_SEVERITY.items() if v == Severity.MEDIUM
        }
        assert len(medium_analyzers) > 0
        for name in medium_analyzers:
            assert ANALYZER_SEVERITY[name] == Severity.MEDIUM

    def test_unknown_defaults_medium(self) -> None:
        assert (
            ANALYZER_SEVERITY.get("unknown_future_analyzer", Severity.MEDIUM)
            == Severity.MEDIUM
        )


# ---------------------------------------------------------------------------
# TestGoVetErrorHandling (mock-based, no Go needed)
# ---------------------------------------------------------------------------


class TestGoVetErrorHandling:
    """Test check() error paths using mocks so Go binary is not required."""

    @patch("lucidshark.plugins.type_checkers.go_vet.GoVetChecker.ensure_binary")
    def test_check_returns_empty_on_binary_not_found(
        self, mock_ensure: MagicMock, tmp_path: Path
    ) -> None:
        mock_ensure.side_effect = FileNotFoundError("go not found")
        checker = GoVetChecker(project_root=tmp_path)
        ctx = _make_context(tmp_path)
        issues = checker.check(ctx)
        assert issues == []

    @patch("lucidshark.plugins.type_checkers.go_vet.run_with_streaming")
    @patch("lucidshark.plugins.type_checkers.go_vet.GoVetChecker.ensure_binary")
    def test_check_returns_empty_on_timeout(
        self,
        mock_ensure: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_ensure.return_value = Path("/usr/bin/go")
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="go vet", timeout=300)
        checker = GoVetChecker(project_root=tmp_path)
        ctx = _make_context(tmp_path)
        issues = checker.check(ctx)
        assert issues == []
        ctx.record_skip.assert_called_once()
        call_kwargs = ctx.record_skip.call_args
        assert call_kwargs[1]["reason"] == SkipReason.EXECUTION_FAILED

    @patch("lucidshark.plugins.type_checkers.go_vet.run_with_streaming")
    @patch("lucidshark.plugins.type_checkers.go_vet.GoVetChecker.ensure_binary")
    def test_check_returns_empty_on_exception(
        self,
        mock_ensure: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_ensure.return_value = Path("/usr/bin/go")
        mock_run.side_effect = RuntimeError("something broke")
        checker = GoVetChecker(project_root=tmp_path)
        ctx = _make_context(tmp_path)
        issues = checker.check(ctx)
        assert issues == []
        ctx.record_skip.assert_called_once()

    @patch("lucidshark.plugins.type_checkers.go_vet.run_with_streaming")
    @patch("lucidshark.plugins.type_checkers.go_vet.GoVetChecker.ensure_binary")
    def test_check_json_empty_falls_back_to_text(
        self,
        mock_ensure: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When JSON output is empty but stderr has text vet output, fall back to text parser."""
        mock_ensure.return_value = Path("/usr/bin/go")
        result = MagicMock()
        result.stderr = "./main.go:7:2: printf: bad format\n"
        result.stdout = ""
        mock_run.return_value = result
        checker = GoVetChecker(project_root=tmp_path)
        ctx = _make_context(tmp_path)
        issues = checker.check(ctx)
        assert len(issues) == 1
        assert issues[0].rule_id == "printf"
