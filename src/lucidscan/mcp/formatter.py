"""AI instruction formatter for MCP tools.

Transforms UnifiedIssue objects into rich, AI-friendly fix instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from lucidscan.core.models import ScanDomain, Severity, ToolDomain, UnifiedIssue


@dataclass
class FixInstruction:
    """Rich fix instruction for AI agents."""

    priority: int  # 1 (highest) to 5 (lowest)
    action: str  # FIX_SECURITY_VULNERABILITY, FIX_TYPE_ERROR, etc.
    summary: str  # One-line summary
    file: str
    line: int
    column: Optional[int] = None
    problem: str = ""  # Detailed problem description
    fix_steps: List[str] = field(default_factory=list)  # Ordered steps to fix
    suggested_fix: Optional[str] = None  # Suggested code replacement
    current_code: Optional[str] = None  # Current code snippet
    documentation_url: Optional[str] = None
    related_issues: List[str] = field(default_factory=list)  # Related issue IDs
    issue_id: str = ""  # Original issue ID for reference


class InstructionFormatter:
    """Transforms UnifiedIssue to AI-friendly instructions."""

    SEVERITY_PRIORITY = {
        Severity.CRITICAL: 1,
        Severity.HIGH: 2,
        Severity.MEDIUM: 3,
        Severity.LOW: 4,
        Severity.INFO: 5,
    }

    # Map both ScanDomain and ToolDomain to action prefixes
    DOMAIN_ACTION_PREFIX = {
        # ScanDomain values
        ScanDomain.SCA: "FIX_DEPENDENCY_",
        ScanDomain.SAST: "FIX_SECURITY_",
        ScanDomain.IAC: "FIX_INFRASTRUCTURE_",
        ScanDomain.CONTAINER: "FIX_CONTAINER_",
        # ToolDomain values
        ToolDomain.LINTING: "FIX_LINTING_",
        ToolDomain.TYPE_CHECKING: "FIX_TYPE_",
        ToolDomain.SECURITY: "FIX_SECURITY_",
        ToolDomain.TESTING: "FIX_TEST_",
        ToolDomain.COVERAGE: "IMPROVE_COVERAGE_",
    }

    def format_scan_result(self, issues: List[UnifiedIssue]) -> Dict[str, Any]:
        """Format scan result as AI instructions.

        Args:
            issues: List of unified issues from scan.

        Returns:
            Dictionary with structured AI instructions.
        """
        instructions = [self._issue_to_instruction(issue) for issue in issues]

        # Sort by priority
        instructions.sort(key=lambda x: x.priority)

        # Count by severity
        severity_counts: dict[str, int] = {}
        for issue in issues:
            sev_name = issue.severity.value if issue.severity else "unknown"
            severity_counts[sev_name] = severity_counts.get(sev_name, 0) + 1

        return {
            "total_issues": len(issues),
            "blocking": any(i.priority <= 2 for i in instructions),
            "summary": self._generate_summary(issues, severity_counts),
            "severity_counts": severity_counts,
            "instructions": [asdict(i) for i in instructions],
        }

    def format_single_issue(
        self,
        issue: UnifiedIssue,
        detailed: bool = False,
    ) -> Dict[str, Any]:
        """Format a single issue for AI consumption.

        Args:
            issue: The issue to format.
            detailed: Whether to include extra detail.

        Returns:
            Dictionary with issue details and fix instructions.
        """
        instruction = self._issue_to_instruction(issue, detailed=detailed)
        return asdict(instruction)

    def _issue_to_instruction(
        self,
        issue: UnifiedIssue,
        detailed: bool = False,
    ) -> FixInstruction:
        """Convert UnifiedIssue to FixInstruction.

        Args:
            issue: The unified issue.
            detailed: Whether to include extra detail.

        Returns:
            FixInstruction instance.
        """
        file_path = str(issue.file_path) if issue.file_path else ""

        return FixInstruction(
            priority=self.SEVERITY_PRIORITY.get(issue.severity, 3),
            action=self._generate_action(issue),
            summary=self._generate_summary_line(issue),
            file=file_path,
            line=issue.line_start or 0,
            column=None,
            problem=issue.description or "",
            fix_steps=self._generate_fix_steps(issue, detailed),
            suggested_fix=self._generate_suggested_fix(issue),
            current_code=issue.code_snippet,
            documentation_url=issue.scanner_metadata.get("documentation_url"),
            related_issues=[],
            issue_id=issue.id,
        )

    def _generate_action(self, issue: UnifiedIssue) -> str:
        """Generate action type from issue.

        Args:
            issue: The unified issue.

        Returns:
            Action string like FIX_SECURITY_VULNERABILITY.
        """
        prefix = self.DOMAIN_ACTION_PREFIX.get(issue.scanner, "FIX_")
        title_lower = issue.title.lower() if issue.title else ""
        scanner = issue.scanner

        # Specific action types based on issue characteristics
        # Handle both ScanDomain and ToolDomain
        if scanner in (ScanDomain.SAST, ToolDomain.SECURITY):
            if "hardcoded" in title_lower or "secret" in title_lower:
                return f"{prefix}HARDCODED_SECRET"
            elif "injection" in title_lower:
                return f"{prefix}INJECTION"
            elif "xss" in title_lower:
                return f"{prefix}XSS"
            return f"{prefix}VULNERABILITY"

        if scanner == ScanDomain.SCA:
            return f"{prefix}VULNERABILITY"

        if scanner == ScanDomain.IAC:
            if "exposed" in title_lower or "public" in title_lower:
                return f"{prefix}EXPOSURE"
            return f"{prefix}MISCONFIGURATION"

        if scanner == ScanDomain.CONTAINER:
            return f"{prefix}VULNERABILITY"

        if scanner == ToolDomain.LINTING:
            return f"{prefix}ERROR"

        if scanner == ToolDomain.TYPE_CHECKING:
            return f"{prefix}ERROR"

        if scanner == ToolDomain.TESTING:
            return f"{prefix}FAILURE"

        if scanner == ToolDomain.COVERAGE:
            return f"{prefix}GAP"

        return "FIX_ISSUE"

    def _generate_summary_line(self, issue: UnifiedIssue) -> str:
        """Generate one-line summary for issue.

        Args:
            issue: The unified issue.

        Returns:
            Summary string.
        """
        file_part = ""
        if issue.file_path:
            file_name = issue.file_path.name if hasattr(issue.file_path, "name") else str(issue.file_path).split("/")[-1]
            if issue.line_start:
                file_part = f" in {file_name}:{issue.line_start}"
            else:
                file_part = f" in {file_name}"

        return f"{issue.title}{file_part}"

    def _generate_summary(
        self,
        issues: List[UnifiedIssue],
        severity_counts: Dict[str, int],
    ) -> str:
        """Generate overall summary string.

        Args:
            issues: List of issues.
            severity_counts: Count by severity.

        Returns:
            Summary string.
        """
        if not issues:
            return "No issues found"

        parts = []
        for sev in ["critical", "high", "medium", "low", "info"]:
            count = severity_counts.get(sev, 0)
            if count > 0:
                parts.append(f"{count} {sev}")

        return f"{len(issues)} issues found: {', '.join(parts)}"

    def _generate_fix_steps(
        self,
        issue: UnifiedIssue,
        detailed: bool = False,
    ) -> List[str]:
        """Generate fix steps from issue context.

        Args:
            issue: The unified issue.
            detailed: Whether to include extra detail.

        Returns:
            List of fix steps.
        """
        steps = []

        # Use recommendation if available
        if issue.recommendation:
            steps.append(issue.recommendation)

        # Add AI explanation if enriched
        ai_explanation = issue.scanner_metadata.get("ai_explanation")
        if ai_explanation:
            steps.extend(self._parse_ai_explanation(ai_explanation))

        # Generate generic steps based on domain if no specific steps
        if not steps:
            steps = self._generate_generic_steps(issue)

        return steps

    def _parse_ai_explanation(self, explanation: str) -> List[str]:
        """Parse AI explanation into steps.

        Args:
            explanation: AI-generated explanation text.

        Returns:
            List of steps extracted from explanation.
        """
        if not explanation:
            return []

        # Split on numbered items or bullet points
        lines = explanation.strip().split("\n")
        steps = []

        for line in lines:
            line = line.strip()
            # Skip empty lines
            if not line:
                continue
            # Remove leading numbers/bullets
            if line[0].isdigit() and "." in line[:3]:
                line = line.split(".", 1)[1].strip()
            elif line.startswith("-") or line.startswith("*"):
                line = line[1:].strip()

            if line and len(line) > 5:
                steps.append(line)

        return steps[:5]  # Limit to 5 steps

    def _generate_generic_steps(self, issue: UnifiedIssue) -> List[str]:
        """Generate generic fix steps based on domain.

        Args:
            issue: The unified issue.

        Returns:
            List of generic fix steps.
        """
        file_ref = f"{issue.file_path}:{issue.line_start}" if issue.file_path and issue.line_start else str(issue.file_path or "the file")
        scanner = issue.scanner

        # Handle both ScanDomain and ToolDomain
        if scanner in (ScanDomain.SAST, ToolDomain.SECURITY):
            return [
                f"Review the security issue at {file_ref}",
                "Apply the recommended fix from the scanner",
                "Verify the fix doesn't break functionality",
                "Consider adding tests to prevent regression",
            ]

        if scanner == ScanDomain.SCA:
            return [
                f"Update the vulnerable dependency mentioned in {issue.title}",
                "Run tests to ensure compatibility with new version",
                "Check for breaking changes in the changelog",
            ]

        if scanner == ScanDomain.IAC:
            return [
                f"Review the infrastructure issue at {file_ref}",
                "Apply security best practices for the resource",
                "Test the changes in a non-production environment",
            ]

        if scanner == ScanDomain.CONTAINER:
            return [
                f"Review the container vulnerability at {file_ref}",
                "Update the base image or vulnerable packages",
                "Rebuild and test the container",
            ]

        if scanner == ToolDomain.LINTING:
            return [
                f"Fix the linting issue at {file_ref}",
                "Consider running 'lucidscan scan --lint --fix' for auto-fix",
            ]

        if scanner == ToolDomain.TYPE_CHECKING:
            return [
                f"Fix the type error at {file_ref}",
                "Ensure type annotations are correct and complete",
                "Check for None values that need handling",
            ]

        if scanner == ToolDomain.TESTING:
            return [
                f"Review the failing test at {file_ref}",
                "Determine if the test or the code needs to be fixed",
                "Run the test in isolation to verify the fix",
            ]

        if scanner == ToolDomain.COVERAGE:
            return [
                f"Add tests to cover the uncovered code at {file_ref}",
                "Focus on critical paths and edge cases",
                "Verify coverage threshold is met after adding tests",
            ]

        return [f"Address the issue at {file_ref}"]

    def _generate_suggested_fix(self, issue: UnifiedIssue) -> Optional[str]:
        """Generate suggested fix code if available.

        Args:
            issue: The unified issue.

        Returns:
            Suggested fix code or None.
        """
        # Check scanner metadata for suggested fix
        suggested = issue.scanner_metadata.get("suggested_fix")
        if suggested:
            return suggested

        # For linting issues, the fix might be auto-applicable
        if issue.scanner == ToolDomain.LINTING:
            auto_fix = issue.scanner_metadata.get("auto_fix")
            if auto_fix:
                return auto_fix

        return None
