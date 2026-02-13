"""Preset registry for LucidShark.

Manages preset loading and provides access to built-in presets.
"""

from typing import Any, Dict, List, Optional
import copy

from lucidshark.presets.builtin import BUILTIN_PRESETS, PRESET_DESCRIPTIONS


# All available presets (can be extended at runtime)
PRESETS: Dict[str, Dict[str, Any]] = copy.deepcopy(BUILTIN_PRESETS)


def get_preset_names() -> List[str]:
    """Get list of all available preset names.

    Returns:
        List of preset names.
    """
    return list(PRESETS.keys())


def get_preset(name: str) -> Optional[Dict[str, Any]]:
    """Get a preset configuration by name.

    Returns a deep copy of the preset to avoid mutation.

    Args:
        name: Preset name (e.g., "python-strict", "minimal").

    Returns:
        Preset configuration dict or None if not found.
    """
    preset = PRESETS.get(name)
    if preset is not None:
        return copy.deepcopy(preset)
    return None


def get_preset_description(name: str) -> Optional[str]:
    """Get the description of a preset.

    Args:
        name: Preset name.

    Returns:
        Description string or None if preset not found.
    """
    return PRESET_DESCRIPTIONS.get(name)


def register_preset(name: str, config: Dict[str, Any], description: str = "") -> None:
    """Register a custom preset.

    Allows extending the preset registry with custom presets at runtime.

    Args:
        name: Preset name.
        config: Preset configuration dict.
        description: Optional description for the preset.
    """
    PRESETS[name] = copy.deepcopy(config)
    if description:
        PRESET_DESCRIPTIONS[name] = description


def is_valid_preset(name: str) -> bool:
    """Check if a preset name is valid.

    Args:
        name: Preset name to check.

    Returns:
        True if preset exists, False otherwise.
    """
    return name in PRESETS
