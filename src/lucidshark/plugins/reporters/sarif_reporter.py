"""SARIF reporter plugin for IDE integration.

Outputs scan results in SARIF 2.1.0 format, compatible with:
- GitHub Security tab (Code Scanning)
- VS Code SARIF Viewer extension
- Other SARIF-compatible tools
"""

from __future__ import annotations

import json
from typing import Any, Dict, IO, List, Optional

from lucidshark.plugins.reporters.base import ReporterPlugin
from lucidshark.core.models import ScanResult, Severity, UnifiedIssue

# SARIF schema URL
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"

# Project information
LUCIDSHARK_INFO_URI = "https://github.com/lucidshark/lucidshark"

# Severity mapping to SARIF security-severity (CVSS-aligned 0.0-10.0)
# and level (error, warning, note)
SEVERITY_MAP: Dict[Severity, Dict[str, Any]] = {
    Severity.CRITICAL: {"security-severity": "9.5", "level": "error"},
    Severity.HIGH: {"security-severity": "7.5", "level": "error"},
    Severity.MEDIUM: {"security-severity": "5.5", "level": "warning"},
    Severity.LOW: {"security-severity": "2.5", "level": "warning"},
    Severity.INFO: {"security-severity": "0.0", "level": "note"},
}


class SARIFReporter(ReporterPlugin):
    """Reporter plugin for SARIF 2.1.0 output format.

    Produces SARIF JSON suitable for upload to GitHub Code Scanning
    or viewing in VS Code with the SARIF Viewer extension.
    """

    @property
    def name(self) -> str:
        return "sarif"

    def report(self, result: ScanResult, output: IO[str]) -> None:
        """Format and write the scan result as SARIF JSON.

        Args:
            result: The aggregated scan result to format.
            output: Output stream to write the formatted result.
        """
        sarif_doc = self._build_sarif(result)
        json.dump(sarif_doc, output, indent=2)
        output.write("\n")

    def _build_sarif(self, result: ScanResult) -> Dict[str, Any]:
        """Build the complete SARIF document.

        Args:
            result: Scan result containing issues and metadata.

        Returns:
            SARIF document as a dictionary.
        """
        # Get lucidshark version from metadata or use default
        version = "unknown"
        if result.metadata:
            version = result.metadata.lucidshark_version

        # Collect unique rules from all issues
        rules = self._collect_rules(result.issues)

        # Convert issues to SARIF results
        results = [
            self._issue_to_result(issue)
            for issue in result.issues
        ]

        return {
            "$schema": SARIF_SCHEMA,
            "version": SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "lucidshark",
                            "version": version,
                            "informationUri": LUCIDSHARK_INFO_URI,
                            "rules": rules,
                        }
                    },
                    "results": results,
                }
            ],
        }

    def _collect_rules(self, issues: List[UnifiedIssue]) -> List[Dict[str, Any]]:
        """Collect unique rules from issues.

        Each unique rule ID becomes a SARIF rule definition.

        Args:
            issues: List of unified issues to extract rules from.

        Returns:
            List of SARIF rule definitions.
        """
        rules_dict: Dict[str, Dict[str, Any]] = {}

        for issue in issues:
            rule_id = self._get_rule_id(issue)

            # Skip if we already have this rule
            if rule_id in rules_dict:
                continue

            # Build rule definition
            rule = self._build_rule(issue, rule_id)
            rules_dict[rule_id] = rule

        return list(rules_dict.values())

    def _build_rule(self, issue: UnifiedIssue, rule_id: str) -> Dict[str, Any]:
        """Build a SARIF rule definition from an issue.

        Args:
            issue: The issue to build a rule from.
            rule_id: The rule identifier.

        Returns:
            SARIF rule definition.
        """
        severity_info = SEVERITY_MAP.get(issue.severity, SEVERITY_MAP[Severity.MEDIUM])

        rule: Dict[str, Any] = {
            "id": rule_id,
            "shortDescription": {
                "text": self._truncate(issue.title, 1024),
            },
            "defaultConfiguration": {
                "level": severity_info["level"],
            },
            "properties": {
                "security-severity": severity_info["security-severity"],
            },
        }

        # Add full description if we have more detail
        if issue.description and issue.description != issue.title:
            rule["fullDescription"] = {
                "text": issue.description,
            }

        # Add help URI from documentation_url or recommendation
        if issue.documentation_url:
            rule["helpUri"] = issue.documentation_url
        elif issue.recommendation:
            # Check if recommendation contains a URL
            if issue.recommendation.startswith("http"):
                rule["helpUri"] = issue.recommendation
            elif "See: " in issue.recommendation:
                # Extract URL from "See: <url>" format
                url = issue.recommendation.replace("See: ", "").strip()
                if url.startswith("http"):
                    rule["helpUri"] = url

        # Add CWE/OWASP tags from metadata if available
        tool_metadata = issue.metadata
        if tool_metadata:
            tags = []
            if "cwe" in tool_metadata:
                cwe_ids = tool_metadata["cwe"]
                if isinstance(cwe_ids, list):
                    tags.extend(cwe_ids)
                elif cwe_ids:
                    tags.append(cwe_ids)
            if "owasp" in tool_metadata:
                owasp_ids = tool_metadata["owasp"]
                if isinstance(owasp_ids, list):
                    tags.extend(owasp_ids)
                elif owasp_ids:
                    tags.append(owasp_ids)
            if tags:
                rule["properties"]["tags"] = tags

        return rule

    def _issue_to_result(self, issue: UnifiedIssue) -> Dict[str, Any]:
        """Convert a UnifiedIssue to a SARIF result.

        Args:
            issue: The issue to convert.

        Returns:
            SARIF result object.
        """
        rule_id = self._get_rule_id(issue)
        severity_info = SEVERITY_MAP.get(issue.severity, SEVERITY_MAP[Severity.MEDIUM])

        result: Dict[str, Any] = {
            "ruleId": rule_id,
            "message": {
                "text": issue.description or issue.title,
            },
            "level": severity_info["level"],
            "fingerprints": {
                "v1": issue.id,
            },
        }

        # Add location if we have file information
        location = self._build_location(issue)
        if location:
            result["locations"] = [location]

        return result

    def _build_location(self, issue: UnifiedIssue) -> Optional[Dict[str, Any]]:
        """Build a SARIF physical location from issue file info.

        Args:
            issue: The issue containing file location info.

        Returns:
            SARIF location object or None if no file info.
        """
        if not issue.file_path:
            return None

        # Use forward slashes for SARIF URIs (per SARIF spec)
        file_uri = issue.file_path.as_posix()
        if file_uri.startswith("/"):
            # Try to make it relative - just use the path as-is for now
            # In practice, the path should already be relative or project-relative
            pass

        location: Dict[str, Any] = {
            "physicalLocation": {
                "artifactLocation": {
                    "uri": file_uri,
                },
            }
        }

        # Add region if we have line information
        if issue.line_start is not None:
            region: Dict[str, Any] = {
                "startLine": issue.line_start,
            }

            if issue.line_end is not None:
                region["endLine"] = issue.line_end

            location["physicalLocation"]["region"] = region

        return location

    def _get_rule_id(self, issue: UnifiedIssue) -> str:
        """Extract or generate a rule ID for an issue.

        Uses the issue's rule_id field, falling back to scanner-specific
        identifiers in metadata if needed.

        Args:
            issue: The issue to get a rule ID from.

        Returns:
            Rule identifier string.
        """
        # Use the new rule_id field if available
        if issue.rule_id:
            return issue.rule_id

        # Fallback to metadata for older scanner output formats
        metadata = issue.metadata

        # Try scanner-specific IDs from metadata
        if "vulnerability_id" in metadata:
            return metadata["vulnerability_id"]
        if "rule_id" in metadata:
            return metadata["rule_id"]
        if "check_id" in metadata:
            return metadata["check_id"]

        # Fallback: construct from source tool and issue title
        # Use a simplified version of the title as rule ID
        title_slug = issue.title.split(":")[0].strip()
        return f"{issue.source_tool}/{title_slug}"

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length with ellipsis.

        Args:
            text: Text to truncate.
            max_length: Maximum allowed length.

        Returns:
            Truncated text.
        """
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."
