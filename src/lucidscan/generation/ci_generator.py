"""CI/CD configuration generator.

Generates CI pipeline configurations for:
- GitHub Actions
- GitLab CI
- Bitbucket Pipelines
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lucidscan.detection import ProjectContext
from lucidscan.generation.config_generator import InitChoices


class CIGenerator:
    """Generates CI/CD pipeline configuration files."""

    def generate_github_actions(
        self,
        context: ProjectContext,
        choices: InitChoices,
    ) -> str:
        """Generate GitHub Actions workflow.

        Args:
            context: Detected project context.
            choices: User initialization choices.

        Returns:
            YAML string for GitHub Actions workflow.
        """
        # Determine Python version
        python_version = "3.11"
        for lang in context.languages:
            if lang.name == "python" and lang.version:
                python_version = lang.version
                break

        workflow = {
            "name": "LucidScan",
            "on": {
                "push": {"branches": ["main", "master"]},
                "pull_request": None,
            },
            "jobs": {
                "quality": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {
                            "name": "Set up Python",
                            "uses": "actions/setup-python@v5",
                            "with": {"python-version": python_version},
                        },
                        {
                            "name": "Install LucidScan",
                            "run": "pip install lucidscan",
                        },
                        {
                            "name": "Run LucidScan",
                            "run": self._build_scan_command(choices, "github"),
                        },
                    ],
                },
            },
        }

        # Add SARIF upload if security is enabled
        if choices.security_enabled:
            workflow["jobs"]["quality"]["steps"].append({  # type: ignore[index]
                "name": "Upload SARIF",
                "uses": "github/codeql-action/upload-sarif@v3",
                "if": "always()",
                "with": {"sarif_file": "lucidscan-results.sarif"},
            })
            # Modify scan command to output SARIF
            for step in workflow["jobs"]["quality"]["steps"]:  # type: ignore[index]
                if step.get("name") == "Run LucidScan":
                    step["run"] = step["run"] + " --format sarif > lucidscan-results.sarif"

        return self._to_yaml(workflow, header="# LucidScan GitHub Actions Workflow\n")

    def generate_gitlab_ci(
        self,
        context: ProjectContext,
        choices: InitChoices,
    ) -> str:
        """Generate GitLab CI configuration.

        Args:
            context: Detected project context.
            choices: User initialization choices.

        Returns:
            YAML string for GitLab CI.
        """
        # Determine Python version
        python_version = "3.11"
        for lang in context.languages:
            if lang.name == "python" and lang.version:
                python_version = lang.version
                break

        config = {
            "lucidscan": {
                "stage": "test",
                "image": f"python:{python_version}",
                "script": [
                    "pip install lucidscan",
                    self._build_scan_command(choices, "gitlab"),
                ],
                "rules": [
                    {"if": '$CI_PIPELINE_SOURCE == "merge_request_event"'},
                    {"if": "$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH"},
                ],
            },
        }

        return self._to_yaml(config, header="# LucidScan GitLab CI Configuration\n")

    def generate_bitbucket_pipelines(
        self,
        context: ProjectContext,
        choices: InitChoices,
    ) -> str:
        """Generate Bitbucket Pipelines configuration.

        Args:
            context: Detected project context.
            choices: User initialization choices.

        Returns:
            YAML string for Bitbucket Pipelines.
        """
        # Determine Python version
        python_version = "3.11"
        for lang in context.languages:
            if lang.name == "python" and lang.version:
                python_version = lang.version
                break

        config = {
            "definitions": {
                "steps": [
                    {
                        "step": {
                            "name": "LucidScan",
                            "image": f"python:{python_version}",
                            "script": [
                                "pip install lucidscan",
                                self._build_scan_command(choices, "bitbucket"),
                            ],
                            "caches": ["pip"],
                        },
                    },
                ],
            },
            "pipelines": {
                "default": [{"step": "*lucidscan"}],
                "pull-requests": {"**": [{"step": "*lucidscan"}]},
            },
        }

        return self._to_yaml(
            config,
            header="# LucidScan Bitbucket Pipelines Configuration\n",
        )

    def write_github_actions(
        self,
        context: ProjectContext,
        choices: InitChoices,
    ) -> Path:
        """Write GitHub Actions workflow file.

        Args:
            context: Detected project context.
            choices: User initialization choices.

        Returns:
            Path to the written file.
        """
        workflows_dir = context.root / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        output_path = workflows_dir / "lucidscan.yml"
        content = self.generate_github_actions(context, choices)
        output_path.write_text(content)

        return output_path

    def write_gitlab_ci(
        self,
        context: ProjectContext,
        choices: InitChoices,
        merge: bool = False,
    ) -> Path:
        """Write GitLab CI configuration.

        Args:
            context: Detected project context.
            choices: User initialization choices.
            merge: If True, merge with existing .gitlab-ci.yml.

        Returns:
            Path to the written file.
        """
        output_path = context.root / ".gitlab-ci.yml"
        content = self.generate_gitlab_ci(context, choices)

        if merge and output_path.exists():
            # TODO: Implement YAML merging for existing configs
            pass

        output_path.write_text(content)
        return output_path

    def write_bitbucket_pipelines(
        self,
        context: ProjectContext,
        choices: InitChoices,
        merge: bool = False,
    ) -> Path:
        """Write Bitbucket Pipelines configuration.

        Args:
            context: Detected project context.
            choices: User initialization choices.
            merge: If True, merge with existing bitbucket-pipelines.yml.

        Returns:
            Path to the written file.
        """
        output_path = context.root / "bitbucket-pipelines.yml"
        content = self.generate_bitbucket_pipelines(context, choices)

        if merge and output_path.exists():
            # TODO: Implement YAML merging for existing configs
            pass

        output_path.write_text(content)
        return output_path

    def _build_scan_command(self, choices: InitChoices, platform: str) -> str:
        """Build the lucidscan scan command.

        Args:
            choices: User initialization choices.
            platform: CI platform name.

        Returns:
            Scan command string.
        """
        parts = ["lucidscan", "scan"]

        # Add domain flags based on choices
        domains = []
        if choices.linter:
            domains.append("--lint")
        if choices.security_enabled:
            domains.append("--sca")
            domains.append("--sast")
        if choices.test_runner:
            # Testing is handled separately in CI usually
            pass

        if domains:
            parts.extend(domains)
        else:
            parts.append("--all")

        # Add fail threshold
        if choices.fail_on_security != "none":
            parts.extend(["--fail-on", choices.fail_on_security])

        return " ".join(parts)

    def _to_yaml(self, config: dict, header: str = "") -> str:
        """Convert config dict to YAML string.

        Args:
            config: Configuration dictionary.
            header: Optional header comment.

        Returns:
            YAML string.
        """
        yaml_content = yaml.dump(
            config,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

        return header + yaml_content
