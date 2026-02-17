"""Tests for lucidshark.cli.commands.doctor."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch


from lucidshark.cli.commands.doctor import CheckResult, DoctorCommand
from lucidshark.cli.exit_codes import EXIT_ISSUES_FOUND, EXIT_SUCCESS
from lucidshark.bootstrap.validation import ToolStatus
from lucidshark.config.validation import ConfigValidationIssue, ValidationSeverity


# ---------------------------------------------------------------------------
# CheckResult tests
# ---------------------------------------------------------------------------


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_passed_status_icon(self) -> None:
        r = CheckResult("test", True, "all good")
        assert r.status_icon == "[OK]"

    def test_failed_status_icon(self) -> None:
        r = CheckResult("test", False, "something wrong")
        assert r.status_icon == "[!!]"

    def test_attributes(self) -> None:
        r = CheckResult("mycheck", True, "msg", hint="fix it")
        assert r.name == "mycheck"
        assert r.passed is True
        assert r.message == "msg"
        assert r.hint == "fix it"

    def test_default_hint_empty(self) -> None:
        r = CheckResult("x", True, "ok")
        assert r.hint == ""


# ---------------------------------------------------------------------------
# DoctorCommand basic
# ---------------------------------------------------------------------------


class TestDoctorCommandBasic:
    """Basic property and plumbing tests."""

    def test_name(self) -> None:
        cmd = DoctorCommand(version="1.0.0")
        assert cmd.name == "doctor"

    def test_version_stored(self) -> None:
        cmd = DoctorCommand(version="2.3.4")
        assert cmd._version == "2.3.4"


# ---------------------------------------------------------------------------
# DoctorCommand.execute
# ---------------------------------------------------------------------------


class TestDoctorExecute:
    """Tests for the execute() entry point."""

    @patch.object(DoctorCommand, "_check_integrations", return_value=[])
    @patch.object(DoctorCommand, "_check_environment", return_value=[])
    @patch.object(DoctorCommand, "_check_tools", return_value=[])
    @patch.object(DoctorCommand, "_check_configuration", return_value=[])
    def test_all_pass(self, mock_conf, mock_tools, mock_env, mock_int, capsys) -> None:
        cmd = DoctorCommand(version="1.0.0")
        result = cmd.execute(Namespace())

        assert result == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "0 issues" in captured.out

    @patch.object(DoctorCommand, "_check_integrations", return_value=[])
    @patch.object(DoctorCommand, "_check_environment", return_value=[])
    @patch.object(DoctorCommand, "_check_tools", return_value=[])
    @patch.object(
        DoctorCommand,
        "_check_configuration",
        return_value=[CheckResult("config_file", False, "No config", "Run init")],
    )
    def test_failure_returns_issues_found(
        self, mock_conf, mock_tools, mock_env, mock_int, capsys
    ) -> None:
        cmd = DoctorCommand(version="1.0.0")
        result = cmd.execute(Namespace())

        assert result == EXIT_ISSUES_FOUND
        captured = capsys.readouterr()
        assert "1 issues" in captured.out
        assert "fix issues" in captured.out.lower()

    @patch.object(DoctorCommand, "_check_integrations", return_value=[])
    @patch.object(DoctorCommand, "_check_environment", return_value=[])
    @patch.object(DoctorCommand, "_check_tools", return_value=[])
    @patch.object(DoctorCommand, "_check_configuration", return_value=[])
    def test_prints_version(self, mock_conf, mock_tools, mock_env, mock_int, capsys) -> None:
        cmd = DoctorCommand(version="0.5.26")
        cmd.execute(Namespace())

        captured = capsys.readouterr()
        assert "0.5.26" in captured.out


# ---------------------------------------------------------------------------
# _check_configuration
# ---------------------------------------------------------------------------


class TestCheckConfiguration:
    """Tests for _check_configuration."""

    @patch("lucidshark.cli.commands.doctor.find_project_config", return_value=None)
    def test_no_config_file(self, mock_find, tmp_path: Path) -> None:
        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_configuration(tmp_path)

        assert len(results) == 1
        assert results[0].passed is False
        assert "No lucidshark.yml" in results[0].message

    @patch("lucidshark.cli.commands.doctor.validate_config_file")
    @patch("lucidshark.cli.commands.doctor.find_project_config")
    def test_config_valid_no_issues(
        self, mock_find, mock_validate, tmp_path: Path
    ) -> None:
        mock_find.return_value = tmp_path / "lucidshark.yml"
        mock_validate.return_value = (True, [])

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_configuration(tmp_path)

        assert len(results) == 2
        assert all(r.passed for r in results)
        assert "is valid" in results[1].message

    @patch("lucidshark.cli.commands.doctor.validate_config_file")
    @patch("lucidshark.cli.commands.doctor.find_project_config")
    def test_config_with_errors(
        self, mock_find, mock_validate, tmp_path: Path
    ) -> None:
        mock_find.return_value = tmp_path / "lucidshark.yml"
        error = ConfigValidationIssue(
            message="Bad key",
            source="lucidshark.yml",
            severity=ValidationSeverity.ERROR,
        )
        mock_validate.return_value = (False, [error])

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_configuration(tmp_path)

        config_valid = [r for r in results if r.name == "config_valid"]
        assert len(config_valid) == 1
        assert config_valid[0].passed is False
        assert "1 error" in config_valid[0].message

    @patch("lucidshark.cli.commands.doctor.validate_config_file")
    @patch("lucidshark.cli.commands.doctor.find_project_config")
    def test_config_with_warnings_only(
        self, mock_find, mock_validate, tmp_path: Path
    ) -> None:
        mock_find.return_value = tmp_path / ".lucidshark.yml"
        warning = ConfigValidationIssue(
            message="Deprecated key",
            source=".lucidshark.yml",
            severity=ValidationSeverity.WARNING,
        )
        mock_validate.return_value = (True, [warning])

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_configuration(tmp_path)

        config_valid = [r for r in results if r.name == "config_valid"]
        assert len(config_valid) == 1
        assert config_valid[0].passed is True
        assert "1 warning" in config_valid[0].message


# ---------------------------------------------------------------------------
# _check_tools
# ---------------------------------------------------------------------------


class TestCheckTools:
    """Tests for _check_tools."""

    @patch("lucidshark.cli.commands.doctor.validate_binary", return_value=ToolStatus.PRESENT)
    @patch("lucidshark.cli.commands.doctor.discover_scanner_plugins")
    @patch.object(DoctorCommand, "_check_pip_tool", return_value=True)
    def test_all_tools_installed(
        self, mock_pip, mock_discover, mock_validate, tmp_path: Path
    ) -> None:
        mock_plugin = MagicMock()
        mock_plugin.return_value.get_version.return_value = "0.50.0"
        mock_discover.return_value = {"trivy": mock_plugin}

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_tools(tmp_path)

        scanner_results = [r for r in results if r.name == "tool_trivy"]
        assert len(scanner_results) == 1
        assert scanner_results[0].passed is True
        assert "installed" in scanner_results[0].message

    @patch("lucidshark.cli.commands.doctor.validate_binary", return_value=ToolStatus.MISSING)
    @patch("lucidshark.cli.commands.doctor.discover_scanner_plugins")
    @patch.object(DoctorCommand, "_check_pip_tool", return_value=False)
    def test_scanner_not_installed(
        self, mock_pip, mock_discover, mock_validate, tmp_path: Path
    ) -> None:
        mock_plugin = MagicMock()
        mock_plugin.return_value.get_version.return_value = "0.50.0"
        mock_discover.return_value = {"trivy": mock_plugin}

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_tools(tmp_path)

        scanner_results = [r for r in results if r.name == "tool_trivy"]
        assert len(scanner_results) == 1
        assert scanner_results[0].passed is False
        assert "not installed" in scanner_results[0].message

    @patch("lucidshark.cli.commands.doctor.discover_scanner_plugins")
    @patch.object(DoctorCommand, "_check_pip_tool", return_value=True)
    def test_scanner_plugin_error(
        self, mock_pip, mock_discover, tmp_path: Path
    ) -> None:
        mock_plugin = MagicMock()
        mock_plugin.side_effect = RuntimeError("Plugin broken")
        mock_discover.return_value = {"broken": mock_plugin}

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_tools(tmp_path)

        error_results = [r for r in results if r.name == "tool_broken"]
        assert len(error_results) == 1
        assert error_results[0].passed is False
        assert "error" in error_results[0].message.lower()

    @patch("lucidshark.cli.commands.doctor.discover_scanner_plugins", return_value={})
    @patch.object(DoctorCommand, "_check_pip_tool")
    def test_pip_tool_available(
        self, mock_pip, mock_discover, tmp_path: Path
    ) -> None:
        mock_pip.return_value = True

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_tools(tmp_path)

        pip_results = [r for r in results if r.name.startswith("tool_")]
        # ruff, mypy, pyright available
        available = [r for r in pip_results if r.passed]
        assert len(available) == 3


# ---------------------------------------------------------------------------
# _check_environment
# ---------------------------------------------------------------------------


class TestCheckEnvironment:
    """Tests for _check_environment."""

    @patch.object(DoctorCommand, "_is_git_repo", return_value=True)
    @patch("lucidshark.cli.commands.doctor.get_platform_info")
    def test_environment_all_good(self, mock_platform, mock_git) -> None:
        mock_pi = MagicMock()
        mock_pi.os = "linux"
        mock_pi.arch = "amd64"
        mock_platform.return_value = mock_pi

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_environment()

        names = {r.name for r in results}
        assert "python_version" in names
        assert "platform" in names
        assert "git_repo" in names
        assert all(r.passed for r in results)

    @patch.object(DoctorCommand, "_is_git_repo", return_value=False)
    @patch("lucidshark.cli.commands.doctor.get_platform_info")
    def test_not_git_repo(self, mock_platform, mock_git) -> None:
        mock_pi = MagicMock()
        mock_pi.os = "darwin"
        mock_pi.arch = "arm64"
        mock_platform.return_value = mock_pi

        cmd = DoctorCommand(version="1.0.0")
        results = cmd._check_environment()

        git_result = [r for r in results if r.name == "git_repo"][0]
        assert git_result.passed is False
        assert "Not a git" in git_result.message


# ---------------------------------------------------------------------------
# _check_integrations (MCP config)
# ---------------------------------------------------------------------------


class TestCheckIntegrations:
    """Tests for _check_integrations / _check_mcp_config."""

    def test_check_mcp_config_project_configured(self, tmp_path: Path) -> None:
        mcp_json = tmp_path / ".mcp.json"
        mcp_json.write_text(json.dumps({"mcpServers": {"lucidshark": {}}}))

        cmd = DoctorCommand(version="1.0.0")
        result = cmd._check_mcp_config(
            name="test_mcp",
            display_name="Test",
            global_config=tmp_path / "global.json",
            project_config=tmp_path / "project.json",
            project_mcp_json=mcp_json,
            init_command="lucidshark init",
        )

        assert result is not None
        assert result.passed is True
        assert "configured" in result.message

    def test_check_mcp_config_global_configured(self, tmp_path: Path) -> None:
        global_config = tmp_path / "global.json"
        global_config.write_text(json.dumps({"mcpServers": {"lucidshark": {}}}))

        cmd = DoctorCommand(version="1.0.0")
        result = cmd._check_mcp_config(
            name="test_mcp",
            display_name="Test",
            global_config=global_config,
            project_config=tmp_path / "project.json",
            init_command="lucidshark init",
        )

        assert result is not None
        assert result.passed is True

    def test_check_mcp_config_exists_but_not_configured(self, tmp_path: Path) -> None:
        global_config = tmp_path / "global.json"
        global_config.write_text(json.dumps({"mcpServers": {"other": {}}}))

        cmd = DoctorCommand(version="1.0.0")
        result = cmd._check_mcp_config(
            name="test_mcp",
            display_name="Test",
            global_config=global_config,
            project_config=tmp_path / "project.json",
            init_command="lucidshark init",
        )

        assert result is not None
        assert result.passed is False
        assert "not configured" in result.message

    def test_check_mcp_config_invalid_json(self, tmp_path: Path) -> None:
        global_config = tmp_path / "global.json"
        global_config.write_text("{invalid json")

        cmd = DoctorCommand(version="1.0.0")
        result = cmd._check_mcp_config(
            name="test_mcp",
            display_name="Test",
            global_config=global_config,
            project_config=tmp_path / "project.json",
            init_command="lucidshark init",
        )

        assert result is not None
        assert result.passed is False
        assert "Could not read" in result.message

    def test_check_mcp_config_not_installed_report(self, tmp_path: Path) -> None:
        cmd = DoctorCommand(version="1.0.0")
        result = cmd._check_mcp_config(
            name="test_mcp",
            display_name="Test",
            global_config=tmp_path / "nonexistent.json",
            project_config=tmp_path / "also_nonexistent.json",
            init_command="lucidshark init",
            report_if_missing=True,
        )

        assert result is not None
        assert result.passed is False
        assert "not installed" in result.message

    def test_check_mcp_config_not_installed_skip(self, tmp_path: Path) -> None:
        cmd = DoctorCommand(version="1.0.0")
        result = cmd._check_mcp_config(
            name="test_mcp",
            display_name="Test",
            global_config=tmp_path / "nonexistent.json",
            project_config=tmp_path / "also_nonexistent.json",
            init_command="lucidshark init",
            report_if_missing=False,
        )

        assert result is None


# ---------------------------------------------------------------------------
# _print_results
# ---------------------------------------------------------------------------


class TestPrintResults:
    """Tests for _print_results output."""

    def test_groups_by_category(self, capsys) -> None:
        results = [
            CheckResult("config_file", True, "Found lucidshark.yml"),
            CheckResult("python_version", True, "Python 3.13"),
            CheckResult("tool_trivy", False, "trivy not installed", "Download it"),
        ]
        cmd = DoctorCommand(version="1.0.0")
        cmd._print_results(results)

        captured = capsys.readouterr()
        assert "Configuration" in captured.out
        assert "Environment" in captured.out
        assert "Tools" in captured.out
        assert "[OK]" in captured.out
        assert "[!!]" in captured.out
        assert "Download it" in captured.out

    def test_empty_results(self, capsys) -> None:
        cmd = DoctorCommand(version="1.0.0")
        cmd._print_results([])

        captured = capsys.readouterr()
        # No categories printed
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Helper methods
# ---------------------------------------------------------------------------


class TestHelperMethods:
    """Tests for _is_git_repo, _check_pip_tool, _get_domain_flag."""

    @patch("lucidshark.cli.commands.doctor.subprocess.run")
    def test_is_git_repo_true(self, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        cmd = DoctorCommand(version="1.0.0")
        assert cmd._is_git_repo() is True

    @patch("lucidshark.cli.commands.doctor.subprocess.run")
    def test_is_git_repo_false(self, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=128)
        cmd = DoctorCommand(version="1.0.0")
        assert cmd._is_git_repo() is False

    @patch("lucidshark.cli.commands.doctor.subprocess.run")
    def test_is_git_repo_exception(self, mock_run) -> None:
        mock_run.side_effect = OSError("not found")
        cmd = DoctorCommand(version="1.0.0")
        assert cmd._is_git_repo() is False

    @patch("lucidshark.cli.commands.doctor.subprocess.run")
    def test_check_pip_tool_found(self, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        cmd = DoctorCommand(version="1.0.0")
        assert cmd._check_pip_tool("ruff") is True

    @patch("lucidshark.cli.commands.doctor.subprocess.run")
    def test_check_pip_tool_not_found(self, mock_run) -> None:
        mock_run.side_effect = FileNotFoundError("ruff not found")
        cmd = DoctorCommand(version="1.0.0")
        assert cmd._check_pip_tool("ruff") is False

    @patch("lucidshark.cli.commands.doctor.subprocess.run")
    def test_check_pip_tool_nonzero_exit(self, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        cmd = DoctorCommand(version="1.0.0")
        assert cmd._check_pip_tool("ruff") is False

    def test_get_domain_flag_known(self) -> None:
        cmd = DoctorCommand(version="1.0.0")
        assert cmd._get_domain_flag("trivy") == "sca"
        assert cmd._get_domain_flag("opengrep") == "sast"
        assert cmd._get_domain_flag("checkov") == "iac"

    def test_get_domain_flag_unknown(self) -> None:
        cmd = DoctorCommand(version="1.0.0")
        assert cmd._get_domain_flag("unknown") == "all"
