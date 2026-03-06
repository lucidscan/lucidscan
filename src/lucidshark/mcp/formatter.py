"""AI instruction formatter for MCP tools.

Transforms UnifiedIssue objects into rich, AI-friendly fix instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from lucidshark.core.models import ScanDomain, Severity, ToolDomain, UnifiedIssue
from lucidshark.plugins.duplication.base import DuplicationResult


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


# Shared constants for AI formatting - used by both MCP formatter and AI reporter
SEVERITY_PRIORITY: Dict[Severity, int] = {
    Severity.CRITICAL: 1,
    Severity.HIGH: 2,
    Severity.MEDIUM: 3,
    Severity.LOW: 4,
    Severity.INFO: 5,
}

# Map both ScanDomain and ToolDomain to action prefixes
DOMAIN_ACTION_PREFIX: Dict[ScanDomain | ToolDomain, str] = {
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


class InstructionFormatter:
    """Transforms UnifiedIssue to AI-friendly instructions."""

    def format_scan_result(
        self,
        issues: List[UnifiedIssue],
        checked_domains: Optional[List[str]] = None,
        duplication_result: Optional[DuplicationResult] = None,
    ) -> Dict[str, Any]:
        """Format scan result as AI instructions.

        Args:
            issues: List of unified issues from scan.
            checked_domains: List of domain names that were checked.
            duplication_result: Optional duplication detection result for percentage display.

        Returns:
            Dictionary with structured AI instructions including:
            - total_issues: Count of all issues
            - blocking: Whether there are high-priority issues
            - summary: Human-readable summary
            - severity_counts: Issues by severity level
            - domain_status: Pass/fail status for each checked domain
            - issues_by_domain: Issues grouped by domain
            - instructions: Sorted list of fix instructions
            - recommended_action: Suggested next step
        """
        # Separate active vs ignored issues
        active_issues = [i for i in issues if not i.ignored]

        instructions = [self._issue_to_instruction(issue) for issue in active_issues]

        # Sort by priority
        instructions.sort(key=lambda x: x.priority)

        # Count by severity (active issues only)
        severity_counts: dict[str, int] = {}
        for issue in active_issues:
            sev_name = issue.severity.value if issue.severity else "unknown"
            severity_counts[sev_name] = severity_counts.get(sev_name, 0) + 1

        # Group active issues by domain (ignored issues go in a separate structure)
        issues_by_domain: Dict[str, List[Dict[str, Any]]] = {}
        ignored_issues_by_domain: Dict[str, List[Dict[str, Any]]] = {}
        for issue in issues:
            domain_name = issue.domain.value if issue.domain else "unknown"
            if issue.ignored:
                if domain_name not in ignored_issues_by_domain:
                    ignored_issues_by_domain[domain_name] = []
                ignored_issues_by_domain[domain_name].append(
                    self._issue_to_brief(issue)
                )
            else:
                if domain_name not in issues_by_domain:
                    issues_by_domain[domain_name] = []
                issues_by_domain[domain_name].append(
                    self._issue_to_brief(issue)
                )

        # Build domain status (pass/fail for each checked domain)
        # Only active (non-ignored) issues count toward pass/fail
        domain_status: Dict[str, Dict[str, Any]] = {}
        if checked_domains:
            for domain in checked_domains:
                # Special handling for duplication domain - show percentage
                if domain == "duplication" and duplication_result is not None:
                    pct = duplication_result.duplication_percent
                    threshold = duplication_result.threshold
                    passed = duplication_result.passed
                    status = "pass" if passed else "fail"
                    status_display = f"{pct:.1f}% duplication (threshold: {threshold:.0f}%)"
                    domain_status[domain] = {
                        "status": status,
                        "display": status_display,
                        "duplication_percent": round(pct, 2),
                        "threshold": threshold,
                    }
                    continue

                # issues_by_domain now only contains active (non-ignored) issues
                domain_issues = issues_by_domain.get(domain, [])
                issue_count = len(domain_issues)
                fixable_count = sum(1 for i in domain_issues if i.get("fixable", False))

                if issue_count == 0:
                    status = "pass"
                    status_display = "Pass"
                else:
                    status = "fail"
                    if fixable_count > 0:
                        status_display = f"{issue_count} issues ({fixable_count} auto-fixable)"
                    else:
                        status_display = f"{issue_count} issues"

                domain_status[domain] = {
                    "status": status,
                    "display": status_display,
                    "issue_count": issue_count,
                    "fixable_count": fixable_count,
                }

        # Generate recommended action
        recommended_action = self._generate_recommended_action(
            active_issues, severity_counts, domain_status
        )

        # Count ignored issues for informational purposes
        ignored_count = sum(1 for i in issues if i.ignored)

        result = {
            "total_issues": len(active_issues),
            "ignored_issues": ignored_count,
            "blocking": any(i.priority <= 2 for i in instructions),
            "summary": self._generate_summary(active_issues, severity_counts),
            "severity_counts": severity_counts,
            "domain_status": domain_status,
            "issues_by_domain": issues_by_domain,
            "instructions": [asdict(i) for i in instructions],
            "recommended_action": recommended_action,
        }
        # Only include ignored_issues_by_domain if there are ignored issues
        if ignored_issues_by_domain:
            result["ignored_issues_by_domain"] = ignored_issues_by_domain
        return result

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
            priority=SEVERITY_PRIORITY.get(issue.severity, 3),
            action=self._generate_action(issue),
            summary=self._generate_summary_line(issue),
            file=file_path,
            line=issue.line_start or 0,
            column=issue.column_start,
            problem=issue.description or "",
            fix_steps=self._generate_fix_steps(issue, detailed),
            suggested_fix=self._generate_suggested_fix(issue),
            current_code=issue.code_snippet,
            documentation_url=issue.documentation_url,
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
        prefix = DOMAIN_ACTION_PREFIX.get(issue.domain, "FIX_")
        title_lower = issue.title.lower() if issue.title else ""
        domain = issue.domain

        # Specific action types based on issue characteristics
        # Handle both ScanDomain and ToolDomain
        if domain in (ScanDomain.SAST, ToolDomain.SECURITY):
            if "hardcoded" in title_lower or "secret" in title_lower:
                return f"{prefix}HARDCODED_SECRET"
            elif "injection" in title_lower:
                return f"{prefix}INJECTION"
            elif "xss" in title_lower:
                return f"{prefix}XSS"
            return f"{prefix}VULNERABILITY"

        if domain == ScanDomain.SCA:
            return f"{prefix}VULNERABILITY"

        if domain == ScanDomain.IAC:
            if "exposed" in title_lower or "public" in title_lower:
                return f"{prefix}EXPOSURE"
            return f"{prefix}MISCONFIGURATION"

        if domain == ScanDomain.CONTAINER:
            return f"{prefix}VULNERABILITY"

        if domain == ToolDomain.LINTING:
            return f"{prefix}ERROR"

        if domain == ToolDomain.TYPE_CHECKING:
            return f"{prefix}ERROR"

        if domain == ToolDomain.TESTING:
            return f"{prefix}FAILURE"

        if domain == ToolDomain.COVERAGE:
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
            issues: List of active (non-ignored) issues.
            severity_counts: Count by severity (active issues only).

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
        ai_explanation = issue.metadata.get("ai_explanation")
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
        domain = issue.domain

        # Handle both ScanDomain and ToolDomain
        if domain in (ScanDomain.SAST, ToolDomain.SECURITY):
            return [
                f"Review the security issue at {file_ref}",
                "Apply the recommended fix from the scanner",
                "Verify the fix doesn't break functionality",
                "Consider adding tests to prevent regression",
            ]

        if domain == ScanDomain.SCA:
            return [
                f"Update the vulnerable dependency mentioned in {issue.title}",
                "Run tests to ensure compatibility with new version",
                "Check for breaking changes in the changelog",
            ]

        if domain == ScanDomain.IAC:
            return [
                f"Review the infrastructure issue at {file_ref}",
                "Apply security best practices for the resource",
                "Test the changes in a non-production environment",
            ]

        if domain == ScanDomain.CONTAINER:
            return [
                f"Review the container vulnerability at {file_ref}",
                "Update the base image or vulnerable packages",
                "Rebuild and test the container",
            ]

        if domain == ToolDomain.LINTING:
            return [
                f"Fix the linting issue at {file_ref}",
                "Consider running 'lucidshark scan --linting --fix' for auto-fix",
            ]

        if domain == ToolDomain.TYPE_CHECKING:
            return [
                f"Fix the type error at {file_ref}",
                "Ensure type annotations are correct and complete",
                "Check for None values that need handling",
            ]

        if domain == ToolDomain.TESTING:
            return [
                f"Review the failing test at {file_ref}",
                "Determine if the test or the code needs to be fixed",
                "Run the test in isolation to verify the fix",
            ]

        if domain == ToolDomain.COVERAGE:
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
        # Use the issue's suggested_fix field directly
        if issue.suggested_fix:
            return issue.suggested_fix

        # For linting issues, check metadata for auto_fix
        if issue.domain == ToolDomain.LINTING:
            auto_fix = issue.metadata.get("auto_fix")
            if auto_fix:
                return auto_fix

        return None

    def _issue_to_brief(self, issue: UnifiedIssue) -> Dict[str, Any]:
        """Convert issue to brief format for domain grouping.

        Args:
            issue: The unified issue.

        Returns:
            Brief issue dictionary.
        """
        file_path = str(issue.file_path) if issue.file_path else ""
        location = file_path
        if issue.line_start:
            location = f"{file_path}:{issue.line_start}"

        brief: Dict[str, Any] = {
            "id": issue.id,
            "location": location,
            "severity": issue.severity.value if issue.severity else "unknown",
            "title": issue.title or "",
            "fixable": issue.fixable,
        }
        if issue.ignored:
            brief["ignored"] = True
            if issue.ignore_reason:
                brief["ignore_reason"] = issue.ignore_reason
        return brief

    def _generate_recommended_action(
        self,
        issues: List[UnifiedIssue],
        severity_counts: Dict[str, int],
        domain_status: Dict[str, Dict[str, Any]],
    ) -> str:
        """Generate recommended next action based on scan results.

        Args:
            issues: List of issues found.
            severity_counts: Count of issues by severity.
            domain_status: Status of each checked domain.

        Returns:
            Recommended action string.
        """
        if not issues:
            return "All checks passed. Ready to proceed."

        # Count fixable issues
        fixable_count = sum(1 for i in issues if i.fixable)
        linting_fixable = sum(
            1 for i in issues if i.domain == ToolDomain.LINTING and i.fixable
        )

        # Check for critical/high severity issues
        critical_count = severity_counts.get("critical", 0)
        high_count = severity_counts.get("high", 0)

        if critical_count > 0:
            return f"Fix {critical_count} critical issue(s) immediately before proceeding."

        if high_count > 0:
            return f"Address {high_count} high-severity issue(s) before committing."

        if linting_fixable > 0:
            return f"Run `scan(fix=true)` to auto-fix {linting_fixable} linting issue(s), then address remaining issues manually."

        if fixable_count > 0:
            return f"Run `scan(fix=true)` to auto-fix {fixable_count} issue(s)."

        # Type errors or other issues
        type_issues = sum(
            1 for i in issues if i.domain == ToolDomain.TYPE_CHECKING
        )
        if type_issues > 0:
            return f"Fix {type_issues} type error(s) by updating type annotations or handling None values."

        return f"Review and fix {len(issues)} issue(s), then re-scan to verify."
