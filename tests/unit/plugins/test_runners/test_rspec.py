"""Unit tests for RSpec runner plugin."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.test_runners.rspec import RspecRunner


class TestRspecRunner:
    """Tests for RspecRunner class."""

    def test_name(self) -> None:
        runner = RspecRunner()
        assert runner.name == "rspec"

    def test_languages(self) -> None:
        runner = RspecRunner()
        assert runner.languages == ["ruby"]

    def test_domain(self) -> None:
        runner = RspecRunner()
        assert runner.domain == ToolDomain.TESTING


class TestRspecRunnerBinaryFinding:
    """Tests for binary finding logic."""

    def test_find_in_binstubs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            bin_dir = project_root / "bin"
            bin_dir.mkdir()
            rspec_bin = bin_dir / "rspec"
            rspec_bin.touch()
            rspec_bin.chmod(0o755)

            runner = RspecRunner(project_root=project_root)
            binary = runner.ensure_binary()
            assert binary == rspec_bin

    @patch("shutil.which")
    def test_find_in_system_path(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/local/bin/rspec"
        runner = RspecRunner()
        binary = runner.ensure_binary()
        assert binary == Path("/usr/local/bin/rspec")

    @patch("shutil.which")
    def test_not_found_raises_error(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        runner = RspecRunner()
        with pytest.raises(FileNotFoundError) as exc:
            runner.ensure_binary()
        assert "RSpec is not installed" in str(exc.value)


class TestRspecJsonParsing:
    """Tests for JSON output parsing."""

    def test_parse_all_passing(self) -> None:
        runner = RspecRunner()
        output = json.dumps({
            "version": "3.12.0",
            "examples": [
                {
                    "id": "./spec/user_spec.rb[1:1]",
                    "description": "is valid",
                    "full_description": "User is valid",
                    "status": "passed",
                    "file_path": "./spec/user_spec.rb",
                    "line_number": 5,
                    "run_time": 0.012,
                },
                {
                    "id": "./spec/user_spec.rb[1:2]",
                    "description": "has a name",
                    "full_description": "User has a name",
                    "status": "passed",
                    "file_path": "./spec/user_spec.rb",
                    "line_number": 10,
                    "run_time": 0.003,
                },
            ],
            "summary": {
                "duration": 0.015,
                "example_count": 2,
                "failure_count": 0,
                "pending_count": 0,
                "errors_outside_of_examples_count": 0,
            },
        })
        result = runner._parse_json_output(output, Path("/project"))
        assert result.passed == 2
        assert result.failed == 0
        assert result.skipped == 0
        assert result.issues == []

    def test_parse_with_failures(self) -> None:
        runner = RspecRunner()
        output = json.dumps({
            "version": "3.12.0",
            "examples": [
                {
                    "id": "./spec/user_spec.rb[1:1]",
                    "description": "is valid",
                    "full_description": "User is valid",
                    "status": "passed",
                    "file_path": "./spec/user_spec.rb",
                    "line_number": 5,
                    "run_time": 0.012,
                },
                {
                    "id": "./spec/user_spec.rb[1:2]",
                    "description": "validates name",
                    "full_description": "User validates name",
                    "status": "failed",
                    "file_path": "./spec/user_spec.rb",
                    "line_number": 10,
                    "run_time": 0.005,
                    "exception": {
                        "class": "RSpec::Expectations::ExpectationNotMetError",
                        "message": "expected true\n     got false",
                        "backtrace": [
                            "./spec/user_spec.rb:10:in `block (2 levels) in <top>'"
                        ],
                    },
                },
            ],
            "summary": {
                "duration": 0.017,
                "example_count": 2,
                "failure_count": 1,
                "pending_count": 0,
                "errors_outside_of_examples_count": 0,
            },
        })
        result = runner._parse_json_output(output, Path("/project"))
        assert result.passed == 1
        assert result.failed == 1
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.severity == Severity.HIGH
        assert issue.domain == ToolDomain.TESTING
        assert issue.source_tool == "rspec"
        assert issue.line_start == 10

    def test_parse_with_pending(self) -> None:
        runner = RspecRunner()
        output = json.dumps({
            "examples": [
                {
                    "id": "./spec/a_spec.rb[1:1]",
                    "description": "pending test",
                    "full_description": "A pending test",
                    "status": "pending",
                    "file_path": "./spec/a_spec.rb",
                    "line_number": 3,
                    "run_time": 0.001,
                    "pending_message": "Not yet implemented",
                },
            ],
            "summary": {
                "duration": 0.001,
                "example_count": 1,
                "failure_count": 0,
                "pending_count": 1,
                "errors_outside_of_examples_count": 0,
            },
        })
        result = runner._parse_json_output(output, Path("/project"))
        assert result.passed == 0
        assert result.skipped == 1
        assert result.issues == []

    def test_parse_empty_output(self) -> None:
        runner = RspecRunner()
        result = runner._parse_json_output("", Path("/project"))
        assert result.passed == 0
        assert result.failed == 0

    def test_parse_invalid_json(self) -> None:
        runner = RspecRunner()
        result = runner._parse_json_output("not json", Path("/project"))
        assert result.passed == 0


class TestRspecAssertionExtraction:
    """Tests for assertion extraction from error messages."""

    def test_extract_expected_message(self) -> None:
        runner = RspecRunner()
        message = "expected true\n     got false"
        assertion = runner._extract_assertion(message)
        assert "expected" in assertion

    def test_extract_to_eq_message(self) -> None:
        runner = RspecRunner()
        message = "expected 1 to eq 2"
        assertion = runner._extract_assertion(message)
        assert "to eq" in assertion

    def test_extract_empty_message(self) -> None:
        runner = RspecRunner()
        assert runner._extract_assertion("") == ""

    def test_fallback_to_first_line(self) -> None:
        runner = RspecRunner()
        message = "Some error occurred\nmore details"
        assertion = runner._extract_assertion(message)
        assert "Some error occurred" in assertion


class TestRspecIssueId:
    """Tests for deterministic issue ID generation."""

    def test_id_starts_with_rspec(self) -> None:
        runner = RspecRunner()
        issue_id = runner._generate_issue_id("User is valid", "expected true")
        assert issue_id.startswith("rspec-")

    def test_id_is_deterministic(self) -> None:
        runner = RspecRunner()
        id1 = runner._generate_issue_id("test name", "assertion")
        id2 = runner._generate_issue_id("test name", "assertion")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        runner = RspecRunner()
        id1 = runner._generate_issue_id("test A", "assertion")
        id2 = runner._generate_issue_id("test B", "assertion")
        assert id1 != id2


class TestRspecExecutionFailure:
    """Tests for execution failure handling."""

    def test_execution_failure_result(self) -> None:
        runner = RspecRunner()
        result = runner._execution_failure_result(["rspec", "--format", "json"])
        assert result.errors == 1
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.HIGH
        assert "RSpec failed to execute" in result.issues[0].title
