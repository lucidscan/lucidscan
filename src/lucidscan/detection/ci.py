"""CI/CD system detection module.

Detects CI/CD systems by looking for configuration files:
- GitHub Actions (.github/workflows/)
- GitLab CI (.gitlab-ci.yml)
- Bitbucket Pipelines (bitbucket-pipelines.yml)
- CircleCI (.circleci/config.yml)
- Travis CI (.travis.yml)
- Jenkins (Jenkinsfile)
- Azure Pipelines (azure-pipelines.yml)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

# CI system detection definitions
# Format: system_name -> (files/directories to check)
CI_SYSTEMS: Dict[str, Dict[str, Any]] = {
    "github_actions": {
        "type": "directory",
        "paths": [".github/workflows"],
        "display_name": "GitHub Actions",
    },
    "gitlab_ci": {
        "type": "file",
        "paths": [".gitlab-ci.yml"],
        "display_name": "GitLab CI",
    },
    "bitbucket_pipelines": {
        "type": "file",
        "paths": ["bitbucket-pipelines.yml"],
        "display_name": "Bitbucket Pipelines",
    },
    "circleci": {
        "type": "file",
        "paths": [".circleci/config.yml"],
        "display_name": "CircleCI",
    },
    "travis": {
        "type": "file",
        "paths": [".travis.yml"],
        "display_name": "Travis CI",
    },
    "jenkins": {
        "type": "file",
        "paths": ["Jenkinsfile"],
        "display_name": "Jenkins",
    },
    "azure_pipelines": {
        "type": "file",
        "paths": ["azure-pipelines.yml", ".azure-pipelines.yml"],
        "display_name": "Azure Pipelines",
    },
    "drone": {
        "type": "file",
        "paths": [".drone.yml"],
        "display_name": "Drone CI",
    },
    "buildkite": {
        "type": "file",
        "paths": [".buildkite/pipeline.yml", "buildkite.yml"],
        "display_name": "Buildkite",
    },
}


def detect_ci_systems(project_root: Path) -> list[str]:
    """Detect CI/CD systems configured in a project.

    Args:
        project_root: Path to the project root directory.

    Returns:
        List of detected CI system identifiers.
    """
    detected = []

    for system_id, config in CI_SYSTEMS.items():
        check_type = config["type"]

        for path in config["paths"]:
            full_path = project_root / path

            if check_type == "directory":
                # Check if directory exists and has files
                if full_path.is_dir() and any(full_path.iterdir()):
                    detected.append(system_id)
                    break
            else:
                # Check if file exists
                if full_path.is_file():
                    detected.append(system_id)
                    break

    return detected


def get_ci_display_name(system_id: str) -> str:
    """Get the display name for a CI system.

    Args:
        system_id: CI system identifier.

    Returns:
        Human-readable display name.
    """
    if system_id in CI_SYSTEMS:
        return CI_SYSTEMS[system_id]["display_name"]
    return system_id.replace("_", " ").title()
