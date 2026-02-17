"""Tests for lucidshark.presets (registry, builtin, __init__)."""

from __future__ import annotations


from lucidshark.presets import (
    PRESETS,
    get_preset,
    get_preset_description,
    get_preset_names,
)
from lucidshark.presets.builtin import (
    BUILTIN_PRESETS,
    MINIMAL,
    PRESET_DESCRIPTIONS,
    PYTHON_MINIMAL,
    PYTHON_STRICT,
    TYPESCRIPT_MINIMAL,
    TYPESCRIPT_STRICT,
)
from lucidshark.presets.registry import is_valid_preset, register_preset


# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------


class TestBuiltinPresets:
    """Verify structure and content of built-in preset configurations."""

    def test_all_builtin_presets_registered(self) -> None:
        expected = {
            "python-strict",
            "python-minimal",
            "typescript-strict",
            "typescript-minimal",
            "minimal",
        }
        assert set(BUILTIN_PRESETS.keys()) == expected

    def test_all_presets_have_descriptions(self) -> None:
        for name in BUILTIN_PRESETS:
            assert name in PRESET_DESCRIPTIONS, f"Missing description for preset: {name}"

    def test_python_strict_has_required_domains(self) -> None:
        pipeline = PYTHON_STRICT["pipeline"]
        assert pipeline["linting"]["enabled"] is True
        assert pipeline["type_checking"]["enabled"] is True
        assert pipeline["testing"]["enabled"] is True
        assert pipeline["coverage"]["enabled"] is True
        assert pipeline["security"]["enabled"] is True
        assert pipeline["duplication"]["enabled"] is True

    def test_python_strict_has_fail_on(self) -> None:
        fail_on = PYTHON_STRICT["fail_on"]
        assert "linting" in fail_on
        assert "security" in fail_on
        assert "testing" in fail_on
        assert "coverage" in fail_on

    def test_python_strict_has_ignore(self) -> None:
        assert len(PYTHON_STRICT["ignore"]) > 0
        # Typical Python ignores
        patterns = PYTHON_STRICT["ignore"]
        assert any("__pycache__" in p for p in patterns)
        assert any(".venv" in p for p in patterns)

    def test_python_minimal_lighter_than_strict(self) -> None:
        """Minimal preset should have fewer domains enabled."""
        minimal_pipeline = PYTHON_MINIMAL["pipeline"]
        # Minimal should not have testing, coverage, or duplication
        assert "testing" not in minimal_pipeline
        assert "coverage" not in minimal_pipeline
        assert "duplication" not in minimal_pipeline
        # But should have linting and security
        assert minimal_pipeline["linting"]["enabled"] is True
        assert minimal_pipeline["security"]["enabled"] is True

    def test_typescript_strict_has_required_domains(self) -> None:
        pipeline = TYPESCRIPT_STRICT["pipeline"]
        assert pipeline["linting"]["enabled"] is True
        assert pipeline["type_checking"]["enabled"] is True
        assert pipeline["testing"]["enabled"] is True
        assert pipeline["coverage"]["enabled"] is True
        assert pipeline["security"]["enabled"] is True

    def test_typescript_strict_uses_eslint(self) -> None:
        pipeline = TYPESCRIPT_STRICT["pipeline"]
        linting_tools = pipeline["linting"]["tools"]
        assert any(t["name"] == "eslint" for t in linting_tools)

    def test_typescript_minimal_has_security(self) -> None:
        pipeline = TYPESCRIPT_MINIMAL["pipeline"]
        assert pipeline["security"]["enabled"] is True

    def test_typescript_presets_ignore_node_modules(self) -> None:
        for preset in [TYPESCRIPT_STRICT, TYPESCRIPT_MINIMAL]:
            assert any("node_modules" in p for p in preset["ignore"])

    def test_minimal_is_security_only(self) -> None:
        pipeline = MINIMAL["pipeline"]
        assert "security" in pipeline
        assert pipeline["security"]["enabled"] is True
        # Should not have linting, type_checking, testing
        assert "linting" not in pipeline
        assert "type_checking" not in pipeline
        assert "testing" not in pipeline

    def test_minimal_has_trivy_and_opengrep(self) -> None:
        tools = MINIMAL["pipeline"]["security"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "trivy" in tool_names
        assert "opengrep" in tool_names

    def test_presets_have_languages_where_expected(self) -> None:
        assert PYTHON_STRICT["project"]["languages"] == ["python"]
        assert PYTHON_MINIMAL["project"]["languages"] == ["python"]
        assert "typescript" in TYPESCRIPT_STRICT["project"]["languages"]
        assert "typescript" in TYPESCRIPT_MINIMAL["project"]["languages"]
        # Minimal has no project section at all
        assert "project" not in MINIMAL


# ---------------------------------------------------------------------------
# Registry functions
# ---------------------------------------------------------------------------


class TestPresetRegistry:
    """Tests for the preset registry functions."""

    def test_get_preset_names_returns_all(self) -> None:
        names = get_preset_names()
        assert "python-strict" in names
        assert "minimal" in names
        assert len(names) >= 5

    def test_get_preset_returns_copy(self) -> None:
        preset = get_preset("python-strict")
        assert preset is not None
        # Mutating the returned copy should not affect the original
        preset["pipeline"]["linting"]["enabled"] = False
        original = PRESETS["python-strict"]
        assert original["pipeline"]["linting"]["enabled"] is True

    def test_get_preset_unknown_returns_none(self) -> None:
        assert get_preset("nonexistent-preset") is None

    def test_get_preset_description(self) -> None:
        desc = get_preset_description("python-strict")
        assert desc is not None
        assert "Python" in desc

    def test_get_preset_description_unknown(self) -> None:
        assert get_preset_description("nonexistent") is None

    def test_is_valid_preset(self) -> None:
        assert is_valid_preset("python-strict") is True
        assert is_valid_preset("minimal") is True
        assert is_valid_preset("does-not-exist") is False

    def test_register_preset(self) -> None:
        custom_config = {"pipeline": {"linting": {"enabled": True}}}
        register_preset("test-custom", custom_config, "A test preset")

        assert is_valid_preset("test-custom")
        assert get_preset("test-custom") is not None
        assert get_preset_description("test-custom") == "A test preset"

        # Clean up
        PRESETS.pop("test-custom", None)
        PRESET_DESCRIPTIONS.pop("test-custom", None)

    def test_register_preset_without_description(self) -> None:
        custom_config: dict[str, dict[str, object]] = {"pipeline": {}}
        register_preset("test-no-desc", custom_config)

        assert is_valid_preset("test-no-desc")
        assert get_preset_description("test-no-desc") is None

        # Clean up
        PRESETS.pop("test-no-desc", None)

    def test_register_preset_deep_copies(self) -> None:
        original = {"pipeline": {"nested": {"key": "value"}}}
        register_preset("test-deepcopy", original)

        # Mutating original should not affect registered
        original["pipeline"]["nested"]["key"] = "changed"
        registered = get_preset("test-deepcopy")
        assert registered is not None
        assert registered["pipeline"]["nested"]["key"] == "value"

        # Clean up
        PRESETS.pop("test-deepcopy", None)

    def test_presets_global_is_deep_copy_of_builtin(self) -> None:
        """PRESETS should be independent of BUILTIN_PRESETS."""
        assert PRESETS is not BUILTIN_PRESETS
        # Keys match
        assert set(PRESETS.keys()) >= set(BUILTIN_PRESETS.keys())


# ---------------------------------------------------------------------------
# __init__.py re-exports
# ---------------------------------------------------------------------------


class TestPresetsInit:
    """Verify that __init__.py re-exports work correctly."""

    def test_get_preset_accessible(self) -> None:
        from lucidshark.presets import get_preset
        assert callable(get_preset)

    def test_get_preset_names_accessible(self) -> None:
        from lucidshark.presets import get_preset_names
        assert callable(get_preset_names)

    def test_get_preset_description_accessible(self) -> None:
        from lucidshark.presets import get_preset_description
        assert callable(get_preset_description)

    def test_presets_dict_accessible(self) -> None:
        from lucidshark.presets import PRESETS
        assert isinstance(PRESETS, dict)
