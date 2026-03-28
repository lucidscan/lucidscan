"""Unit tests for RuboCop formatter plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.formatters.rubocop_format import (
    RubocopFormatter,
    RUBY_EXTENSIONS,
)


def make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestRubocopFormatterProperties:
    """Tests for RubocopFormatter basic properties."""

    def test_name(self) -> None:
        formatter = RubocopFormatter()
        assert formatter.name == "rubocop_format"

    def test_languages(self) -> None:
        formatter = RubocopFormatter()
        assert formatter.languages == ["ruby"]

    def test_domain(self) -> None:
        formatter = RubocopFormatter()
        assert formatter.domain == ToolDomain.FORMATTING

    def test_supports_fix(self) -> None:
        formatter = RubocopFormatter()
        assert formatter.supports_fix is True

    def test_ruby_extensions(self) -> None:
        assert ".rb" in RUBY_EXTENSIONS
        assert ".rake" in RUBY_EXTENSIONS
        assert ".gemspec" in RUBY_EXTENSIONS


class TestRubocopFormatterCheck:
    """Tests for RubocopFormatter.check()."""

    def test_check_no_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.rb").write_text("x = 1\n")

            formatter = RubocopFormatter(project_root=project_root)
            context = ScanContext(
                project_root=project_root,
                paths=[project_root / "test.rb"],
                enabled_domains=[ToolDomain.FORMATTING],
            )

            output = json.dumps({
                "files": [{"path": "test.rb", "offenses": []}],
                "summary": {"offense_count": 0},
            })
            result = make_completed_process(0, output)
            with (
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/rubocop")
                ),
                patch(
                    "lucidshark.plugins.formatters.rubocop_format.run_with_streaming",
                    return_value=result,
                ),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_with_formatting_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.rb").write_text("x=1\n")

            formatter = RubocopFormatter(project_root=project_root)
            context = ScanContext(
                project_root=project_root,
                paths=[project_root / "test.rb"],
                enabled_domains=[ToolDomain.FORMATTING],
            )

            output = json.dumps({
                "files": [
                    {
                        "path": "test.rb",
                        "offenses": [
                            {
                                "severity": "convention",
                                "message": "Surrounding space missing for operator `=`.",
                                "cop_name": "Layout/SpaceAroundOperators",
                                "corrected": False,
                                "correctable": True,
                                "location": {
                                    "start_line": 1,
                                    "start_column": 2,
                                    "last_line": 1,
                                    "last_column": 2,
                                    "line": 1,
                                    "column": 2,
                                },
                            }
                        ],
                    }
                ],
                "summary": {"offense_count": 1},
            })
            result = make_completed_process(1, output)
            with (
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/rubocop")
                ),
                patch(
                    "lucidshark.plugins.formatters.rubocop_format.run_with_streaming",
                    return_value=result,
                ),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert issues[0].domain == ToolDomain.FORMATTING
                assert issues[0].severity == Severity.LOW
                assert issues[0].fixable is True
                assert "Layout/SpaceAroundOperators" in issues[0].rule_id


class TestRubocopFormatterParseOutput:
    """Tests for output parsing."""

    def test_parse_empty_output(self) -> None:
        formatter = RubocopFormatter()
        issues = formatter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_invalid_json(self) -> None:
        formatter = RubocopFormatter()
        issues = formatter._parse_output("not json", Path("/project"))
        assert issues == []

    def test_parse_no_offenses(self) -> None:
        formatter = RubocopFormatter()
        output = json.dumps({
            "files": [{"path": "test.rb", "offenses": []}],
            "summary": {"offense_count": 0},
        })
        issues = formatter._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_with_offenses(self) -> None:
        formatter = RubocopFormatter()
        output = json.dumps({
            "files": [
                {
                    "path": "test.rb",
                    "offenses": [
                        {
                            "severity": "convention",
                            "message": "Bad indentation",
                            "cop_name": "Layout/IndentationWidth",
                            "corrected": False,
                            "correctable": True,
                            "location": {"line": 5, "column": 1},
                        }
                    ],
                }
            ]
        })
        issues = formatter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].source_tool == "rubocop_format"
        assert issues[0].domain == ToolDomain.FORMATTING

    def test_parse_multiple_files(self) -> None:
        formatter = RubocopFormatter()
        output = json.dumps({
            "files": [
                {
                    "path": "a.rb",
                    "offenses": [
                        {
                            "cop_name": "Layout/A",
                            "message": "a",
                            "correctable": True,
                            "location": {"line": 1},
                        }
                    ],
                },
                {
                    "path": "b.rb",
                    "offenses": [
                        {
                            "cop_name": "Layout/B",
                            "message": "b",
                            "correctable": False,
                            "location": {"line": 2},
                        }
                    ],
                },
            ]
        })
        issues = formatter._parse_output(output, Path("/project"))
        assert len(issues) == 2


class TestRubocopFormatterFix:
    """Tests for fix() method."""

    def test_fix_returns_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.rb").write_text("x=1\n")

            formatter = RubocopFormatter(project_root=project_root)
            context = ScanContext(
                project_root=project_root,
                paths=[project_root / "test.rb"],
                enabled_domains=[ToolDomain.FORMATTING],
            )

            output = json.dumps({
                "files": [
                    {
                        "path": "test.rb",
                        "offenses": [
                            {
                                "cop_name": "Layout/SpaceAroundOperators",
                                "message": "fixed",
                                "corrected": True,
                                "correctable": True,
                                "location": {"line": 1, "column": 2},
                            }
                        ],
                    }
                ]
            })
            result = make_completed_process(0, output)
            with (
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/rubocop")
                ),
                patch(
                    "lucidshark.plugins.formatters.rubocop_format.run_with_streaming",
                    return_value=result,
                ),
            ):
                fix_result = formatter.fix(context)
                assert fix_result.issues_fixed == 1
