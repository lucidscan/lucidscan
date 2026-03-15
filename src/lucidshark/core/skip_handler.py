"""Handler for tool skip processing and mandatory skip enforcement.

This module processes tool skips recorded during scan execution and
converts mandatory skips to issues that can trigger scan failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple

from lucidshark.core.models import (
    Severity,
    SkipReason,
    ToolSkipInfo,
    UnifiedIssue,
)

if TYPE_CHECKING:
    from lucidshark.config.models import LucidSharkConfig


# Skip reasons that should never cause mandatory failures
# (tool not applicable to project type)
INFORMATIONAL_REASONS = {
    SkipReason.NO_APPLICABLE_FILES,
}

# Skip reasons that should always cause mandatory failures
# (tool crashed during execution - scan result is incomplete)
ALWAYS_MANDATORY_REASONS = {
    SkipReason.EXECUTION_FAILED,
}


def process_skips(
    skips: List[ToolSkipInfo],
    config: "LucidSharkConfig",
) -> Tuple[List[ToolSkipInfo], List[UnifiedIssue]]:
    """Process tool skips and generate issues for mandatory failures.

    Args:
        skips: List of tool skip infos from scan context.
        config: LucidShark configuration.

    Returns:
        Tuple of (all skips with mandatory flag set, mandatory skip issues).
    """
    mandatory_issues: List[UnifiedIssue] = []

    for skip in skips:
        # Determine if this skip is mandatory
        is_mandatory = _is_skip_mandatory(skip, config)
        skip.mandatory = is_mandatory

        # Only generate issues for non-informational mandatory skips
        if is_mandatory and skip.reason not in INFORMATIONAL_REASONS:
            mandatory_issues.append(_skip_to_issue(skip))

    return skips, mandatory_issues


def _is_skip_mandatory(skip: ToolSkipInfo, config: "LucidSharkConfig") -> bool:
    """Determine if a skip should be treated as mandatory failure.

    Args:
        skip: The tool skip info.
        config: LucidShark configuration.

    Returns:
        True if this skip should cause scan failure.
    """
    # EXECUTION_FAILED is always mandatory - tool crashed, scan is incomplete
    if skip.reason in ALWAYS_MANDATORY_REASONS:
        return True

    # Global strict mode
    if config.settings.strict_mode:
        return skip.reason not in INFORMATIONAL_REASONS

    # Per-tool mandatory config
    domain_name = (
        skip.domain.value if hasattr(skip.domain, "value") else str(skip.domain)
    )

    # Check pipeline domain config for tool-specific mandatory flag
    domain_config = getattr(config.pipeline, domain_name, None)
    if domain_config and hasattr(domain_config, "tools"):
        for tool in domain_config.tools:
            if tool.name == skip.tool_name:
                return tool.mandatory

    return False


def _skip_to_issue(skip: ToolSkipInfo) -> UnifiedIssue:
    """Convert a mandatory tool skip to a UnifiedIssue.

    Args:
        skip: The tool skip info.

    Returns:
        UnifiedIssue representing the mandatory skip failure.
    """
    title_map = {
        SkipReason.TOOL_NOT_INSTALLED: f"Mandatory tool '{skip.tool_name}' is not installed",
        SkipReason.MISSING_PREREQUISITE: f"Mandatory tool '{skip.tool_name}' missing prerequisites",
        SkipReason.EXECUTION_FAILED: f"Mandatory tool '{skip.tool_name}' failed to execute",
        SkipReason.NO_APPLICABLE_FILES: f"Mandatory tool '{skip.tool_name}' found no applicable files",
    }

    return UnifiedIssue(
        id=f"mandatory-skip-{skip.tool_name}",
        domain=skip.domain,
        source_tool="lucidshark",
        severity=Severity.HIGH,
        rule_id="mandatory-tool-skipped",
        title=title_map.get(
            skip.reason, f"Mandatory tool '{skip.tool_name}' was skipped"
        ),
        description=skip.message,
        recommendation=skip.suggestion,
        fixable=False,
        metadata={
            "skip_reason": skip.reason.value,
            "tool_name": skip.tool_name,
        },
    )
