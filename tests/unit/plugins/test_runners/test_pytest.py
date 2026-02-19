"""Unit tests for pytest runner plugin."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.test_runners.pytest import PytestRunner


class TestPytestRunner:
    """Tests for PytestRunner class."""

    def test_name(self) -> None:
        """Test plugin name."""
        runner = PytestRunner()
        assert runner.name == "pytest"

    def test_languages(self) -> None:
        """Test supported languages."""
        runner = PytestRunner()
        assert runner.languages == ["python"]

    def test_domain(self) -> None:
        """Test domain is TESTING."""
        runner = PytestRunner()
        assert runner.domain == ToolDomain.TESTING


class TestPytestRunnerBinaryFinding:
    """Tests for binary finding logic."""

    def test_find_in_venv(self) -> None:
        """Test finding pytest in project .venv."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            pytest_bin = venv_bin / "pytest"
            pytest_bin.touch()
            pytest_bin.chmod(0o755)

            runner = PytestRunner(project_root=project_root)
            binary = runner.ensure_binary()

            assert binary == pytest_bin

    @patch("shutil.which")
    def test_find_in_system_path(self, mock_which: MagicMock) -> None:
        """Test finding pytest in system PATH."""
        mock_which.return_value = "/usr/local/bin/pytest"

        runner = PytestRunner()
        binary = runner.ensure_binary()

        assert binary == Path("/usr/local/bin/pytest")

    @patch("shutil.which")
    def test_not_found_raises_error(self, mock_which: MagicMock) -> None:
        """Test FileNotFoundError when pytest not found."""
        mock_which.return_value = None

        runner = PytestRunner()
        with pytest.raises(FileNotFoundError) as exc:
            runner.ensure_binary()

        assert "pytest is not installed" in str(exc.value)


class TestPytestJsonParsing:
    """Tests for JSON report parsing."""

    def test_parse_json_report_with_failures(self) -> None:
        """Test parsing JSON report with test failures."""
        runner = PytestRunner()

        report = {
            "summary": {
                "passed": 5,
                "failed": 2,
                "skipped": 1,
                "error": 0,
                "xfailed": 0,
            },
            "duration": 1.5,
            "tests": [
                {
                    "nodeid": "tests/test_example.py::test_success",
                    "outcome": "passed",
                },
                {
                    "nodeid": "tests/test_example.py::test_failure",
                    "outcome": "failed",
                    "lineno": 10,
                    "call": {
                        "longrepr": "assert 1 == 2\nAssertionError: assert 1 == 2",
                        "duration": 0.01,
                        "crash": {"lineno": 10},
                    },
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "report.json"
            report_file.write_text(json.dumps(report))

            result = runner._parse_json_report(report_file, project_root)

            assert result.passed == 5
            assert result.failed == 2
            assert result.skipped == 1
            assert result.errors == 0
            assert result.duration_ms == 1500
            assert len(result.issues) == 1

            issue = result.issues[0]
            assert "test_failure" in issue.title
            assert issue.severity == Severity.HIGH
            assert issue.domain == ToolDomain.TESTING
            assert issue.source_tool == "pytest"

    def test_parse_json_report_all_passed(self) -> None:
        """Test parsing JSON report with all tests passed."""
        runner = PytestRunner()

        report = {
            "summary": {
                "passed": 10,
                "failed": 0,
                "skipped": 0,
                "error": 0,
                "xfailed": 0,
            },
            "duration": 2.0,
            "tests": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "report.json"
            report_file.write_text(json.dumps(report))

            result = runner._parse_json_report(report_file, project_root)

            assert result.passed == 10
            assert result.failed == 0
            assert result.success is True
            assert len(result.issues) == 0


class TestPytestJunitParsing:
    """Tests for JUnit XML parsing."""

    def test_parse_junit_xml_with_failures(self) -> None:
        """Test parsing JUnit XML with test failures."""
        runner = PytestRunner()

        junit_xml = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="pytest" tests="3" failures="1" errors="0" skipped="0" time="1.5">
            <testcase classname="tests.test_example" name="test_success" time="0.1"/>
            <testcase classname="tests.test_example" name="test_failure" file="tests/test_example.py" line="10" time="0.05">
                <failure message="AssertionError: assert 1 == 2">
                assert 1 == 2
                </failure>
            </testcase>
        </testsuite>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "junit.xml"
            report_file.write_text(junit_xml)

            result = runner._parse_junit_xml(report_file, project_root)

            assert result.passed == 2
            assert result.failed == 1
            assert result.errors == 0
            assert result.duration_ms == 1500
            assert len(result.issues) == 1

            issue = result.issues[0]
            assert "test_failure" in issue.title
            assert issue.severity == Severity.HIGH


class TestPytestAssertionExtraction:
    """Tests for assertion message extraction."""

    def test_extract_assertion_error(self) -> None:
        """Test extracting AssertionError message."""
        runner = PytestRunner()

        longrepr = """
>       assert user.is_authenticated
E       AssertionError: False is not true
        """

        result = runner._extract_assertion_message(longrepr)
        assert "False is not true" in result

    def test_extract_assert_statement(self) -> None:
        """Test extracting assert statement."""
        runner = PytestRunner()

        longrepr = """
>       assert 1 == 2
E       assert 1 == 2
        """

        result = runner._extract_assertion_message(longrepr)
        assert "assert" in result or "==" in result

    def test_empty_longrepr(self) -> None:
        """Test empty longrepr returns empty string."""
        runner = PytestRunner()
        result = runner._extract_assertion_message("")
        assert result == ""


class TestPytestIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_same_input_same_id(self) -> None:
        """Test same input produces same ID."""
        runner = PytestRunner()

        id1 = runner._generate_issue_id("test::test_foo", "assert True")
        id2 = runner._generate_issue_id("test::test_foo", "assert True")

        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        """Test different input produces different ID."""
        runner = PytestRunner()

        id1 = runner._generate_issue_id("test::test_foo", "assert True")
        id2 = runner._generate_issue_id("test::test_bar", "assert True")

        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID format starts with pytest-."""
        runner = PytestRunner()

        issue_id = runner._generate_issue_id("test::test_foo", "assert True")

        assert issue_id.startswith("pytest-")
        assert len(issue_id) == len("pytest-") + 12  # 12 char hash


class TestBuildBaseCmd:
    """Tests for _build_base_cmd to verify coverage wrapping behavior."""

    def test_without_coverage_returns_plain_pytest(self) -> None:
        """Without coverage_binary, _build_base_cmd returns just the pytest binary."""
        runner = PytestRunner()
        binary = Path("/usr/bin/pytest")

        cmd = runner._build_base_cmd(binary)

        assert cmd == [str(binary)]

    def test_with_coverage_wraps_with_coverage_run(self) -> None:
        """With coverage_binary, _build_base_cmd wraps pytest with 'coverage run -m pytest'."""
        runner = PytestRunner()
        binary = Path("/usr/bin/pytest")
        coverage_binary = Path("/usr/bin/coverage")

        cmd = runner._build_base_cmd(binary, coverage_binary)

        assert cmd[0] == str(coverage_binary)
        assert "run" in cmd
        assert "-m" in cmd
        assert "pytest" in cmd

    def test_with_coverage_command_structure(self) -> None:
        """Verify the exact command structure: coverage run [-m] pytest."""
        runner = PytestRunner()
        binary = Path("/path/to/pytest")
        coverage_binary = Path("/path/to/coverage")

        cmd = runner._build_base_cmd(binary, coverage_binary)

        # Should be: [coverage_path, "run", "-m", "pytest"]
        # or: [coverage_path, "run", "--source", <dir>, "-m", "pytest"]
        # The key requirement is that "run" comes after coverage binary,
        # and "-m" "pytest" appears for module-based execution
        assert cmd[0] == str(coverage_binary)
        assert cmd[1] == "run"
        # -m pytest must appear (possibly after --source <dir>)
        m_idx = cmd.index("-m")
        assert cmd[m_idx + 1] == "pytest"

    def test_with_coverage_adds_source_for_src_layout(self) -> None:
        """Test that --source is added when project has src/<pkg> layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pkg = project_root / "src" / "mypackage"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").touch()

            runner = PytestRunner()
            binary = Path("/usr/bin/pytest")
            cov = Path("/usr/bin/coverage")

            cmd = runner._build_base_cmd(
                binary, coverage_binary=cov, project_root=project_root
            )

            assert cmd == [
                str(cov),
                "run",
                "--source",
                "src/mypackage",
                "-m",
                "pytest",
            ]

    def test_with_coverage_skips_source_when_already_configured(self) -> None:
        """Test that --source is NOT added when project has existing coverage config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pkg = project_root / "src" / "mypackage"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").touch()
            # Add existing coverage source config
            pyproject = project_root / "pyproject.toml"
            pyproject.write_text(
                '[tool.coverage.run]\nsource = ["src/mypackage"]\n'
            )

            runner = PytestRunner()
            binary = Path("/usr/bin/pytest")
            cov = Path("/usr/bin/coverage")

            cmd = runner._build_base_cmd(
                binary, coverage_binary=cov, project_root=project_root
            )

            # Should NOT include --source since user already configured it
            assert "--source" not in cmd
            assert cmd == [str(cov), "run", "-m", "pytest"]

    def test_with_coverage_no_project_root_skips_source(self) -> None:
        """Test that --source is skipped when project_root is None."""
        runner = PytestRunner()
        binary = Path("/usr/bin/pytest")
        cov = Path("/usr/bin/coverage")

        cmd = runner._build_base_cmd(binary, coverage_binary=cov)

        assert "--source" not in cmd
        assert cmd == [str(cov), "run", "-m", "pytest"]

    def test_with_coverage_no_source_detected(self) -> None:
        """Test that --source is omitted when source dir cannot be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Empty project - no src/, no package dir

            runner = PytestRunner()
            binary = Path("/usr/bin/pytest")
            cov = Path("/usr/bin/coverage")

            cmd = runner._build_base_cmd(
                binary, coverage_binary=cov, project_root=project_root
            )

            assert "--source" not in cmd
            assert cmd == [str(cov), "run", "-m", "pytest"]
