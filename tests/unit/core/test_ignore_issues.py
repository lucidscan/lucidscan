"""Tests for lucidshark.core.ignore_issues."""

from __future__ import annotations

from datetime import date, timedelta

from lucidshark.config.models import IgnoreIssueEntry
from lucidshark.core.ignore_issues import apply_ignore_issues
from lucidshark.core.models import Severity, ToolDomain, UnifiedIssue


def _make_issue(
    rule_id: str = "TEST001",
    domain=ToolDomain.LINTING,
    severity=Severity.MEDIUM,
) -> UnifiedIssue:
    return UnifiedIssue(
        id=f"test-{rule_id}",
        domain=domain,
        source_tool="test",
        severity=severity,
        rule_id=rule_id,
        title=f"Issue {rule_id}",
        description=f"Description for {rule_id}",
    )


class TestApplyIgnoreIssuesBasic:
    """Basic matching behavior."""

    def test_matching_rule_id_marks_ignored(self) -> None:
        issues = [_make_issue("E501")]
        entries = [IgnoreIssueEntry(rule_id="E501")]

        warnings = apply_ignore_issues(issues, entries)

        assert issues[0].ignored is True
        assert warnings == []

    def test_non_matching_rule_id_not_ignored(self) -> None:
        issues = [_make_issue("E501")]
        entries = [IgnoreIssueEntry(rule_id="E502")]

        apply_ignore_issues(issues, entries)

        assert issues[0].ignored is False

    def test_reason_is_set(self) -> None:
        issues = [_make_issue("CVE-2021-1234")]
        entries = [IgnoreIssueEntry(
            rule_id="CVE-2021-1234",
            reason="Accepted risk per security review",
        )]

        apply_ignore_issues(issues, entries)

        assert issues[0].ignored is True
        assert issues[0].ignore_reason == "Accepted risk per security review"

    def test_no_reason_leaves_none(self) -> None:
        issues = [_make_issue("E501")]
        entries = [IgnoreIssueEntry(rule_id="E501")]

        apply_ignore_issues(issues, entries)

        assert issues[0].ignore_reason is None

    def test_empty_entries_no_changes(self) -> None:
        issues = [_make_issue("E501")]

        warnings = apply_ignore_issues(issues, [])

        assert issues[0].ignored is False
        assert warnings == []

    def test_empty_issues_no_warnings_for_unmatched(self) -> None:
        """No issues means entries don't match -> warnings."""
        entries = [IgnoreIssueEntry(rule_id="E501")]

        warnings = apply_ignore_issues([], entries)

        assert len(warnings) == 1
        assert "did not match" in warnings[0]


class TestApplyIgnoreIssuesMultiple:
    """Multiple entries and issues."""

    def test_multiple_issues_same_rule(self) -> None:
        issues = [_make_issue("E501"), _make_issue("E501")]
        entries = [IgnoreIssueEntry(rule_id="E501")]

        warnings = apply_ignore_issues(issues, entries)

        assert all(i.ignored for i in issues)
        assert warnings == []

    def test_multiple_entries_different_rules(self) -> None:
        issues = [
            _make_issue("E501"),
            _make_issue("CVE-2021-1234"),
            _make_issue("W503"),
        ]
        entries = [
            IgnoreIssueEntry(rule_id="E501"),
            IgnoreIssueEntry(rule_id="CVE-2021-1234", reason="accepted"),
        ]

        warnings = apply_ignore_issues(issues, entries)

        assert issues[0].ignored is True
        assert issues[1].ignored is True
        assert issues[1].ignore_reason == "accepted"
        assert issues[2].ignored is False
        assert warnings == []

    def test_mixed_simple_and_structured_entries(self) -> None:
        issues = [_make_issue("E501"), _make_issue("W503")]
        entries = [
            IgnoreIssueEntry(rule_id="E501"),  # simple
            IgnoreIssueEntry(rule_id="W503", reason="known issue"),  # structured
        ]

        apply_ignore_issues(issues, entries)

        assert issues[0].ignored is True
        assert issues[0].ignore_reason is None
        assert issues[1].ignored is True
        assert issues[1].ignore_reason == "known issue"


class TestApplyIgnoreIssuesExpiry:
    """Expiry date handling."""

    def test_expired_entry_does_not_suppress(self) -> None:
        issues = [_make_issue("E501")]
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        entries = [IgnoreIssueEntry(rule_id="E501", expires=yesterday)]

        warnings = apply_ignore_issues(issues, entries)

        assert issues[0].ignored is False
        assert len(warnings) == 1
        assert "expired" in warnings[0]

    def test_future_expiry_still_suppresses(self) -> None:
        issues = [_make_issue("E501")]
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        entries = [IgnoreIssueEntry(rule_id="E501", expires=tomorrow)]

        warnings = apply_ignore_issues(issues, entries)

        assert issues[0].ignored is True
        # No expiry warning, but possible unmatched warning won't fire
        assert not any("expired" in w for w in warnings)

    def test_today_expiry_still_suppresses(self) -> None:
        """Expiry date == today means it hasn't expired yet."""
        issues = [_make_issue("E501")]
        today = date.today().isoformat()
        entries = [IgnoreIssueEntry(rule_id="E501", expires=today)]

        apply_ignore_issues(issues, entries)

        assert issues[0].ignored is True

    def test_invalid_expires_format_warns_but_still_applies(self) -> None:
        issues = [_make_issue("E501")]
        entries = [IgnoreIssueEntry(rule_id="E501", expires="not-a-date")]

        warnings = apply_ignore_issues(issues, entries)

        # Invalid date -> warning about format, but entry is still active
        assert issues[0].ignored is True
        assert len(warnings) == 1
        assert "invalid" in warnings[0].lower()


class TestApplyIgnoreIssuesUnmatched:
    """Unmatched entry warnings."""

    def test_unmatched_entry_produces_warning(self) -> None:
        issues = [_make_issue("E501")]
        entries = [
            IgnoreIssueEntry(rule_id="E501"),
            IgnoreIssueEntry(rule_id="NONEXISTENT"),
        ]

        warnings = apply_ignore_issues(issues, entries)

        assert len(warnings) == 1
        assert "NONEXISTENT" in warnings[0]
        assert "did not match" in warnings[0]

    def test_all_matched_no_warning(self) -> None:
        issues = [_make_issue("E501"), _make_issue("W503")]
        entries = [
            IgnoreIssueEntry(rule_id="E501"),
            IgnoreIssueEntry(rule_id="W503"),
        ]

        warnings = apply_ignore_issues(issues, entries)

        assert warnings == []
