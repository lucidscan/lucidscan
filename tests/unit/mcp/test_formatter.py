"""Unit tests for MCP instruction formatter."""

from __future__ import annotations

from pathlib import Path

import pytest

from lucidscan.core.models import ScanDomain, Severity, ToolDomain, UnifiedIssue
from lucidscan.mcp.formatter import FixInstruction, InstructionFormatter


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
                scanner=ScanDomain.SAST,
                source_tool="opengrep",
                severity=Severity.HIGH,
                title="SQL Injection vulnerability",
                description="User input is directly used in SQL query",
                file_path=Path("src/db.py"),
                line_start=42,
            ),
            UnifiedIssue(
                id="issue-2",
                scanner=ToolDomain.LINTING,
                source_tool="ruff",
                severity=Severity.LOW,
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
        assert formatter.SEVERITY_PRIORITY[Severity.CRITICAL] == 1
        assert formatter.SEVERITY_PRIORITY[Severity.HIGH] == 2
        assert formatter.SEVERITY_PRIORITY[Severity.MEDIUM] == 3
        assert formatter.SEVERITY_PRIORITY[Severity.LOW] == 4
        assert formatter.SEVERITY_PRIORITY[Severity.INFO] == 5

    def test_generate_action_for_security_issues(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test action generation for security issues."""
        # SQL injection
        issue = UnifiedIssue(
            id="test-1",
            scanner=ScanDomain.SAST,
            source_tool="test",
            severity=Severity.HIGH,
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
            scanner=ToolDomain.LINTING,
            source_tool="ruff",
            severity=Severity.LOW,
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
            scanner=ToolDomain.TYPE_CHECKING,
            source_tool="mypy",
            severity=Severity.MEDIUM,
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
            scanner=ToolDomain.TESTING,
            source_tool="pytest",
            severity=Severity.HIGH,
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
            scanner=ToolDomain.COVERAGE,
            source_tool="coverage.py",
            severity=Severity.LOW,
            title="Uncovered lines",
            description="Test",
        )
        action = formatter._generate_action(issue)
        assert action == "IMPROVE_COVERAGE_GAP"

    def test_format_single_issue(self, formatter: InstructionFormatter) -> None:
        """Test formatting a single issue."""
        issue = UnifiedIssue(
            id="test-1",
            scanner=ScanDomain.SAST,
            source_tool="opengrep",
            severity=Severity.CRITICAL,
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
        assert result["file"] == "src/handler.py"
        assert result["line"] == 100
        assert len(result["fix_steps"]) > 0

    def test_generate_generic_steps_for_each_domain(
        self, formatter: InstructionFormatter
    ) -> None:
        """Test generic step generation for each domain."""
        domains_and_expected = [
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
                scanner=domain,
                source_tool="test",
                severity=Severity.MEDIUM,
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
                scanner=ScanDomain.SAST,
                source_tool="test",
                severity=sev,
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
