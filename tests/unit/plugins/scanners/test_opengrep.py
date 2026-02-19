"""Unit tests for OpenGrep scanner plugin."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, ScanDomain, Severity
from lucidshark.plugins.scanners.opengrep import (
    OpenGrepScanner,
    OPENGREP_SEVERITY_MAP,
)

_IS_WINDOWS = sys.platform == "win32"
_OPENGREP_BINARY = "opengrep.exe" if _IS_WINDOWS else "opengrep"


def _make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def scanner(tmp_path: Path) -> OpenGrepScanner:
    return OpenGrepScanner(version="1.100.0", project_root=tmp_path)


@pytest.fixture
def scan_context(tmp_path: Path) -> ScanContext:
    return ScanContext(
        project_root=tmp_path,
        paths=[tmp_path],
        enabled_domains=[ScanDomain.SAST],
    )


@pytest.fixture
def sample_opengrep_output() -> str:
    return json.dumps(
        {
            "results": [
                {
                    "check_id": "python.lang.security.audit.exec-used",
                    "path": "src/app.py",
                    "start": {"line": 15, "col": 1},
                    "end": {"line": 15, "col": 20},
                    "extra": {
                        "message": "Use of exec() is a security risk.",
                        "severity": "WARNING",
                        "lines": "exec(user_input)",
                        "metadata": {
                            "severity": "HIGH",
                            "cwe": ["CWE-78"],
                            "owasp": ["A03:2021"],
                            "references": ["https://owasp.org/injection"],
                            "category": "security",
                            "technology": ["python"],
                            "confidence": "HIGH",
                            "fix": "Use ast.literal_eval instead.",
                        },
                        "metavars": {"$VAR": {"abstract_content": "user_input"}},
                        "fingerprint": "abc123",
                        "engine_kind": "OSS",
                        "validation_state": "NO_VALIDATOR",
                        "fix": "ast.literal_eval(user_input)",
                    },
                }
            ],
            "errors": [],
        }
    )


# --- Properties ---


class TestOpenGrepScannerProperties:
    def test_name(self, scanner: OpenGrepScanner) -> None:
        assert scanner.name == "opengrep"

    def test_domains(self, scanner: OpenGrepScanner) -> None:
        assert scanner.domains == [ScanDomain.SAST]

    def test_get_version(self, scanner: OpenGrepScanner) -> None:
        assert scanner.get_version() == "1.100.0"

    def test_default_project_root(self) -> None:
        s = OpenGrepScanner(version="1.100.0")
        assert s.name == "opengrep"


# --- ensure_binary ---


class TestOpenGrepEnsureBinary:
    def test_binary_exists(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        binary_dir = scanner._paths.plugin_bin_dir("opengrep", "1.100.0")
        binary_dir.mkdir(parents=True, exist_ok=True)
        binary = binary_dir / _OPENGREP_BINARY
        binary.touch()
        result = scanner.ensure_binary()
        assert result == binary

    def test_download_triggered(self, scanner: OpenGrepScanner) -> None:
        with patch.object(scanner, "_download_binary") as mock_dl:
            def create_binary(dest_dir: Path) -> None:
                dest_dir.mkdir(parents=True, exist_ok=True)
                (dest_dir / _OPENGREP_BINARY).touch()

            mock_dl.side_effect = create_binary
            result = scanner.ensure_binary()
            mock_dl.assert_called_once()
            assert result.name == _OPENGREP_BINARY

    def test_raises_when_download_fails(self, scanner: OpenGrepScanner) -> None:
        with patch.object(scanner, "_download_binary"):
            with pytest.raises(RuntimeError, match="Failed to download"):
                scanner.ensure_binary()


# --- _get_binary_name ---


class TestOpenGrepBinaryName:
    def test_unix(self, scanner: OpenGrepScanner) -> None:
        with patch(
            "lucidshark.plugins.scanners.opengrep.get_platform_info"
        ) as mock_pi:
            mock_pi.return_value = MagicMock(os="linux", arch="amd64")
            assert scanner._get_binary_name() == "opengrep"

    def test_windows(self, scanner: OpenGrepScanner) -> None:
        with patch(
            "lucidshark.plugins.scanners.opengrep.get_platform_info"
        ) as mock_pi:
            mock_pi.return_value = MagicMock(os="windows", arch="amd64")
            assert scanner._get_binary_name() == "opengrep.exe"


# --- _download_binary ---


class TestOpenGrepDownloadBinary:
    def test_unsupported_platform(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        with patch(
            "lucidshark.plugins.scanners.opengrep.get_platform_info"
        ) as mock_pi:
            mock_pi.return_value = MagicMock(os="freebsd", arch="amd64")
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                scanner._download_binary(tmp_path / "dest")

    def test_download_failure_cleans_up(
        self, scanner: OpenGrepScanner, tmp_path: Path
    ) -> None:
        dest = tmp_path / "dest"
        with patch(
            "lucidshark.plugins.scanners.opengrep.get_platform_info"
        ) as mock_pi:
            mock_pi.return_value = MagicMock(os="linux", arch="amd64")
            with patch(
                "lucidshark.plugins.scanners.opengrep.secure_urlopen",
                side_effect=Exception("network error"),
            ):
                with pytest.raises(RuntimeError, match="Failed to download"):
                    scanner._download_binary(dest)


# --- scan ---


class TestOpenGrepScan:
    def test_skips_when_sast_not_enabled(
        self, scanner: OpenGrepScanner, tmp_path: Path
    ) -> None:
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )
        assert scanner.scan(context) == []

    def test_calls_run_sast_scan(
        self, scanner: OpenGrepScanner, scan_context: ScanContext
    ) -> None:
        with patch.object(
            scanner, "ensure_binary", return_value=Path("/bin/opengrep")
        ):
            with patch.object(
                scanner, "_run_sast_scan", return_value=[]
            ) as mock_run:
                scanner.scan(scan_context)
                mock_run.assert_called_once_with(
                    Path("/bin/opengrep"), scan_context
                )


# --- _run_sast_scan ---


class TestOpenGrepRunSastScan:
    def test_successful_scan(
        self,
        scanner: OpenGrepScanner,
        scan_context: ScanContext,
        sample_opengrep_output: str,
    ) -> None:
        mock_result = _make_completed_process(1, sample_opengrep_output)
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            return_value=mock_result,
        ):
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_sast_scan(
                    Path("/bin/opengrep"), scan_context
                )
                assert len(issues) == 1
                assert issues[0].rule_id == "python.lang.security.audit.exec-used"

    def test_empty_output(
        self, scanner: OpenGrepScanner, scan_context: ScanContext
    ) -> None:
        mock_result = _make_completed_process(0, "")
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            return_value=mock_result,
        ):
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_sast_scan(
                    Path("/bin/opengrep"), scan_context
                )
                assert issues == []

    def test_nonzero_exit_with_stderr(
        self, scanner: OpenGrepScanner, scan_context: ScanContext
    ) -> None:
        mock_result = _make_completed_process(2, "", "fatal error")
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            return_value=mock_result,
        ):
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_sast_scan(
                    Path("/bin/opengrep"), scan_context
                )
                assert issues == []

    def test_timeout(
        self, scanner: OpenGrepScanner, scan_context: ScanContext
    ) -> None:
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            side_effect=subprocess.TimeoutExpired("opengrep", 180),
        ):
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_sast_scan(
                    Path("/bin/opengrep"), scan_context
                )
                assert issues == []

    def test_generic_exception(
        self, scanner: OpenGrepScanner, scan_context: ScanContext
    ) -> None:
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            side_effect=OSError("command failed"),
        ):
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                issues = scanner._run_sast_scan(
                    Path("/bin/opengrep"), scan_context
                )
                assert issues == []

    def test_custom_ruleset(
        self, scanner: OpenGrepScanner, tmp_path: Path
    ) -> None:
        config = MagicMock()
        config.get_scanner_options.return_value = {
            "ruleset": ["p/security-audit"],
            "timeout": 60,
        }
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SAST],
            config=config,
        )
        mock_result = _make_completed_process(
            0, json.dumps({"results": [], "errors": []})
        )
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                scanner._run_sast_scan(Path("/bin/opengrep"), context)
                cmd = mock_run.call_args.kwargs.get("cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else [])
                assert "--config" in cmd
                assert "p/security-audit" in cmd
                assert "--timeout" in cmd
                assert "60" in cmd

    def test_auto_ruleset(
        self, scanner: OpenGrepScanner, tmp_path: Path
    ) -> None:
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SAST],
        )
        mock_result = _make_completed_process(
            0, json.dumps({"results": [], "errors": []})
        )
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                scanner._run_sast_scan(Path("/bin/opengrep"), context)
                cmd = mock_run.call_args.kwargs.get("cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else [])
                assert "--config" in cmd
                assert "auto" in cmd

    def test_exclude_patterns(
        self, scanner: OpenGrepScanner, tmp_path: Path
    ) -> None:
        ignore = MagicMock()
        ignore.get_exclude_patterns.return_value = ["node_modules", "*.min.js"]
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SAST],
            ignore_patterns=ignore,
        )
        mock_result = _make_completed_process(
            0, json.dumps({"results": [], "errors": []})
        )
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                scanner._run_sast_scan(Path("/bin/opengrep"), context)
                cmd = mock_run.call_args.kwargs.get("cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else [])
                assert cmd.count("--exclude") == 2
                assert "node_modules" in cmd
                assert "*.min.js" in cmd

    def test_string_ruleset(
        self, scanner: OpenGrepScanner, tmp_path: Path
    ) -> None:
        """Test non-list ruleset config falls back to auto."""
        config = MagicMock()
        config.get_scanner_options.return_value = {
            "ruleset": "not-a-list",
        }
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SAST],
            config=config,
        )
        mock_result = _make_completed_process(
            0, json.dumps({"results": [], "errors": []})
        )
        with patch(
            "lucidshark.plugins.scanners.opengrep.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            with patch(
                "lucidshark.plugins.scanners.opengrep.temporary_env"
            ) as mock_env:
                mock_env.return_value.__enter__ = MagicMock()
                mock_env.return_value.__exit__ = MagicMock(return_value=False)
                scanner._run_sast_scan(Path("/bin/opengrep"), context)
                cmd = mock_run.call_args.kwargs.get("cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else [])
                assert "--config" in cmd
                assert "auto" in cmd


# --- _parse_opengrep_json ---


class TestOpenGrepParseJson:
    def test_valid_output(
        self, scanner: OpenGrepScanner, sample_opengrep_output: str, tmp_path: Path
    ) -> None:
        issues = scanner._parse_opengrep_json(sample_opengrep_output, tmp_path)
        assert len(issues) == 1
        assert issues[0].rule_id == "python.lang.security.audit.exec-used"

    def test_invalid_json(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        issues = scanner._parse_opengrep_json("not json", tmp_path)
        assert issues == []

    def test_empty_results(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        data = json.dumps({"results": [], "errors": []})
        issues = scanner._parse_opengrep_json(data, tmp_path)
        assert issues == []

    def test_errors_logged(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        data = json.dumps(
            {
                "results": [],
                "errors": [
                    {"message": "Failed to parse file", "path": "bad.py"}
                ],
            }
        )
        issues = scanner._parse_opengrep_json(data, tmp_path)
        assert issues == []


# --- _result_to_unified_issue ---


class TestOpenGrepResultToUnifiedIssue:
    def test_full_result(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        result = {
            "check_id": "python.lang.security.audit.exec-used",
            "path": "src/app.py",
            "start": {"line": 15, "col": 1},
            "end": {"line": 15, "col": 20},
            "extra": {
                "message": "Use of exec() is a security risk.",
                "severity": "WARNING",
                "lines": "exec(user_input)",
                "metadata": {
                    "severity": "HIGH",
                    "cwe": ["CWE-78"],
                    "owasp": ["A03:2021"],
                    "references": ["https://owasp.org/injection"],
                    "category": "security",
                    "technology": ["python"],
                    "confidence": "HIGH",
                    "fix": "Use ast.literal_eval instead.",
                },
                "metavars": {"$VAR": {"abstract_content": "user_input"}},
                "fingerprint": "abc123",
                "engine_kind": "OSS",
                "validation_state": "NO_VALIDATOR",
                "fix": "ast.literal_eval(user_input)",
            },
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.rule_id == "python.lang.security.audit.exec-used"
        assert issue.severity == Severity.HIGH  # From metadata, not extra
        assert issue.line_start == 15
        assert issue.line_end == 15
        assert issue.code_snippet == "exec(user_input)"
        assert issue.fixable is True
        assert issue.suggested_fix == "ast.literal_eval(user_input)"
        assert issue.documentation_url == "https://owasp.org/injection"
        assert issue.domain == ScanDomain.SAST
        assert issue.source_tool == "opengrep"
        # Metadata includes CWE/OWASP info
        assert issue.metadata["metadata"]["cwe"] == ["CWE-78"]
        assert issue.metadata["metadata"]["owasp"] == ["A03:2021"]

    def test_relative_path(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        result = {
            "check_id": "test-rule",
            "path": "src/file.py",
            "start": {"line": 1, "col": 1},
            "end": {"line": 1, "col": 10},
            "extra": {"message": "Test", "severity": "INFO", "lines": "x = 1"},
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.file_path == tmp_path / "src/file.py"

    def test_absolute_path(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        abs_path = str(tmp_path / "absolute" / "path" / "file.py")
        result = {
            "check_id": "test-rule",
            "path": abs_path,
            "start": {"line": 1, "col": 1},
            "end": {"line": 1, "col": 10},
            "extra": {"message": "Test", "severity": "INFO", "lines": "x = 1"},
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.file_path == Path(abs_path)

    def test_no_metadata(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        result = {
            "check_id": "simple-rule",
            "path": "file.py",
            "start": {"line": 1, "col": 1},
            "end": {"line": 1, "col": 5},
            "extra": {
                "message": "Simple finding",
                "severity": "ERROR",
                "lines": "eval(x)",
            },
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.severity == Severity.HIGH  # ERROR maps to HIGH
        assert issue.recommendation is None

    def test_fix_from_metadata(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        result = {
            "check_id": "rule",
            "path": "file.py",
            "start": {"line": 1, "col": 1},
            "end": {"line": 1, "col": 5},
            "extra": {
                "message": "Finding",
                "severity": "WARNING",
                "lines": "code",
                "metadata": {
                    "fix": "Use safer alternative",
                },
            },
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.recommendation == "Use safer alternative"

    def test_no_metavars(self, scanner: OpenGrepScanner, tmp_path: Path) -> None:
        result = {
            "check_id": "rule",
            "path": "file.py",
            "start": {"line": 1, "col": 1},
            "end": {"line": 1, "col": 5},
            "extra": {
                "message": "Finding",
                "severity": "WARNING",
                "lines": "code",
            },
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        # Description should not include "Matched values" if no metavars
        assert "Matched values" not in issue.description

    def test_exception_returns_none(
        self, scanner: OpenGrepScanner, tmp_path: Path
    ) -> None:
        with patch.object(
            scanner, "_generate_issue_id", side_effect=ValueError("test")
        ):
            issue = scanner._result_to_unified_issue(
                {
                    "check_id": "rule",
                    "path": "file.py",
                    "start": {"line": 1, "col": 1},
                    "end": {"line": 1, "col": 5},
                    "extra": {"message": "Msg", "severity": "INFO", "lines": "x"},
                },
                tmp_path,
            )
            assert issue is None


# --- _format_title ---


class TestOpenGrepFormatTitle:
    def test_short_message(self, scanner: OpenGrepScanner) -> None:
        title = scanner._format_title("rule-id", "Short message")
        assert title == "rule-id: Short message"

    def test_long_message_truncated(self, scanner: OpenGrepScanner) -> None:
        long_msg = "A" * 100
        title = scanner._format_title("rule-id", long_msg)
        assert len(title) <= 100  # rule-id + ": " + truncated message
        assert title.endswith("...")

    def test_exact_80_chars_not_truncated(self, scanner: OpenGrepScanner) -> None:
        msg = "A" * 80
        title = scanner._format_title("id", msg)
        # Exactly 80 chars is not truncated (only > 80 is)
        assert title == "id: " + "A" * 80

    def test_over_80_chars_truncated(self, scanner: OpenGrepScanner) -> None:
        msg = "A" * 81
        title = scanner._format_title("id", msg)
        assert "..." in title


# --- _generate_issue_id ---


class TestOpenGrepIssueId:
    def test_deterministic(self, scanner: OpenGrepScanner) -> None:
        id1 = scanner._generate_issue_id("rule", "file.py", 10, 5)
        id2 = scanner._generate_issue_id("rule", "file.py", 10, 5)
        assert id1 == id2

    def test_different_inputs(self, scanner: OpenGrepScanner) -> None:
        id1 = scanner._generate_issue_id("rule1", "file.py", 10, 5)
        id2 = scanner._generate_issue_id("rule2", "file.py", 10, 5)
        assert id1 != id2

    def test_prefix(self, scanner: OpenGrepScanner) -> None:
        issue_id = scanner._generate_issue_id("rule", "file.py", 10, 5)
        assert issue_id.startswith("opengrep-")


# --- Severity mapping ---


class TestOpenGrepSeverityMap:
    def test_all_severities(self) -> None:
        assert OPENGREP_SEVERITY_MAP["ERROR"] == Severity.HIGH
        assert OPENGREP_SEVERITY_MAP["WARNING"] == Severity.MEDIUM
        assert OPENGREP_SEVERITY_MAP["INFO"] == Severity.LOW
        assert OPENGREP_SEVERITY_MAP["CRITICAL"] == Severity.CRITICAL
        assert OPENGREP_SEVERITY_MAP["HIGH"] == Severity.HIGH
        assert OPENGREP_SEVERITY_MAP["MEDIUM"] == Severity.MEDIUM
        assert OPENGREP_SEVERITY_MAP["LOW"] == Severity.LOW


# --- _get_scan_env ---


class TestOpenGrepScanEnv:
    def test_returns_expected_env_vars(self, scanner: OpenGrepScanner) -> None:
        env = scanner._get_scan_env()
        assert env["SEMGREP_SEND_METRICS"] == "off"
        assert env["OPENGREP_SEND_METRICS"] == "off"
