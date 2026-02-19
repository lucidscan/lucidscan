"""Unit tests for Trivy scanner plugin."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, ScanDomain, Severity
from lucidshark.plugins.scanners.trivy import TrivyScanner, TRIVY_SEVERITY_MAP

_TRIVY_BINARY = "trivy.exe" if sys.platform == "win32" else "trivy"


def _make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def scanner(tmp_path: Path) -> TrivyScanner:
    return TrivyScanner(version="0.68.1", project_root=tmp_path)


@pytest.fixture
def sca_context(tmp_path: Path) -> ScanContext:
    return ScanContext(
        project_root=tmp_path,
        paths=[tmp_path],
        enabled_domains=[ScanDomain.SCA],
    )


@pytest.fixture
def container_context(tmp_path: Path) -> ScanContext:
    config = MagicMock()
    config.get_scanner_options.return_value = {"images": ["nginx:latest"]}
    return ScanContext(
        project_root=tmp_path,
        paths=[tmp_path],
        enabled_domains=[ScanDomain.CONTAINER],
        config=config,
    )


@pytest.fixture
def sample_trivy_output() -> str:
    return json.dumps(
        {
            "Results": [
                {
                    "Target": "requirements.txt",
                    "Type": "pip",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2024-1234",
                            "PkgName": "requests",
                            "InstalledVersion": "2.28.0",
                            "FixedVersion": "2.31.0",
                            "Severity": "HIGH",
                            "Title": "SSRF vulnerability in requests",
                            "Description": "A server-side request forgery vulnerability.",
                            "References": ["https://nvd.nist.gov/vuln/detail/CVE-2024-1234"],
                            "CVSS": {"nvd": {"V3Score": 7.5}},
                            "CweIDs": ["CWE-918"],
                            "PublishedDate": "2024-01-15",
                            "LastModifiedDate": "2024-02-01",
                        }
                    ],
                }
            ]
        }
    )


# --- Properties ---


class TestTrivyScannerProperties:
    def test_name(self, scanner: TrivyScanner) -> None:
        assert scanner.name == "trivy"

    def test_domains(self, scanner: TrivyScanner) -> None:
        assert scanner.domains == [ScanDomain.SCA, ScanDomain.CONTAINER]

    def test_get_version(self, scanner: TrivyScanner) -> None:
        assert scanner.get_version() == "0.68.1"

    def test_default_project_root(self) -> None:
        s = TrivyScanner(version="0.68.1")
        assert s.name == "trivy"


# --- ensure_binary ---


class TestTrivyEnsureBinary:
    def test_binary_exists(self, scanner: TrivyScanner, tmp_path: Path) -> None:
        binary_dir = scanner._paths.plugin_bin_dir("trivy", "0.68.1")
        binary_dir.mkdir(parents=True, exist_ok=True)
        binary = binary_dir / _TRIVY_BINARY
        binary.touch()
        result = scanner.ensure_binary()
        assert result == binary

    def test_download_triggered(self, scanner: TrivyScanner) -> None:
        with patch.object(scanner, "_download_binary") as mock_dl:
            def create_binary(dest_dir: Path) -> None:
                dest_dir.mkdir(parents=True, exist_ok=True)
                (dest_dir / _TRIVY_BINARY).touch()

            mock_dl.side_effect = create_binary
            result = scanner.ensure_binary()
            mock_dl.assert_called_once()
            assert result.name == _TRIVY_BINARY

    def test_raises_when_download_fails(self, scanner: TrivyScanner) -> None:
        with patch.object(scanner, "_download_binary"):
            with pytest.raises(RuntimeError, match="Failed to download"):
                scanner.ensure_binary()


# --- scan ---


class TestTrivyScan:
    def test_sca_scan(
        self,
        scanner: TrivyScanner,
        sca_context: ScanContext,
    ) -> None:
        with patch.object(
            scanner, "ensure_binary", return_value=Path("/bin/trivy")
        ):
            with patch.object(scanner, "_run_fs_scan", return_value=[]) as mock_fs:
                scanner.scan(sca_context)
                mock_fs.assert_called_once()

    def test_container_scan(
        self,
        scanner: TrivyScanner,
        container_context: ScanContext,
    ) -> None:
        with patch.object(
            scanner, "ensure_binary", return_value=Path("/bin/trivy")
        ):
            with patch.object(
                scanner, "_run_image_scan", return_value=[]
            ) as mock_img:
                scanner.scan(container_context)
                mock_img.assert_called_once_with(
                    Path("/bin/trivy"),
                    "nginx:latest",
                    scanner._paths.plugin_cache_dir("trivy"),
                    container_context.stream_handler,
                )

    def test_both_domains_scan(self, scanner: TrivyScanner, tmp_path: Path) -> None:
        config = MagicMock()
        config.get_scanner_options.return_value = {"images": ["app:v1"]}
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA, ScanDomain.CONTAINER],
            config=config,
        )
        with patch.object(
            scanner, "ensure_binary", return_value=Path("/bin/trivy")
        ):
            with patch.object(scanner, "_run_fs_scan", return_value=[]) as mock_fs:
                with patch.object(
                    scanner, "_run_image_scan", return_value=[]
                ) as mock_img:
                    scanner.scan(context)
                    mock_fs.assert_called_once()
                    mock_img.assert_called_once()


# --- _run_fs_scan ---


class TestTrivyRunFsScan:
    def test_successful_scan(
        self,
        scanner: TrivyScanner,
        sca_context: ScanContext,
        sample_trivy_output: str,
    ) -> None:
        mock_result = _make_completed_process(0, sample_trivy_output)
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            return_value=mock_result,
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_fs_scan(
                Path("/bin/trivy"), sca_context, cache_dir
            )
            assert len(issues) == 1
            assert issues[0].rule_id == "CVE-2024-1234"

    def test_empty_output(
        self, scanner: TrivyScanner, sca_context: ScanContext
    ) -> None:
        mock_result = _make_completed_process(0, "")
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            return_value=mock_result,
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_fs_scan(
                Path("/bin/trivy"), sca_context, cache_dir
            )
            assert issues == []

    def test_nonzero_exit_with_stderr(
        self, scanner: TrivyScanner, sca_context: ScanContext
    ) -> None:
        mock_result = _make_completed_process(1, "", "db update failed")
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            return_value=mock_result,
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_fs_scan(
                Path("/bin/trivy"), sca_context, cache_dir
            )
            assert issues == []

    def test_timeout(
        self, scanner: TrivyScanner, sca_context: ScanContext
    ) -> None:
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            side_effect=subprocess.TimeoutExpired("trivy", 180),
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_fs_scan(
                Path("/bin/trivy"), sca_context, cache_dir
            )
            assert issues == []

    def test_generic_exception(
        self, scanner: TrivyScanner, sca_context: ScanContext
    ) -> None:
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            side_effect=OSError("command failed"),
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_fs_scan(
                Path("/bin/trivy"), sca_context, cache_dir
            )
            assert issues == []

    def test_config_options(
        self, scanner: TrivyScanner, tmp_path: Path
    ) -> None:
        config = MagicMock()
        config.get_scanner_options.return_value = {
            "ignore_unfixed": True,
            "skip_db_update": True,
            "severity": ["CRITICAL", "HIGH"],
        }
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
            config=config,
        )
        mock_result = _make_completed_process(0, json.dumps({"Results": []}))
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            scanner._run_fs_scan(Path("/bin/trivy"), context, cache_dir)
            cmd = mock_run.call_args.kwargs.get("cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else [])
            assert "--ignore-unfixed" in cmd
            assert "--skip-db-update" in cmd
            assert "--severity" in cmd
            assert "CRITICAL,HIGH" in cmd

    def test_exclude_patterns_dirs_and_files(
        self, scanner: TrivyScanner, tmp_path: Path
    ) -> None:
        ignore = MagicMock()
        ignore.get_exclude_patterns.return_value = [
            "node_modules/",
            ".venv/**",
            "*.bak",
        ]
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
            ignore_patterns=ignore,
        )
        mock_result = _make_completed_process(0, json.dumps({"Results": []}))
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            return_value=mock_result,
        ) as mock_run:
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            scanner._run_fs_scan(Path("/bin/trivy"), context, cache_dir)
            cmd = mock_run.call_args.kwargs.get("cmd", mock_run.call_args[0][0] if mock_run.call_args[0] else [])
            assert "--skip-dirs" in cmd
            assert "node_modules" in cmd
            assert ".venv" in cmd
            assert "--skip-files" in cmd
            assert "*.bak" in cmd


# --- _run_image_scan ---


class TestTrivyRunImageScan:
    def test_successful_scan(
        self, scanner: TrivyScanner, sample_trivy_output: str
    ) -> None:
        mock_result = _make_completed_process(0, sample_trivy_output)
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            return_value=mock_result,
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_image_scan(
                Path("/bin/trivy"), "nginx:latest", cache_dir
            )
            assert len(issues) == 1

    def test_empty_output(self, scanner: TrivyScanner) -> None:
        mock_result = _make_completed_process(0, "")
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            return_value=mock_result,
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_image_scan(
                Path("/bin/trivy"), "nginx:latest", cache_dir
            )
            assert issues == []

    def test_timeout(self, scanner: TrivyScanner) -> None:
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            side_effect=subprocess.TimeoutExpired("trivy", 300),
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_image_scan(
                Path("/bin/trivy"), "nginx:latest", cache_dir
            )
            assert issues == []

    def test_generic_exception(self, scanner: TrivyScanner) -> None:
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            side_effect=OSError("docker not running"),
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_image_scan(
                Path("/bin/trivy"), "nginx:latest", cache_dir
            )
            assert issues == []

    def test_nonzero_exit_with_stderr(self, scanner: TrivyScanner) -> None:
        mock_result = _make_completed_process(1, "", "image not found")
        with patch(
            "lucidshark.plugins.scanners.trivy.run_with_streaming",
            return_value=mock_result,
        ):
            cache_dir = scanner._paths.plugin_cache_dir("trivy")
            cache_dir.mkdir(parents=True, exist_ok=True)
            issues = scanner._run_image_scan(
                Path("/bin/trivy"), "nginx:latest", cache_dir
            )
            assert issues == []


# --- _parse_trivy_json ---


class TestTrivyParseJson:
    def test_valid_output(
        self, scanner: TrivyScanner, sample_trivy_output: str
    ) -> None:
        issues = scanner._parse_trivy_json(sample_trivy_output, ScanDomain.SCA)
        assert len(issues) == 1
        assert issues[0].rule_id == "CVE-2024-1234"
        assert issues[0].severity == Severity.HIGH

    def test_invalid_json(self, scanner: TrivyScanner) -> None:
        issues = scanner._parse_trivy_json("not json", ScanDomain.SCA)
        assert issues == []

    def test_empty_results(self, scanner: TrivyScanner) -> None:
        data = json.dumps({"Results": []})
        issues = scanner._parse_trivy_json(data, ScanDomain.SCA)
        assert issues == []

    def test_no_vulnerabilities(self, scanner: TrivyScanner) -> None:
        data = json.dumps(
            {"Results": [{"Target": "Gemfile.lock", "Type": "bundler", "Vulnerabilities": None}]}
        )
        issues = scanner._parse_trivy_json(data, ScanDomain.SCA)
        assert issues == []

    def test_multiple_results(self, scanner: TrivyScanner) -> None:
        data = json.dumps(
            {
                "Results": [
                    {
                        "Target": "requirements.txt",
                        "Type": "pip",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2024-1111",
                                "PkgName": "flask",
                                "InstalledVersion": "2.0.0",
                                "Severity": "HIGH",
                                "Title": "Vuln 1",
                                "Description": "Desc 1",
                            }
                        ],
                    },
                    {
                        "Target": "package-lock.json",
                        "Type": "npm",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2024-2222",
                                "PkgName": "lodash",
                                "InstalledVersion": "4.17.20",
                                "Severity": "CRITICAL",
                                "Title": "Vuln 2",
                                "Description": "Desc 2",
                            }
                        ],
                    },
                ]
            }
        )
        issues = scanner._parse_trivy_json(data, ScanDomain.SCA)
        assert len(issues) == 2

    def test_container_domain_with_image_ref(self, scanner: TrivyScanner) -> None:
        data = json.dumps(
            {
                "Results": [
                    {
                        "Target": "nginx:latest (debian 12.0)",
                        "Type": "debian",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2024-3333",
                                "PkgName": "openssl",
                                "InstalledVersion": "3.0.0",
                                "Severity": "MEDIUM",
                                "Title": "OpenSSL vuln",
                                "Description": "Desc",
                            }
                        ],
                    }
                ]
            }
        )
        issues = scanner._parse_trivy_json(
            data, ScanDomain.CONTAINER, image_ref="nginx:latest"
        )
        assert len(issues) == 1
        assert issues[0].metadata["image_ref"] == "nginx:latest"
        # Container domain should not have file_path
        assert issues[0].file_path is None


# --- _vuln_to_unified_issue ---


class TestTrivyVulnToUnifiedIssue:
    def test_full_vulnerability(self, scanner: TrivyScanner) -> None:
        vuln = {
            "VulnerabilityID": "CVE-2024-1234",
            "PkgName": "requests",
            "InstalledVersion": "2.28.0",
            "FixedVersion": "2.31.0",
            "Severity": "HIGH",
            "Title": "SSRF vulnerability",
            "Description": "A server-side request forgery.",
            "References": ["https://nvd.nist.gov/vuln/detail/CVE-2024-1234"],
            "CVSS": {"nvd": {"V3Score": 7.5}},
            "CweIDs": ["CWE-918"],
            "PublishedDate": "2024-01-15",
            "LastModifiedDate": "2024-02-01",
        }
        issue = scanner._vuln_to_unified_issue(
            vuln, ScanDomain.SCA, "requirements.txt", "pip"
        )
        assert issue is not None
        assert issue.rule_id == "CVE-2024-1234"
        assert issue.severity == Severity.HIGH
        assert issue.domain == ScanDomain.SCA
        assert issue.source_tool == "trivy"
        assert issue.dependency is not None
        assert "requests@2.28.0" in issue.dependency
        assert "pip" in issue.dependency
        assert issue.recommendation == "Upgrade requests to version 2.31.0"
        assert issue.fixable is True
        assert issue.suggested_fix == "Upgrade to version 2.31.0"
        assert issue.documentation_url == "https://nvd.nist.gov/vuln/detail/CVE-2024-1234"
        assert issue.file_path == Path("requirements.txt")

    def test_no_fixed_version(self, scanner: TrivyScanner) -> None:
        vuln = {
            "VulnerabilityID": "CVE-2024-5678",
            "PkgName": "pkg",
            "InstalledVersion": "1.0.0",
            "FixedVersion": "",
            "Severity": "LOW",
            "Title": "Vuln title",
            "Description": "Desc",
        }
        issue = scanner._vuln_to_unified_issue(
            vuln, ScanDomain.SCA, "Gemfile.lock", "bundler"
        )
        assert issue is not None
        assert issue.fixable is False
        assert issue.recommendation is None
        assert issue.suggested_fix is None

    def test_container_domain_no_file_path(self, scanner: TrivyScanner) -> None:
        vuln = {
            "VulnerabilityID": "CVE-2024-9999",
            "PkgName": "openssl",
            "InstalledVersion": "3.0.0",
            "Severity": "CRITICAL",
            "Title": "SSL vuln",
            "Description": "Critical SSL issue",
        }
        issue = scanner._vuln_to_unified_issue(
            vuln, ScanDomain.CONTAINER, "layer", "debian", image_ref="nginx:latest"
        )
        assert issue is not None
        assert issue.file_path is None
        assert issue.metadata["image_ref"] == "nginx:latest"

    def test_unknown_severity(self, scanner: TrivyScanner) -> None:
        vuln = {
            "VulnerabilityID": "CVE-UNKNOWN",
            "PkgName": "pkg",
            "InstalledVersion": "1.0",
            "Severity": "UNKNOWN",
            "Title": "Unknown",
            "Description": "Unknown sev",
        }
        issue = scanner._vuln_to_unified_issue(
            vuln, ScanDomain.SCA, "target", "pip"
        )
        assert issue is not None
        assert issue.severity == Severity.INFO

    def test_missing_fields_use_defaults(self, scanner: TrivyScanner) -> None:
        vuln = {
            "VulnerabilityID": "CVE-MINIMAL",
            "PkgName": "pkg",
        }
        issue = scanner._vuln_to_unified_issue(
            vuln, ScanDomain.SCA, "target", "pip"
        )
        assert issue is not None
        assert issue.dependency is not None
        assert "unknown" in issue.dependency

    def test_exception_returns_none(self, scanner: TrivyScanner) -> None:
        with patch.object(
            scanner,
            "_generate_issue_id",
            side_effect=ValueError("test"),
        ):
            issue = scanner._vuln_to_unified_issue(
                {"VulnerabilityID": "X", "PkgName": "Y", "InstalledVersion": "1"},
                ScanDomain.SCA,
                "target",
                "pip",
            )
            assert issue is None

    def test_no_references(self, scanner: TrivyScanner) -> None:
        vuln = {
            "VulnerabilityID": "CVE-2024-0000",
            "PkgName": "pkg",
            "InstalledVersion": "1.0",
            "Severity": "LOW",
            "Title": "Title",
            "Description": "Desc",
            "References": [],
        }
        issue = scanner._vuln_to_unified_issue(
            vuln, ScanDomain.SCA, "target", "pip"
        )
        assert issue is not None
        assert issue.documentation_url is None


# --- _generate_issue_id ---


class TestTrivyIssueId:
    def test_deterministic(self, scanner: TrivyScanner) -> None:
        id1 = scanner._generate_issue_id("CVE-2024-1234", "requests", "2.28.0", "requirements.txt")
        id2 = scanner._generate_issue_id("CVE-2024-1234", "requests", "2.28.0", "requirements.txt")
        assert id1 == id2

    def test_different_inputs(self, scanner: TrivyScanner) -> None:
        id1 = scanner._generate_issue_id("CVE-2024-1234", "requests", "2.28.0", "requirements.txt")
        id2 = scanner._generate_issue_id("CVE-2024-5678", "requests", "2.28.0", "requirements.txt")
        assert id1 != id2

    def test_prefix(self, scanner: TrivyScanner) -> None:
        issue_id = scanner._generate_issue_id("CVE-2024-1234", "pkg", "1.0", "target")
        assert issue_id.startswith("trivy-")


# --- Severity mapping ---


class TestTrivySeverityMap:
    def test_all_severities(self) -> None:
        assert TRIVY_SEVERITY_MAP["CRITICAL"] == Severity.CRITICAL
        assert TRIVY_SEVERITY_MAP["HIGH"] == Severity.HIGH
        assert TRIVY_SEVERITY_MAP["MEDIUM"] == Severity.MEDIUM
        assert TRIVY_SEVERITY_MAP["LOW"] == Severity.LOW
        assert TRIVY_SEVERITY_MAP["UNKNOWN"] == Severity.INFO
