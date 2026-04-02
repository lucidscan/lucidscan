"""Tests for anonymous telemetry module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucidshark import telemetry


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Reset telemetry state before and after each test."""
    telemetry.reset()
    yield
    telemetry.reset()


@pytest.fixture
def _enable_telemetry(monkeypatch):
    """Ensure telemetry is enabled for the test."""
    monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("CI", raising=False)


class TestIsEnabled:
    """Tests for telemetry opt-out checks."""

    def test_disabled_by_env_var_zero(self, monkeypatch):
        monkeypatch.setenv("LUCIDSHARK_TELEMETRY", "0")
        assert telemetry.is_enabled() is False

    def test_disabled_by_env_var_false(self, monkeypatch):
        monkeypatch.setenv("LUCIDSHARK_TELEMETRY", "false")
        assert telemetry.is_enabled() is False

    def test_disabled_by_env_var_no(self, monkeypatch):
        monkeypatch.setenv("LUCIDSHARK_TELEMETRY", "no")
        assert telemetry.is_enabled() is False

    def test_disabled_by_env_var_off(self, monkeypatch):
        monkeypatch.setenv("LUCIDSHARK_TELEMETRY", "off")
        assert telemetry.is_enabled() is False

    def test_disabled_by_do_not_track(self, monkeypatch):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        assert telemetry.is_enabled() is False

    def test_disabled_in_ci(self, monkeypatch):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.setenv("CI", "true")
        assert telemetry.is_enabled() is False

    def test_disabled_by_optout_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        optout_file = tmp_path / "telemetry-optout"
        optout_file.touch()
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )
        assert telemetry.is_enabled() is False

    def test_enabled_by_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        # Point to a dir without optout file
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )
        assert telemetry.is_enabled() is True

    def test_enabled_caches_result(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )
        assert telemetry.is_enabled() is True
        # Should return cached value even if env changes
        monkeypatch.setenv("LUCIDSHARK_TELEMETRY", "0")
        assert telemetry.is_enabled() is True  # Still cached as True


class TestAnonymousId:
    """Tests for anonymous ID generation and persistence."""

    def test_generates_uuid(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )
        anon_id = telemetry._get_anonymous_id()
        assert len(anon_id) == 36  # UUID format
        assert "-" in anon_id

    def test_persists_to_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )
        anon_id = telemetry._get_anonymous_id()

        id_file = tmp_path / "anonymous-id"
        assert id_file.exists()
        assert id_file.read_text().strip() == anon_id

    def test_reads_existing_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )
        id_file = tmp_path / "anonymous-id"
        id_file.write_text("existing-test-id-12345")

        anon_id = telemetry._get_anonymous_id()
        assert anon_id == "existing-test-id-12345"

    def test_returns_stable_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )
        id1 = telemetry._get_anonymous_id()
        # Reset the cached value but keep the file
        telemetry._anonymous_id = None
        id2 = telemetry._get_anonymous_id()
        assert id1 == id2

    def test_handles_unwritable_dir(self, monkeypatch):
        monkeypatch.setattr(
            telemetry,
            "_get_lucidshark_dir",
            lambda: Path("/nonexistent/deeply/nested/path"),
        )
        # Should not raise, just generate in-memory ID
        anon_id = telemetry._get_anonymous_id()
        assert len(anon_id) == 36


class TestTrackEvent:
    """Tests for event tracking."""

    def test_noop_when_disabled(self, monkeypatch):
        monkeypatch.setenv("LUCIDSHARK_TELEMETRY", "0")
        # Should not raise even without posthog installed
        telemetry.track_event("test_event", {"key": "value"})

    def test_never_raises(self, monkeypatch, tmp_path):
        """Telemetry must never crash the CLI."""
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )

        # Mock _get_client to raise
        monkeypatch.setattr(
            telemetry, "_get_client", MagicMock(side_effect=RuntimeError("boom"))
        )
        # Should not raise
        telemetry.track_event("test_event")

    def test_calls_posthog_capture(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )

        mock_client = MagicMock()
        monkeypatch.setattr(telemetry, "_get_client", lambda: mock_client)

        telemetry.track_event("test_event", {"custom": "prop"})

        mock_client.capture.assert_called_once()
        call_kwargs = mock_client.capture.call_args
        assert call_kwargs.kwargs["event"] == "test_event"
        assert "custom" in call_kwargs.kwargs["properties"]
        assert call_kwargs.kwargs["properties"]["custom"] == "prop"
        # Should include base properties
        assert "lucidshark_version" in call_kwargs.kwargs["properties"]
        assert "os" in call_kwargs.kwargs["properties"]

    def test_includes_base_properties(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )

        mock_client = MagicMock()
        monkeypatch.setattr(telemetry, "_get_client", lambda: mock_client)

        telemetry.track_event("test_event")

        props = mock_client.capture.call_args.kwargs["properties"]
        assert "lucidshark_version" in props
        assert "os" in props
        assert "arch" in props
        assert "python_version" in props


class TestTrackCommand:
    """Tests for command tracking."""

    def test_tracks_command_name(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )

        mock_client = MagicMock()
        monkeypatch.setattr(telemetry, "_get_client", lambda: mock_client)

        telemetry.track_command("scan")

        mock_client.capture.assert_called_once()
        call_kwargs = mock_client.capture.call_args
        assert call_kwargs.kwargs["event"] == "command_executed"
        assert call_kwargs.kwargs["properties"]["command"] == "scan"


class TestTrackScanCompleted:
    """Tests for scan completion tracking."""

    def test_tracks_scan_with_all_properties(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )

        mock_client = MagicMock()
        monkeypatch.setattr(telemetry, "_get_client", lambda: mock_client)

        telemetry.track_scan_completed(
            domains=["linting", "sast"],
            languages=["python", "typescript"],
            tools_used=["ruff", "opengrep"],
            total_issues=42,
            issues_by_severity={"high": 5, "low": 37},
            issues_by_domain={"linting": 30, "sast": 12},
            duration_ms=5000,
            scan_mode="full",
            output_format="json",
            fix_enabled=True,
            coverage_percent=85.5,
            duplication_percent=3.2,
        )

        mock_client.capture.assert_called_once()
        props = mock_client.capture.call_args.kwargs["properties"]

        assert props["domains"] == ["linting", "sast"]
        assert props["domain_count"] == 2
        assert props["languages"] == ["python", "typescript"]
        assert props["language_count"] == 2
        assert props["tools_used"] == ["opengrep", "ruff"]  # sorted
        assert props["tool_count"] == 2
        assert props["total_issues"] == 42
        assert props["issues_by_severity"] == {"high": 5, "low": 37}
        assert props["issues_by_domain"] == {"linting": 30, "sast": 12}
        assert props["duration_ms"] == 5000
        assert props["scan_mode"] == "full"
        assert props["output_format"] == "json"
        assert props["fix_enabled"] is True
        assert props["coverage_percent"] == 85.5
        assert props["duplication_percent"] == 3.2
        # Base properties
        assert "lucidshark_version" in props
        assert "os" in props

    def test_optional_coverage_and_duplication(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )

        mock_client = MagicMock()
        monkeypatch.setattr(telemetry, "_get_client", lambda: mock_client)

        telemetry.track_scan_completed(
            domains=["linting"],
            languages=["python"],
            tools_used=["ruff"],
            total_issues=0,
            issues_by_severity={},
            issues_by_domain={},
            duration_ms=100,
            scan_mode="incremental",
            output_format="summary",
            fix_enabled=False,
        )

        props = mock_client.capture.call_args.kwargs["properties"]
        assert "coverage_percent" not in props
        assert "duplication_percent" not in props


class TestReset:
    """Tests for reset functionality."""

    def test_reset_clears_cached_state(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LUCIDSHARK_TELEMETRY", raising=False)
        monkeypatch.delenv("DO_NOT_TRACK", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            telemetry, "_get_lucidshark_dir", lambda: tmp_path
        )

        # Prime caches
        telemetry.is_enabled()
        telemetry._get_anonymous_id()

        # Reset
        telemetry.reset()

        assert telemetry._enabled is None
        assert telemetry._anonymous_id is None
        assert telemetry._telemetry_client is None
