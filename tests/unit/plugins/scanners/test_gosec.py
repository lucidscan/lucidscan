"""Unit tests for Gosec scanner plugin."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, ScanDomain, Severity
from lucidshark.plugins.scanners.gosec import (
    GOSEC_RULE_DESCRIPTIONS,
    GOSEC_SEVERITY_MAP,
    GosecScanner,
)

_GOSEC_BINARY = "gosec"


def _make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def scanner(tmp_path: Path) -> GosecScanner:
    return GosecScanner(version="2.21.4", project_root=tmp_path)


@pytest.fixture
def scan_context(tmp_path: Path) -> ScanContext:
    # Create go.mod so the scanner doesn't skip
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    return ScanContext(
        project_root=tmp_path,
        paths=[tmp_path],
        enabled_domains=[ScanDomain.SAST],
    )


@pytest.fixture
def sample_gosec_output() -> str:
    return json.dumps(
        {
            "Golang errors": {},
            "Issues": [
                {
                    "severity": "MEDIUM",
                    "confidence": "HIGH",
                    "cwe": {
                        "id": "326",
                        "url": "https://cwe.mitre.org/data/definitions/326.html",
                    },
                    "rule_id": "G401",
                    "details": "Use of weak cryptographic primitive",
                    "file": "crypto/hash.go",
                    "code": "15-16: md5.New()",
                    "line": "15",
                    "column": "12",
                    "nosec": False,
                    "suppressions": None,
                }
            ],
            "Stats": {"files": 10, "lines": 500, "nosec": 0, "found": 1},
        }
    )


@pytest.fixture
def multi_issue_gosec_output() -> str:
    return json.dumps(
        {
            "Golang errors": {},
            "Issues": [
                {
                    "severity": "HIGH",
                    "confidence": "HIGH",
                    "cwe": {
                        "id": "89",
                        "url": "https://cwe.mitre.org/data/definitions/89.html",
                    },
                    "rule_id": "G201",
                    "details": "SQL string formatting",
                    "file": "db/query.go",
                    "code": '10: fmt.Sprintf("SELECT * FROM %s", table)',
                    "line": "10",
                    "column": "5",
                    "nosec": False,
                    "suppressions": None,
                },
                {
                    "severity": "HIGH",
                    "confidence": "MEDIUM",
                    "cwe": {
                        "id": "78",
                        "url": "https://cwe.mitre.org/data/definitions/78.html",
                    },
                    "rule_id": "G204",
                    "details": "Subprocess launched with variable",
                    "file": "cmd/run.go",
                    "code": "25: exec.Command(userInput)",
                    "line": "25",
                    "column": "3",
                    "nosec": False,
                    "suppressions": None,
                },
                {
                    "severity": "LOW",
                    "confidence": "HIGH",
                    "cwe": {
                        "id": "327",
                        "url": "https://cwe.mitre.org/data/definitions/327.html",
                    },
                    "rule_id": "G501",
                    "details": "Blocklisted import crypto/md5",
                    "file": "crypto/hash.go",
                    "code": '3: "crypto/md5"',
                    "line": "3",
                    "column": "2",
                    "nosec": False,
                    "suppressions": None,
                },
            ],
            "Stats": {"files": 15, "lines": 800, "nosec": 0, "found": 3},
        }
    )


# --- Properties ---


class TestGosecScannerProperties:
    def test_name(self, scanner: GosecScanner) -> None:
        assert scanner.name == "gosec"

    def test_domains(self, scanner: GosecScanner) -> None:
        assert scanner.domains == [ScanDomain.SAST]

    def test_get_version(self, scanner: GosecScanner) -> None:
        assert scanner.get_version() == "2.21.4"

    def test_default_project_root(self) -> None:
        s = GosecScanner(version="2.21.4")
        assert s.name == "gosec"


# --- ensure_binary ---


class TestGosecEnsureBinary:
    def test_binary_exists(self, scanner: GosecScanner, tmp_path: Path) -> None:
        binary_dir = scanner._paths.plugin_bin_dir("gosec", "2.21.4")
        binary_dir.mkdir(parents=True, exist_ok=True)
        binary = binary_dir / _GOSEC_BINARY
        binary.touch()
        result = scanner.ensure_binary()
        assert result == binary

    def test_download_triggered(self, scanner: GosecScanner) -> None:
        with patch.object(scanner, "_download_binary") as mock_dl:

            def create_binary(dest_dir: Path) -> None:
                dest_dir.mkdir(parents=True, exist_ok=True)
                (dest_dir / _GOSEC_BINARY).touch()

            mock_dl.side_effect = create_binary
            result = scanner.ensure_binary()
            mock_dl.assert_called_once()
            assert result.name == _GOSEC_BINARY

    def test_raises_when_download_fails(self, scanner: GosecScanner) -> None:
        with patch.object(scanner, "_download_binary"):
            with pytest.raises(RuntimeError, match="Failed to download"):
                scanner.ensure_binary()


# --- _get_binary_name ---


class TestGosecBinaryName:
    def test_unix(self, scanner: GosecScanner) -> None:
        with patch("lucidshark.plugins.scanners.gosec.get_platform_info") as mock_pi:
            mock_pi.return_value = MagicMock(os="linux", arch="amd64")
            assert scanner._get_binary_name() == "gosec"


# --- _download_binary ---


class TestGosecDownloadBinary:
    def test_unsupported_platform(self, scanner: GosecScanner, tmp_path: Path) -> None:
        with patch("lucidshark.plugins.scanners.gosec.get_platform_info") as mock_pi:
            mock_pi.return_value = MagicMock(os="freebsd", arch="amd64")
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                scanner._download_binary(tmp_path / "dest")

    def test_download_failure_cleans_up(
        self, scanner: GosecScanner, tmp_path: Path
    ) -> None:
        dest = tmp_path / "dest"
        with patch("lucidshark.plugins.scanners.gosec.get_platform_info") as mock_pi:
            mock_pi.return_value = MagicMock(os="linux", arch="amd64")
            with patch(
                "lucidshark.plugins.scanners.gosec.secure_urlopen",
                side_effect=Exception("network error"),
            ):
                with pytest.raises(Exception, match="network error"):
                    scanner._download_binary(dest)


# --- scan ---


class TestGosecScan:
    def test_skips_when_sast_not_enabled(
        self, scanner: GosecScanner, tmp_path: Path
    ) -> None:
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )
        assert scanner.scan(context) == []

    def test_skips_when_no_go_mod(self, scanner: GosecScanner, tmp_path: Path) -> None:
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SAST],
        )
        # tmp_path has no go.mod
        assert scanner.scan(context) == []

    def test_skips_when_go_not_available(
        self, scanner: GosecScanner, tmp_path: Path
    ) -> None:
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SAST],
        )
        with patch(
            "lucidshark.plugins.scanners.gosec.find_go",
            side_effect=FileNotFoundError("go not found"),
        ):
            assert scanner.scan(context) == []

    def test_calls_run_sast_scan(
        self, scanner: GosecScanner, scan_context: ScanContext
    ) -> None:
        with patch.object(scanner, "ensure_binary", return_value=Path("/bin/gosec")):
            with patch.object(scanner, "_run_sast_scan", return_value=[]) as mock_run:
                with patch(
                    "lucidshark.plugins.scanners.gosec.find_go",
                    return_value=Path("/usr/bin/go"),
                ):
                    scanner.scan(scan_context)
                    mock_run.assert_called_once_with(Path("/bin/gosec"), scan_context)


# --- _run_sast_scan ---


class TestGosecRunSastScan:
    def test_successful_scan(
        self,
        scanner: GosecScanner,
        scan_context: ScanContext,
        sample_gosec_output: str,
    ) -> None:
        mock_result = _make_completed_process(1, sample_gosec_output)
        with patch(
            "lucidshark.plugins.scanners.gosec.run_with_streaming",
            return_value=mock_result,
        ):
            issues = scanner._run_sast_scan(Path("/bin/gosec"), scan_context)
            assert len(issues) == 1
            assert issues[0].rule_id == "G401"

    def test_multi_issue_scan(
        self,
        scanner: GosecScanner,
        scan_context: ScanContext,
        multi_issue_gosec_output: str,
    ) -> None:
        mock_result = _make_completed_process(1, multi_issue_gosec_output)
        with patch(
            "lucidshark.plugins.scanners.gosec.run_with_streaming",
            return_value=mock_result,
        ):
            issues = scanner._run_sast_scan(Path("/bin/gosec"), scan_context)
            assert len(issues) == 3
            rule_ids = {i.rule_id for i in issues}
            assert rule_ids == {"G201", "G204", "G501"}

    def test_empty_output(
        self, scanner: GosecScanner, scan_context: ScanContext
    ) -> None:
        mock_result = _make_completed_process(0, "")
        with patch(
            "lucidshark.plugins.scanners.gosec.run_with_streaming",
            return_value=mock_result,
        ):
            issues = scanner._run_sast_scan(Path("/bin/gosec"), scan_context)
            assert issues == []

    def test_nonzero_exit_with_stderr(
        self, scanner: GosecScanner, scan_context: ScanContext
    ) -> None:
        mock_result = _make_completed_process(2, "", "fatal error")
        with patch(
            "lucidshark.plugins.scanners.gosec.run_with_streaming",
            return_value=mock_result,
        ):
            issues = scanner._run_sast_scan(Path("/bin/gosec"), scan_context)
            assert issues == []

    def test_timeout(self, scanner: GosecScanner, scan_context: ScanContext) -> None:
        with patch(
            "lucidshark.plugins.scanners.gosec.run_with_streaming",
            side_effect=subprocess.TimeoutExpired("gosec", 300),
        ):
            issues = scanner._run_sast_scan(Path("/bin/gosec"), scan_context)
            assert issues == []

    def test_generic_exception(
        self, scanner: GosecScanner, scan_context: ScanContext
    ) -> None:
        with patch(
            "lucidshark.plugins.scanners.gosec.run_with_streaming",
            side_effect=OSError("command failed"),
        ):
            issues = scanner._run_sast_scan(Path("/bin/gosec"), scan_context)
            assert issues == []

    def test_exclude_patterns(self, scanner: GosecScanner, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        ignore = MagicMock()
        ignore.get_exclude_patterns.return_value = ["vendor", "testdata"]
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SAST],
            ignore_patterns=ignore,
        )
        mock_result = _make_completed_process(
            0, json.dumps({"Golang errors": {}, "Issues": [], "Stats": {}})
        )
        with patch(
            "lucidshark.plugins.scanners.gosec.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            scanner._run_sast_scan(Path("/bin/gosec"), context)
            cmd = mock_run.call_args.kwargs.get(
                "cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else []
            )
            assert "-exclude-dir" in cmd
            # Directories are sorted alphabetically
            assert "testdata,vendor" in cmd or "vendor,testdata" in cmd


# --- _parse_gosec_json ---


class TestGosecParseJson:
    def test_valid_output(
        self,
        scanner: GosecScanner,
        sample_gosec_output: str,
        tmp_path: Path,
    ) -> None:
        issues = scanner._parse_gosec_json(sample_gosec_output, tmp_path)
        assert len(issues) == 1
        assert issues[0].rule_id == "G401"

    def test_invalid_json(self, scanner: GosecScanner, tmp_path: Path) -> None:
        issues = scanner._parse_gosec_json("not json", tmp_path)
        assert issues == []

    def test_empty_issues(self, scanner: GosecScanner, tmp_path: Path) -> None:
        data = json.dumps({"Golang errors": {}, "Issues": [], "Stats": {"found": 0}})
        issues = scanner._parse_gosec_json(data, tmp_path)
        assert issues == []

    def test_golang_errors_logged(self, scanner: GosecScanner, tmp_path: Path) -> None:
        data = json.dumps(
            {
                "Golang errors": {"main": [{"error": "cannot find package"}]},
                "Issues": [],
                "Stats": {},
            }
        )
        issues = scanner._parse_gosec_json(data, tmp_path)
        assert issues == []

    def test_multiple_issues_parsed(
        self,
        scanner: GosecScanner,
        multi_issue_gosec_output: str,
        tmp_path: Path,
    ) -> None:
        issues = scanner._parse_gosec_json(multi_issue_gosec_output, tmp_path)
        assert len(issues) == 3
        severities = {i.severity for i in issues}
        assert Severity.HIGH in severities
        assert Severity.LOW in severities


# --- _result_to_unified_issue ---


class TestGosecResultToUnifiedIssue:
    def test_full_result_with_cwe(self, scanner: GosecScanner, tmp_path: Path) -> None:
        result = {
            "severity": "MEDIUM",
            "confidence": "HIGH",
            "cwe": {
                "id": "326",
                "url": "https://cwe.mitre.org/data/definitions/326.html",
            },
            "rule_id": "G401",
            "details": "Use of weak cryptographic primitive",
            "file": "crypto/hash.go",
            "code": "15-16: md5.New()",
            "line": "15",
            "column": "12",
            "nosec": False,
            "suppressions": None,
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.rule_id == "G401"
        assert issue.severity == Severity.MEDIUM
        assert issue.line_start == 15
        assert issue.code_snippet == "15-16: md5.New()"
        assert issue.fixable is False
        assert issue.domain == ScanDomain.SAST
        assert issue.source_tool == "gosec"
        assert (
            issue.documentation_url == "https://cwe.mitre.org/data/definitions/326.html"
        )
        assert issue.metadata["cwe"]["id"] == "326"
        assert issue.metadata["confidence"] == "HIGH"

    def test_relative_path(self, scanner: GosecScanner, tmp_path: Path) -> None:
        result = {
            "rule_id": "G101",
            "severity": "HIGH",
            "confidence": "LOW",
            "details": "Hard-coded credentials",
            "file": "internal/config.go",
            "code": 'password := "secret"',
            "line": "5",
            "column": "1",
            "nosec": False,
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.file_path == tmp_path / "internal/config.go"

    def test_absolute_path(self, scanner: GosecScanner, tmp_path: Path) -> None:
        abs_path = str(tmp_path / "absolute" / "path" / "file.go")
        result = {
            "rule_id": "G101",
            "severity": "HIGH",
            "confidence": "HIGH",
            "details": "Hard-coded credentials",
            "file": abs_path,
            "code": 'key := "abc"',
            "line": "3",
            "column": "1",
            "nosec": False,
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        # Absolute path under project root gets resolved
        assert str(issue.file_path).startswith(str(tmp_path))

    def test_no_cwe(self, scanner: GosecScanner, tmp_path: Path) -> None:
        result = {
            "rule_id": "G104",
            "severity": "MEDIUM",
            "confidence": "HIGH",
            "details": "Errors unhandled",
            "file": "main.go",
            "code": "f.Close()",
            "line": "10",
            "column": "1",
            "nosec": False,
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.documentation_url is None
        assert "cwe" not in issue.metadata

    def test_nosec_annotated(self, scanner: GosecScanner, tmp_path: Path) -> None:
        result = {
            "rule_id": "G401",
            "severity": "MEDIUM",
            "confidence": "HIGH",
            "details": "Weak crypto",
            "file": "hash.go",
            "code": "md5.New() // nosec",
            "line": "5",
            "column": "1",
            "nosec": True,
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.metadata["nosec"] is True

    def test_with_suppressions(self, scanner: GosecScanner, tmp_path: Path) -> None:
        result = {
            "rule_id": "G401",
            "severity": "MEDIUM",
            "confidence": "HIGH",
            "details": "Weak crypto",
            "file": "hash.go",
            "code": "md5.New()",
            "line": "5",
            "column": "1",
            "nosec": False,
            "suppressions": [{"kind": "inSource", "justification": "legacy code"}],
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.metadata["suppressions"] == [
            {"kind": "inSource", "justification": "legacy code"}
        ]

    def test_exception_returns_none(
        self, scanner: GosecScanner, tmp_path: Path
    ) -> None:
        with patch.object(
            scanner, "_generate_issue_id", side_effect=ValueError("test")
        ):
            issue = scanner._result_to_unified_issue(
                {
                    "rule_id": "G101",
                    "severity": "HIGH",
                    "confidence": "HIGH",
                    "details": "Test",
                    "file": "file.go",
                    "code": "x",
                    "line": "1",
                    "column": "1",
                    "nosec": False,
                },
                tmp_path,
            )
            assert issue is None

    def test_high_severity_mapping(self, scanner: GosecScanner, tmp_path: Path) -> None:
        result = {
            "rule_id": "G201",
            "severity": "HIGH",
            "confidence": "HIGH",
            "details": "SQL injection",
            "file": "db.go",
            "code": "query",
            "line": "5",
            "column": "1",
            "nosec": False,
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.severity == Severity.HIGH

    def test_low_severity_mapping(self, scanner: GosecScanner, tmp_path: Path) -> None:
        result = {
            "rule_id": "G501",
            "severity": "LOW",
            "confidence": "HIGH",
            "details": "Blocklisted import",
            "file": "hash.go",
            "code": "import",
            "line": "3",
            "column": "1",
            "nosec": False,
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.severity == Severity.LOW


# --- _format_title ---


class TestGosecFormatTitle:
    def test_short_message(self, scanner: GosecScanner) -> None:
        title = scanner._format_title("G401", "Use of weak crypto")
        assert title == "G401: Use of weak crypto"

    def test_long_message_truncated(self, scanner: GosecScanner) -> None:
        long_msg = "A" * 100
        title = scanner._format_title("G401", long_msg)
        assert len(title) <= 100
        assert title.endswith("...")

    def test_exact_80_chars_not_truncated(self, scanner: GosecScanner) -> None:
        msg = "A" * 80
        title = scanner._format_title("id", msg)
        assert title == "id: " + "A" * 80

    def test_over_80_chars_truncated(self, scanner: GosecScanner) -> None:
        msg = "A" * 81
        title = scanner._format_title("id", msg)
        assert "..." in title


# --- _generate_issue_id ---


class TestGosecIssueId:
    def test_deterministic(self, scanner: GosecScanner) -> None:
        id1 = scanner._generate_issue_id("G401", "hash.go", 10, 5)
        id2 = scanner._generate_issue_id("G401", "hash.go", 10, 5)
        assert id1 == id2

    def test_different_inputs(self, scanner: GosecScanner) -> None:
        id1 = scanner._generate_issue_id("G401", "hash.go", 10, 5)
        id2 = scanner._generate_issue_id("G201", "hash.go", 10, 5)
        assert id1 != id2

    def test_prefix(self, scanner: GosecScanner) -> None:
        issue_id = scanner._generate_issue_id("G401", "hash.go", 10, 5)
        assert issue_id.startswith("gosec-")

    def test_different_files(self, scanner: GosecScanner) -> None:
        id1 = scanner._generate_issue_id("G401", "a.go", 10, 5)
        id2 = scanner._generate_issue_id("G401", "b.go", 10, 5)
        assert id1 != id2

    def test_different_lines(self, scanner: GosecScanner) -> None:
        id1 = scanner._generate_issue_id("G401", "a.go", 10, 5)
        id2 = scanner._generate_issue_id("G401", "a.go", 20, 5)
        assert id1 != id2


# --- Severity mapping ---


class TestGosecSeverityMap:
    def test_all_severities(self) -> None:
        assert GOSEC_SEVERITY_MAP["HIGH"] == Severity.HIGH
        assert GOSEC_SEVERITY_MAP["MEDIUM"] == Severity.MEDIUM
        assert GOSEC_SEVERITY_MAP["LOW"] == Severity.LOW

    def test_unknown_severity_defaults(
        self, scanner: GosecScanner, tmp_path: Path
    ) -> None:
        result = {
            "rule_id": "G401",
            "severity": "UNKNOWN",
            "confidence": "HIGH",
            "details": "Test",
            "file": "test.go",
            "code": "x",
            "line": "1",
            "column": "1",
            "nosec": False,
        }
        issue = scanner._result_to_unified_issue(result, tmp_path)
        assert issue is not None
        assert issue.severity == Severity.MEDIUM  # Default fallback


# --- Rule descriptions ---


class TestGosecRuleDescriptions:
    def test_sql_injection_rules_present(self) -> None:
        assert "G201" in GOSEC_RULE_DESCRIPTIONS
        assert "G202" in GOSEC_RULE_DESCRIPTIONS

    def test_command_injection_present(self) -> None:
        assert "G204" in GOSEC_RULE_DESCRIPTIONS

    def test_crypto_rules_present(self) -> None:
        assert "G401" in GOSEC_RULE_DESCRIPTIONS
        assert "G402" in GOSEC_RULE_DESCRIPTIONS
        assert "G403" in GOSEC_RULE_DESCRIPTIONS
        assert "G404" in GOSEC_RULE_DESCRIPTIONS

    def test_credential_rule_present(self) -> None:
        assert "G101" in GOSEC_RULE_DESCRIPTIONS

    def test_file_permission_rules_present(self) -> None:
        assert "G301" in GOSEC_RULE_DESCRIPTIONS
        assert "G302" in GOSEC_RULE_DESCRIPTIONS
        assert "G306" in GOSEC_RULE_DESCRIPTIONS

    def test_blocklist_rules_present(self) -> None:
        assert "G501" in GOSEC_RULE_DESCRIPTIONS
        assert "G502" in GOSEC_RULE_DESCRIPTIONS
        assert "G503" in GOSEC_RULE_DESCRIPTIONS
        assert "G504" in GOSEC_RULE_DESCRIPTIONS
        assert "G505" in GOSEC_RULE_DESCRIPTIONS
