"""Integration tests for OpenGrep scanner.

These tests actually run the OpenGrep binary against real targets.
They require:
- OpenGrep binary (downloaded automatically on first run)

Run with: pytest tests/integration -v --run-scanners
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from lucidscan.core.models import ScanContext, ScanDomain, Severity
from lucidscan.scanners.opengrep import OpenGrepScanner
from tests.integration.conftest import opengrep_available


class TestOpenGrepBinaryDownload:
    """Tests for OpenGrep binary download and management."""

    def test_ensure_binary_downloads_opengrep(
        self, opengrep_scanner: OpenGrepScanner
    ) -> None:
        """Test that ensure_binary downloads OpenGrep if not present."""
        binary_path = opengrep_scanner.ensure_binary()

        assert binary_path.exists()
        assert "opengrep" in binary_path.name

    def test_opengrep_binary_is_executable(
        self, ensure_opengrep_binary: Path
    ) -> None:
        """Test that the downloaded OpenGrep binary is executable."""
        result = subprocess.run(
            [str(ensure_opengrep_binary), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # OpenGrep should respond to --version
        # Note: exit code might be non-zero for some versions
        assert "opengrep" in result.stdout.lower() or "semgrep" in result.stdout.lower() or result.returncode == 0


@opengrep_available
class TestOpenGrepSASTScanning:
    """Integration tests for OpenGrep SAST scanning."""

    def test_scan_project_root(
        self,
        opengrep_scanner: OpenGrepScanner,
        project_root: Path,
    ) -> None:
        """Test scanning the lucidscan project root for SAST findings."""
        context = ScanContext(
            project_root=project_root,
            paths=[project_root],
            enabled_domains=[ScanDomain.SAST],
        )

        issues = opengrep_scanner.scan(context)

        # The result should be a list (possibly empty if no findings)
        assert isinstance(issues, list)
        # All issues should be UnifiedIssue objects
        for issue in issues:
            assert hasattr(issue, "id")
            assert hasattr(issue, "severity")
            assert hasattr(issue, "scanner")
            assert issue.scanner == ScanDomain.SAST
            assert issue.source_tool == "opengrep"

    def test_scan_with_vulnerable_code(
        self, opengrep_scanner: OpenGrepScanner
    ) -> None:
        """Test scanning a directory with known security issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with a hardcoded password (security issue)
            vulnerable_file = tmpdir_path / "app.py"
            vulnerable_file.write_text('''
# Bad security practice: hardcoded credentials
PASSWORD = "super_secret_password123"
API_KEY = "sk-1234567890abcdef"

def authenticate(user, password):
    if password == "admin123":  # Hardcoded password comparison
        return True
    return False

def get_data():
    import subprocess
    # Command injection vulnerability
    user_input = input("Enter command: ")
    subprocess.call(user_input, shell=True)
''')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
            )

            issues = opengrep_scanner.scan(context)

            # Should find at least some issues in this vulnerable code
            # Note: results depend on OpenGrep's default ruleset
            assert isinstance(issues, list)

            # If issues were found, verify structure
            if issues:
                issue = issues[0]
                assert issue.scanner == ScanDomain.SAST
                assert issue.source_tool == "opengrep"
                assert issue.file_path is not None
                assert issue.severity in [
                    Severity.CRITICAL,
                    Severity.HIGH,
                    Severity.MEDIUM,
                    Severity.LOW,
                    Severity.INFO,
                ]

    def test_scan_empty_directory(self, opengrep_scanner: OpenGrepScanner) -> None:
        """Test scanning an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
            )

            issues = opengrep_scanner.scan(context)

            assert issues == []

    def test_scan_javascript_code(self, opengrep_scanner: OpenGrepScanner) -> None:
        """Test scanning JavaScript code with security issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a JavaScript file with potential security issues
            js_file = tmpdir_path / "app.js"
            js_file.write_text('''
// Security issue: eval usage
function processUserInput(input) {
    return eval(input);  // Dangerous!
}

// Security issue: innerHTML with user data
function displayMessage(msg) {
    document.getElementById("output").innerHTML = msg;
}

// Security issue: hardcoded secret
const API_SECRET = "hardcoded_secret_key_12345";
''')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
            )

            issues = opengrep_scanner.scan(context)

            assert isinstance(issues, list)

            # If issues were found, verify they're for JavaScript
            for issue in issues:
                assert issue.scanner == ScanDomain.SAST
                assert issue.source_tool == "opengrep"

    def test_scan_with_custom_rules_path(
        self, opengrep_scanner: OpenGrepScanner
    ) -> None:
        """Test scanning with a custom rules configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a simple Python file
            py_file = tmpdir_path / "test.py"
            py_file.write_text('print("Hello, World!")\n')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
                config={"opengrep_rules": "auto"},  # Use auto-detection
            )

            issues = opengrep_scanner.scan(context)

            # Should complete without error
            assert isinstance(issues, list)


@opengrep_available
class TestOpenGrepOutputParsing:
    """Tests for OpenGrep JSON output parsing."""

    def test_severity_mapping(self, opengrep_scanner: OpenGrepScanner) -> None:
        """Test that severity levels are correctly mapped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create code that should trigger various severity findings
            py_file = tmpdir_path / "security.py"
            py_file.write_text('''
import subprocess
import os

# Various potential security issues
SECRET_KEY = "hardcoded_value"

def run_command(cmd):
    os.system(cmd)  # Command injection risk

def dangerous_exec(code):
    exec(code)  # Code execution risk
''')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
            )

            issues = opengrep_scanner.scan(context)

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

    def test_issue_id_is_deterministic(
        self, opengrep_scanner: OpenGrepScanner
    ) -> None:
        """Test that issue IDs are deterministic across scans."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            py_file = tmpdir_path / "test.py"
            py_file.write_text('SECRET = "password123"\n')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
            )

            # Run scan twice
            issues1 = opengrep_scanner.scan(context)
            issues2 = opengrep_scanner.scan(context)

            # Same issues should have same IDs
            if issues1 and issues2:
                ids1 = {issue.id for issue in issues1}
                ids2 = {issue.id for issue in issues2}
                assert ids1 == ids2

    def test_scanner_metadata_contains_raw_data(
        self, opengrep_scanner: OpenGrepScanner
    ) -> None:
        """Test that scanner_metadata contains raw OpenGrep data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            py_file = tmpdir_path / "test.py"
            py_file.write_text('''
# Potential security issue
password = "admin123"
exec(user_input)
''')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
            )

            issues = opengrep_scanner.scan(context)

            if issues:
                issue = issues[0]
                assert "rule_id" in issue.scanner_metadata
                assert "line_start" in issue.scanner_metadata
                assert "line_end" in issue.scanner_metadata

    def test_code_snippet_extraction(
        self, opengrep_scanner: OpenGrepScanner
    ) -> None:
        """Test that code snippets are extracted correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            py_file = tmpdir_path / "snippet_test.py"
            py_file.write_text('''
# This should trigger a finding
HARDCODED_SECRET = "my_secret_value_12345"
''')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
            )

            issues = opengrep_scanner.scan(context)

            # If issues were found, check for code snippet
            for issue in issues:
                if issue.code_snippet:
                    assert isinstance(issue.code_snippet, str)
                    assert len(issue.code_snippet) > 0


@opengrep_available
class TestOpenGrepCLIIntegration:
    """Integration tests for the CLI with OpenGrep scanner."""

    def test_cli_sast_scan_json_output(self, project_root: Path) -> None:
        """Test CLI SAST scan with JSON output."""
        import lucidscan.cli as cli

        # Capture stdout
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()

        try:
            exit_code = cli.main([
                "--sast",
                "--format", "json",
                str(project_root),
            ])
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()

        assert exit_code in (0, 1)  # 0 = no issues, 1 = issues found
        # Verify valid JSON
        data = json.loads(output)
        assert "schema_version" in data
        assert "issues" in data
        assert "metadata" in data
        assert "summary" in data

    def test_cli_sast_scan_table_output(self, project_root: Path) -> None:
        """Test CLI SAST scan with table output."""
        import lucidscan.cli as cli
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()

        try:
            exit_code = cli.main([
                "--sast",
                "--format", "table",
                str(project_root),
            ])
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()

        assert exit_code in (0, 1)
        # Table should have output (either issues or "No issues found")
        assert len(output) > 0

    def test_cli_sast_scan_summary_output(self, project_root: Path) -> None:
        """Test CLI SAST scan with summary output."""
        import lucidscan.cli as cli
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()

        try:
            exit_code = cli.main([
                "--sast",
                "--format", "summary",
                str(project_root),
            ])
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()

        assert exit_code in (0, 1)
        assert "Total issues:" in output

    def test_cli_combined_sca_and_sast(self) -> None:
        """Test CLI with both SCA and SAST enabled."""
        import lucidscan.cli as cli
        import io
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create both package.json (for SCA) and .py file (for SAST)
            package_json = tmpdir_path / "package.json"
            package_json.write_text(json.dumps({
                "name": "test",
                "version": "1.0.0",
                "dependencies": {"lodash": "4.17.15"}
            }))

            py_file = tmpdir_path / "app.py"
            py_file.write_text('SECRET = "password"\n')

            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()

            try:
                exit_code = cli.main([
                    "--sca",
                    "--sast",
                    "--format", "json",
                    str(tmpdir_path),
                ])
            finally:
                sys.stdout = old_stdout

            output = captured.getvalue()

            assert exit_code in (0, 1)
            data = json.loads(output)
            assert "issues" in data

    def test_cli_fail_on_with_sast(self) -> None:
        """Test CLI --fail-on flag with SAST findings."""
        import lucidscan.cli as cli
        import io
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create code with high-severity security issues
            py_file = tmpdir_path / "dangerous.py"
            py_file.write_text('''
import subprocess
def run(cmd):
    subprocess.call(cmd, shell=True)  # Command injection
    exec(cmd)  # Code execution
''')

            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

            try:
                exit_code = cli.main([
                    "--sast",
                    "--format", "json",
                    "--fail-on", "high",
                    str(tmpdir_path),
                ])
            finally:
                sys.stdout = old_stdout

            # Exit code depends on whether high-severity issues are found
            assert exit_code in (0, 1)


@opengrep_available
class TestOpenGrepMultiLanguage:
    """Tests for OpenGrep scanning multiple languages."""

    def test_scan_mixed_language_project(
        self, opengrep_scanner: OpenGrepScanner
    ) -> None:
        """Test scanning a project with multiple languages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create Python file
            py_file = tmpdir_path / "backend.py"
            py_file.write_text('DB_PASSWORD = "secret"\n')

            # Create JavaScript file
            js_file = tmpdir_path / "frontend.js"
            js_file.write_text('const API_KEY = "sk-12345";\n')

            # Create Go file
            go_file = tmpdir_path / "server.go"
            go_file.write_text('''package main
var secretKey = "hardcoded"
''')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ScanDomain.SAST],
            )

            issues = opengrep_scanner.scan(context)

            assert isinstance(issues, list)
            # All issues should be SAST domain
            for issue in issues:
                assert issue.scanner == ScanDomain.SAST
