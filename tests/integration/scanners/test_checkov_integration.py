"""Integration tests for Checkov scanner.

These tests actually run Checkov against real IaC files.
They require:
- Checkov binary (downloaded automatically on first run from GitHub releases)

Run with: pytest tests/integration -v --run-scanners
"""

from __future__ import annotations

import subprocess
from pathlib import Path


from lucidshark.config.models import LucidSharkConfig, ScannerDomainConfig
from lucidshark.core.models import ScanContext, ScanDomain, Severity
from lucidshark.plugins.scanners.checkov import CheckovScanner
from tests.integration.conftest import checkov_available


@checkov_available
class TestCheckovInstallation:
    """Tests for Checkov installation and management."""

    def test_ensure_binary_installs_checkov(
        self, checkov_scanner: CheckovScanner
    ) -> None:
        """Test that ensure_binary installs Checkov if not present."""
        binary_path = checkov_scanner.ensure_binary()

        assert binary_path.exists()
        assert "checkov" in binary_path.name

    def test_checkov_binary_is_executable(
        self, ensure_checkov_binary: Path
    ) -> None:
        """Test that the installed Checkov binary is executable."""
        result = subprocess.run(
            [str(ensure_checkov_binary), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

        assert result.returncode == 0
        # Checkov outputs version info to stdout or stderr
        output = result.stdout + result.stderr
        assert "checkov" in output.lower() or "." in output  # Version number


@checkov_available
class TestCheckovIaCScanning:
    """Integration tests for Checkov IaC scanning."""

    def test_scan_terraform_file(
        self, checkov_scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        """Test scanning a Terraform file with security issues."""
        # Create a Terraform file with a known insecure configuration
        # S3 bucket without encryption
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('''
resource "aws_s3_bucket" "example" {
  bucket = "my-test-bucket"
  acl    = "public-read"
}

resource "aws_security_group" "allow_all" {
  name        = "allow_all"
  description = "Allow all inbound traffic"

  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
''')

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
        )

        issues = checkov_scanner.scan(context)

        # This configuration should have issues
        assert len(issues) > 0, "Expected IaC issues in insecure Terraform"

        # Verify issue structure
        for issue in issues:
            assert issue.domain == ScanDomain.IAC
            assert issue.source_tool == "checkov"
            assert issue.severity in [
                Severity.CRITICAL,
                Severity.HIGH,
                Severity.MEDIUM,
                Severity.LOW,
                Severity.INFO,
            ]

    def test_scan_kubernetes_manifest(
        self, checkov_scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        """Test scanning a Kubernetes manifest with security issues."""
        # Create a Kubernetes deployment with security issues
        k8s_file = tmp_path / "deployment.yaml"
        k8s_file.write_text('''
apiVersion: apps/v1
kind: Deployment
metadata:
  name: insecure-nginx
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        securityContext:
          privileged: true
          runAsRoot: true
''')

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
        )

        issues = checkov_scanner.scan(context)

        # This manifest should have issues (privileged container, latest tag)
        assert len(issues) > 0, "Expected IaC issues in insecure K8s manifest"

    def test_scan_empty_directory(
        self, checkov_scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        """Test scanning an empty directory returns no issues."""
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
        )

        issues = checkov_scanner.scan(context)

        assert issues == []

    def test_scan_secure_terraform(
        self, checkov_scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        """Test scanning a secure Terraform configuration."""
        # Create a more secure Terraform file
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('''
resource "aws_s3_bucket" "example" {
  bucket = "my-secure-bucket"
}

resource "aws_s3_bucket_public_access_block" "example" {
  bucket = aws_s3_bucket.example.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "example" {
  bucket = aws_s3_bucket.example.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
''')

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
        )

        issues = checkov_scanner.scan(context)

        # This configuration should have fewer issues
        # (may still have some depending on Checkov rules)
        assert isinstance(issues, list)

    def test_scan_with_framework_filter(
        self, checkov_scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        """Test scanning with specific framework filter."""
        # Create both Terraform and Kubernetes files
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('resource "aws_s3_bucket" "test" { bucket = "test" }')

        k8s_file = tmp_path / "pod.yaml"
        k8s_file.write_text('''
apiVersion: v1
kind: Pod
metadata:
  name: test
spec:
  containers:
  - name: test
    image: nginx
''')

        # Scan only Terraform
        config = LucidSharkConfig(
            scanners={
                "iac": ScannerDomainConfig(
                    enabled=True,
                    options={"framework": ["terraform"]},
                )
            }
        )
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
            config=config,
        )

        issues = checkov_scanner.scan(context)

        # All issues should be from Terraform
        for issue in issues:
            assert issue.metadata.get("check_type") in [
                "terraform", "terraform_plan"
            ], f"Unexpected check_type: {issue.metadata.get('check_type')}"


@checkov_available
class TestCheckovOutputParsing:
    """Tests for Checkov JSON output parsing."""

    def test_severity_mapping_and_metadata(
        self, checkov_scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        """Test severity mapping, metadata, and issue structure in a single scan."""
        # Create Terraform with issues of varying severity
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('''
resource "aws_s3_bucket" "my_bucket" {
  bucket = "test-bucket"
  acl    = "public-read"
}

resource "aws_security_group" "allow_all" {
  name = "allow_all"
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
''')

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
        )

        issues = checkov_scanner.scan(context)

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

        # Verify scanner_metadata contains raw Checkov data
        if issues:
            issue = issues[0]
            assert "check_id" in issue.metadata
            assert "check_type" in issue.metadata
            assert issue.metadata["check_id"].startswith("CKV")

        # Find S3 bucket issues and verify iac_resource
        s3_issues = [
            i for i in issues
            if i.iac_resource and "aws_s3_bucket" in i.iac_resource
        ]
        if s3_issues:
            issue = s3_issues[0]
            assert issue.iac_resource and "aws_s3_bucket.my_bucket" in issue.iac_resource

    def test_issue_id_is_deterministic(
        self, checkov_scanner: CheckovScanner, tmp_path: Path
    ) -> None:
        """Test that issue IDs are deterministic across scans."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('''
resource "aws_s3_bucket" "test" {
  bucket = "test"
  acl    = "public-read"
}
''')

        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.IAC],
        )

        # Run scan twice
        issues1 = checkov_scanner.scan(context)
        issues2 = checkov_scanner.scan(context)

        # Same issues should have same IDs
        ids1 = {issue.id for issue in issues1}
        ids2 = {issue.id for issue in issues2}
        assert ids1 == ids2
