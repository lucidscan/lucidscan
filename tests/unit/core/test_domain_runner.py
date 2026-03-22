"""Unit tests for domain runner utilities."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Type
from unittest.mock import patch, MagicMock


from lucidshark.config.models import LucidSharkConfig
from lucidshark.core.domain_runner import (
    DomainRunner,
    EXTENSION_LANGUAGE,
    PLUGIN_LANGUAGES,
    _has_jest_config,
    _has_vitest_config,
    check_severity_threshold,
    detect_language,
    filter_plugins_by_language,
    get_domains_for_language,
)
from lucidshark.core.models import Severity, ToolDomain, UnifiedIssue


class MockPlugin:
    """Mock plugin for testing."""

    pass


class MockPythonPlugin:
    """Mock Python plugin."""

    pass


class MockJsPlugin:
    """Mock JavaScript plugin."""

    pass


class TestFilterPluginsByLanguage:
    """Tests for filter_plugins_by_language function."""

    def test_returns_all_plugins_when_no_languages(self) -> None:
        """Test all plugins returned when no languages specified."""
        plugins: Dict[str, Type[Any]] = {
            "ruff": MockPythonPlugin,
            "eslint": MockJsPlugin,
        }

        result = filter_plugins_by_language(plugins, [])

        assert result == plugins

    def test_filters_plugins_by_language(self) -> None:
        """Test plugins are filtered by supported language."""
        plugins: Dict[str, Type[Any]] = {
            "ruff": MockPythonPlugin,
            "eslint": MockJsPlugin,
        }

        result = filter_plugins_by_language(plugins, ["python"])

        assert "ruff" in result
        assert "eslint" not in result

    def test_includes_plugin_for_any_matching_language(self) -> None:
        """Test plugin included if any language matches."""
        plugins: Dict[str, Type[Any]] = {
            "eslint": MockJsPlugin,
        }

        # eslint supports both javascript and typescript
        result = filter_plugins_by_language(plugins, ["typescript"])

        assert "eslint" in result

    def test_case_insensitive_language_matching(self) -> None:
        """Test language matching is case insensitive."""
        plugins: Dict[str, Type[Any]] = {
            "ruff": MockPythonPlugin,
        }

        result = filter_plugins_by_language(plugins, ["Python"])

        assert "ruff" in result

    def test_includes_plugins_without_language_restrictions(self) -> None:
        """Test plugins with no language restrictions are included."""
        plugins: Dict[str, Type[Any]] = {
            "unknown_plugin": MockPlugin,
        }

        # Unknown plugins not in PLUGIN_LANGUAGES are included
        result = filter_plugins_by_language(plugins, ["python"])

        assert "unknown_plugin" in result

    def test_multiple_languages_filter(self) -> None:
        """Test filtering with multiple languages."""
        plugins: Dict[str, Type[Any]] = {
            "ruff": MockPythonPlugin,
            "mypy": MockPythonPlugin,
            "eslint": MockJsPlugin,
            "typescript": MockJsPlugin,
        }

        result = filter_plugins_by_language(plugins, ["python", "typescript"])

        assert "ruff" in result
        assert "mypy" in result
        assert "eslint" in result
        assert "typescript" in result


class TestDetectLanguage:
    """Tests for detect_language function."""

    def test_detects_python(self) -> None:
        """Test Python detection from .py extension."""
        assert detect_language(Path("test.py")) == "python"

    def test_detects_python_stub(self) -> None:
        """Test Python stub detection from .pyi extension."""
        assert detect_language(Path("types.pyi")) == "python"

    def test_detects_javascript(self) -> None:
        """Test JavaScript detection from .js extension."""
        assert detect_language(Path("index.js")) == "javascript"

    def test_detects_jsx(self) -> None:
        """Test JSX detection as javascript."""
        assert detect_language(Path("component.jsx")) == "javascript"

    def test_detects_typescript(self) -> None:
        """Test TypeScript detection from .ts extension."""
        assert detect_language(Path("app.ts")) == "typescript"

    def test_detects_tsx(self) -> None:
        """Test TSX detection as typescript."""
        assert detect_language(Path("component.tsx")) == "typescript"

    def test_detects_java(self) -> None:
        """Test Java detection from .java extension."""
        assert detect_language(Path("Main.java")) == "java"

    def test_detects_go(self) -> None:
        """Test Go detection from .go extension."""
        assert detect_language(Path("main.go")) == "go"

    def test_detects_rust(self) -> None:
        """Test Rust detection from .rs extension."""
        assert detect_language(Path("lib.rs")) == "rust"

    def test_detects_terraform(self) -> None:
        """Test Terraform detection from .tf extension."""
        assert detect_language(Path("main.tf")) == "terraform"

    def test_detects_yaml(self) -> None:
        """Test YAML detection from .yaml and .yml extensions."""
        assert detect_language(Path("config.yaml")) == "yaml"
        assert detect_language(Path("config.yml")) == "yaml"

    def test_detects_json(self) -> None:
        """Test JSON detection from .json extension."""
        assert detect_language(Path("package.json")) == "json"

    def test_returns_unknown_for_unrecognized(self) -> None:
        """Test unknown returned for unrecognized extensions."""
        assert detect_language(Path("readme.md")) == "unknown"
        assert detect_language(Path("Makefile")) == "unknown"
        assert detect_language(Path("script.sh")) == "unknown"

    def test_case_insensitive_extension(self) -> None:
        """Test extension matching is case insensitive."""
        assert detect_language(Path("Test.PY")) == "python"
        assert detect_language(Path("App.TS")) == "typescript"


class TestGetDomainsForLanguage:
    """Tests for get_domains_for_language function."""

    def test_python_domains(self) -> None:
        """Test Python gets all standard domains."""
        domains = get_domains_for_language("python")

        assert "linting" in domains
        assert "type_checking" in domains
        assert "testing" in domains
        assert "coverage" in domains
        assert "sast" in domains
        assert "sca" in domains

    def test_javascript_domains(self) -> None:
        """Test JavaScript gets all standard domains."""
        domains = get_domains_for_language("javascript")

        assert "linting" in domains
        assert "type_checking" in domains
        assert "testing" in domains
        assert "coverage" in domains

    def test_typescript_domains(self) -> None:
        """Test TypeScript gets all standard domains."""
        domains = get_domains_for_language("typescript")

        assert "linting" in domains
        assert "type_checking" in domains
        assert "testing" in domains
        assert "coverage" in domains

    def test_java_domains(self) -> None:
        """Test Java gets all standard domains."""
        domains = get_domains_for_language("java")

        assert "linting" in domains
        assert "type_checking" in domains
        assert "testing" in domains
        assert "coverage" in domains

    def test_kotlin_domains(self) -> None:
        """Test Kotlin gets all standard domains."""
        domains = get_domains_for_language("kotlin")

        assert "linting" in domains
        assert "type_checking" in domains
        assert "testing" in domains
        assert "coverage" in domains

    def test_terraform_domains(self) -> None:
        """Test Terraform gets IAC domain only."""
        domains = get_domains_for_language("terraform")

        assert domains == ["iac"]

    def test_yaml_domains(self) -> None:
        """Test YAML gets IAC and SAST domains."""
        domains = get_domains_for_language("yaml")

        assert "iac" in domains
        assert "sast" in domains

    def test_json_domains(self) -> None:
        """Test JSON gets IAC and SAST domains."""
        domains = get_domains_for_language("json")

        assert "iac" in domains
        assert "sast" in domains

    def test_unknown_language_domains(self) -> None:
        """Test unknown language gets default domains."""
        domains = get_domains_for_language("unknown")

        assert "linting" in domains
        assert "sast" in domains
        assert "sca" in domains


class TestCheckSeverityThreshold:
    """Tests for check_severity_threshold function."""

    def _create_issue(self, severity: Severity) -> UnifiedIssue:
        """Helper to create a test issue."""
        return UnifiedIssue(
            id="test-001",
            domain=ToolDomain.LINTING,
            source_tool="test",
            severity=severity,
            rule_id="test-rule",
            title="Test issue",
            description="Test description",
        )

    def test_returns_false_when_no_threshold(self) -> None:
        """Test returns False when no threshold specified."""
        issues = [self._create_issue(Severity.CRITICAL)]

        assert check_severity_threshold(issues, None) is False

    def test_returns_false_when_no_issues(self) -> None:
        """Test returns False when no issues."""
        assert check_severity_threshold([], "high") is False

    def test_returns_true_when_critical_meets_critical_threshold(self) -> None:
        """Test critical issue meets critical threshold."""
        issues = [self._create_issue(Severity.CRITICAL)]

        assert check_severity_threshold(issues, "critical") is True

    def test_returns_true_when_critical_exceeds_high_threshold(self) -> None:
        """Test critical issue exceeds high threshold."""
        issues = [self._create_issue(Severity.CRITICAL)]

        assert check_severity_threshold(issues, "high") is True

    def test_returns_false_when_low_below_high_threshold(self) -> None:
        """Test low issue doesn't meet high threshold."""
        issues = [self._create_issue(Severity.LOW)]

        assert check_severity_threshold(issues, "high") is False

    def test_returns_true_when_medium_meets_medium_threshold(self) -> None:
        """Test medium issue meets medium threshold."""
        issues = [self._create_issue(Severity.MEDIUM)]

        assert check_severity_threshold(issues, "medium") is True

    def test_returns_true_when_any_issue_meets_threshold(self) -> None:
        """Test returns True if any issue meets threshold."""
        issues = [
            self._create_issue(Severity.LOW),
            self._create_issue(Severity.MEDIUM),
            self._create_issue(Severity.HIGH),
        ]

        assert check_severity_threshold(issues, "high") is True

    def test_case_insensitive_threshold(self) -> None:
        """Test threshold comparison is case insensitive."""
        issues = [self._create_issue(Severity.HIGH)]

        assert check_severity_threshold(issues, "HIGH") is True
        assert check_severity_threshold(issues, "High") is True

    def test_unknown_threshold_matches_all_issues(self) -> None:
        """Test unknown threshold matches all issues (level 99 is very permissive)."""
        issues = [self._create_issue(Severity.LOW)]

        # Unknown threshold gets level 99, all issue severities (0-3) will be <= 99
        assert check_severity_threshold(issues, "unknown_level") is True


class TestPluginLanguagesMapping:
    """Tests for PLUGIN_LANGUAGES constant."""

    def test_ruff_supports_python(self) -> None:
        """Test ruff is mapped to Python."""
        assert "python" in PLUGIN_LANGUAGES["ruff"]

    def test_eslint_supports_js_and_ts(self) -> None:
        """Test eslint supports JavaScript and TypeScript."""
        assert "javascript" in PLUGIN_LANGUAGES["eslint"]
        assert "typescript" in PLUGIN_LANGUAGES["eslint"]

    def test_mypy_supports_python(self) -> None:
        """Test mypy is mapped to Python."""
        assert "python" in PLUGIN_LANGUAGES["mypy"]

    def test_pytest_supports_python(self) -> None:
        """Test pytest is mapped to Python."""
        assert "python" in PLUGIN_LANGUAGES["pytest"]

    def test_duplo_supports_multiple_languages(self) -> None:
        """Test duplo supports many languages."""
        duplo_langs = PLUGIN_LANGUAGES["duplo"]
        assert "python" in duplo_langs
        assert "java" in duplo_langs
        assert "javascript" in duplo_langs
        assert "go" in duplo_langs


class TestExtensionLanguageMapping:
    """Tests for EXTENSION_LANGUAGE constant."""

    def test_python_extensions(self) -> None:
        """Test Python extensions are mapped correctly."""
        assert EXTENSION_LANGUAGE[".py"] == "python"
        assert EXTENSION_LANGUAGE[".pyi"] == "python"

    def test_javascript_extensions(self) -> None:
        """Test JavaScript extensions are mapped correctly."""
        assert EXTENSION_LANGUAGE[".js"] == "javascript"
        assert EXTENSION_LANGUAGE[".jsx"] == "javascript"

    def test_typescript_extensions(self) -> None:
        """Test TypeScript extensions are mapped correctly."""
        assert EXTENSION_LANGUAGE[".ts"] == "typescript"
        assert EXTENSION_LANGUAGE[".tsx"] == "typescript"

    def test_java_extension(self) -> None:
        """Test Java extension is mapped correctly."""
        assert EXTENSION_LANGUAGE[".java"] == "java"

    def test_infrastructure_extensions(self) -> None:
        """Test infrastructure file extensions are mapped."""
        assert EXTENSION_LANGUAGE[".tf"] == "terraform"
        assert EXTENSION_LANGUAGE[".yaml"] == "yaml"
        assert EXTENSION_LANGUAGE[".yml"] == "yaml"
        assert EXTENSION_LANGUAGE[".json"] == "json"


class TestDomainRunnerCommand:
    """Tests for DomainRunner.run_tests with command and post_command."""

    def _make_runner(self, tmp_path: Path) -> DomainRunner:
        """Create a DomainRunner with default config."""
        config = LucidSharkConfig()
        return DomainRunner(tmp_path, config)

    def _make_context(self, tmp_path: Path) -> Any:
        """Create a minimal ScanContext-like mock."""
        ctx = MagicMock()
        ctx.project_root = tmp_path
        ctx.ignore_patterns = MagicMock()
        return ctx

    def test_command_success(self, tmp_path: Path) -> None:
        """Test that a successful command returns no issues."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
            issues = runner.run_tests(context, command="echo test")

        assert len(issues) == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == "echo test"
        assert call_args[1]["shell"] is True

    def test_command_failure(self, tmp_path: Path) -> None:
        """Test that a failed command creates a test failure issue."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="FAILED: test_foo"
            )
            issues = runner.run_tests(context, command="make test")

        assert len(issues) == 1
        assert issues[0].id == "custom-test-failure"
        assert issues[0].domain == ToolDomain.TESTING
        assert issues[0].severity == Severity.HIGH
        assert "exited with code 1" in issues[0].description
        assert "FAILED: test_foo" in issues[0].description

    def test_command_skips_plugin_discovery(self, tmp_path: Path) -> None:
        """Test that command skips plugin-based test runner discovery."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)

        with (
            patch("lucidshark.core.domain_runner.subprocess.run") as mock_run,
            patch(
                "lucidshark.plugins.test_runners.discover_test_runner_plugins"
            ) as mock_discover,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
            runner.run_tests(context, command="npm test")

        # Plugin discovery should NOT be called when command is set
        mock_discover.assert_not_called()

    def test_no_command_uses_plugins(self, tmp_path: Path) -> None:
        """Test that without command, plugin-based discovery is used."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)

        with patch(
            "lucidshark.plugins.test_runners.discover_test_runner_plugins"
        ) as mock_discover:
            mock_discover.return_value = {}
            runner.run_tests(context, command=None)

        mock_discover.assert_called_once()

    def test_post_command_runs_after_command(self, tmp_path: Path) -> None:
        """Test that post_command runs after command."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> MagicMock:
            call_order.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_tests(
                context,
                command="make test",
                post_command="make clean",
            )

        assert call_order == ["make test", "make clean"]

    def test_post_command_runs_after_plugins(self, tmp_path: Path) -> None:
        """Test that post_command runs after plugin-based tests (no command)."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)

        with (
            patch(
                "lucidshark.plugins.test_runners.discover_test_runner_plugins"
            ) as mock_discover,
            patch("lucidshark.core.domain_runner.subprocess.run") as mock_run,
        ):
            mock_discover.return_value = {}
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runner.run_tests(context, post_command="make clean")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == "make clean"

    def test_post_command_failure_logged_not_raised(self, tmp_path: Path) -> None:
        """Test that post_command failure is logged but doesn't raise."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)

        call_count = 0

        def side_effect(_cmd: str, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=0, stdout="OK", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="cleanup error")

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            issues = runner.run_tests(
                context,
                command="make test",
                post_command="bad-cleanup",
            )

        # Test command succeeded, so no test failure issues
        assert len(issues) == 0


class TestDomainRunnerCoveragePostCommand:
    """Tests for DomainRunner.run_coverage with post_command."""

    def _make_runner(self, tmp_path: Path) -> DomainRunner:
        """Create a DomainRunner with default config."""
        config = LucidSharkConfig()
        return DomainRunner(tmp_path, config)

    def _make_context(self, tmp_path: Path) -> Any:
        """Create a minimal ScanContext-like mock."""
        ctx = MagicMock()
        ctx.project_root = tmp_path
        ctx.ignore_patterns = MagicMock()
        return ctx

    def test_post_command_runs_after_coverage(self, tmp_path: Path) -> None:
        """Test that post_command runs after coverage analysis."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)

        with (
            patch(
                "lucidshark.plugins.coverage.discover_coverage_plugins"
            ) as mock_discover,
            patch("lucidshark.core.domain_runner.subprocess.run") as mock_run,
        ):
            mock_discover.return_value = {}
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runner.run_coverage(context, post_command="make report")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == "make report"

    def test_no_post_command_skips_subprocess(self, tmp_path: Path) -> None:
        """Test that no post_command means no subprocess call."""
        runner = self._make_runner(tmp_path)
        context = self._make_context(tmp_path)

        with (
            patch(
                "lucidshark.plugins.coverage.discover_coverage_plugins"
            ) as mock_discover,
            patch("lucidshark.core.domain_runner.subprocess.run") as mock_run,
        ):
            mock_discover.return_value = {}
            runner.run_coverage(context, post_command=None)

        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers for command output parsing tests
# ---------------------------------------------------------------------------


def _make_runner(tmp_path: Path) -> DomainRunner:
    """Create a DomainRunner with default config."""
    config = LucidSharkConfig()
    return DomainRunner(tmp_path, config)


def _make_context(tmp_path: Path) -> Any:
    """Create a minimal ScanContext-like mock."""
    ctx = MagicMock()
    ctx.project_root = tmp_path
    ctx.ignore_patterns = MagicMock()
    return ctx


def _completed(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args="test",
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _minimal_sarif(
    results: list[dict[str, Any]],
    *,
    tool_name: str = "mytool",
    rules: list[dict[str, Any]] | None = None,
) -> str:
    """Return a minimal SARIF 2.1.0 JSON string."""
    driver: dict[str, Any] = {"name": tool_name}
    if rules is not None:
        driver["rules"] = rules
    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": driver}, "results": results}],
    }
    return json.dumps(sarif)


# ---------------------------------------------------------------------------
# TestParseCommandOutput  -  auto-detection router
# ---------------------------------------------------------------------------


class TestParseCommandOutput:
    """Tests for DomainRunner._parse_command_output auto-detection logic."""

    def test_sarif_output_detected_and_parsed(self, tmp_path: Path) -> None:
        """SARIF output (with $schema + sarif) is routed to SARIF parser."""
        runner = _make_runner(tmp_path)
        sarif = _minimal_sarif(
            [
                {
                    "ruleId": "R1",
                    "level": "error",
                    "message": {"text": "bad"},
                    "locations": [],
                },
            ]
        )
        result = _completed(returncode=1, stdout=sarif)

        issues = runner._parse_command_output(result, ToolDomain.LINTING, "cmd")

        assert len(issues) == 1
        assert issues[0].rule_id == "R1"
        assert issues[0].severity == Severity.HIGH

    def test_json_array_output_detected(self, tmp_path: Path) -> None:
        """JSON array output is routed to JSON parser."""
        runner = _make_runner(tmp_path)
        data = [{"file": "a.py", "line": 1, "message": "bad style"}]
        result = _completed(returncode=1, stdout=json.dumps(data))

        issues = runner._parse_command_output(result, ToolDomain.LINTING, "cmd")

        assert len(issues) == 1
        assert issues[0].description == "bad style"

    def test_json_object_output_detected(self, tmp_path: Path) -> None:
        """JSON object with 'issues' key is routed to JSON parser."""
        runner = _make_runner(tmp_path)
        data = {"issues": [{"file": "b.py", "line": 5, "message": "unused import"}]}
        result = _completed(returncode=1, stdout=json.dumps(data))

        issues = runner._parse_command_output(result, ToolDomain.LINTING, "cmd")

        assert len(issues) == 1
        assert "unused import" in issues[0].description

    def test_plain_text_nonzero_exit(self, tmp_path: Path) -> None:
        """Non-JSON output + non-zero exit → single failure issue."""
        runner = _make_runner(tmp_path)
        result = _completed(
            returncode=1, stdout="FAIL: some test", stderr="error detail"
        )

        issues = runner._parse_command_output(result, ToolDomain.LINTING, "lint cmd")

        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM
        assert "exited with code 1" in issues[0].description
        assert "error detail" in issues[0].description

    def test_plain_text_zero_exit_no_issues(self, tmp_path: Path) -> None:
        """Non-JSON output + zero exit → success, no issues."""
        runner = _make_runner(tmp_path)
        result = _completed(returncode=0, stdout="All checks passed")

        issues = runner._parse_command_output(result, ToolDomain.LINTING, "cmd")

        assert issues == []

    def test_empty_stdout_nonzero_exit(self, tmp_path: Path) -> None:
        """Empty stdout + non-zero exit → failure issue with 'Command failed'."""
        runner = _make_runner(tmp_path)
        result = _completed(returncode=1, stdout="", stderr="")

        issues = runner._parse_command_output(result, ToolDomain.LINTING, "cmd")

        assert len(issues) == 1
        assert "Command failed" in issues[0].description

    def test_empty_stdout_zero_exit(self, tmp_path: Path) -> None:
        """Empty stdout + zero exit → empty list."""
        runner = _make_runner(tmp_path)
        result = _completed(returncode=0, stdout="", stderr="")

        issues = runner._parse_command_output(result, ToolDomain.LINTING, "cmd")

        assert issues == []

    def test_malformed_json_falls_through(self, tmp_path: Path) -> None:
        """Malformed JSON falls through to plain text handling."""
        runner = _make_runner(tmp_path)
        result = _completed(returncode=1, stdout="{broken json", stderr="parse error")

        issues = runner._parse_command_output(result, ToolDomain.LINTING, "cmd")

        # Falls through JSON attempt → plain text path
        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM
        assert "exited with code 1" in issues[0].description


# ---------------------------------------------------------------------------
# TestParseSarifOutput  -  SARIF 2.1.0 parsing
# ---------------------------------------------------------------------------


class TestParseSarifOutput:
    """Tests for DomainRunner._parse_sarif_output."""

    def test_basic_sarif_result(self, tmp_path: Path) -> None:
        """Minimal SARIF result is parsed with correct fields."""
        runner = _make_runner(tmp_path)
        sarif = _minimal_sarif(
            [
                {
                    "ruleId": "no-eval",
                    "level": "error",
                    "message": {"text": "eval is evil"},
                    "locations": [],
                },
            ]
        )

        issues = runner._parse_sarif_output(sarif, ToolDomain.LINTING)

        assert len(issues) == 1
        assert issues[0].rule_id == "no-eval"
        assert issues[0].severity == Severity.HIGH
        assert issues[0].domain == ToolDomain.LINTING
        assert issues[0].source_tool == "mytool"
        assert "eval is evil" in issues[0].description

    def test_sarif_severity_mapping(self, tmp_path: Path) -> None:
        """SARIF levels map correctly to Severity enum values."""
        runner = _make_runner(tmp_path)
        levels = [
            ("error", Severity.HIGH),
            ("warning", Severity.MEDIUM),
            ("note", Severity.LOW),
            ("none", Severity.INFO),
        ]
        results = [
            {
                "ruleId": f"R-{lvl}",
                "level": lvl,
                "message": {"text": f"msg-{lvl}"},
                "locations": [],
            }
            for lvl, _ in levels
        ]
        sarif = _minimal_sarif(results)

        issues = runner._parse_sarif_output(sarif, ToolDomain.LINTING)

        assert len(issues) == len(levels)
        for issue, (_, expected_sev) in zip(issues, levels):
            assert issue.severity == expected_sev

    def test_sarif_with_location(self, tmp_path: Path) -> None:
        """Result with physical location populates file_path and line_start."""
        runner = _make_runner(tmp_path)
        sarif = _minimal_sarif(
            [
                {
                    "ruleId": "E501",
                    "level": "warning",
                    "message": {"text": "line too long"},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": "src/main.py"},
                                "region": {"startLine": 42},
                            },
                        }
                    ],
                }
            ]
        )

        issues = runner._parse_sarif_output(sarif, ToolDomain.LINTING)

        assert len(issues) == 1
        assert issues[0].file_path == "src/main.py"
        assert issues[0].line_start == 42

    def test_sarif_without_location(self, tmp_path: Path) -> None:
        """Result with no locations array → file_path and line_start are None."""
        runner = _make_runner(tmp_path)
        sarif = _minimal_sarif(
            [
                {
                    "ruleId": "G001",
                    "level": "note",
                    "message": {"text": "general issue"},
                    "locations": [],
                }
            ]
        )

        issues = runner._parse_sarif_output(sarif, ToolDomain.LINTING)

        assert len(issues) == 1
        assert issues[0].file_path is None
        assert issues[0].line_start is None

    def test_sarif_with_rule_definitions(self, tmp_path: Path) -> None:
        """Rules array supplies shortDescription as title."""
        runner = _make_runner(tmp_path)
        rules = [
            {
                "id": "SEC-01",
                "shortDescription": {"text": "Hardcoded secret"},
                "fullDescription": {"text": "Do not hardcode secrets in source code."},
            }
        ]
        sarif = _minimal_sarif(
            [
                {
                    "ruleId": "SEC-01",
                    "level": "error",
                    "message": {"text": "found secret"},
                    "locations": [],
                }
            ],
            rules=rules,
        )

        issues = runner._parse_sarif_output(sarif, ToolDomain.LINTING)

        assert len(issues) == 1
        assert issues[0].title == "Hardcoded secret"
        assert "found secret" in issues[0].description

    def test_sarif_multiple_runs(self, tmp_path: Path) -> None:
        """Issues from multiple SARIF runs are collected."""
        runner = _make_runner(tmp_path)
        sarif_data = {
            "$schema": "https://sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": "toolA"}},
                    "results": [
                        {
                            "ruleId": "A1",
                            "level": "error",
                            "message": {"text": "from A"},
                            "locations": [],
                        }
                    ],
                },
                {
                    "tool": {"driver": {"name": "toolB"}},
                    "results": [
                        {
                            "ruleId": "B1",
                            "level": "warning",
                            "message": {"text": "from B"},
                            "locations": [],
                        }
                    ],
                },
            ],
        }

        issues = runner._parse_sarif_output(json.dumps(sarif_data), ToolDomain.LINTING)

        assert len(issues) == 2
        tool_names = {i.source_tool for i in issues}
        assert tool_names == {"toolA", "toolB"}

    def test_sarif_empty_runs(self, tmp_path: Path) -> None:
        """Empty runs array → empty list."""
        runner = _make_runner(tmp_path)
        sarif_data = {
            "$schema": "https://sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [],
        }

        issues = runner._parse_sarif_output(json.dumps(sarif_data), ToolDomain.LINTING)

        assert issues == []


# ---------------------------------------------------------------------------
# TestParseJsonOutput  -  generic JSON parsing
# ---------------------------------------------------------------------------


class TestParseJsonOutput:
    """Tests for DomainRunner._parse_json_output."""

    def test_json_array_of_issues(self, tmp_path: Path) -> None:
        """JSON array of issue objects parses correctly."""
        runner = _make_runner(tmp_path)
        data = json.dumps(
            [
                {"file": "a.py", "line": 1, "message": "bad"},
            ]
        )

        issues = runner._parse_json_output(data, ToolDomain.LINTING)

        assert len(issues) == 1
        assert issues[0].file_path == Path("a.py")
        assert issues[0].line_start == 1
        assert issues[0].description == "bad"

    def test_json_object_with_issues_key(self, tmp_path: Path) -> None:
        """Object with 'issues' key extracts nested array."""
        runner = _make_runner(tmp_path)
        data = json.dumps(
            {"issues": [{"message": "unused var", "file": "x.py", "line": 10}]}
        )

        issues = runner._parse_json_output(data, ToolDomain.LINTING)

        assert len(issues) == 1
        assert "unused var" in issues[0].description

    def test_json_object_with_errors_key(self, tmp_path: Path) -> None:
        """Object with 'errors' key extracts nested array."""
        runner = _make_runner(tmp_path)
        data = json.dumps({"errors": [{"message": "type mismatch"}]})

        issues = runner._parse_json_output(data, ToolDomain.TYPE_CHECKING)

        assert len(issues) == 1
        assert issues[0].domain == ToolDomain.TYPE_CHECKING

    def test_json_object_with_diagnostics_key(self, tmp_path: Path) -> None:
        """Object with 'diagnostics' key extracts nested array."""
        runner = _make_runner(tmp_path)
        data = json.dumps({"diagnostics": [{"message": "diag msg"}]})

        issues = runner._parse_json_output(data, ToolDomain.LINTING)

        assert len(issues) == 1
        assert "diag msg" in issues[0].description

    def test_json_object_with_results_key(self, tmp_path: Path) -> None:
        """Object with 'results' key extracts nested array."""
        runner = _make_runner(tmp_path)
        data = json.dumps({"results": [{"message": "result msg"}]})

        issues = runner._parse_json_output(data, ToolDomain.LINTING)

        assert len(issues) == 1
        assert "result msg" in issues[0].description

    def test_json_field_name_variations(self, tmp_path: Path) -> None:
        """Various field names for file path and line number are recognized."""
        runner = _make_runner(tmp_path)
        items = [
            {"path": "a.py", "startLine": 10, "message": "msg1"},
            {"filePath": "b.py", "row": 20, "message": "msg2"},
            {"filename": "c.py", "lineNumber": 30, "message": "msg3"},
        ]
        data = json.dumps(items)

        issues = runner._parse_json_output(data, ToolDomain.LINTING)

        assert len(issues) == 3
        assert issues[0].file_path == Path("a.py")
        assert issues[0].line_start == 10
        assert issues[1].file_path == Path("b.py")
        assert issues[1].line_start == 20
        assert issues[2].file_path == Path("c.py")
        assert issues[2].line_start == 30

    def test_json_severity_string_mapping(self, tmp_path: Path) -> None:
        """String severity values map to correct Severity enums."""
        runner = _make_runner(tmp_path)
        items = [
            {"message": "e", "severity": "error"},
            {"message": "w", "severity": "warning"},
            {"message": "i", "severity": "info"},
            {"message": "h", "severity": "hint"},
        ]
        data = json.dumps(items)

        issues = runner._parse_json_output(data, ToolDomain.LINTING)

        assert len(issues) == 4
        assert issues[0].severity == Severity.HIGH
        assert issues[1].severity == Severity.MEDIUM
        assert issues[2].severity == Severity.LOW
        assert issues[3].severity == Severity.INFO

    def test_json_severity_numeric_mapping(self, tmp_path: Path) -> None:
        """Numeric severity values (ESLint style: 1=MEDIUM, 2=HIGH)."""
        runner = _make_runner(tmp_path)
        items = [
            {"message": "medium", "severity": 1},
            {"message": "high", "severity": 2},
        ]
        data = json.dumps(items)

        issues = runner._parse_json_output(data, ToolDomain.LINTING)

        assert len(issues) == 2
        assert issues[0].severity == Severity.MEDIUM
        assert issues[1].severity == Severity.HIGH

    def test_json_item_without_message_skipped(self, tmp_path: Path) -> None:
        """Items missing 'message' field are skipped."""
        runner = _make_runner(tmp_path)
        items = [
            {"file": "a.py", "line": 1},  # no message
            {"file": "b.py", "line": 2, "message": "ok"},
        ]
        data = json.dumps(items)

        issues = runner._parse_json_output(data, ToolDomain.LINTING)

        assert len(issues) == 1
        assert issues[0].description == "ok"

    def test_json_empty_array(self, tmp_path: Path) -> None:
        """Empty JSON array → empty list."""
        runner = _make_runner(tmp_path)

        issues = runner._parse_json_output("[]", ToolDomain.LINTING)

        assert issues == []

    def test_json_empty_object(self, tmp_path: Path) -> None:
        """Empty JSON object → empty list."""
        runner = _make_runner(tmp_path)

        issues = runner._parse_json_output("{}", ToolDomain.LINTING)

        assert issues == []


# ---------------------------------------------------------------------------
# TestLintingCommand  -  run_linting() with command/post_command
# ---------------------------------------------------------------------------


class TestLintingCommand:
    """Tests for DomainRunner.run_linting with command and post_command."""

    def test_command_with_json_output(self, tmp_path: Path) -> None:
        """Linting command returning JSON issues → parsed into UnifiedIssues."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        data = [
            {
                "file": "a.py",
                "line": 1,
                "message": "missing docstring",
                "severity": "warning",
            }
        ]

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=1, stdout=json.dumps(data))
            issues = runner.run_linting(context, command="custom-lint .")

        assert len(issues) == 1
        assert issues[0].domain == ToolDomain.LINTING
        assert "missing docstring" in issues[0].description

    def test_command_with_sarif_output(self, tmp_path: Path) -> None:
        """Linting command returning SARIF → parsed correctly."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        sarif = _minimal_sarif(
            [
                {
                    "ruleId": "E501",
                    "level": "warning",
                    "message": {"text": "line too long"},
                    "locations": [],
                },
            ]
        )

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=1, stdout=sarif)
            issues = runner.run_linting(context, command="sarif-lint")

        assert len(issues) == 1
        assert issues[0].rule_id == "E501"

    def test_command_failure_plain_text(self, tmp_path: Path) -> None:
        """Command failure with non-JSON output → failure issue."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(
                returncode=2, stdout="syntax error", stderr="crash"
            )
            issues = runner.run_linting(context, command="broken-lint")

        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM
        assert "exited with code 2" in issues[0].description

    def test_command_success_no_issues(self, tmp_path: Path) -> None:
        """Successful command with no parseable output → empty list."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=0, stdout="All clean")
            issues = runner.run_linting(context, command="lint .")

        assert issues == []

    def test_command_skips_plugin_discovery(self, tmp_path: Path) -> None:
        """When command is set, linter plugins are not discovered."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with (
            patch("lucidshark.core.domain_runner.subprocess.run") as mock_run,
            patch(
                "lucidshark.plugins.linters.discover_linter_plugins"
            ) as mock_discover,
        ):
            mock_run.return_value = _completed(returncode=0, stdout="")
            runner.run_linting(context, command="my-lint")

        mock_discover.assert_not_called()

    def test_post_command_runs_after_command(self, tmp_path: Path) -> None:
        """post_command executes after main command."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_order.append(cmd)
            return _completed(returncode=0)

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_linting(context, command="lint .", post_command="lint-report")

        assert call_order == ["lint .", "lint-report"]

    def test_post_command_runs_after_plugins(self, tmp_path: Path) -> None:
        """post_command runs even without custom command (after plugins)."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        mock_plugin = MagicMock()
        mock_plugin.return_value.supports_fix = False
        mock_plugin.return_value.lint.return_value = []

        with (
            patch(
                "lucidshark.plugins.linters.discover_linter_plugins"
            ) as mock_discover,
            patch(
                "lucidshark.core.domain_runner.filter_plugins_by_config"
            ) as mock_filter,
            patch("lucidshark.core.domain_runner.subprocess.run") as mock_run,
        ):
            mock_discover.return_value = {"mock_linter": mock_plugin}
            mock_filter.return_value = {"mock_linter": mock_plugin}
            mock_run.return_value = _completed(returncode=0)
            runner.run_linting(context, post_command="post-lint-hook")

        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == "post-lint-hook"

    def test_post_command_failure_logged(self, tmp_path: Path) -> None:
        """post_command failure is logged, not raised."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_count = 0

        def side_effect(_cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(returncode=0, stdout="OK")
            return _completed(returncode=1, stderr="cleanup failed")

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            issues = runner.run_linting(
                context,
                command="lint .",
                post_command="bad-cleanup",
            )

        # Main command succeeded → no issues despite post_command failure
        assert issues == []


# ---------------------------------------------------------------------------
# TestTypeCheckingCommand  -  run_type_checking() with command/post_command
# ---------------------------------------------------------------------------


class TestTypeCheckingCommand:
    """Tests for DomainRunner.run_type_checking with command and post_command."""

    def test_command_with_json_output(self, tmp_path: Path) -> None:
        """Type checking command returning JSON → parsed."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        data = [
            {
                "file": "mod.py",
                "line": 10,
                "message": "Incompatible types",
                "severity": "error",
            }
        ]

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=1, stdout=json.dumps(data))
            issues = runner.run_type_checking(context, command="mypy --json .")

        assert len(issues) == 1
        assert issues[0].domain == ToolDomain.TYPE_CHECKING
        assert "Incompatible types" in issues[0].description

    def test_command_failure_plain_text(self, tmp_path: Path) -> None:
        """Command failure with plain text → failure issue."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(
                returncode=1, stdout="error: module not found", stderr=""
            )
            issues = runner.run_type_checking(context, command="pyright .")

        assert len(issues) == 1
        assert issues[0].domain == ToolDomain.TYPE_CHECKING
        assert "exited with code 1" in issues[0].description

    def test_command_skips_plugin_discovery(self, tmp_path: Path) -> None:
        """When command is set, type checker plugins are not discovered."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with (
            patch("lucidshark.core.domain_runner.subprocess.run") as mock_run,
            patch(
                "lucidshark.plugins.type_checkers.discover_type_checker_plugins"
            ) as mock_discover,
        ):
            mock_run.return_value = _completed(returncode=0)
            runner.run_type_checking(context, command="mypy .")

        mock_discover.assert_not_called()

    def test_post_command_runs_after_command(self, tmp_path: Path) -> None:
        """post_command executes after main command."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_order.append(cmd)
            return _completed(returncode=0)

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_type_checking(
                context, command="mypy .", post_command="type-report"
            )

        assert call_order == ["mypy .", "type-report"]

    def test_post_command_failure_logged(self, tmp_path: Path) -> None:
        """post_command failure is logged, not raised."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_count = 0

        def side_effect(_cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(returncode=0)
            return _completed(returncode=1, stderr="report failed")

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            issues = runner.run_type_checking(
                context,
                command="mypy .",
                post_command="bad-hook",
            )

        assert issues == []


# ---------------------------------------------------------------------------
# TestCoverageCommand  -  run_coverage() with command/post_command
# ---------------------------------------------------------------------------


class TestCoverageCommand:
    """Tests for DomainRunner.run_coverage with command and post_command."""

    def test_command_success(self, tmp_path: Path) -> None:
        """Successful coverage command → no issues."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=0, stdout="Coverage: 90%")
            issues = runner.run_coverage(context, command="coverage run")

        assert issues == []

    def test_command_failure(self, tmp_path: Path) -> None:
        """Failed coverage command → MEDIUM severity issue (not HIGH like testing)."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(
                returncode=1, stdout="", stderr="Coverage below threshold"
            )
            issues = runner.run_coverage(context, command="coverage run")

        assert len(issues) == 1
        assert issues[0].id == "custom-coverage-failure"
        assert issues[0].domain == ToolDomain.COVERAGE
        assert issues[0].severity == Severity.MEDIUM
        assert "Coverage below threshold" in issues[0].description

    def test_command_skips_plugin_discovery(self, tmp_path: Path) -> None:
        """When command is set, coverage plugins are not discovered."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with (
            patch("lucidshark.core.domain_runner.subprocess.run") as mock_run,
            patch(
                "lucidshark.plugins.coverage.discover_coverage_plugins"
            ) as mock_discover,
        ):
            mock_run.return_value = _completed(returncode=0)
            runner.run_coverage(context, command="coverage run")

        mock_discover.assert_not_called()

    def test_post_command_runs_after_command(self, tmp_path: Path) -> None:
        """post_command executes after main coverage command."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_order.append(cmd)
            return _completed(returncode=0)

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_coverage(
                context, command="coverage run", post_command="coverage html"
            )

        assert call_order == ["coverage run", "coverage html"]

    def test_command_success_sets_coverage_result(self, tmp_path: Path) -> None:
        """Successful coverage command sets context.coverage_result."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=0, stdout="Coverage: 90%")
            runner.run_coverage(context, command="coverage run", threshold=80.0)

        assert context.coverage_result is not None
        assert context.coverage_result.threshold == 80.0
        assert context.coverage_result.tool == "custom"

    def test_command_failure_sets_coverage_result(self, tmp_path: Path) -> None:
        """Failed coverage command also sets context.coverage_result."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(
                returncode=1, stdout="", stderr="Coverage below threshold"
            )
            issues = runner.run_coverage(
                context, command="coverage run", threshold=80.0
            )

        # coverage_result should be set even on failure
        assert context.coverage_result is not None
        assert context.coverage_result.threshold == 80.0
        assert context.coverage_result.tool == "custom"
        # Issues should be copied to the result
        assert len(issues) == 1

    def test_coverage_result_set_on_original_context_with_exclude_patterns(
        self, tmp_path: Path
    ) -> None:
        """Coverage result must be set on original context even when exclude_patterns are provided.

        When exclude_patterns are provided, _context_with_domain_excludes creates a copy
        of the context. The coverage_result must be copied back to the original context
        so the caller can access it. This regression test ensures the fix works.
        """
        from lucidshark.core.models import ScanContext

        runner = _make_runner(tmp_path)
        # Use a real ScanContext to test the dataclasses.replace() behavior
        context = ScanContext(
            project_root=tmp_path, paths=[tmp_path], enabled_domains=[]
        )

        with patch("lucidshark.core.domain_runner.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=0, stdout="Coverage: 90%")
            runner.run_coverage(
                context,
                command="coverage run",
                threshold=80.0,
                exclude_patterns=["**/test_*.py"],  # This triggers context copy
            )

        # The coverage_result must be set on the ORIGINAL context, not just the copy
        assert context.coverage_result is not None
        assert context.coverage_result.threshold == 80.0
        assert context.coverage_result.tool == "custom"

    def test_coverage_result_set_on_original_context_with_plugin(
        self, tmp_path: Path
    ) -> None:
        """Coverage result from plugin must be set on original context with exclude_patterns.

        Tests the plugin-based coverage path (not custom command) to ensure the
        coverage_result is copied back to the original context when a copy is created.
        """
        from lucidshark.core.models import ScanContext
        from lucidshark.plugins.coverage.base import CoverageResult

        runner = _make_runner(tmp_path)
        context = ScanContext(
            project_root=tmp_path, paths=[tmp_path], enabled_domains=[]
        )

        # Create a mock coverage result
        mock_result = CoverageResult(
            total_lines=100,
            covered_lines=85,
            threshold=80.0,
            tool="mock_plugin",
        )

        # Mock the plugin discovery and execution
        mock_plugin_instance = MagicMock()
        mock_plugin_instance.measure_coverage.return_value = mock_result
        mock_plugin_class = MagicMock(return_value=mock_plugin_instance)

        with patch(
            "lucidshark.plugins.coverage.discover_coverage_plugins",
            return_value={"mock_plugin": mock_plugin_class},
        ):
            runner.run_coverage(
                context,
                threshold=80.0,
                exclude_patterns=["**/test_*.py"],  # This triggers context copy
            )

        # The coverage_result must be set on the ORIGINAL context
        assert context.coverage_result is not None
        assert context.coverage_result.tool == "mock_plugin"
        assert context.coverage_result.percentage == 85.0


# ---------------------------------------------------------------------------
# TestPreCommand  -  pre_command support for all domains
# ---------------------------------------------------------------------------


class TestPreCommand:
    """Tests for pre_command support across all domains."""

    def test_pre_command_runs_before_test_command(self, tmp_path: Path) -> None:
        """pre_command executes before main test command."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_order.append(cmd)
            return _completed(returncode=0)

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_tests(
                context,
                command="make test",
                pre_command="docker stop mongo",
                post_command="make clean",
            )

        assert call_order == ["docker stop mongo", "make test", "make clean"]

    def test_pre_command_runs_before_linting_command(self, tmp_path: Path) -> None:
        """pre_command executes before main linting command."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_order.append(cmd)
            return _completed(returncode=0)

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_linting(
                context,
                command="lint .",
                pre_command="setup-lint",
                post_command="cleanup-lint",
            )

        assert call_order == ["setup-lint", "lint .", "cleanup-lint"]

    def test_pre_command_runs_before_type_checking_command(
        self, tmp_path: Path
    ) -> None:
        """pre_command executes before main type checking command."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_order.append(cmd)
            return _completed(returncode=0)

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_type_checking(
                context,
                command="mypy .",
                pre_command="generate-stubs",
                post_command="cleanup-stubs",
            )

        assert call_order == ["generate-stubs", "mypy .", "cleanup-stubs"]

    def test_pre_command_runs_before_coverage_command(self, tmp_path: Path) -> None:
        """pre_command executes before main coverage command."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_order.append(cmd)
            return _completed(returncode=0)

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_coverage(
                context,
                command="coverage run",
                pre_command="docker stop db",
                post_command="coverage html",
            )

        assert call_order == ["docker stop db", "coverage run", "coverage html"]

    def test_pre_command_failure_logged_not_raised(self, tmp_path: Path) -> None:
        """pre_command failure is logged but main command still runs."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_count = 0

        def side_effect(_cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # pre_command fails
                return _completed(returncode=1, stderr="cleanup failed")
            # main command succeeds
            return _completed(returncode=0, stdout="OK")

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            issues = runner.run_tests(
                context,
                command="make test",
                pre_command="bad-cleanup",
            )

        # Main command succeeded, so no test failure issues
        # (pre_command failure is just logged)
        assert len(issues) == 0
        assert call_count == 2  # Both commands ran

    def test_pre_command_none_skips_subprocess(self, tmp_path: Path) -> None:
        """No pre_command means no extra subprocess call."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)
        call_order: list[str] = []

        def side_effect(cmd: str, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            call_order.append(cmd)
            return _completed(returncode=0)

        with patch(
            "lucidshark.core.domain_runner.subprocess.run", side_effect=side_effect
        ):
            runner.run_tests(context, command="make test", pre_command=None)

        assert call_order == ["make test"]


# ---------------------------------------------------------------------------
# Coverage plugin deduplication tests
# ---------------------------------------------------------------------------


class TestCoveragePluginDeduplication:
    """Tests for JS/TS coverage plugin deduplication in run_coverage."""

    def test_vitest_config_selects_vitest_coverage(self, tmp_path: Path) -> None:
        """When vitest.config.ts exists, vitest_coverage wins over istanbul."""
        (tmp_path / "vitest.config.ts").write_text("export default {}")
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        mock_istanbul = MagicMock()
        mock_vitest = MagicMock()
        fake_plugins = {"istanbul": mock_istanbul, "vitest_coverage": mock_vitest}

        with (
            patch(
                "lucidshark.plugins.coverage.discover_coverage_plugins",
                return_value=dict(fake_plugins),
            ),
            patch(
                "lucidshark.core.domain_runner.filter_plugins_by_config",
                return_value=dict(fake_plugins),
            ),
        ):
            # Mock the vitest_coverage plugin instance
            vitest_instance = MagicMock()
            vitest_result = MagicMock()
            vitest_result.passed = True
            vitest_result.percentage = 85.0
            vitest_result.covered_lines = 85
            vitest_result.total_lines = 100
            vitest_result.issues = []
            vitest_instance.measure_coverage.return_value = vitest_result
            mock_vitest.return_value = vitest_instance

            runner.run_coverage(context)

        # vitest_coverage should have been called, istanbul should not
        mock_vitest.assert_called_once()
        mock_istanbul.assert_not_called()

    def test_jest_config_selects_istanbul(self, tmp_path: Path) -> None:
        """When jest.config.js exists, istanbul wins over vitest_coverage."""
        (tmp_path / "jest.config.js").write_text("module.exports = {}")
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        mock_istanbul = MagicMock()
        mock_vitest = MagicMock()
        fake_plugins = {"istanbul": mock_istanbul, "vitest_coverage": mock_vitest}

        with (
            patch(
                "lucidshark.plugins.coverage.discover_coverage_plugins",
                return_value=dict(fake_plugins),
            ),
            patch(
                "lucidshark.core.domain_runner.filter_plugins_by_config",
                return_value=dict(fake_plugins),
            ),
        ):
            istanbul_instance = MagicMock()
            istanbul_result = MagicMock()
            istanbul_result.passed = True
            istanbul_result.percentage = 90.0
            istanbul_result.covered_lines = 90
            istanbul_result.total_lines = 100
            istanbul_result.issues = []
            istanbul_instance.measure_coverage.return_value = istanbul_result
            mock_istanbul.return_value = istanbul_instance

            runner.run_coverage(context)

        mock_istanbul.assert_called_once()
        mock_vitest.assert_not_called()

    def test_no_config_defaults_to_istanbul(self, tmp_path: Path) -> None:
        """When neither vitest nor jest config exists, istanbul is the default."""
        runner = _make_runner(tmp_path)
        context = _make_context(tmp_path)

        mock_istanbul = MagicMock()
        mock_vitest = MagicMock()
        fake_plugins = {"istanbul": mock_istanbul, "vitest_coverage": mock_vitest}

        with (
            patch(
                "lucidshark.plugins.coverage.discover_coverage_plugins",
                return_value=dict(fake_plugins),
            ),
            patch(
                "lucidshark.core.domain_runner.filter_plugins_by_config",
                return_value=dict(fake_plugins),
            ),
        ):
            istanbul_instance = MagicMock()
            istanbul_result = MagicMock()
            istanbul_result.passed = True
            istanbul_result.percentage = 90.0
            istanbul_result.covered_lines = 90
            istanbul_result.total_lines = 100
            istanbul_result.issues = []
            istanbul_instance.measure_coverage.return_value = istanbul_result
            mock_istanbul.return_value = istanbul_instance

            runner.run_coverage(context)

        mock_istanbul.assert_called_once()
        mock_vitest.assert_not_called()

    def test_explicit_config_skips_deduplication(self, tmp_path: Path) -> None:
        """When user explicitly configures both tools, both should run."""
        from lucidshark.config.models import (
            PipelineConfig,
            CoveragePipelineConfig,
            ToolConfig,
        )

        config = LucidSharkConfig()
        config.pipeline = PipelineConfig(
            coverage=CoveragePipelineConfig(
                enabled=True,
                tools=[
                    ToolConfig(name="istanbul"),
                    ToolConfig(name="vitest_coverage"),
                ],
            ),
        )
        runner = DomainRunner(tmp_path, config)
        context = _make_context(tmp_path)

        mock_istanbul = MagicMock()
        mock_vitest = MagicMock()

        # When tools are explicitly configured, filter_plugins_by_config returns
        # only those tools. We simulate that both are returned.
        fake_plugins = {"istanbul": mock_istanbul, "vitest_coverage": mock_vitest}

        with (
            patch(
                "lucidshark.plugins.coverage.discover_coverage_plugins",
                return_value=dict(fake_plugins),
            ),
            patch(
                "lucidshark.core.domain_runner.filter_plugins_by_config",
                return_value=dict(fake_plugins),
            ),
        ):
            istanbul_instance = MagicMock()
            istanbul_result = MagicMock()
            istanbul_result.passed = True
            istanbul_result.percentage = 90.0
            istanbul_result.covered_lines = 90
            istanbul_result.total_lines = 100
            istanbul_result.issues = []
            istanbul_instance.measure_coverage.return_value = istanbul_result
            mock_istanbul.return_value = istanbul_instance

            vitest_instance = MagicMock()
            vitest_result = MagicMock()
            vitest_result.passed = True
            vitest_result.percentage = 85.0
            vitest_result.covered_lines = 85
            vitest_result.total_lines = 100
            vitest_result.issues = []
            vitest_instance.measure_coverage.return_value = vitest_result
            mock_vitest.return_value = vitest_instance

            runner.run_coverage(context)

        # Both should have been instantiated since user explicitly configured both
        mock_istanbul.assert_called_once()
        mock_vitest.assert_called_once()


class TestHasVitestConfig:
    """Tests for _has_vitest_config helper."""

    def test_vitest_config_ts(self, tmp_path: Path) -> None:
        (tmp_path / "vitest.config.ts").write_text("")
        assert _has_vitest_config(tmp_path) is True

    def test_vite_config_js(self, tmp_path: Path) -> None:
        (tmp_path / "vite.config.js").write_text("")
        assert _has_vitest_config(tmp_path) is True

    def test_no_config(self, tmp_path: Path) -> None:
        assert _has_vitest_config(tmp_path) is False


class TestHasJestConfig:
    """Tests for _has_jest_config helper."""

    def test_jest_config_js(self, tmp_path: Path) -> None:
        (tmp_path / "jest.config.js").write_text("")
        assert _has_jest_config(tmp_path) is True

    def test_jest_in_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"jest": {"coverage": true}}')
        assert _has_jest_config(tmp_path) is True

    def test_package_json_without_jest(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "my-app"}')
        assert _has_jest_config(tmp_path) is False

    def test_no_config(self, tmp_path: Path) -> None:
        assert _has_jest_config(tmp_path) is False


class TestLogCommandFailure:
    """Tests for _log_command_failure helper method."""

    def test_no_output_when_not_verbose(self, tmp_path: Path) -> None:
        """When verbose is False, _log_command_failure should not emit or log."""
        mock_handler = MagicMock()
        runner = DomainRunner(
            tmp_path, LucidSharkConfig(), verbose=False, stream_handler=mock_handler
        )
        result = subprocess.CompletedProcess(
            args="test", returncode=1, stdout="error output", stderr="stderr output"
        )

        with patch("lucidshark.core.domain_runner.LOGGER") as mock_logger:
            runner._log_command_failure("test_command", result)
            # Neither stream handler nor logger should be called
            mock_handler.emit.assert_not_called()
            mock_logger.info.assert_not_called()

    def test_logs_via_stream_handler_when_verbose(self, tmp_path: Path) -> None:
        """When verbose and stream_handler present, emits via stream_handler."""
        from lucidshark.core.streaming import StreamHandler, StreamEvent, StreamType

        mock_handler = MagicMock(spec=StreamHandler)
        runner = DomainRunner(
            tmp_path, LucidSharkConfig(), verbose=True, stream_handler=mock_handler
        )
        result = subprocess.CompletedProcess(
            args="test", returncode=1, stdout="", stderr="test error message"
        )

        runner._log_command_failure("test_command", result)

        mock_handler.emit.assert_called_once()
        event = mock_handler.emit.call_args[0][0]
        assert isinstance(event, StreamEvent)
        assert event.tool_name == "test_command"
        assert event.stream_type == StreamType.STDERR
        assert "test error message" in event.content

    def test_truncates_long_output(self, tmp_path: Path) -> None:
        """Truncates output to last N lines when output is very long."""
        mock_handler = MagicMock()
        runner = DomainRunner(
            tmp_path, LucidSharkConfig(), verbose=True, stream_handler=mock_handler
        )

        # Create output with 200 lines
        long_output = "\n".join([f"line {i}" for i in range(200)])
        result = subprocess.CompletedProcess(
            args="test", returncode=1, stdout="", stderr=long_output
        )

        runner._log_command_failure("test_command", result, max_lines=50)

        mock_handler.emit.assert_called_once()
        event = mock_handler.emit.call_args[0][0]
        assert "showing last 50 of 200 lines" in event.content
        # Should contain the last lines
        assert "line 199" in event.content
        # Should NOT contain early lines
        assert "line 0\n" not in event.content

    def test_combines_stdout_and_stderr(self, tmp_path: Path) -> None:
        """When both stdout and stderr present, combines them with stderr marked."""
        mock_handler = MagicMock()
        runner = DomainRunner(
            tmp_path, LucidSharkConfig(), verbose=True, stream_handler=mock_handler
        )
        result = subprocess.CompletedProcess(
            args="test",
            returncode=1,
            stdout="stdout content",
            stderr="stderr content",
        )

        runner._log_command_failure("test_command", result)

        event = mock_handler.emit.call_args[0][0]
        # Both should be in the output with stderr marked
        assert "stdout content" in event.content
        assert "--- stderr ---" in event.content
        assert "stderr content" in event.content

    def test_stdout_only(self, tmp_path: Path) -> None:
        """When only stdout has content, shows stdout."""
        mock_handler = MagicMock()
        runner = DomainRunner(
            tmp_path, LucidSharkConfig(), verbose=True, stream_handler=mock_handler
        )
        result = subprocess.CompletedProcess(
            args="test", returncode=1, stdout="stdout only", stderr=""
        )

        runner._log_command_failure("test_command", result)

        event = mock_handler.emit.call_args[0][0]
        assert "stdout only" in event.content
        # No stderr marker when stderr is empty
        assert "--- stderr ---" not in event.content

    def test_no_output_when_both_empty(self, tmp_path: Path) -> None:
        """When both stdout and stderr are empty, nothing is emitted."""
        mock_handler = MagicMock()
        runner = DomainRunner(
            tmp_path, LucidSharkConfig(), verbose=True, stream_handler=mock_handler
        )
        result = subprocess.CompletedProcess(
            args="test", returncode=1, stdout="", stderr=""
        )

        runner._log_command_failure("test_command", result)

        mock_handler.emit.assert_not_called()

    def test_whitespace_only_treated_as_empty(self, tmp_path: Path) -> None:
        """Whitespace-only output is treated as empty."""
        mock_handler = MagicMock()
        runner = DomainRunner(
            tmp_path, LucidSharkConfig(), verbose=True, stream_handler=mock_handler
        )
        result = subprocess.CompletedProcess(
            args="test", returncode=1, stdout="   \n\t  ", stderr="  \n  "
        )

        runner._log_command_failure("test_command", result)

        mock_handler.emit.assert_not_called()

    def test_falls_back_to_logger_without_stream_handler(self, tmp_path: Path) -> None:
        """When verbose but no stream_handler, falls back to logger."""
        runner = DomainRunner(
            tmp_path, LucidSharkConfig(), verbose=True, stream_handler=None
        )
        result = subprocess.CompletedProcess(
            args="test", returncode=1, stdout="", stderr="error output"
        )

        with patch("lucidshark.core.domain_runner.LOGGER") as mock_logger:
            runner._log_command_failure("test_command", result)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            assert "error output" in call_args
