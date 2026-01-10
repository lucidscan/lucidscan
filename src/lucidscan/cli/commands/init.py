"""Init command implementation.

Opinionated project initialization that:
1. Detects project characteristics
2. Auto-selects recommended tools when none are detected
3. Installs tools to package manager files
4. Generates lucidscan.yml configuration
5. Optionally generates CI configuration
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from lucidscan.config.models import LucidScanConfig

import questionary
from questionary import Style

from lucidscan.cli.commands import Command
from lucidscan.cli.exit_codes import EXIT_SUCCESS, EXIT_INVALID_USAGE
from lucidscan.core.logging import get_logger
from lucidscan.detection import CodebaseDetector, ProjectContext
from lucidscan.detection.ci import get_ci_display_name
from lucidscan.generation import ConfigGenerator, CIGenerator, InitChoices, PackageInstaller

LOGGER = get_logger(__name__)

# Custom questionary style
STYLE = Style([
    ("qmark", "fg:cyan bold"),
    ("question", "bold"),
    ("answer", "fg:cyan"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan bold"),
    ("selected", "fg:green"),
    ("separator", "fg:gray"),
    ("instruction", "fg:gray"),
])

# Opinionated defaults - tools to use when none are detected
PYTHON_DEFAULT_LINTER = "ruff"
PYTHON_DEFAULT_TYPE_CHECKER = "mypy"
PYTHON_DEFAULT_TEST_RUNNER = "pytest"
JS_DEFAULT_LINTER = "eslint"
JS_DEFAULT_TYPE_CHECKER = "typescript"
JS_DEFAULT_TEST_RUNNER = "jest"


class InitCommand(Command):
    """Opinionated project initialization command."""

    @property
    def name(self) -> str:
        """Command identifier."""
        return "init"

    def execute(self, args: Namespace, config: "LucidScanConfig | None" = None) -> int:
        """Execute the init command.

        Args:
            args: Parsed command-line arguments.
            config: Optional LucidScan configuration (unused).

        Returns:
            Exit code.
        """
        project_root = Path(args.path).resolve()

        if not project_root.is_dir():
            print(f"Error: {project_root} is not a directory")
            return EXIT_INVALID_USAGE

        # Check for existing config
        config_path = project_root / "lucidscan.yml"
        if config_path.exists() and not args.force:
            if args.non_interactive:
                print(f"Error: {config_path} already exists. Use --force to overwrite.")
                return EXIT_INVALID_USAGE

            overwrite = questionary.confirm(
                "lucidscan.yml already exists. Overwrite?",
                default=False,
                style=STYLE,
            ).ask()

            if not overwrite:
                print("Aborted.")
                return EXIT_SUCCESS

        # Detect project
        print("\nAnalyzing project...\n")
        detector = CodebaseDetector()
        context = detector.detect(project_root)

        # Display detection results
        self._display_detection(context)

        # Get opinionated choices (auto-select tools)
        choices = self._get_opinionated_choices(context, args)

        # In interactive mode, only ask about CI platform
        if not args.non_interactive:
            ci_choice, cancelled = self._prompt_ci_platform(context, args)
            if cancelled:
                print("\nAborted.")
                return EXIT_SUCCESS
            choices.ci_platform = ci_choice

        # Display what will be configured
        print("\nConfiguration:")
        self._display_choices(choices, context)

        # In interactive mode, confirm before proceeding
        if not args.non_interactive:
            proceed = questionary.confirm(
                "Proceed with this configuration?",
                default=True,
                style=STYLE,
            ).ask()

            if not proceed:
                print("\nAborted.")
                return EXIT_SUCCESS

        # Install tools to package files
        tools_to_install = self._get_tools_to_install(choices, context)
        if tools_to_install:
            print("\nInstalling tools...")
            installer = PackageInstaller()
            installed = installer.install_tools(context, tools_to_install)

            for tool, path in installed.items():
                rel_path = path.relative_to(project_root)
                print(f"  Added {tool} to {rel_path}")

            if installed:
                # Show install command hint
                if context.has_python:
                    print("\n  Run: pip install -e '.[dev]' to install tools")
                if context.has_javascript:
                    print("\n  Run: npm install to install tools")

        # Generate configuration
        print("\nGenerating configuration...")

        config_gen = ConfigGenerator()
        config_path = config_gen.write(context, choices)
        print(f"  Created {config_path.relative_to(project_root)}")

        # Generate CI config if requested
        ci_path = None
        if choices.ci_platform:
            ci_gen = CIGenerator()
            if choices.ci_platform == "github":
                ci_path = ci_gen.write_github_actions(context, choices)
            elif choices.ci_platform == "gitlab":
                ci_path = ci_gen.write_gitlab_ci(context, choices)
            elif choices.ci_platform == "bitbucket":
                ci_path = ci_gen.write_bitbucket_pipelines(context, choices)

            if ci_path:
                print(f"  Created {ci_path.relative_to(project_root)}")

        # Summary
        print("\nDone! Next steps:")
        print("  1. Review the generated lucidscan.yml")
        print("  2. Run 'lucidscan scan --all' to test the configuration")
        if ci_path:
            print("  3. Commit the CI configuration to enable automated checks")

        return EXIT_SUCCESS

    def _display_detection(self, context: ProjectContext) -> None:
        """Display detected project characteristics."""
        print("Detected:")

        # Languages
        if context.languages:
            langs = []
            for lang in context.languages[:3]:  # Show top 3
                version = f" {lang.version}" if lang.version else ""
                langs.append(f"{lang.name.title()}{version}")
            print(f"  Languages:    {', '.join(langs)}")
        else:
            print("  Languages:    (none detected)")

        # Frameworks
        if context.frameworks:
            print(f"  Frameworks:   {', '.join(context.frameworks[:3])}")

        # Test frameworks
        if context.test_frameworks:
            print(f"  Testing:      {', '.join(context.test_frameworks)}")

        # Existing tools
        if context.existing_tools:
            tools = list(context.existing_tools.keys())[:5]
            print(f"  Tools:        {', '.join(tools)}")

        # CI systems
        if context.ci_systems:
            ci_names = [get_ci_display_name(ci) for ci in context.ci_systems]
            print(f"  CI:           {', '.join(ci_names)}")

        print()

    def _get_opinionated_choices(
        self,
        context: ProjectContext,
        args: Namespace,
    ) -> InitChoices:
        """Get opinionated default choices.

        This method auto-selects tools based on the detected project.
        If tools are already detected, use them. Otherwise, pick our
        recommended defaults.

        Args:
            context: Detected project context.
            args: Parsed command-line arguments.

        Returns:
            InitChoices with opinionated defaults.
        """
        choices = InitChoices()

        # Linter: use detected or default
        if context.has_python:
            if "ruff" in context.existing_tools:
                choices.linter = "ruff"
            else:
                choices.linter = PYTHON_DEFAULT_LINTER
        elif context.has_javascript:
            if "eslint" in context.existing_tools:
                choices.linter = "eslint"
            elif "biome" in context.existing_tools:
                choices.linter = "biome"
            else:
                choices.linter = JS_DEFAULT_LINTER

        # Type checker: use detected or default
        if context.has_python:
            if "mypy" in context.existing_tools:
                choices.type_checker = "mypy"
            elif "pyright" in context.existing_tools:
                choices.type_checker = "pyright"
            else:
                choices.type_checker = PYTHON_DEFAULT_TYPE_CHECKER
        elif context.has_javascript:
            if "typescript" in context.existing_tools:
                choices.type_checker = "typescript"
            else:
                choices.type_checker = JS_DEFAULT_TYPE_CHECKER

        # Security always enabled
        choices.security_enabled = True
        choices.security_tools = ["trivy", "opengrep"]

        # Test runner: use detected or default
        if context.test_frameworks:
            choices.test_runner = context.test_frameworks[0]
        elif context.has_python:
            choices.test_runner = PYTHON_DEFAULT_TEST_RUNNER
        elif context.has_javascript:
            choices.test_runner = JS_DEFAULT_TEST_RUNNER

        # CI from args or detection
        if args.ci:
            choices.ci_platform = args.ci
        elif context.ci_systems:
            ci_map = {
                "github_actions": "github",
                "gitlab_ci": "gitlab",
                "bitbucket_pipelines": "bitbucket",
            }
            for ci in context.ci_systems:
                if ci in ci_map:
                    choices.ci_platform = ci_map[ci]
                    break

        return choices

    def _prompt_ci_platform(
        self,
        context: ProjectContext,
        args: Namespace,
    ) -> Tuple[Optional[str], bool]:
        """Prompt user for CI platform choice.

        This is the only prompt in interactive mode - everything else
        is auto-selected.

        Args:
            context: Detected project context.
            args: Parsed command-line arguments.

        Returns:
            Tuple of (CI platform string or None, cancelled flag).
            cancelled is True if user pressed Ctrl+C.
        """
        if args.ci:
            return args.ci, False

        options = []

        # Check if CI systems are already detected
        if "github_actions" in context.ci_systems:
            options.append(questionary.Choice("GitHub Actions (detected)", value="github"))
        else:
            options.append(questionary.Choice("GitHub Actions (recommended)", value="github"))

        if "gitlab_ci" in context.ci_systems:
            options.append(questionary.Choice("GitLab CI (detected)", value="gitlab"))
        else:
            options.append(questionary.Choice("GitLab CI", value="gitlab"))

        if "bitbucket_pipelines" in context.ci_systems:
            options.append(questionary.Choice("Bitbucket Pipelines (detected)", value="bitbucket"))
        else:
            options.append(questionary.Choice("Bitbucket Pipelines", value="bitbucket"))

        options.append(questionary.Choice("Skip CI configuration", value="skip"))

        result = questionary.select(
            "CI platform:",
            choices=options,
            style=STYLE,
        ).ask()

        # result is None if user pressed Ctrl+C
        if result is None:
            return None, True

        # "skip" means user chose to skip CI
        if result == "skip":
            return None, False

        return result, False

    def _display_choices(self, choices: InitChoices, context: ProjectContext) -> None:
        """Display the tools that will be configured."""
        items = []

        if choices.linter:
            status = "(detected)" if choices.linter in context.existing_tools else "(will install)"
            items.append(f"  Linter:       {choices.linter} {status}")

        if choices.type_checker:
            status = "(detected)" if choices.type_checker in context.existing_tools else "(will install)"
            items.append(f"  Type checker: {choices.type_checker} {status}")

        if choices.security_enabled:
            items.append(f"  Security:     {', '.join(choices.security_tools)}")

        if choices.test_runner:
            status = "(detected)" if choices.test_runner in context.test_frameworks else "(will install)"
            items.append(f"  Test runner:  {choices.test_runner} {status}")

        if choices.ci_platform:
            items.append(f"  CI platform:  {choices.ci_platform}")

        for item in items:
            print(item)

    def _get_tools_to_install(
        self,
        choices: InitChoices,
        context: ProjectContext,
    ) -> List[str]:
        """Get list of tools that need to be installed.

        Only returns tools that are not already detected in the project.

        Args:
            choices: Selected tool choices.
            context: Detected project context.

        Returns:
            List of tool names to install.
        """
        tools = []

        # Linter
        if choices.linter and choices.linter not in context.existing_tools:
            tools.append(choices.linter)

        # Type checker
        if choices.type_checker and choices.type_checker not in context.existing_tools:
            tools.append(choices.type_checker)

        # Test runner
        if choices.test_runner and choices.test_runner not in context.test_frameworks:
            tools.append(choices.test_runner)

        return tools
