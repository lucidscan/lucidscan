"""Prompt templates for AI explanations.

Provides domain-specific prompt templates for generating security issue
explanations using LLMs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lucidscan.core.models import ScanDomain, UnifiedIssue

# Prompt template version - included in cache key for invalidation
PROMPT_VERSION = "v1"

# Base system prompt for consistent behavior
SYSTEM_PROMPT = """You are a security expert assistant. Your task is to explain security vulnerabilities and issues to developers in a clear, actionable way.

Guidelines:
- Be concise but thorough
- Focus on the "why" - explain the risk and potential impact
- Provide specific, actionable remediation steps
- Use technical terminology appropriately
- Do NOT repeat the issue title or description verbatim
- Do NOT use markdown formatting
- Keep explanations under 200 words"""

# Domain-specific templates
SCA_TEMPLATE = """Explain this dependency vulnerability:

Vulnerability: {title}
Package: {dependency}
Severity: {severity}
Description: {description}
{recommendation_section}
{code_section}

Provide:
1. What is the security risk? (1-2 sentences)
2. How could this be exploited? (1-2 sentences)
3. Remediation steps (bullet points)"""

SAST_TEMPLATE = """Explain this code security issue:

Issue: {title}
Severity: {severity}
File: {file_path}:{line_info}
Description: {description}
{code_section}

Provide:
1. What is the security risk? (1-2 sentences)
2. How could this be exploited? (1-2 sentences)
3. How to fix this code (specific example)"""

IAC_TEMPLATE = """Explain this Infrastructure-as-Code security issue:

Issue: {title}
Severity: {severity}
Resource: {iac_resource}
File: {file_path}
Description: {description}
{code_section}

Provide:
1. What is the security risk? (1-2 sentences)
2. What could an attacker do? (1-2 sentences)
3. Secure configuration example"""

CONTAINER_TEMPLATE = """Explain this container vulnerability:

Vulnerability: {title}
Severity: {severity}
Image: {image_ref}
Package: {dependency}
Description: {description}
{recommendation_section}

Provide:
1. What is the security risk? (1-2 sentences)
2. Remediation steps (bullet points)"""

# Fallback for unknown domains
DEFAULT_TEMPLATE = """Explain this security issue:

Issue: {title}
Severity: {severity}
Description: {description}
{code_section}

Provide:
1. What is the security risk?
2. How to remediate this issue?"""


def get_prompt_template(domain: "ScanDomain") -> str:
    """Get the appropriate prompt template for a scan domain.

    Args:
        domain: The scan domain (SCA, SAST, IAC, CONTAINER).

    Returns:
        Prompt template string for the domain.
    """
    from lucidscan.core.models import ScanDomain

    templates = {
        ScanDomain.SCA: SCA_TEMPLATE,
        ScanDomain.SAST: SAST_TEMPLATE,
        ScanDomain.IAC: IAC_TEMPLATE,
        ScanDomain.CONTAINER: CONTAINER_TEMPLATE,
    }
    return templates.get(domain, DEFAULT_TEMPLATE)


def format_prompt(issue: "UnifiedIssue", include_code: bool = True) -> str:
    """Format a prompt for a specific issue.

    Args:
        issue: The security issue to explain.
        include_code: Whether to include code snippets in the prompt.

    Returns:
        Formatted prompt string ready to send to LLM.
    """
    template = get_prompt_template(issue.scanner)

    # Build optional sections
    code_section = ""
    if include_code and issue.code_snippet:
        code_section = f"\nCode:\n```\n{issue.code_snippet}\n```"

    recommendation_section = ""
    if issue.recommendation:
        recommendation_section = f"\nRecommendation: {issue.recommendation}"

    # Get image reference from scanner metadata for container issues
    image_ref = issue.scanner_metadata.get("image_ref", "unknown")

    # Build line info
    line_info = ""
    if issue.line_start:
        if issue.line_end and issue.line_end != issue.line_start:
            line_info = f"{issue.line_start}-{issue.line_end}"
        else:
            line_info = str(issue.line_start)

    return template.format(
        title=issue.title,
        severity=issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity),
        description=issue.description,
        dependency=issue.dependency or "N/A",
        file_path=str(issue.file_path) if issue.file_path else "N/A",
        line_info=line_info or "N/A",
        iac_resource=issue.iac_resource or "N/A",
        image_ref=image_ref,
        code_section=code_section,
        recommendation_section=recommendation_section,
    )
