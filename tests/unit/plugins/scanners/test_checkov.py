"""Unit tests for Checkov scanner plugin."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, ScanDomain, Severity
from lucidshark.plugins.scanners.checkov import (
    CheckovScanner,
    CHECKOV_SEVERITY_MAP,
    _glob_to_regex,
)

_CHECKOV_BINARY = "checkov.exe" if sys.platform == "win32" else "checkov"


def _make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def scanner(tmp_path: Path) -> CheckovScanner:
    return CheckovScanner(version="3.2.499", project_root=tmp_path)


@pytest.fixture
def scan_context(tmp_path: Path) -> ScanContext:
    return ScanContext(
        project_root=tmp_path,
        paths=[tmp_path],
        enabled_domains=[ScanDomain.IAC],
    )


@pytest.fixture
def sample_checkov_output() -> str:
    return json.dumps(
        {
            "check_type": "terraform",
            "results": {
                "failed_checks": [
                    {
                        "check_id": "CKV_AWS_18",
                        "check": "Ensure the S3 bucket has access logging enabled",
                        "check_result": {"result": "FAILED"},
                        "file_path": "/main.tf",
                        "resource": "aws_s3_bucket.data",
                        "file_line_range": [1, 10],
                        "severity": "HIGH",
                        "guideline": "https://docs.example.com/CKV_AWS_18",
                        "bc_check_id": "BC_AWS_18",
                        "resource_address": "aws_s3_bucket.data",
                    }
                ],
                "passed_checks": [],
            },
        }
    )


# --- GlobToRegex ---


class TestGlobToRegex:
    def test_double_star(self) -> None:
        assert _glob_to_regex(".venv/**") == "\\.venv/.*"

    def test_single_star(self) -> None:
        assert _glob_to_regex("*.tf") == "[^/]*\\.tf"

    def test_question_mark(self) -> None:
        assert _glob_to_regex("file?.txt") == "file[^/]\\.txt"

    def test_plain_text(self) -> None:
        assert _glob_to_regex("node_modules") == "node_modules"

    def test_special_regex_chars_escaped(self) -> None:
        result = _glob_to_regex("some.path[0]")
        assert "\\." in result
        assert "\\[" in result
        assert "\\]" in result

    def test_dot_escaped(self) -> None:
        assert _glob_to_regex(".env") == "\\.env"

    def test_complex_pattern(self) -> None:
        result = _glob_to_regex("build/**/*.min.js")
        assert result == "build/.*/[^/]*\\.min\\.js"


# --- Properties ---


class TestCheckovScannerProperties:
    def test_name(self, scanner: CheckovScanner) -> None:
        assert scanner.name == "checkov"

    def test_domains(self, scanner: CheckovScanner) -> None:
        assert scanner.domains == [ScanDomain.IAC]

    def test_get_version(self, scanner: CheckovScanner) -> None:
        assert scanner.get_version() == "3.2.499"

    def test_default_project_root(self) -> None:
        s = CheckovScanner(version="3.2.499")
        assert s.name == "checkov"


# --- ensure_binary ---


class TestCheckovEnsureBinary:
    def test_binary_exists(self, scanner: CheckovScanner, tmp_path: Path) -> None:
        binary_dir = scanner._paths.plugin_bin_dir("checkov", "3.2.499")
        binary_dir.mkdir(parents=True, exist_ok=True)
        binary = binary_dir / _CHECKOV_BINARY
        binary.touch()
        result = scanner.ensure_binary()
        assert result == binary

    def test_download_triggered_when_missing(self, scanner: CheckovScanner) -> None:
        with patch.object(scanner, "_download_binary") as mock_dl:
            # After download, simulate binary existing
            def create_binary(dest_dir: Path) -> None:
                dest_dir.mkdir(parents=True, exist_ok=True)
                (dest_dir / _CHECKOV_BINARY).touch()

            mock_dl.side_effect = create_binary
            result = scanner.ensure_binary()
            mock_dl.assert_called_once()
            assert result.name == _CHECKOV_BINARY

    def test_raises_when_download_fails(self, scanner: CheckovScanner) -> None:
        with patch.object(scanner, "_download_binary"):
            with pytest.raises(RuntimeError, match="Failed to download"):
                scanner.ensure_binary()


# --- scan ---


class TestCheckovScan:
    def test_skips_when_iac_not_enabled(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )
        result = scanner.scan(context)
        assert result == []

    def test_scan_calls_run_iac_scan(
        self, scanner: CheckovScanner, scan_context: ScanContext
    ) -> None:
        with patch.object(
            scanner, "ensure_binary", return_value=Path("/bin/checkov")
        ):
            with patch.object(scanner, "_run_iac_scan", return_value=[]) as mock_run:
                scanner.scan(scan_context)
                mock_run.assert_called_once_with(Path("/bin/checkov"), scan_context)


# --- _run_iac_scan ---


class TestCheckovRunIacScan:
    def test_successful_scan(
        self,
        scanner: CheckovScanner,
        scan_context: ScanContext,
        sample_checkov_output: str,
    ) -> None:
        mock_result = _make_completed_process(1, sample_checkov_output)
        with patch(
            "lucidshark.plugins.scanners.checkov.run_with_streaming",
            return_value=mock_result,
        ):
            with patch(
                "lucidshark.plugins.scanners.checkov.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_iac_scan(
                    Path("/bin/checkov"), scan_context
                )
                assert len(issues) == 1
                assert issues[0].rule_id == "CKV_AWS_18"

    def test_empty_output(
        self, scanner: CheckovScanner, scan_context: ScanContext
    ) -> None:
        mock_result = _make_completed_process(0, "")
        with patch(
            "lucidshark.plugins.scanners.checkov.run_with_streaming",
            return_value=mock_result,
        ):
            with patch(
                "lucidshark.plugins.scanners.checkov.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_iac_scan(
                    Path("/bin/checkov"), scan_context
                )
                assert issues == []

    def test_exit_code_2_with_stderr(
        self, scanner: CheckovScanner, scan_context: ScanContext
    ) -> None:
        mock_result = _make_completed_process(2, "", "error occurred")
        with patch(
            "lucidshark.plugins.scanners.checkov.run_with_streaming",
            return_value=mock_result,
        ):
            with patch(
                "lucidshark.plugins.scanners.checkov.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_iac_scan(
                    Path("/bin/checkov"), scan_context
                )
                assert issues == []

    def test_timeout(
        self, scanner: CheckovScanner, scan_context: ScanContext
    ) -> None:
        with patch(
            "lucidshark.plugins.scanners.checkov.run_with_streaming",
            side_effect=subprocess.TimeoutExpired("checkov", 180),
        ):
            with patch(
                "lucidshark.plugins.scanners.checkov.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_iac_scan(
                    Path("/bin/checkov"), scan_context
                )
                assert issues == []

    def test_generic_exception(
        self, scanner: CheckovScanner, scan_context: ScanContext
    ) -> None:
        with patch(
            "lucidshark.plugins.scanners.checkov.run_with_streaming",
            side_effect=OSError("command failed"),
        ):
            with patch(
                "lucidshark.plugins.scanners.checkov.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_iac_scan(
                    Path("/bin/checkov"), scan_context
                )
                assert issues == []

    def test_framework_filter_in_command(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        config = MagicMock()
        config.get_scanner_options.return_value = {
            "framework": ["terraform", "kubernetes"],
            "skip_checks": ["CKV_AWS_1"],
        }
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
            config=config,
        )
        mock_result = _make_completed_process(0, "[]")
        with patch(
            "lucidshark.plugins.scanners.checkov.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            with patch(
                "lucidshark.plugins.scanners.checkov.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                scanner._run_iac_scan(Path("/bin/checkov"), context)
                cmd = mock_run.call_args.kwargs.get("cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else [])
                assert "--framework" in cmd
                assert "terraform" in cmd
                assert "kubernetes" in cmd
                assert "--skip-check" in cmd
                assert "CKV_AWS_1" in cmd

    def test_exclude_patterns_converted_to_regex(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        ignore = MagicMock()
        ignore.get_exclude_patterns.return_value = [".venv/**", "*.bak"]
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
            ignore_patterns=ignore,
        )
        mock_result = _make_completed_process(0, "[]")
        with patch(
            "lucidshark.plugins.scanners.checkov.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            with patch(
                "lucidshark.plugins.scanners.checkov.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                scanner._run_iac_scan(Path("/bin/checkov"), context)
                cmd = mock_run.call_args.kwargs.get("cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else [])
                assert "--skip-path" in cmd
                # Regex conversions
                assert "\\.venv/.*" in cmd
                assert "[^/]*\\.bak" in cmd


# --- _parse_checkov_json ---


class TestCheckovParseJson:
    def test_valid_single_result(
        self, scanner: CheckovScanner, sample_checkov_output: str, tmp_path: Path
    ) -> None:
        issues = scanner._parse_checkov_json(sample_checkov_output, tmp_path)
        assert len(issues) == 1
        assert issues[0].rule_id == "CKV_AWS_18"
        assert issues[0].severity == Severity.HIGH
        assert issues[0].domain == ScanDomain.IAC
        assert issues[0].source_tool == "checkov"
        assert issues[0].line_start == 1
        assert issues[0].line_end == 10

    def test_valid_list_result(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        data = json.dumps(
            [
                {
                    "check_type": "terraform",
                    "results": {
                        "failed_checks": [
                            {
                                "check_id": "CKV_AWS_1",
                                "check": "Check 1",
                                "file_path": "/main.tf",
                                "resource": "res1",
                                "file_line_range": [5, 15],
                                "severity": "MEDIUM",
                            }
                        ]
                    },
                },
                {
                    "check_type": "kubernetes",
                    "results": {
                        "failed_checks": [
                            {
                                "check_id": "CKV_K8S_1",
                                "check": "Check 2",
                                "file_path": "/deploy.yaml",
                                "resource": "Deployment.default.app",
                                "file_line_range": [1, 20],
                                "severity": "LOW",
                            }
                        ]
                    },
                },
            ]
        )
        issues = scanner._parse_checkov_json(data, tmp_path)
        assert len(issues) == 2
        assert issues[0].rule_id == "CKV_AWS_1"
        assert issues[1].rule_id == "CKV_K8S_1"

    def test_invalid_json(self, scanner: CheckovScanner, tmp_path: Path) -> None:
        issues = scanner._parse_checkov_json("not json", tmp_path)
        assert issues == []

    def test_empty_failed_checks(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        data = json.dumps(
            {"check_type": "terraform", "results": {"failed_checks": []}}
        )
        issues = scanner._parse_checkov_json(data, tmp_path)
        assert issues == []

    def test_non_dict_in_list_skipped(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        data = json.dumps(["not a dict", {"check_type": "tf", "results": {"failed_checks": []}}])
        issues = scanner._parse_checkov_json(data, tmp_path)
        assert issues == []

    def test_missing_results_key(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        data = json.dumps({"check_type": "terraform"})
        issues = scanner._parse_checkov_json(data, tmp_path)
        assert issues == []


# --- _check_to_unified_issue ---


class TestCheckovCheckToUnifiedIssue:
    def test_full_check(self, scanner: CheckovScanner, tmp_path: Path) -> None:
        check = {
            "check_id": "CKV_AWS_18",
            "check": "Ensure S3 bucket has access logging",
            "file_path": "/main.tf",
            "resource": "aws_s3_bucket.data",
            "file_line_range": [1, 10],
            "severity": "HIGH",
            "guideline": "https://docs.example.com/CKV_AWS_18",
            "bc_check_id": "BC_AWS_18",
            "resource_address": "aws_s3_bucket.data",
            "evaluations": None,
            "check_class": "checkov.terraform.checks.resource",
        }
        issue = scanner._check_to_unified_issue(check, "terraform", tmp_path)
        assert issue is not None
        assert issue.rule_id == "CKV_AWS_18"
        assert issue.severity == Severity.HIGH
        assert issue.line_start == 1
        assert issue.line_end == 10
        assert issue.iac_resource == "aws_s3_bucket.data"
        assert issue.recommendation is not None
        assert "See: https://docs.example.com/CKV_AWS_18" in issue.recommendation
        assert issue.documentation_url == "https://docs.example.com/CKV_AWS_18"
        assert issue.metadata["check_type"] == "terraform"
        assert issue.metadata["bc_check_id"] == "BC_AWS_18"
        assert issue.fixable is False

    def test_none_severity_defaults_to_medium(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        check = {
            "check_id": "CKV_TEST",
            "check": "Test check",
            "file_path": "/test.tf",
            "resource": "",
            "file_line_range": [1],
            "severity": None,
        }
        issue = scanner._check_to_unified_issue(check, "terraform", tmp_path)
        assert issue is not None
        assert issue.severity == Severity.MEDIUM

    def test_missing_severity_defaults_to_medium(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        check = {
            "check_id": "CKV_TEST",
            "check": "Test",
            "file_path": "/test.tf",
            "resource": "",
            "file_line_range": [],
        }
        issue = scanner._check_to_unified_issue(check, "terraform", tmp_path)
        assert issue is not None
        assert issue.severity == Severity.MEDIUM
        assert issue.line_start is None
        assert issue.line_end is None

    def test_empty_file_path(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        check = {
            "check_id": "CKV_TEST",
            "check": "Test",
            "file_path": "",
            "resource": "",
            "file_line_range": [],
        }
        issue = scanner._check_to_unified_issue(check, "terraform", tmp_path)
        assert issue is not None
        assert issue.file_path is None

    def test_no_guideline(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        check = {
            "check_id": "CKV_TEST",
            "check": "Test",
            "file_path": "/test.tf",
            "resource": "res",
            "file_line_range": [1, 5],
        }
        issue = scanner._check_to_unified_issue(check, "terraform", tmp_path)
        assert issue is not None
        assert issue.recommendation is None

    def test_no_resource(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        check = {
            "check_id": "CKV_TEST",
            "check": "Test",
            "file_path": "/test.tf",
            "resource": "",
            "file_line_range": [1, 5],
        }
        issue = scanner._check_to_unified_issue(check, "terraform", tmp_path)
        assert issue is not None
        assert issue.iac_resource is None

    def test_exception_returns_none(
        self, scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        # Pass something that causes an exception in conversion
        with patch.object(
            scanner,
            "_generate_issue_id",
            side_effect=ValueError("test error"),
        ):
            issue = scanner._check_to_unified_issue(
                {"check_id": "X", "check": "Y", "file_path": "/z", "resource": "", "file_line_range": []},
                "terraform",
                tmp_path,
            )
            assert issue is None


# --- _generate_issue_id ---


class TestCheckovIssueId:
    def test_deterministic(self, scanner: CheckovScanner) -> None:
        id1 = scanner._generate_issue_id("CKV_AWS_18", "/main.tf", "res", 1)
        id2 = scanner._generate_issue_id("CKV_AWS_18", "/main.tf", "res", 1)
        assert id1 == id2

    def test_different_inputs(self, scanner: CheckovScanner) -> None:
        id1 = scanner._generate_issue_id("CKV_AWS_18", "/a.tf", "res", 1)
        id2 = scanner._generate_issue_id("CKV_AWS_19", "/a.tf", "res", 1)
        assert id1 != id2

    def test_prefix(self, scanner: CheckovScanner) -> None:
        issue_id = scanner._generate_issue_id("CKV_AWS_18", "/a.tf", "res", 1)
        assert issue_id.startswith("checkov-")

    def test_none_line(self, scanner: CheckovScanner) -> None:
        issue_id = scanner._generate_issue_id("CKV_AWS_18", "/a.tf", "res", None)
        assert issue_id.startswith("checkov-")


# --- Severity mapping ---


class TestCheckovSeverityMap:
    def test_all_severities_mapped(self) -> None:
        assert CHECKOV_SEVERITY_MAP["CRITICAL"] == Severity.CRITICAL
        assert CHECKOV_SEVERITY_MAP["HIGH"] == Severity.HIGH
        assert CHECKOV_SEVERITY_MAP["MEDIUM"] == Severity.MEDIUM
        assert CHECKOV_SEVERITY_MAP["LOW"] == Severity.LOW
        assert CHECKOV_SEVERITY_MAP["INFO"] == Severity.INFO
        assert CHECKOV_SEVERITY_MAP["UNKNOWN"] == Severity.INFO


# --- _get_scan_env ---


class TestCheckovScanEnv:
    def test_returns_expected_env_vars(self, scanner: CheckovScanner) -> None:
        env = scanner._get_scan_env()
        assert env["BC_SKIP_MAPPING"] == "TRUE"
        assert env["CHECKOV_RUN_SCA_PACKAGE_SCAN"] == "false"
