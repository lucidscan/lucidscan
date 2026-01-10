"""Tests for lucidscan.config.validation."""

from __future__ import annotations


from lucidscan.config.validation import (
    ConfigValidationWarning,
    validate_config,
    _suggest_key,
)


class TestSuggestKey:
    """Tests for _suggest_key function."""

    def test_suggests_close_match(self) -> None:
        result = _suggest_key("sac", {"sca", "sast", "iac"})
        assert result == "sca"

    def test_suggests_typo_fix(self) -> None:
        result = _suggest_key("faol_on", {"fail_on", "ignore", "output"})
        assert result == "fail_on"

    def test_returns_none_for_no_match(self) -> None:
        result = _suggest_key("xyz", {"fail_on", "ignore", "output"})
        assert result is None

    def test_handles_empty_valid_keys(self) -> None:
        result = _suggest_key("test", set())
        assert result is None


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_valid_config_returns_no_warnings(self) -> None:
        data = {
            "fail_on": "high",
            "ignore": ["tests/**"],
            "output": {"format": "json"},
            "scanners": {
                "sca": {"enabled": True},
            },
        }
        warnings = validate_config(data, source="test.yml")
        # Filter out INFO-level warnings
        errors = [w for w in warnings if "Unknown" in w.message]
        assert len(errors) == 0

    def test_warns_on_unknown_top_level_key(self) -> None:
        data = {"unknown_key": "value"}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "unknown_key" in warnings[0].message
        assert warnings[0].key == "unknown_key"

    def test_suggests_typo_fix_for_top_level(self) -> None:
        data = {"fail_ob": "high"}  # typo: should be fail_on
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert warnings[0].suggestion == "fail_on"

    def test_warns_on_invalid_fail_on_severity(self) -> None:
        data = {"fail_on": "super_high"}  # invalid severity
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "Invalid severity" in warnings[0].message

    def test_warns_on_invalid_fail_on_type(self) -> None:
        data = {"fail_on": 123}  # should be string
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a string" in warnings[0].message

    def test_warns_on_invalid_ignore_type(self) -> None:
        data = {"ignore": "should-be-list"}  # should be list
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a list" in warnings[0].message

    def test_warns_on_invalid_output_type(self) -> None:
        data = {"output": "json"}  # should be dict
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a mapping" in warnings[0].message

    def test_warns_on_unknown_output_key(self) -> None:
        data = {"output": {"unknown": "value"}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "output.unknown" in warnings[0].message

    def test_warns_on_invalid_scanners_type(self) -> None:
        data = {"scanners": ["sca"]}  # should be dict
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a mapping" in warnings[0].message

    def test_warns_on_unknown_domain(self) -> None:
        data = {"scanners": {"unknowndomain": {"enabled": True}}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "Unknown scanner domain" in warnings[0].message

    def test_suggests_domain_typo_fix(self) -> None:
        data = {"scanners": {"sac": {"enabled": True}}}  # typo: should be sca
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert warnings[0].suggestion == "sca"

    def test_warns_on_invalid_enabled_type(self) -> None:
        data = {"scanners": {"sca": {"enabled": "yes"}}}  # should be bool
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a boolean" in warnings[0].message

    def test_warns_on_invalid_plugin_type(self) -> None:
        data = {"scanners": {"sca": {"plugin": 123}}}  # should be string
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a string" in warnings[0].message

    def test_allows_plugin_specific_options(self) -> None:
        # Plugin-specific options should not trigger warnings
        data = {
            "scanners": {
                "sca": {
                    "enabled": True,
                    "plugin": "trivy",
                    "ignore_unfixed": True,  # plugin-specific
                    "severity": ["HIGH"],  # plugin-specific
                    "custom_option": "value",  # plugin-specific
                },
            }
        }
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_returns_warning_for_non_dict_data(self) -> None:
        warnings = validate_config("not a dict", source="test.yml")
        assert len(warnings) == 1
        assert "must be a mapping" in warnings[0].message


class TestConfigValidationWarning:
    """Tests for ConfigValidationWarning dataclass."""

    def test_basic_warning(self) -> None:
        warning = ConfigValidationWarning(
            message="Test message",
            source="test.yml",
        )
        assert warning.message == "Test message"
        assert warning.source == "test.yml"
        assert warning.key is None
        assert warning.suggestion is None

    def test_warning_with_key_and_suggestion(self) -> None:
        warning = ConfigValidationWarning(
            message="Unknown key",
            source="test.yml",
            key="fail_ob",
            suggestion="fail_on",
        )
        assert warning.key == "fail_ob"
        assert warning.suggestion == "fail_on"
