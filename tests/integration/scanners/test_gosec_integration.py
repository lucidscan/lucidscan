"""Integration tests for Gosec scanner plugin.

These tests require the gosec binary to be available (downloaded or on PATH)
and Go to be installed. They are skipped automatically if prerequisites are not met.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from lucidshark.core.models import ScanContext, ScanDomain, Severity
from lucidshark.plugins.scanners.gosec import GosecScanner

# Import markers from conftest
from tests.integration.conftest import go_available, gosec_available


# =============================================================================
# Binary download tests
# =============================================================================


@pytest.mark.integration
class TestGosecBinaryDownload:
    """Tests for gosec binary download and availability."""

    @gosec_available
    def test_ensure_binary_downloads_gosec(self, gosec_scanner: GosecScanner) -> None:
        """Ensure gosec binary can be downloaded or found."""
        binary = gosec_scanner.ensure_binary()
        assert binary.exists()
        assert binary.name == "gosec"

    @gosec_available
    def test_gosec_binary_is_executable(self, gosec_scanner: GosecScanner) -> None:
        """Verify the gosec binary has executable permissions."""
        binary = gosec_scanner.ensure_binary()
        assert binary.stat().st_mode & 0o111  # Has some executable bit


# =============================================================================
# SAST scanning tests
# =============================================================================


def _create_vulnerable_go_project(project_dir: Path) -> None:
    """Create a minimal Go project with known security issues."""
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "go.mod").write_text("module example.com/vuln\n\ngo 1.21\n")

    (project_dir / "main.go").write_text(
        textwrap.dedent("""\
        package main

        import (
        \t"crypto/md5"
        \t"database/sql"
        \t"fmt"
        \t"net/http"
        \t"os/exec"
        )

        func weakHash(data string) string {
        \th := md5.New()
        \th.Write([]byte(data))
        \treturn fmt.Sprintf("%x", h.Sum(nil))
        }

        func sqlInject(db *sql.DB, input string) {
        \tquery := "SELECT * FROM users WHERE name = '" + input + "'"
        \tdb.Query(query)
        }

        func cmdInject(input string) {
        \texec.Command("sh", "-c", input).Run()
        }

        func main() {
        \tfmt.Println(weakHash("test"))
        \thttp.ListenAndServe(":8080", nil)
        }
        """)
    )


def _create_clean_go_project(project_dir: Path) -> None:
    """Create a minimal Go project with no security issues."""
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "go.mod").write_text("module example.com/clean\n\ngo 1.21\n")

    (project_dir / "main.go").write_text(
        textwrap.dedent("""\
        package main

        import "fmt"

        func main() {
        \tfmt.Println("Hello, World!")
        }
        """)
    )


@pytest.mark.integration
class TestGosecSASTScanning:
    """Tests for gosec SAST scanning on real Go code."""

    @gosec_available
    @go_available
    def test_scan_vulnerable_go_code(self, tmp_path: Path) -> None:
        """Gosec should find security issues in vulnerable code."""
        project_dir = tmp_path / "vuln-project"
        _create_vulnerable_go_project(project_dir)

        scanner = GosecScanner(project_root=project_dir)
        context = ScanContext(
            project_root=project_dir,
            paths=[project_dir],
            enabled_domains=[ScanDomain.SAST],
        )

        issues = scanner.scan(context)
        assert len(issues) > 0

        rule_ids = {i.rule_id for i in issues}
        # Should find at least some of: G401 (weak crypto), G201/G202 (SQL),
        # G204 (command injection), G114 (net/http serve)
        known_rules = {"G401", "G201", "G202", "G204", "G114", "G501"}
        assert rule_ids & known_rules, f"Expected known rules, got: {rule_ids}"

    @gosec_available
    @go_available
    def test_scan_clean_go_code(self, tmp_path: Path) -> None:
        """Gosec should find few/no issues in clean code."""
        project_dir = tmp_path / "clean-project"
        _create_clean_go_project(project_dir)

        scanner = GosecScanner(project_root=project_dir)
        context = ScanContext(
            project_root=project_dir,
            paths=[project_dir],
            enabled_domains=[ScanDomain.SAST],
        )

        issues = scanner.scan(context)
        # Clean project should have zero or very few issues
        assert len(issues) <= 1

    @gosec_available
    def test_scan_non_go_project_skips(self, tmp_path: Path) -> None:
        """Gosec should skip when there's no go.mod."""
        # No go.mod  -  should skip
        (tmp_path / "app.py").write_text("print('hello')\n")

        scanner = GosecScanner(project_root=tmp_path)
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SAST],
        )

        issues = scanner.scan(context)
        assert issues == []

    @gosec_available
    @go_available
    def test_issue_structure(self, tmp_path: Path) -> None:
        """Verify issue structure has all required fields."""
        project_dir = tmp_path / "struct-project"
        _create_vulnerable_go_project(project_dir)

        scanner = GosecScanner(project_root=project_dir)
        context = ScanContext(
            project_root=project_dir,
            paths=[project_dir],
            enabled_domains=[ScanDomain.SAST],
        )

        issues = scanner.scan(context)
        assert len(issues) > 0

        issue = issues[0]
        assert issue.id.startswith("gosec-")
        assert issue.domain == ScanDomain.SAST
        assert issue.source_tool == "gosec"
        assert issue.severity in (Severity.HIGH, Severity.MEDIUM, Severity.LOW)
        assert issue.rule_id is not None
        assert issue.title is not None
        assert issue.description is not None
        assert issue.file_path is not None
        assert issue.line_start is not None and issue.line_start >= 0
        assert issue.metadata is not None
        assert "confidence" in issue.metadata

    @gosec_available
    @go_available
    def test_issue_id_is_deterministic(self, tmp_path: Path) -> None:
        """Running the same scan twice should produce same issue IDs."""
        project_dir = tmp_path / "deterministic-project"
        _create_vulnerable_go_project(project_dir)

        scanner = GosecScanner(project_root=project_dir)
        context = ScanContext(
            project_root=project_dir,
            paths=[project_dir],
            enabled_domains=[ScanDomain.SAST],
        )

        issues1 = scanner.scan(context)
        issues2 = scanner.scan(context)

        ids1 = {i.id for i in issues1}
        ids2 = {i.id for i in issues2}
        assert ids1 == ids2


# =============================================================================
# Severity and CWE mapping tests
# =============================================================================


@pytest.mark.integration
class TestGosecOutputParsing:
    """Tests for gosec output parsing with real scan results."""

    @gosec_available
    @go_available
    def test_severity_mapping(self, tmp_path: Path) -> None:
        """Verify severity mapping from gosec output to unified severity."""
        project_dir = tmp_path / "severity-project"
        _create_vulnerable_go_project(project_dir)

        scanner = GosecScanner(project_root=project_dir)
        context = ScanContext(
            project_root=project_dir,
            paths=[project_dir],
            enabled_domains=[ScanDomain.SAST],
        )

        issues = scanner.scan(context)
        assert len(issues) > 0

        for issue in issues:
            assert issue.severity in (
                Severity.HIGH,
                Severity.MEDIUM,
                Severity.LOW,
            )

    @gosec_available
    @go_available
    def test_cwe_references_present(self, tmp_path: Path) -> None:
        """Verify CWE references are included in issue metadata."""
        project_dir = tmp_path / "cwe-project"
        _create_vulnerable_go_project(project_dir)

        scanner = GosecScanner(project_root=project_dir)
        context = ScanContext(
            project_root=project_dir,
            paths=[project_dir],
            enabled_domains=[ScanDomain.SAST],
        )

        issues = scanner.scan(context)
        # At least some issues should have CWE references
        issues_with_cwe = [i for i in issues if "cwe" in i.metadata]
        assert len(issues_with_cwe) > 0

        for issue in issues_with_cwe:
            cwe = issue.metadata["cwe"]
            assert "id" in cwe
            assert cwe["id"]  # Non-empty CWE ID
