"""Tests for lucidshark.cli.commands.scan."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.cli.commands.scan import ScanCommand
from lucidshark.cli.exit_codes import (
    EXIT_ISSUES_FOUND,
    EXIT_SCANNER_ERROR,
    EXIT_SUCCESS,
)
from lucidshark.config.models import (
    DomainPipelineConfig,
    DuplicationPipelineConfig,
    CoveragePipelineConfig,
    FailOnConfig,
    LucidSharkConfig,
    OutputConfig,
    PipelineConfig,
    ProjectConfig,
    ToolConfig,
)
from lucidshark.core.models import (
    CoverageSummary,
    DuplicationSummary,
    ScanDomain,
    ScanResult,
    Severity,
    ToolDomain,
    UnifiedIssue,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides: object) -> LucidSharkConfig:
    """Build a minimal LucidSharkConfig with sensible defaults."""
    defaults: dict[str, object] = dict(
        project=ProjectConfig(name="test", languages=["python"]),
        output=OutputConfig(format="json"),
        pipeline=PipelineConfig(),
        scanners={},
        fail_on=None,
        ignore=[],
    )
    defaults.update(overrides)
    return LucidSharkConfig(**defaults)  # type: ignore[arg-type]


def _make_args(tmp_path: Path, **overrides) -> Namespace:
    """Build a minimal Namespace with sensible defaults for a scan."""
    defaults = dict(
        path=str(tmp_path),
        format="json",
        fail_on=None,
        dry_run=False,
        all=False,
        linting=False,
        type_checking=False,
        testing=False,
        coverage=False,
        duplication=False,
        sca=False,
        sast=False,
        iac=False,
        container=False,
        fix=False,
        stream=False,
        verbose=False,
        files=None,
        all_files=False,
        sequential=False,
        images=None,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def _make_issue(
    domain=ToolDomain.LINTING,
    severity=Severity.MEDIUM,
    rule_id="TEST001",
) -> UnifiedIssue:
    return UnifiedIssue(
        id="test-1",
        domain=domain,
        source_tool="test",
        severity=severity,
        rule_id=rule_id,
        title="Test issue",
        description="A test issue",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScanCommandBasic:
    """Basic ScanCommand properties and guard clauses."""

    def test_name(self) -> None:
        cmd = ScanCommand(version="1.0.0")
        assert cmd.name == "scan"

    def test_execute_requires_config(self, tmp_path: Path) -> None:
        cmd = ScanCommand(version="1.0.0")
        args = _make_args(tmp_path)
        result = cmd.execute(args, config=None)
        assert result == EXIT_SCANNER_ERROR


class TestScanCommandExecute:
    """Tests for the execute() method with mocked internal scan."""

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    def test_execute_success_no_issues(
        self, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.return_value = ScanResult(issues=[])
        mock_reporter = MagicMock()
        mock_get_reporter.return_value = mock_reporter

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        result = cmd.execute(args, config)

        assert result == EXIT_SUCCESS
        mock_reporter.report.assert_called_once()

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    def test_execute_reporter_not_found(
        self, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.return_value = ScanResult(issues=[])
        mock_get_reporter.return_value = None

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        result = cmd.execute(args, config)

        assert result == EXIT_SCANNER_ERROR

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    def test_execute_format_from_cli(
        self, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.return_value = ScanResult(issues=[])
        mock_reporter = MagicMock()
        mock_get_reporter.return_value = mock_reporter

        cmd = ScanCommand(version="1.0.0")
        config = _make_config(output=OutputConfig(format="sarif"))
        args = _make_args(tmp_path, format="table")

        cmd.execute(args, config)

        # CLI format takes precedence
        mock_get_reporter.assert_called_once_with("table")

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    def test_execute_format_from_config(
        self, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.return_value = ScanResult(issues=[])
        mock_reporter = MagicMock()
        mock_get_reporter.return_value = mock_reporter

        cmd = ScanCommand(version="1.0.0")
        config = _make_config(output=OutputConfig(format="sarif"))
        args = _make_args(tmp_path, format=None)

        cmd.execute(args, config)

        mock_get_reporter.assert_called_once_with("sarif")

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    def test_execute_format_default_json(
        self, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.return_value = ScanResult(issues=[])
        mock_reporter = MagicMock()
        mock_get_reporter.return_value = mock_reporter

        cmd = ScanCommand(version="1.0.0")
        config = _make_config(output=OutputConfig(format=""))
        args = _make_args(tmp_path, format=None)

        cmd.execute(args, config)

        mock_get_reporter.assert_called_once_with("json")

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    def test_execute_fail_on_cli_override(
        self, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        issue = _make_issue(severity=Severity.HIGH)
        mock_run_scan.return_value = ScanResult(issues=[issue])
        mock_get_reporter.return_value = MagicMock()

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, fail_on="high")

        result = cmd.execute(args, config)

        assert result == EXIT_ISSUES_FOUND

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    def test_execute_fail_on_cli_no_match(
        self, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        issue = _make_issue(severity=Severity.LOW)
        mock_run_scan.return_value = ScanResult(issues=[issue])
        mock_get_reporter.return_value = MagicMock()

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, fail_on="critical")

        result = cmd.execute(args, config)

        assert result == EXIT_SUCCESS

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    @patch.object(ScanCommand, "_check_domain_thresholds", return_value=True)
    def test_execute_domain_thresholds_fail(
        self, mock_check, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.return_value = ScanResult(issues=[_make_issue()])
        mock_get_reporter.return_value = MagicMock()

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        result = cmd.execute(args, config)

        assert result == EXIT_ISSUES_FOUND

    @patch.object(ScanCommand, "_run_scan")
    @patch("lucidshark.cli.commands.scan.get_reporter_plugin")
    @patch.object(ScanCommand, "_check_domain_thresholds", return_value=False)
    def test_execute_domain_thresholds_pass(
        self, mock_check, mock_get_reporter, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.return_value = ScanResult(issues=[_make_issue()])
        mock_get_reporter.return_value = MagicMock()

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        result = cmd.execute(args, config)

        assert result == EXIT_SUCCESS

    @patch.object(ScanCommand, "_run_scan")
    def test_execute_file_not_found(
        self, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.side_effect = FileNotFoundError("Path does not exist")

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        with pytest.raises(FileNotFoundError):
            cmd.execute(args, config)

    @patch.object(ScanCommand, "_run_scan")
    def test_execute_unexpected_error(
        self, mock_run_scan, tmp_path: Path
    ) -> None:
        mock_run_scan.side_effect = RuntimeError("Unexpected")

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        with pytest.raises(RuntimeError):
            cmd.execute(args, config)

    @patch.object(ScanCommand, "_dry_run", return_value=EXIT_SUCCESS)
    def test_execute_dry_run_delegates(
        self, mock_dry_run, tmp_path: Path
    ) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, dry_run=True)

        result = cmd.execute(args, config)

        assert result == EXIT_SUCCESS
        mock_dry_run.assert_called_once_with(args, config)


class TestScanCommandRunScan:
    """Tests for _run_scan with mocked DomainRunner and PipelineExecutor."""

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_linting_only(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.coverage_result = None
        mock_ctx.duplication_result = None
        mock_create_ctx.return_value = mock_ctx

        mock_runner = MagicMock()
        mock_runner.run_linting.return_value = [_make_issue()]
        mock_runner_cls.return_value = mock_runner

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, linting=True)

        result = cmd._run_scan(args, config)

        assert len(result.issues) == 1
        mock_runner.run_linting.assert_called_once()

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_type_checking(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.coverage_result = None
        mock_ctx.duplication_result = None
        mock_create_ctx.return_value = mock_ctx

        mock_runner = MagicMock()
        mock_runner.run_type_checking.return_value = [
            _make_issue(domain=ToolDomain.TYPE_CHECKING)
        ]
        mock_runner_cls.return_value = mock_runner

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, type_checking=True)

        result = cmd._run_scan(args, config)

        assert len(result.issues) == 1
        mock_runner.run_type_checking.assert_called_once()

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_testing_only(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.coverage_result = None
        mock_ctx.duplication_result = None
        mock_create_ctx.return_value = mock_ctx

        mock_runner = MagicMock()
        mock_runner.run_tests.return_value = []
        mock_runner_cls.return_value = mock_runner

        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            pipeline=PipelineConfig(
                testing=DomainPipelineConfig(enabled=True),
            )
        )
        args = _make_args(tmp_path, testing=True)

        result = cmd._run_scan(args, config)

        assert result.issues == []
        mock_runner.run_tests.assert_called_once_with(mock_ctx, with_coverage=False)

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_testing_with_coverage(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = []
        mock_ctx = MagicMock()
        mock_cov_result = MagicMock()
        mock_cov_result.to_summary.return_value = CoverageSummary(
            coverage_percentage=85.0, passed=True
        )
        mock_ctx.coverage_result = mock_cov_result
        mock_ctx.duplication_result = None
        mock_create_ctx.return_value = mock_ctx

        mock_runner = MagicMock()
        mock_runner.run_tests.return_value = []
        mock_runner.run_coverage.return_value = []
        mock_runner_cls.return_value = mock_runner

        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            pipeline=PipelineConfig(
                testing=DomainPipelineConfig(enabled=True),
                coverage=CoveragePipelineConfig(enabled=True, threshold=80),
            )
        )
        args = _make_args(tmp_path, testing=True, coverage=True)

        result = cmd._run_scan(args, config)

        mock_runner.run_tests.assert_called_once_with(mock_ctx, with_coverage=True)
        mock_runner.run_coverage.assert_called_once()
        assert result.coverage_summary is not None
        assert result.coverage_summary.coverage_percentage == 85.0

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_duplication(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.coverage_result = None
        mock_dup_result = MagicMock()
        mock_dup_result.to_summary.return_value = DuplicationSummary(
            duplication_percent=3.0, passed=True
        )
        mock_ctx.duplication_result = mock_dup_result
        mock_create_ctx.return_value = mock_ctx

        mock_runner = MagicMock()
        mock_runner.run_duplication.return_value = []
        mock_runner_cls.return_value = mock_runner

        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            pipeline=PipelineConfig(
                duplication=DuplicationPipelineConfig(
                    enabled=True, threshold=10.0, min_lines=4
                ),
            )
        )
        args = _make_args(tmp_path, duplication=True)

        result = cmd._run_scan(args, config)

        mock_runner.run_duplication.assert_called_once()
        assert result.duplication_summary is not None
        assert result.duplication_summary.duplication_percent == 3.0

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_security_domains(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = [ScanDomain.SCA]
        mock_ctx = MagicMock()
        mock_ctx.coverage_result = None
        mock_ctx.duplication_result = None
        mock_create_ctx.return_value = mock_ctx

        mock_runner_cls.return_value = MagicMock()

        mock_config = _make_config()
        mock_config.get_plugin_for_domain = MagicMock(return_value="trivy")  # type: ignore[method-assign]

        pipeline_result = ScanResult(issues=[_make_issue(domain=ScanDomain.SCA)])
        pipeline_result.metadata = None
        mock_executor = MagicMock()
        mock_executor.execute.return_value = pipeline_result
        mock_executor_cls.return_value = mock_executor

        cmd = ScanCommand(version="1.0.0")
        args = _make_args(tmp_path, sca=True)

        result = cmd._run_scan(args, mock_config)

        assert len(result.issues) == 1
        mock_executor.execute.assert_called_once()

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_nonexistent_path(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        nonexistent = tmp_path / "does_not_exist"
        args = _make_args(tmp_path, path=str(nonexistent))

        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            cmd._run_scan(args, config)

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_all_flag_with_configured_domains(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.coverage_result = None
        mock_ctx.duplication_result = None
        mock_create_ctx.return_value = mock_ctx

        mock_runner = MagicMock()
        mock_runner.run_linting.return_value = []
        mock_runner.run_type_checking.return_value = []
        mock_runner_cls.return_value = mock_runner

        cmd = ScanCommand(version="1.0.0")
        # linting=None means default (enabled), type_checking=None means default (enabled)
        config = _make_config()
        args = _make_args(tmp_path, **{"all": True})

        cmd._run_scan(args, config)

        # With --all and default pipeline config (linting/type_checking are None -> enabled)
        mock_runner.run_linting.assert_called_once()
        mock_runner.run_type_checking.assert_called_once()

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_with_stream_handler(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.coverage_result = None
        mock_ctx.duplication_result = None
        mock_create_ctx.return_value = mock_ctx
        mock_runner_cls.return_value = MagicMock()

        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, stream=True)

        # Should not raise - stream handler is created internally
        cmd._run_scan(args, config)

        mock_create_ctx.assert_called_once()

    @patch("lucidshark.cli.commands.scan.PipelineExecutor")
    @patch("lucidshark.cli.commands.scan.DomainRunner")
    @patch("lucidshark.cli.commands.scan.ScanContext.create")
    @patch("lucidshark.cli.commands.scan.ConfigBridge.get_enabled_domains")
    def test_run_scan_preserves_pipeline_metadata(
        self,
        mock_get_domains,
        mock_create_ctx,
        mock_runner_cls,
        mock_executor_cls,
        tmp_path: Path,
    ) -> None:
        mock_get_domains.return_value = [ScanDomain.SAST]
        mock_ctx = MagicMock()
        mock_ctx.coverage_result = None
        mock_ctx.duplication_result = None
        mock_create_ctx.return_value = mock_ctx
        mock_runner_cls.return_value = MagicMock()

        mock_config = _make_config()
        mock_config.get_plugin_for_domain = MagicMock(return_value="opengrep")  # type: ignore[method-assign]

        metadata = MagicMock()
        pipeline_result = ScanResult(issues=[])
        pipeline_result.metadata = metadata
        mock_executor = MagicMock()
        mock_executor.execute.return_value = pipeline_result
        mock_executor_cls.return_value = mock_executor

        cmd = ScanCommand(version="1.0.0")
        args = _make_args(tmp_path, sast=True)

        result = cmd._run_scan(args, mock_config)

        assert result.metadata is metadata


class TestCheckDomainThresholds:
    """Tests for _check_domain_thresholds."""

    def _cmd(self) -> ScanCommand:
        return ScanCommand(version="1.0.0")

    def test_no_threshold_returns_false(self) -> None:
        config = _make_config(fail_on=None)
        result = ScanResult(issues=[_make_issue()])
        assert self._cmd()._check_domain_thresholds(result, config) is False

    def test_threshold_any_with_issues(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(linting="any")
        )
        result = ScanResult(issues=[_make_issue(domain=ToolDomain.LINTING)])
        assert self._cmd()._check_domain_thresholds(result, config) is True

    def test_threshold_any_no_issues(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(linting="any")
        )
        result = ScanResult(issues=[])
        assert self._cmd()._check_domain_thresholds(result, config) is False

    def test_threshold_error_with_high_severity(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(linting="error")
        )
        issue = _make_issue(domain=ToolDomain.LINTING, severity=Severity.HIGH)
        result = ScanResult(issues=[issue])
        assert self._cmd()._check_domain_thresholds(result, config) is True

    def test_threshold_error_with_low_severity(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(linting="error")
        )
        issue = _make_issue(domain=ToolDomain.LINTING, severity=Severity.LOW)
        result = ScanResult(issues=[issue])
        assert self._cmd()._check_domain_thresholds(result, config) is False

    def test_threshold_none_never_fails(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(linting="none")
        )
        issue = _make_issue(domain=ToolDomain.LINTING, severity=Severity.CRITICAL)
        result = ScanResult(issues=[issue])
        assert self._cmd()._check_domain_thresholds(result, config) is False

    def test_threshold_above_threshold_duplication_fail(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(duplication="above_threshold")
        )
        issue = _make_issue(domain=ToolDomain.DUPLICATION)
        result = ScanResult(issues=[issue])
        result.duplication_summary = DuplicationSummary(
            duplication_percent=15.0, threshold=10.0, passed=False
        )
        assert self._cmd()._check_domain_thresholds(result, config) is True

    def test_threshold_above_threshold_duplication_pass(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(duplication="above_threshold")
        )
        issue = _make_issue(domain=ToolDomain.DUPLICATION)
        result = ScanResult(issues=[issue])
        result.duplication_summary = DuplicationSummary(
            duplication_percent=5.0, threshold=10.0, passed=True
        )
        assert self._cmd()._check_domain_thresholds(result, config) is False

    def test_threshold_below_threshold_coverage_fail(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(coverage="below_threshold")
        )
        issue = _make_issue(domain=ToolDomain.COVERAGE)
        result = ScanResult(issues=[issue])
        result.coverage_summary = CoverageSummary(
            coverage_percentage=60.0, threshold=80.0, passed=False
        )
        assert self._cmd()._check_domain_thresholds(result, config) is True

    def test_threshold_below_threshold_coverage_pass(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(coverage="below_threshold")
        )
        issue = _make_issue(domain=ToolDomain.COVERAGE)
        result = ScanResult(issues=[issue])
        result.coverage_summary = CoverageSummary(
            coverage_percentage=90.0, threshold=80.0, passed=True
        )
        assert self._cmd()._check_domain_thresholds(result, config) is False

    def test_threshold_percentage_duplication(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(duplication="5%")
        )
        issue = _make_issue(domain=ToolDomain.DUPLICATION)
        result = ScanResult(issues=[issue])
        result.duplication_summary = DuplicationSummary(
            duplication_percent=8.0, threshold=5.0, passed=False
        )
        assert self._cmd()._check_domain_thresholds(result, config) is True

    def test_threshold_percentage_duplication_under(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(duplication="10%")
        )
        issue = _make_issue(domain=ToolDomain.DUPLICATION)
        result = ScanResult(issues=[issue])
        result.duplication_summary = DuplicationSummary(
            duplication_percent=3.0, threshold=10.0, passed=True
        )
        assert self._cmd()._check_domain_thresholds(result, config) is False

    def test_threshold_invalid_percentage(self) -> None:
        config = _make_config(
            fail_on=FailOnConfig(duplication="abc%")
        )
        issue = _make_issue(domain=ToolDomain.DUPLICATION)
        result = ScanResult(issues=[issue])
        result.duplication_summary = DuplicationSummary()
        assert self._cmd()._check_domain_thresholds(result, config) is False

    @patch("lucidshark.cli.commands.scan.check_severity_threshold", return_value=True)
    def test_threshold_severity_string(self, mock_check) -> None:
        config = _make_config(
            fail_on=FailOnConfig(security="high")
        )
        issue = _make_issue(domain=ScanDomain.SCA, severity=Severity.HIGH)
        result = ScanResult(issues=[issue])
        assert self._cmd()._check_domain_thresholds(result, config) is True

    def test_scan_domain_maps_to_security(self) -> None:
        """SCA, CONTAINER, IAC, SAST issues all map to 'security' domain."""
        config = _make_config(
            fail_on=FailOnConfig(security="any")
        )
        for domain in [ScanDomain.SCA, ScanDomain.CONTAINER, ScanDomain.IAC, ScanDomain.SAST]:
            issue = _make_issue(domain=domain)
            result = ScanResult(issues=[issue])
            assert self._cmd()._check_domain_thresholds(result, config) is True


class TestDryRun:
    """Tests for _dry_run output and behavior."""

    def test_dry_run_returns_success(self, tmp_path: Path) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        result = cmd._dry_run(args, config)

        assert result == EXIT_SUCCESS

    def test_dry_run_with_linting_flag(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, linting=True)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "linting" in captured.out
        assert "Domains to scan:" in captured.out

    def test_dry_run_with_all_flag(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(enabled=True),
                type_checking=DomainPipelineConfig(enabled=True),
            )
        )
        args = _make_args(tmp_path, **{"all": True})

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "linting" in captured.out
        assert "type_checking" in captured.out

    def test_dry_run_no_domains(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config(pipeline=PipelineConfig(linting=DomainPipelineConfig(enabled=False)))
        args = _make_args(tmp_path)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "No domains selected" in captured.out

    def test_dry_run_specific_files(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, files=["src/app.py", "src/main.py"])

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "src/app.py" in captured.out

    def test_dry_run_all_files(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, all_files=True)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "All files" in captured.out

    def test_dry_run_changed_files_default(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "Changed files" in captured.out

    def test_dry_run_fail_on_cli(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, fail_on="high")

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "high" in captured.out
        assert "CLI override" in captured.out

    def test_dry_run_fail_on_config_default(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "per-domain thresholds" in captured.out

    def test_dry_run_project_info(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            project=ProjectConfig(name="my-project", languages=["python", "typescript"])
        )
        args = _make_args(tmp_path)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "my-project" in captured.out
        assert "python" in captured.out

    def test_dry_run_container_images(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config()
        args = _make_args(tmp_path, images=["nginx:latest", "alpine:3.18"])

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "nginx:latest" in captured.out
        assert "alpine:3.18" in captured.out

    def test_dry_run_testing_flag(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            pipeline=PipelineConfig(
                testing=DomainPipelineConfig(enabled=True),
            )
        )
        args = _make_args(tmp_path, testing=True)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "testing" in captured.out

    def test_dry_run_coverage_flag(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            pipeline=PipelineConfig(
                coverage=CoveragePipelineConfig(enabled=True),
            )
        )
        args = _make_args(tmp_path, coverage=True)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "coverage" in captured.out

    def test_dry_run_duplication_flag(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            pipeline=PipelineConfig(
                duplication=DuplicationPipelineConfig(enabled=True),
            )
        )
        args = _make_args(tmp_path, duplication=True)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "duplication" in captured.out

    def test_dry_run_with_tools_listed(self, tmp_path: Path, capsys) -> None:
        cmd = ScanCommand(version="1.0.0")
        config = _make_config(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="ruff")],
                ),
            )
        )
        args = _make_args(tmp_path, linting=True)

        cmd._dry_run(args, config)

        captured = capsys.readouterr()
        assert "ruff" in captured.out
        assert "Tools that would run:" in captured.out
