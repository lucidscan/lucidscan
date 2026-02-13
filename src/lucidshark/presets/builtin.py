"""Built-in preset definitions for LucidShark.

Each preset is a dictionary that follows the lucidshark.yml schema.
Presets can be merged with user configuration using the config loader.
"""

from typing import Any, Dict

# Preset metadata (name -> description)
PRESET_DESCRIPTIONS: Dict[str, str] = {
    "python-strict": "Production Python setup with strict linting, type checking, testing, coverage, and security",
    "python-minimal": "Quick Python setup with basic linting and security scanning",
    "typescript-strict": "Production TypeScript/React setup with ESLint, type checking, and security",
    "typescript-minimal": "Quick TypeScript setup with basic linting and security",
    "minimal": "Minimal setup - security scanning only (SCA + SAST)",
}

# Python strict preset - comprehensive Python quality checks
PYTHON_STRICT: Dict[str, Any] = {
    "project": {
        "languages": ["python"],
    },
    "pipeline": {
        "linting": {
            "enabled": True,
            "tools": [{"name": "ruff"}],
        },
        "type_checking": {
            "enabled": True,
            "tools": [{"name": "mypy", "strict": True}],
        },
        "testing": {
            "enabled": True,
            "tools": [{"name": "pytest"}],
        },
        "coverage": {
            "enabled": True,
            "threshold": 80,
            "tools": [{"name": "coverage_py"}],
        },
        "security": {
            "enabled": True,
            "tools": [
                {"name": "trivy", "domains": ["sca"]},
                {"name": "opengrep", "domains": ["sast"]},
            ],
        },
        "duplication": {
            "enabled": True,
            "threshold": 5.0,
            "min_lines": 7,
        },
    },
    "fail_on": {
        "linting": "error",
        "type_checking": "error",
        "security": "high",
        "testing": "any",
        "coverage": "below_threshold",
        "duplication": "above_threshold",
    },
    "ignore": [
        "**/__pycache__/**",
        "**/.venv/**",
        "**/venv/**",
        "**/.pytest_cache/**",
        "**/.mypy_cache/**",
        "**/.ruff_cache/**",
        "**/dist/**",
        "**/build/**",
        "**/*.egg-info/**",
    ],
}

# Python minimal preset - quick setup
PYTHON_MINIMAL: Dict[str, Any] = {
    "project": {
        "languages": ["python"],
    },
    "pipeline": {
        "linting": {
            "enabled": True,
            "tools": [{"name": "ruff"}],
        },
        "type_checking": {
            "enabled": True,
            "tools": [{"name": "mypy"}],
        },
        "security": {
            "enabled": True,
            "tools": [
                {"name": "trivy", "domains": ["sca"]},
                {"name": "opengrep", "domains": ["sast"]},
            ],
        },
    },
    "fail_on": {
        "linting": "error",
        "type_checking": "error",
        "security": "high",
    },
    "ignore": [
        "**/__pycache__/**",
        "**/.venv/**",
        "**/venv/**",
    ],
}

# TypeScript strict preset - comprehensive TypeScript/React setup
TYPESCRIPT_STRICT: Dict[str, Any] = {
    "project": {
        "languages": ["typescript", "javascript"],
    },
    "pipeline": {
        "linting": {
            "enabled": True,
            "tools": [{"name": "eslint"}],
        },
        "type_checking": {
            "enabled": True,
            "tools": [{"name": "typescript"}],
        },
        "testing": {
            "enabled": True,
            "tools": [{"name": "jest"}],
        },
        "coverage": {
            "enabled": True,
            "threshold": 80,
            "tools": [{"name": "istanbul"}],
        },
        "security": {
            "enabled": True,
            "tools": [
                {"name": "trivy", "domains": ["sca"]},
                {"name": "opengrep", "domains": ["sast"]},
            ],
        },
    },
    "fail_on": {
        "linting": "error",
        "type_checking": "error",
        "security": "high",
        "testing": "any",
        "coverage": "below_threshold",
    },
    "ignore": [
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.next/**",
        "**/coverage/**",
    ],
}

# TypeScript minimal preset - quick setup
TYPESCRIPT_MINIMAL: Dict[str, Any] = {
    "project": {
        "languages": ["typescript", "javascript"],
    },
    "pipeline": {
        "linting": {
            "enabled": True,
            "tools": [{"name": "eslint"}],
        },
        "type_checking": {
            "enabled": True,
            "tools": [{"name": "typescript"}],
        },
        "security": {
            "enabled": True,
            "tools": [
                {"name": "trivy", "domains": ["sca"]},
                {"name": "opengrep", "domains": ["sast"]},
            ],
        },
    },
    "fail_on": {
        "linting": "error",
        "type_checking": "error",
        "security": "high",
    },
    "ignore": [
        "**/node_modules/**",
        "**/dist/**",
    ],
}

# Minimal preset - security only
MINIMAL: Dict[str, Any] = {
    "pipeline": {
        "security": {
            "enabled": True,
            "tools": [
                {"name": "trivy", "domains": ["sca"]},
                {"name": "opengrep", "domains": ["sast"]},
            ],
        },
    },
    "fail_on": {
        "security": "high",
    },
    "ignore": [
        "**/.git/**",
        "**/node_modules/**",
        "**/__pycache__/**",
        "**/.venv/**",
    ],
}

# Map preset names to their configurations
BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "python-strict": PYTHON_STRICT,
    "python-minimal": PYTHON_MINIMAL,
    "typescript-strict": TYPESCRIPT_STRICT,
    "typescript-minimal": TYPESCRIPT_MINIMAL,
    "minimal": MINIMAL,
}
