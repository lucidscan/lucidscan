"""Preset configurations for LucidShark.

Presets provide pre-configured setups for common project types,
reducing the time to get started with LucidShark.
"""

from lucidshark.presets.registry import (
    get_preset,
    get_preset_names,
    get_preset_description,
    PRESETS,
)

__all__ = [
    "get_preset",
    "get_preset_names",
    "get_preset_description",
    "PRESETS",
]
