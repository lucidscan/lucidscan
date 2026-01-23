"""Autoconfigure command implementation.

Opinionated project autoconfiguration that:
1. Detects project characteristics
2. Auto-selects recommended tools when none are detected
3. Installs tools to package manager files
4. Generates lucidshark.yml configuration
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from lucidshark.config.models import LucidSharkConfig

import questionary
from questionary import Style

from lucidshark.cli.commands import Command
from lucidshark.cli.exit_codes import EXIT_SUCCESS, EXIT_INVALID_USAGE
from lucidshark.core.logging import get_logger
from lucidshark.detection import CodebaseDetector, ProjectContext
from lucidshark.generation import ConfigGenerator, InitChoices, PackageInstaller

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


class AutoconfigureCommand(Command):
    """Opinionated project autoconfiguration command."""

    @property
    def name(self) -> str:
        """Command identifier."""
        return "autoconfigure"

    def execute(self, args: Namespace, config: "LucidSharkConfig | None" = None) -> int:
        """Execute the autoconfigure command.

        Args:
            args: Parsed command-line arguments.
            config: Optional LucidShark configuration (unused).

        Returns:
            Exit code.
        """
        project_root = Path(args.path).resolve()

        if not project_root.is_dir():
            print(f"Error: {project_root} is not a directory")
            return EXIT_INVALID_USAGE

        # Check for existing config
        config_path = project_root / "lucidshark.yml"
        if config_path.exists() and not args.force:
            if args.non_interactive:
                print(f"Error: {config_path} already exists. Use --force to overwrite.")
                return EXIT_INVALID_USAGE

            overwrite = questionary.confirm(
                "lucidshark.yml already exists. Overwrite?",
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

        # Summary
        print("\nDone! Next steps:")
        print("  1. Review the generated lucidshark.yml")
        print("  2. Run 'lucidshark scan --all' to test the configuration")

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

        # Duplication detection always enabled
        choices.duplication_enabled = True

        # Test runner: use detected or default
        if context.test_frameworks:
            choices.test_runner = context.test_frameworks[0]
        elif context.has_python:
            choices.test_runner = PYTHON_DEFAULT_TEST_RUNNER
        elif context.has_javascript:
            choices.test_runner = JS_DEFAULT_TEST_RUNNER

        return choices

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

        if choices.duplication_enabled:
            items.append(f"  Duplication:  duplo (threshold: {choices.duplication_threshold}%)")

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
