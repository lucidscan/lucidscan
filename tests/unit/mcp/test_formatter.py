"""Unit tests for MCP instruction formatter."""

from __future__ import annotations

from pathlib import Path

import pytest

from lucidshark.core.models import ScanDomain, Severity, ToolDomain, UnifiedIssue
from lucidshark.mcp.formatter import (
    FixInstruction,
    InstructionFormatter,
    SEVERITY_PRIORITY,
)


class TestFixInstruction:
    """Tests for FixInstruction dataclass."""

    def test_fix_instruction_creation(self) -> None:
        """Test creating a FixInstruction with required fields."""
        instruction = FixInstruction(
            priority=1,
            action="FIX_SECURITY_VULNERABILITY",
            summary="SQL injection in auth.py:23",
            file="src/auth.py",
            line=23,
        )

        assert instruction.priority == 1
        assert instruction.action == "FIX_SECURITY_VULNERABILITY"
        assert instruction.summary == "SQL injection in auth.py:23"
        assert instruction.file == "src/auth.py"
        assert instruction.line == 23
        assert instruction.column is None
        assert instruction.fix_steps == []

    def test_fix_instruction_with_optional_fields(self) -> None:
        """Test creating a FixInstruction with optional fields."""
        instruction = FixInstruction(
            priority=2,
            action="FIX_TYPE_ERROR",
            summary="Type error in utils.py:45",
            file="src/utils.py",
            line=45,
            column=10,
            problem="Argument of type 'str' cannot be assigned to 'int'",
            fix_steps=["Change argument type to int", "Add type cast"],
            suggested_fix="int(value)",
            current_code="value",
            documentation_url="https://example.com/docs",
        )

        assert instruction.column == 10
        assert instruction.problem == "Argument of type 'str' cannot be assigned to 'int'"
        assert len(instruction.fix_steps) == 2
        assert instruction.suggested_fix == "int(value)"


class TestInstructionFormatter:
    """Tests for InstructionFormatter."""

    @pytest.fixture
    def formatter(self) -> InstructionFormatter:
        """Create a formatter instance."""
        return InstructionFormatter()

    def test_format_empty_scan_result(self, formatter: InstructionFormatter) -> None:
        """Test formatting empty scan results."""
        result = formatter.format_scan_result([])

        assert result["total_issues"] == 0
        assert result["blocking"] is False
        assert result["summary"] == "No issues found"
        assert result["instructions"] == []

    def test_format_scan_result_with_issues(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test formatting scan results with issues."""
        issues = [
            UnifiedIssue(
                id="issue-1",
                domain=ScanDomain.SAST,
                source_tool="opengrep",
                severity=Severity.HIGH,
                rule_id="python.security.sql-injection",
                title="SQL Injection vulnerability",
                description="User input is directly used in SQL query",
                file_path=Path("src/db.py"),
                line_start=42,
            ),
            UnifiedIssue(
                id="issue-2",
                domain=ToolDomain.LINTING,
                source_tool="ruff",
                severity=Severity.LOW,
                rule_id="F401",
                title="Unused import",
                description="'os' imported but unused",
                file_path=Path("src/utils.py"),
                line_start=5,
            ),
        ]

        result = formatter.format_scan_result(issues)

        assert result["total_issues"] == 2
        assert result["blocking"] is True  # HIGH severity = priority 2
        assert len(result["instructions"]) == 2

        # Check instructions are sorted by priority
        assert result["instructions"][0]["priority"] <= result["instructions"][1]["priority"]

    def test_severity_to_priority_mapping(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test severity to priority mapping."""
        assert SEVERITY_PRIORITY[Severity.CRITICAL] == 1
        assert SEVERITY_PRIORITY[Severity.HIGH] == 2
        assert SEVERITY_PRIORITY[Severity.MEDIUM] == 3
        assert SEVERITY_PRIORITY[Severity.LOW] == 4
        assert SEVERITY_PRIORITY[Severity.INFO] == 5

    def test_generate_action_for_security_issues(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for security issues."""
        # SQL injection
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.SAST,
            source_tool="test",
            severity=Severity.HIGH,
            rule_id="sql-injection",
            title="SQL Injection detected",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_SECURITY_INJECTION"

        # Hardcoded secret
        issue.title = "Hardcoded password found"
        action = formatter._generate_action(issue)
        assert action == "FIX_SECURITY_HARDCODED_SECRET"

        # XSS
        issue.title = "XSS vulnerability"
        action = formatter._generate_action(issue)
        assert action == "FIX_SECURITY_XSS"

    def test_generate_action_for_linting_issues(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for linting issues."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ToolDomain.LINTING,
            source_tool="ruff",
            severity=Severity.LOW,
            rule_id="E501",
            title="Line too long",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_LINTING_ERROR"

    def test_generate_action_for_type_checking_issues(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for type checking issues."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ToolDomain.TYPE_CHECKING,
            source_tool="mypy",
            severity=Severity.MEDIUM,
            rule_id="arg-type",
            title="Type mismatch",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_TYPE_ERROR"

    def test_generate_action_for_test_failures(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for test failures."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ToolDomain.TESTING,
            source_tool="pytest",
            severity=Severity.HIGH,
            rule_id="failed",
            title="test_auth_login failed",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_TEST_FAILURE"

    def test_generate_action_for_coverage_gaps(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for coverage gaps."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ToolDomain.COVERAGE,
            source_tool="coverage.py",
            severity=Severity.LOW,
            rule_id="coverage_below_threshold",
            title="Uncovered lines",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "IMPROVE_COVERAGE_GAP"

    def test_format_single_issue(self, formatter: InstructionFormatter) -> None:
        """Test formatting a single issue."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.SAST,
            source_tool="opengrep",
            severity=Severity.CRITICAL,
            rule_id="python.lang.security.audit.eval.eval",
            title="Remote Code Execution",
            description="Unsafe eval() usage allows arbitrary code execution",
            file_path=Path("src/handler.py"),
            line_start=100,
            recommendation="Use ast.literal_eval() instead of eval()",
        )

        result = formatter.format_single_issue(issue)

        assert result["priority"] == 1
        assert result["action"] == "FIX_SECURITY_VULNERABILITY"
        assert "handler.py" in result["summary"]
        # Use Path for cross-platform comparison
        assert Path(result["file"]) == Path("src/handler.py")
        assert result["line"] == 100
        assert len(result["fix_steps"]) > 0

    def test_generate_generic_steps_for_each_domain(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test generic step generation for each domain."""
        domains_and_expected: list[tuple[ScanDomain | ToolDomain, str]] = [
            (ScanDomain.SAST, "security"),
            (ScanDomain.SCA, "vulnerable dependency"),
            (ScanDomain.IAC, "infrastructure"),
            (ScanDomain.CONTAINER, "container"),
            (ToolDomain.LINTING, "linting"),
            (ToolDomain.TYPE_CHECKING, "type"),
            (ToolDomain.TESTING, "test"),
            (ToolDomain.COVERAGE, "tests to cover"),
        ]

        for domain, expected_keyword in domains_and_expected:
            issue = UnifiedIssue(
                id="test",
                domain=domain,
                source_tool="test",
                severity=Severity.MEDIUM,
                rule_id="test-rule",
                title="Test issue",
                description="Test",
                file_path=Path("test.py"),
                line_start=1,
            )
            steps = formatter._generate_generic_steps(issue)
            assert len(steps) > 0
            # At least one step should contain domain-relevant text
            combined = " ".join(steps).lower()
            assert expected_keyword in combined or "test.py" in combined

    def test_parse_ai_explanation(self, formatter: InstructionFormatter) -> None:
        """Test parsing AI explanation into steps."""
        explanation = """
1. First, import the os module
2. Replace hardcoded value with environment variable
3. Test the change
        """
        steps = formatter._parse_ai_explanation(explanation)
        assert len(steps) == 3
        assert "import" in steps[0].lower()

    def test_parse_ai_explanation_with_bullets(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test parsing AI explanation with bullet points."""
        explanation = """
- Update the package version
- Run npm install
- Verify the fix
        """
        steps = formatter._parse_ai_explanation(explanation)
        assert len(steps) == 3
        assert "package" in steps[0].lower()

    def test_generate_summary_with_counts(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test summary generation with severity counts."""
        issues = [
            UnifiedIssue(
                id=f"issue-{i}",
                domain=ScanDomain.SAST,
                source_tool="test",
                severity=sev,
                rule_id=f"test-rule-{i}",
                title="Test",
                description="Test",
            )
            for i, sev in enumerate([
                Severity.CRITICAL,
                Severity.HIGH,
                Severity.HIGH,
                Severity.MEDIUM,
            ])
        ]

        result = formatter.format_scan_result(issues)
        summary = result["summary"]

        assert "4 issues found" in summary
        assert "1 critical" in summary
        assert "2 high" in summary
        assert "1 medium" in summary

    def test_generate_action_for_sca_issues(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for SCA issues."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.HIGH,
            rule_id="CVE-2021-1234",
            title="Vulnerable dependency",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_DEPENDENCY_VULNERABILITY"

    def test_generate_action_for_iac_exposed(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for IAC with exposed resource."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.IAC,
            source_tool="checkov",
            severity=Severity.HIGH,
            rule_id="CKV_AWS_20",
            title="S3 bucket is exposed to public",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_INFRASTRUCTURE_EXPOSURE"

    def test_generate_action_for_iac_public(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for IAC with public resource."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.IAC,
            source_tool="checkov",
            severity=Severity.MEDIUM,
            rule_id="CKV_AWS_88",
            title="EC2 instance has public IP",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_INFRASTRUCTURE_EXPOSURE"

    def test_generate_action_for_iac_misconfiguration(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for IAC misconfiguration."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.IAC,
            source_tool="checkov",
            severity=Severity.LOW,
            rule_id="CKV_AWS_19",
            title="Missing encryption at rest",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_INFRASTRUCTURE_MISCONFIGURATION"

    def test_generate_action_for_container_issues(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for container issues."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.CONTAINER,
            source_tool="trivy",
            severity=Severity.HIGH,
            rule_id="CVE-2021-5678",
            title="Vulnerable base image",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "FIX_CONTAINER_VULNERABILITY"

    def test_generate_action_for_unknown_scanner(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for unknown scanner returns default."""
        # Create issue with non-standard domain value using MagicMock
        from unittest.mock import MagicMock
        issue = MagicMock()
        issue.domain = "unknown_domain"
        issue.title = "Some issue"
        action = formatter._generate_action(issue)
        assert action == "FIX_ISSUE"

    def test_summary_line_with_file_no_line(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test summary line generation with file but no line number."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.SAST,
            source_tool="test",
            severity=Severity.HIGH,
            rule_id="test-rule",
            title="Security issue",
            description="Test",
            file_path=Path("src/module.py"),
            line_start=None,
        )
        summary = formatter._generate_summary_line(issue)
        assert "Security issue" in summary
        assert "module.py" in summary
        assert ":" not in summary.split("module.py")[1]  # No line number after file

    def test_summary_line_with_no_file(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test summary line generation with no file."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.SAST,
            source_tool="test",
            severity=Severity.HIGH,
            rule_id="test-rule",
            title="Security issue",
            description="Test",
        )
        summary = formatter._generate_summary_line(issue)
        assert summary == "Security issue"

    def test_format_detailed_issue(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test formatting issue with detailed mode."""
        issue = UnifiedIssue(
            id="test-1",
            domain=ScanDomain.SAST,
            source_tool="opengrep",
            severity=Severity.CRITICAL,
            rule_id="python.lang.security.audit.subprocess-shell-true",
            title="Command Injection",
            description="User input used in shell command",
            file_path=Path("src/handler.py"),
            line_start=100,
            recommendation="Use subprocess with shell=False",
            code_snippet="os.system(user_input)",
        )

        result = formatter.format_single_issue(issue, detailed=True)

        assert "issue_id" in result
        assert result["issue_id"] == "test-1"
        assert "current_code" in result

    def test_format_scan_result_excludes_ignored_from_totals(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test that ignored issues are excluded from total_issues, blocking, and summary."""
        active_issue = UnifiedIssue(
            id="active-1",
            domain=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.MEDIUM,
            rule_id="CVE-2024-1234",
            title="Medium vulnerability",
            description="Test active issue",
        )
        ignored_issue = UnifiedIssue(
            id="ignored-1",
            domain=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.HIGH,
            rule_id="GHSA-xxxx-yyyy",
            title="Ignored vulnerability",
            description="Test ignored issue",
            ignored=True,
            ignore_reason="Accepted risk",
        )

        result = formatter.format_scan_result([active_issue, ignored_issue])

        # Only active issue counts in totals
        assert result["total_issues"] == 1
        assert result["ignored_issues"] == 1
        # HIGH severity ignored issue should NOT make it blocking
        assert result["blocking"] is False
        # Summary should only mention the 1 active issue
        assert "1 issues found" in result["summary"]
        # Ignored issue should still appear in issues_by_domain with tag
        sca_issues = result["issues_by_domain"].get("sca", [])
        assert len(sca_issues) == 2
        ignored_in_list = [i for i in sca_issues if i.get("ignored")]
        assert len(ignored_in_list) == 1
        assert ignored_in_list[0]["ignore_reason"] == "Accepted risk"

    def test_format_scan_result_domain_status_excludes_ignored(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test that domain status pass/fail excludes ignored issues."""
        ignored_issue = UnifiedIssue(
            id="ignored-1",
            domain=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.HIGH,
            rule_id="CVE-2024-9999",
            title="Ignored high severity",
            description="Should not cause fail",
            ignored=True,
        )

        result = formatter.format_scan_result(
            [ignored_issue],
            checked_domains=["sca"],
        )

        # Domain should pass because the only issue is ignored
        assert result["domain_status"]["sca"]["status"] == "pass"
        assert result["domain_status"]["sca"]["issue_count"] == 0
