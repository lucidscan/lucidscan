"""Tests for lucidscan.config.loader."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidscan.config.loader import (
    ConfigError,
    dict_to_config,
    expand_env_vars,
    find_project_config,
    load_config,
    load_yaml_file,
    merge_configs,
)
from lucidscan.config.models import LucidScanConfig


class TestExpandEnvVars:
    """Tests for expand_env_vars function."""

    def test_expands_simple_env_var(self) -> None:
        with patch.dict(os.environ, {"MY_VAR": "test_value"}):
            result = expand_env_vars("${MY_VAR}")
            assert result == "test_value"

    def test_expands_env_var_with_default(self) -> None:
        # Remove the var if it exists
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("UNSET_VAR", None)
            result = expand_env_vars("${UNSET_VAR:-default}")
            assert result == "default"

    def test_uses_value_when_set_ignoring_default(self) -> None:
        with patch.dict(os.environ, {"SET_VAR": "actual"}):
            result = expand_env_vars("${SET_VAR:-default}")
            assert result == "actual"

    def test_returns_empty_for_unset_without_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("UNSET_VAR", None)
            result = expand_env_vars("${UNSET_VAR}")
            assert result == ""

    def test_expands_in_dict_values(self) -> None:
        with patch.dict(os.environ, {"TOKEN": "secret"}):
            data = {"api_token": "${TOKEN}"}
            result = expand_env_vars(data)
            assert result == {"api_token": "secret"}

    def test_expands_in_list_items(self) -> None:
        with patch.dict(os.environ, {"PATH1": "/a", "PATH2": "/b"}):
            data = ["${PATH1}", "${PATH2}"]
            result = expand_env_vars(data)
            assert result == ["/a", "/b"]

    def test_expands_in_nested_structures(self) -> None:
        with patch.dict(os.environ, {"TOKEN": "secret", "URL": "http://example.com"}):
            data = {
                "api": {
                    "token": "${TOKEN}",
                    "url": "${URL}",
                },
                "paths": ["${TOKEN}"],
            }
            result = expand_env_vars(data)
            assert result["api"]["token"] == "secret"
            assert result["api"]["url"] == "http://example.com"
            assert result["paths"] == ["secret"]

    def test_preserves_non_string_values(self) -> None:
        data = {"number": 42, "boolean": True, "none": None}
        result = expand_env_vars(data)
        assert result == data


class TestMergeConfigs:
    """Tests for merge_configs function."""

    def test_overlay_replaces_scalars(self) -> None:
        base = {"a": 1, "b": 2}
        overlay = {"b": 3}
        result = merge_configs(base, overlay)
        assert result == {"a": 1, "b": 3}

    def test_overlay_adds_new_keys(self) -> None:
        base = {"a": 1}
        overlay = {"b": 2}
        result = merge_configs(base, overlay)
        assert result == {"a": 1, "b": 2}

    def test_overlay_replaces_lists(self) -> None:
        base = {"items": [1, 2]}
        overlay = {"items": [3, 4, 5]}
        result = merge_configs(base, overlay)
        assert result == {"items": [3, 4, 5]}

    def test_deep_merges_dicts(self) -> None:
        base = {"scanners": {"sca": {"enabled": True, "timeout": 60}}}
        overlay = {"scanners": {"sca": {"timeout": 120}}}
        result = merge_configs(base, overlay)
        assert result == {"scanners": {"sca": {"enabled": True, "timeout": 120}}}

    def test_empty_overlay_returns_base(self) -> None:
        base = {"a": 1}
        result = merge_configs(base, {})
        assert result == {"a": 1}

    def test_empty_base_returns_overlay(self) -> None:
        overlay = {"a": 1}
        result = merge_configs({}, overlay)
        assert result == {"a": 1}


class TestDictToConfig:
    """Tests for dict_to_config function."""

    def test_empty_dict_returns_default_config(self) -> None:
        config = dict_to_config({})
        assert config.fail_on is None
        assert config.ignore == []
        assert config.output.format == "json"
        assert config.scanners == {}

    def test_parses_fail_on(self) -> None:
        config = dict_to_config({"fail_on": "high"})
        assert config.fail_on == "high"

    def test_parses_ignore_patterns(self) -> None:
        config = dict_to_config({"ignore": ["tests/**", "*.md"]})
        assert config.ignore == ["tests/**", "*.md"]

    def test_parses_output_format(self) -> None:
        config = dict_to_config({"output": {"format": "table"}})
        assert config.output.format == "table"

    def test_parses_scanner_config(self) -> None:
        data = {
            "scanners": {
                "sca": {
                    "enabled": True,
                    "plugin": "snyk",
                    "api_token": "secret",
                }
            }
        }
        config = dict_to_config(data)
        assert "sca" in config.scanners
        assert config.scanners["sca"].enabled is True
        assert config.scanners["sca"].plugin == "snyk"
        assert config.scanners["sca"].options == {"api_token": "secret"}

    def test_parses_enrichers(self) -> None:
        data = {"enrichers": {"ai": {"enabled": False}}}
        config = dict_to_config(data)
        assert config.enrichers == {"ai": {"enabled": False}}


class TestFindProjectConfig:
    """Tests for find_project_config function."""

    def test_finds_lucidscan_yml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidscan.yml"
        config_file.write_text("fail_on: high")
        result = find_project_config(tmp_path)
        assert result == config_file

    def test_finds_lucidscan_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidscan.yaml"
        config_file.write_text("fail_on: high")
        result = find_project_config(tmp_path)
        assert result == config_file

    def test_returns_none_when_no_config(self, tmp_path: Path) -> None:
        result = find_project_config(tmp_path)
        assert result is None

    def test_prefers_yml_over_yaml(self, tmp_path: Path) -> None:
        yml_file = tmp_path / ".lucidscan.yml"
        yaml_file = tmp_path / ".lucidscan.yaml"
        yml_file.write_text("fail_on: high")
        yaml_file.write_text("fail_on: low")
        result = find_project_config(tmp_path)
        assert result == yml_file


class TestLoadYamlFile:
    """Tests for load_yaml_file function."""

    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("fail_on: high\nignore:\n  - tests/**")
        result = load_yaml_file(config_file)
        assert result == {"fail_on": "high", "ignore": ["tests/**"]}

    def test_returns_empty_dict_for_empty_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("")
        result = load_yaml_file(config_file)
        assert result == {}

    def test_raises_for_invalid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("invalid: yaml: content:")
        with pytest.raises(Exception):  # yaml.YAMLError
            load_yaml_file(config_file)

    def test_raises_for_non_dict_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("- item1\n- item2")
        with pytest.raises(ConfigError):
            load_yaml_file(config_file)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_returns_default_config_when_no_files(self, tmp_path: Path) -> None:
        config = load_config(tmp_path)
        assert isinstance(config, LucidScanConfig)
        assert config.fail_on is None

    def test_loads_project_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidscan.yml"
        config_file.write_text("fail_on: high")
        config = load_config(tmp_path)
        assert config.fail_on == "high"

    def test_cli_overrides_take_precedence(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidscan.yml"
        config_file.write_text("fail_on: low")
        config = load_config(
            tmp_path,
            cli_overrides={"fail_on": "critical"},
        )
        assert config.fail_on == "critical"

    def test_custom_config_path(self, tmp_path: Path) -> None:
        custom_config = tmp_path / "custom.yml"
        custom_config.write_text("fail_on: medium")
        config = load_config(tmp_path, cli_config_path=custom_config)
        assert config.fail_on == "medium"

    def test_raises_for_missing_custom_config(self, tmp_path: Path) -> None:
        missing_config = tmp_path / "missing.yml"
        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path, cli_config_path=missing_config)
        assert "not found" in str(exc_info.value)

    def test_tracks_config_sources(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidscan.yml"
        config_file.write_text("fail_on: high")
        config = load_config(tmp_path, cli_overrides={"ignore": ["*.md"]})
        assert any("project" in s for s in config._config_sources)
        assert "cli" in config._config_sources

    def test_env_vars_expanded_in_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidscan.yml"
        config_file.write_text(
            "scanners:\n"
            "  sca:\n"
            "    api_token: ${TEST_TOKEN}\n"
        )
        with patch.dict(os.environ, {"TEST_TOKEN": "secret123"}):
            config = load_config(tmp_path)
        assert config.scanners["sca"].options["api_token"] == "secret123"


class TestLoadConfigMerging:
    """Tests for config merging behavior."""

    def test_scanner_options_merged(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidscan.yml"
        config_file.write_text(
            "scanners:\n"
            "  sca:\n"
            "    enabled: true\n"
            "    ignore_unfixed: true\n"
        )
        config = load_config(
            tmp_path,
            cli_overrides={
                "scanners": {
                    "sca": {"severity": ["HIGH", "CRITICAL"]},
                }
            },
        )
        # Both file config and CLI override should be present
        sca_config = config.scanners["sca"]
        assert sca_config.enabled is True
        assert sca_config.options.get("ignore_unfixed") is True
        assert sca_config.options.get("severity") == ["HIGH", "CRITICAL"]
