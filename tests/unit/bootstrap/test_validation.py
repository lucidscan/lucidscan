"""Tests for tool validation functionality."""

from __future__ import annotations

import stat
from pathlib import Path


from lucidscan.bootstrap.validation import (
    validate_binary,
    PluginValidationResult,
    ToolStatus,
)


class TestToolStatus:
    """Tests for ToolStatus enum."""

    def test_status_values(self) -> None:
        assert ToolStatus.PRESENT.value == "present"
        assert ToolStatus.MISSING.value == "missing"
        assert ToolStatus.NOT_EXECUTABLE.value == "not_executable"


class TestPluginValidationResult:
    """Tests for PluginValidationResult dataclass."""

    def test_all_valid_when_all_present(self) -> None:
        result = PluginValidationResult(
            statuses={
                "plugin_a": ToolStatus.PRESENT,
                "plugin_b": ToolStatus.PRESENT,
            }
        )
        assert result.all_valid() is True

    def test_all_valid_true_when_empty(self) -> None:
        result = PluginValidationResult()
        assert result.all_valid() is True

    def test_all_valid_false_when_missing(self) -> None:
        result = PluginValidationResult(
            statuses={
                "plugin_a": ToolStatus.MISSING,
                "plugin_b": ToolStatus.PRESENT,
            }
        )
        assert result.all_valid() is False

    def test_all_valid_false_when_not_executable(self) -> None:
        result = PluginValidationResult(
            statuses={
                "plugin_a": ToolStatus.PRESENT,
                "plugin_b": ToolStatus.NOT_EXECUTABLE,
            }
        )
        assert result.all_valid() is False

    def test_missing_plugins_returns_list(self) -> None:
        result = PluginValidationResult(
            statuses={
                "plugin_a": ToolStatus.MISSING,
                "plugin_b": ToolStatus.PRESENT,
                "plugin_c": ToolStatus.NOT_EXECUTABLE,
            }
        )
        missing = result.missing_plugins()
        assert "plugin_a" in missing
        assert "plugin_c" in missing
        assert "plugin_b" not in missing

    def test_get_status(self) -> None:
        result = PluginValidationResult(
            statuses={
                "plugin_a": ToolStatus.PRESENT,
            }
        )
        assert result.get_status("plugin_a") == ToolStatus.PRESENT
        assert result.get_status("unknown") == ToolStatus.MISSING

    def test_to_dict(self) -> None:
        result = PluginValidationResult(
            statuses={
                "plugin_a": ToolStatus.PRESENT,
                "plugin_b": ToolStatus.MISSING,
                "plugin_c": ToolStatus.NOT_EXECUTABLE,
            }
        )
        d = result.to_dict()
        assert d["plugin_a"] == "present"
        assert d["plugin_b"] == "missing"
        assert d["plugin_c"] == "not_executable"


class TestValidateBinary:
    """Tests for validate_binary function."""

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent"
        status = validate_binary(path)
        assert status == ToolStatus.MISSING

    def test_present_executable(self, tmp_path: Path) -> None:
        path = tmp_path / "tool"
        path.write_text("#!/bin/bash\necho hello")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

        status = validate_binary(path)
        assert status == ToolStatus.PRESENT

    def test_present_not_executable(self, tmp_path: Path) -> None:
        path = tmp_path / "tool"
        path.write_text("#!/bin/bash\necho hello")
        # Remove execute permission
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        status = validate_binary(path)
        assert status == ToolStatus.NOT_EXECUTABLE
