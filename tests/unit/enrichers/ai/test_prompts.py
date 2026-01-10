"""Unit tests for AI prompt templates."""

from pathlib import Path

import pytest

from lucidscan.core.models import ScanDomain, Severity, UnifiedIssue
from lucidscan.plugins.enrichers.ai.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    format_prompt,
    get_prompt_template,
    SCA_TEMPLATE,
    SAST_TEMPLATE,
    IAC_TEMPLATE,
    CONTAINER_TEMPLATE,
)


class TestGetPromptTemplate:
    """Tests for get_prompt_template function."""

    def test_sca_domain_returns_sca_template(self) -> None:
        """Test SCA domain returns correct template."""
        template = get_prompt_template(ScanDomain.SCA)
        assert template == SCA_TEMPLATE
        assert "Package:" in template
        assert "dependency vulnerability" in template.lower()

    def test_sast_domain_returns_sast_template(self) -> None:
        """Test SAST domain returns correct template."""
        template = get_prompt_template(ScanDomain.SAST)
        assert template == SAST_TEMPLATE
        assert "code security issue" in template.lower()
        assert "File:" in template

    def test_iac_domain_returns_iac_template(self) -> None:
        """Test IAC domain returns correct template."""
        template = get_prompt_template(ScanDomain.IAC)
        assert template == IAC_TEMPLATE
        assert "Infrastructure-as-Code" in template
        assert "Resource:" in template

    def test_container_domain_returns_container_template(self) -> None:
        """Test CONTAINER domain returns correct template."""
        template = get_prompt_template(ScanDomain.CONTAINER)
        assert template == CONTAINER_TEMPLATE
        assert "container vulnerability" in template.lower()
        assert "Image:" in template


class TestFormatPrompt:
    """Tests for format_prompt function."""

    @pytest.fixture
    def sca_issue(self) -> UnifiedIssue:
        """Create a sample SCA issue."""
        return UnifiedIssue(
            id="CVE-2024-1234",
            scanner=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.HIGH,
            title="SQL Injection in sqlparse",
            description="The sqlparse library is vulnerable to SQL injection.",
            dependency="sqlparse@0.4.0",
            recommendation="Upgrade to sqlparse >= 0.5.0",
        )

    @pytest.fixture
    def sast_issue(self) -> UnifiedIssue:
        """Create a sample SAST issue."""
        return UnifiedIssue(
            id="opengrep:PY001",
            scanner=ScanDomain.SAST,
            source_tool="opengrep",
            severity=Severity.CRITICAL,
            title="Hardcoded Password",
            description="Password is hardcoded in source code.",
            file_path=Path("src/auth.py"),
            line_start=42,
            line_end=42,
            code_snippet='password = "secret123"',
        )

    @pytest.fixture
    def iac_issue(self) -> UnifiedIssue:
        """Create a sample IAC issue."""
        return UnifiedIssue(
            id="CKV_AWS_1",
            scanner=ScanDomain.IAC,
            source_tool="checkov",
            severity=Severity.MEDIUM,
            title="S3 Bucket Without Encryption",
            description="S3 bucket does not have encryption enabled.",
            file_path=Path("terraform/main.tf"),
            iac_resource="aws_s3_bucket.data",
            code_snippet='resource "aws_s3_bucket" "data" {\n  bucket = "my-bucket"\n}',
        )

    def test_format_sca_prompt(self, sca_issue: UnifiedIssue) -> None:
        """Test formatting SCA issue prompt."""
        prompt = format_prompt(sca_issue)
        assert "sqlparse" in prompt
        assert "SQL Injection" in prompt
        assert "high" in prompt.lower()
        assert "0.5.0" in prompt  # Recommendation

    def test_format_sast_prompt_with_code(self, sast_issue: UnifiedIssue) -> None:
        """Test formatting SAST issue prompt with code snippet."""
        prompt = format_prompt(sast_issue, include_code=True)
        assert "Hardcoded Password" in prompt
        assert "src/auth.py" in prompt
        assert "42" in prompt  # Line number
        assert "secret123" in prompt  # Code snippet

    def test_format_sast_prompt_without_code(self, sast_issue: UnifiedIssue) -> None:
        """Test formatting SAST issue prompt without code snippet."""
        prompt = format_prompt(sast_issue, include_code=False)
        assert "Hardcoded Password" in prompt
        assert "secret123" not in prompt  # Code excluded

    def test_format_iac_prompt(self, iac_issue: UnifiedIssue) -> None:
        """Test formatting IAC issue prompt."""
        prompt = format_prompt(iac_issue)
        assert "S3 Bucket" in prompt
        assert "aws_s3_bucket.data" in prompt
        assert "terraform/main.tf" in prompt

    def test_format_handles_missing_fields(self) -> None:
        """Test formatting handles missing optional fields."""
        issue = UnifiedIssue(
            id="test-1",
            scanner=ScanDomain.SCA,
            source_tool="test",
            severity=Severity.LOW,
            title="Test Issue",
            description="Test description",
        )
        prompt = format_prompt(issue)
        assert "Test Issue" in prompt
        assert "N/A" in prompt  # Missing dependency


class TestPromptConstants:
    """Tests for prompt constants."""

    def test_prompt_version_is_set(self) -> None:
        """Test that PROMPT_VERSION is set."""
        assert PROMPT_VERSION
        assert isinstance(PROMPT_VERSION, str)

    def test_system_prompt_is_set(self) -> None:
        """Test that SYSTEM_PROMPT is set."""
        assert SYSTEM_PROMPT
        assert "security expert" in SYSTEM_PROMPT.lower()
        assert "concise" in SYSTEM_PROMPT.lower()
