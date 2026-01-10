"""Integration tests for Trivy scanner.

These tests actually run the Trivy binary against real targets.
They require:
- Trivy binary (downloaded automatically on first run)
- Docker (for container scanning tests)

Run with: pytest tests/integration -v --run-scanners
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


from lucidscan.config.models import LucidScanConfig, ScannerDomainConfig
from lucidscan.core.models import ScanContext, ScanDomain, Severity
from lucidscan.plugins.scanners.trivy import TrivyScanner
from tests.integration.conftest import trivy_available, docker_available


class TestTrivyBinaryDownload:
    """Tests for Trivy binary download and management."""

    def test_ensure_binary_downloads_trivy(self, trivy_scanner: TrivyScanner) -> None:
        """Test that ensure_binary downloads Trivy if not present."""
        binary_path = trivy_scanner.ensure_binary()

        assert binary_path.exists()
        assert binary_path.name == "trivy"

    def test_trivy_binary_is_executable(
        self, ensure_trivy_binary: Path
    ) -> None:
        """Test that the downloaded Trivy binary is executable."""
        result = subprocess.run(
            [str(ensure_trivy_binary), "version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Version:" in result.stdout or "version" in result.stdout.lower()


@trivy_available
class TestTrivySCAScanning:
    """Integration tests for Trivy SCA (filesystem) scanning."""

    def test_scan_project_root(
        self,
        trivy_scanner: TrivyScanner,
        project_root: Path,
    ) -> None:
        """Test scanning the lucidscan project root for SCA vulnerabilities."""
        context = ScanContext(
            project_root=project_root,
            paths=[project_root],
            enabled_domains=[ScanDomain.SCA],
        )

        issues = trivy_scanner.scan(context)

        # The result should be a list (possibly empty if no vulnerabilities)
        assert isinstance(issues, list)
        # All issues should be UnifiedIssue objects
        for issue in issues:
            assert hasattr(issue, "id")
            assert hasattr(issue, "severity")
            assert hasattr(issue, "scanner")
            assert issue.scanner == ScanDomain.SCA
            assert issue.source_tool == "trivy"

    def test_scan_with_vulnerable_package(
        self, trivy_scanner: TrivyScanner, tmp_path: Path
    ) -> None:
        """Test scanning a directory with a known vulnerable package."""
        # Create a package.json with a known vulnerable package
        # lodash 4.17.15 has known vulnerabilities
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({
            "name": "test-project",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "4.17.15"
            }
        }))

        # Create a minimal package-lock.json
        package_lock = tmp_path / "package-lock.json"
        package_lock.write_text(json.dumps({
            "name": "test-project",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "requires": True,
            "packages": {
                "": {
                    "name": "test-project",
                    "version": "1.0.0",
                    "dependencies": {
                        "lodash": "4.17.15"
                    }
                },
                "node_modules/lodash": {
                    "version": "4.17.15",
                    "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.15.tgz"
                }
            },
            "dependencies": {
                "lodash": {
                    "version": "4.17.15"
                }
            }
        }))

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )

        issues = trivy_scanner.scan(context)

        # lodash 4.17.15 should have vulnerabilities
        assert len(issues) > 0, "Expected vulnerabilities in lodash 4.17.15"

        # Verify issue structure
        issue = issues[0]
        assert issue.scanner == ScanDomain.SCA
        assert issue.source_tool == "trivy"
        assert issue.severity in [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        ]
        assert issue.dependency is not None
        assert "lodash" in issue.dependency.lower()

    def test_scan_empty_directory(
        self, trivy_scanner: TrivyScanner, tmp_path: Path
    ) -> None:
        """Test scanning an empty directory returns no issues."""
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )

        issues = trivy_scanner.scan(context)

        assert issues == []

    def test_scan_python_requirements(
        self, trivy_scanner: TrivyScanner, tmp_path: Path
    ) -> None:
        """Test scanning a Python project with requirements.txt."""
        # Create a requirements.txt with a known vulnerable package
        # django 2.2.0 has known vulnerabilities
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("django==2.2.0\n")

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )

        issues = trivy_scanner.scan(context)

        # django 2.2.0 should have vulnerabilities
        assert len(issues) > 0, "Expected vulnerabilities in django 2.2.0"

        # Find django-related issues
        django_issues = [
            i for i in issues if "django" in (i.dependency or "").lower()
        ]
        assert len(django_issues) > 0, "Expected django vulnerabilities"


@trivy_available
@docker_available
class TestTrivyContainerScanning:
    """Integration tests for Trivy container image scanning.

    These tests require Docker to be installed and running.
    """

    def test_scan_alpine_image(self, trivy_scanner: TrivyScanner) -> None:
        """Test scanning an alpine image."""
        # Pull the image first to ensure it's available
        subprocess.run(
            ["docker", "pull", "alpine:3.14"],
            capture_output=True,
            timeout=120,
        )

        config = LucidScanConfig(
            scanners={
                "container": ScannerDomainConfig(
                    enabled=True,
                    options={"images": ["alpine:3.14"]},
                )
            }
        )
        context = ScanContext(
            project_root=Path.cwd(),
            paths=[],
            enabled_domains=[ScanDomain.CONTAINER],
            config=config,
        )

        issues = trivy_scanner.scan(context)

        # Verify the scan completed and returns valid structure
        assert isinstance(issues, list)

        # If there are issues, verify structure
        if issues:
            issue = issues[0]
            assert issue.scanner == ScanDomain.CONTAINER
            assert issue.source_tool == "trivy"
            assert "image_ref" in issue.scanner_metadata
            assert issue.scanner_metadata["image_ref"] == "alpine:3.14"

    def test_scan_vulnerable_image(self, trivy_scanner: TrivyScanner) -> None:
        """Test scanning an image with known vulnerabilities (python:3.8-slim-buster)."""
        # python:3.8-slim-buster is an older image with known vulnerabilities
        subprocess.run(
            ["docker", "pull", "python:3.8-slim-buster"],
            capture_output=True,
            timeout=180,
        )

        config = LucidScanConfig(
            scanners={
                "container": ScannerDomainConfig(
                    enabled=True,
                    options={"images": ["python:3.8-slim-buster"]},
                )
            }
        )
        context = ScanContext(
            project_root=Path.cwd(),
            paths=[],
            enabled_domains=[ScanDomain.CONTAINER],
            config=config,
        )

        issues = trivy_scanner.scan(context)

        # This image should have vulnerabilities
        assert len(issues) > 0, "Expected vulnerabilities in python:3.8-slim-buster"

        # Verify issue structure
        issue = issues[0]
        assert issue.scanner == ScanDomain.CONTAINER
        assert issue.source_tool == "trivy"
        assert "image_ref" in issue.scanner_metadata

    def test_scan_multiple_images(self, trivy_scanner: TrivyScanner) -> None:
        """Test scanning multiple container images."""
        # Pull images first
        for image in ["alpine:latest", "busybox:latest"]:
            subprocess.run(
                ["docker", "pull", image],
                capture_output=True,
                timeout=120,
            )

        config = LucidScanConfig(
            scanners={
                "container": ScannerDomainConfig(
                    enabled=True,
                    options={"images": ["alpine:latest", "busybox:latest"]},
                )
            }
        )
        context = ScanContext(
            project_root=Path.cwd(),
            paths=[],
            enabled_domains=[ScanDomain.CONTAINER],
            config=config,
        )

        issues = trivy_scanner.scan(context)

        # Scan should complete successfully
        assert isinstance(issues, list)

        # If issues exist, they should be from one of the scanned images
        if issues:
            image_refs = {i.scanner_metadata.get("image_ref") for i in issues}
            assert image_refs.issubset({"alpine:latest", "busybox:latest", None})

    def test_scan_latest_alpine(self, trivy_scanner: TrivyScanner) -> None:
        """Test scanning alpine:latest."""
        subprocess.run(
            ["docker", "pull", "alpine:latest"],
            capture_output=True,
            timeout=120,
        )

        config = LucidScanConfig(
            scanners={
                "container": ScannerDomainConfig(
                    enabled=True,
                    options={"images": ["alpine:latest"]},
                )
            }
        )
        context = ScanContext(
            project_root=Path.cwd(),
            paths=[],
            enabled_domains=[ScanDomain.CONTAINER],
            config=config,
        )

        issues = trivy_scanner.scan(context)

        # alpine:latest may or may not have vulnerabilities
        # Just verify the scan completes and returns valid structure
        assert isinstance(issues, list)
        for issue in issues:
            assert issue.scanner == ScanDomain.CONTAINER


@trivy_available
class TestTrivyOutputParsing:
    """Tests for Trivy JSON output parsing."""

    def test_severity_mapping_and_metadata(
        self, trivy_scanner: TrivyScanner, tmp_path: Path
    ) -> None:
        """Test severity mapping and metadata in a single scan."""
        # Create requirements with packages of varying severity
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("django==2.2.0\nrequests==2.20.0\n")

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )

        issues = trivy_scanner.scan(context)

        # Verify severity is one of the expected values
        severities = {issue.severity for issue in issues}
        valid_severities = {
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        }
        assert severities.issubset(valid_severities)

        # Verify scanner_metadata contains raw Trivy data
        if issues:
            issue = issues[0]
            assert "vulnerability_id" in issue.scanner_metadata
            assert "pkg_name" in issue.scanner_metadata
            assert "installed_version" in issue.scanner_metadata

    def test_issue_id_is_deterministic(
        self, trivy_scanner: TrivyScanner, tmp_path: Path
    ) -> None:
        """Test that issue IDs are deterministic across scans."""
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("django==2.2.0\n")

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )

        # Run scan twice
        issues1 = trivy_scanner.scan(context)
        issues2 = trivy_scanner.scan(context)

        # Same issues should have same IDs
        ids1 = {issue.id for issue in issues1}
        ids2 = {issue.id for issue in issues2}
        assert ids1 == ids2


@trivy_available
class TestTrivyCLIIntegration:
    """Integration tests for the CLI with Trivy scanner."""

    def test_cli_sca_scan_json_output(self, project_root: Path) -> None:
        """Test CLI SCA scan with JSON output."""
        import lucidscan.cli as cli

        # Capture stdout
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()

        try:
            exit_code = cli.main([
                "scan",
                "--sca",
                "--format", "json",
                str(project_root),
            ])
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()

        assert exit_code == 0
        # Verify valid JSON
        data = json.loads(output)
        assert "schema_version" in data
        assert "issues" in data
        assert "metadata" in data
        assert "summary" in data

    def test_cli_sca_scan_table_output(self, project_root: Path) -> None:
        """Test CLI SCA scan with table output."""
        import lucidscan.cli as cli
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()

        try:
            exit_code = cli.main([
                "scan",
                "--sca",
                "--format", "table",
                str(project_root),
            ])
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()

        assert exit_code == 0
        # Table should have output (either issues or "No issues found")
        assert len(output) > 0

    def test_cli_sca_scan_summary_output(self, project_root: Path) -> None:
        """Test CLI SCA scan with summary output."""
        import lucidscan.cli as cli
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()

        try:
            exit_code = cli.main([
                "scan",
                "--sca",
                "--format", "summary",
                str(project_root),
            ])
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()

        assert exit_code == 0
        assert "Total issues:" in output

    def test_cli_fail_on_high(self, tmp_path: Path) -> None:
        """Test CLI --fail-on flag with high severity threshold."""
        import lucidscan.cli as cli
        import io
        import sys

        # Create requirements with known high/critical vulnerabilities
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("django==2.2.0\n")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            exit_code = cli.main([
                "scan",
                "--sca",
                "--format", "json",
                "--fail-on", "high",
                str(tmp_path),
            ])
        finally:
            sys.stdout = old_stdout

        # django 2.2.0 has high/critical vulnerabilities, should return 1
        assert exit_code == 1
