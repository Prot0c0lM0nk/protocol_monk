"""Interactive Setup Wizard for Protocol Monk.

Implements an animated setup wizard with typewriter questions.
Configures provider, model, and workspace for each session.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .input_handler import RichInputHandler
from .styles import console as default_console
from .typewriter import TypewriterConfig, TYPEWRITER_PRESETS, typewriter_print

if TYPE_CHECKING:
    from protocol_monk.config.settings import Settings


@dataclass
class WizardChoice:
    """Represents a choice in the setup wizard."""

    label: str
    value: str
    description: str = ""


@dataclass
class WizardQuestion:
    """A single question in the setup wizard."""

    question: str
    choices: Sequence[WizardChoice] | None = None  # None = text input
    default: str = ""
    allow_custom: bool = False  # For text input, allow custom values
    panel_title: str = "Select"  # Title for the selection panel


class SetupWizard:
    """Interactive setup wizard with typewriter animation.

    Configures the session with 3 questions:
    1. Provider selection (Ollama/OpenRouter)
    2. Model selection (from discovery)
    3. Workspace path selection (Desktop directories)

    After wizard completes, clears screen for boot animation.
    """

    def __init__(
        self,
        *,
        console: Console | None = None,
        input_handler: RichInputHandler | None = None,
        typewriter_config: TypewriterConfig | None = None,
    ) -> None:
        self._console = console or default_console
        self._input_handler = input_handler or RichInputHandler()
        self._typewriter_config = typewriter_config or TYPEWRITER_PRESETS["dramatic"]
        self._choices: Dict[str, Any] = {}

    def _get_provider_choices(self) -> List[WizardChoice]:
        """Get available provider choices."""
        return [
            WizardChoice(
                label="Ollama",
                value="ollama",
                description="Local inference via Ollama",
            ),
            WizardChoice(
                label="OpenRouter",
                value="openrouter",
                description="Cloud models via OpenRouter API",
            ),
        ]

    def _get_model_choices(self, settings: Settings) -> List[WizardChoice]:
        """Get available model choices from settings.

        Only includes models that support tools, as the app requires function calling.
        """
        models_config = settings.models_config or {}
        models = models_config.get("models", {})

        if not models:
            # Fallback choices
            return [
                WizardChoice(
                    label="Default Model",
                    value="default",
                    description="Use default model configuration",
                ),
            ]

        choices = []
        for name, config in models.items():
            # Skip models that don't support tools (required for function calling)
            if not config.get("supports_tools", False):
                continue

            if len(choices) >= 20:  # Limit to 20 models for usability
                break

            # Build description with family and context window
            family = config.get("family", "unknown")
            ctx = config.get("context_window", "?")
            supports_thinking = "thinking" if config.get("supports_thinking") else ""
            features = supports_thinking if supports_thinking else ""

            description = f"{family} | {ctx} ctx"
            if features:
                description = f"{description} | {features}"

            choices.append(
                WizardChoice(
                    label=name,
                    value=name,
                    description=description,
                )
            )

        return choices

    def _get_workspace_choices(self, current_workspace: str = "") -> List[WizardChoice]:
        """Get workspace choices from Desktop directories.

        Args:
            current_workspace: Current workspace path to highlight as default

        Returns:
            List of WizardChoice objects for workspace selection
        """
        desktop = Path.home() / "Desktop"
        choices: List[WizardChoice] = []

        # Add current workspace if it exists and is a directory
        if current_workspace:
            current_path = Path(current_workspace)
            if current_path.exists() and current_path.is_dir():
                choices.append(
                    WizardChoice(
                        label=f"Current: {current_path.name}",
                        value=str(current_path),
                        description=f"{current_path}",
                    )
                )

        # Add Desktop directories
        if desktop.exists():
            for item in sorted(desktop.iterdir()):
                if item.is_dir() and not item.name.startswith('.'):
                    # Skip if already added as current workspace
                    if str(item) == current_workspace:
                        continue
                    choices.append(
                        WizardChoice(
                            label=item.name,
                            value=str(item),
                            description=f"~/Desktop/{item.name}",
                        )
                    )

        # Limit to 15 choices for usability
        if len(choices) > 15:
            choices = choices[:15]

        # Add "Other..." option for custom path
        choices.append(
            WizardChoice(
                label="Other...",
                value="__custom__",
                description="Enter a custom path",
            )
        )

        return choices

    def _get_workspace_choices(self) -> List[WizardChoice]:
        """Get workspace choices from Desktop directories."""
        desktop = Path.home() / "Desktop"
        choices: List[WizardChoice] = []

        if desktop.exists() and desktop.is_dir():
            try:
                for item in sorted(desktop.iterdir(), key=lambda x: x.name.lower()):
                    if item.is_dir() and not item.name.startswith('.'):
                        # Truncate long names for display
                        display_name = item.name[:30] + "..." if len(item.name) > 30 else item.name
                        choices.append(
                            WizardChoice(
                                label=display_name,
                                value=str(item),
                                description=f"~/Desktop/{item.name}",
                            )
                        )
            except PermissionError:
                pass  # Fall through to default choices

        # Limit to 15 directories for usability
        choices = choices[:15]

        # Add "Other..." option for custom path
        choices.append(
            WizardChoice(
                label="Other...",
                value="__custom__",
                description="Enter a custom path",
            )
        )

        return choices

    async def _ask_question(
        self,
        question: WizardQuestion,
        *,
        question_number: int,
        total_questions: int,
    ) -> str:
        """Ask a single wizard question with typewriter animation."""
        # Print question header
        self._console.print()

        # Animate the question with typewriter effect
        await typewriter_print(
            f"{question.question}",
            console=self._console,
            config=self._typewriter_config,
            style="monk.text",
        )
        self._console.print()

        # Small pause before showing options
        await asyncio.sleep(self._typewriter_config.pause_before_prompt)

        if question.choices:
            # Panel-based selection
            options = [f"{c.label} - {c.description}" for c in question.choices]

            # Build choices panel using Text.from_markup to parse style tags
            lines = []
            for i, choice in enumerate(question.choices):
                marker = "→" if i == 0 else " "
                lines.append(f"{marker} [{i}] {choice.label}")
                if choice.description:
                    lines.append(f"      [dim]{choice.description}[/]")

            content = Text.from_markup("\n".join(lines))
            self._console.print(
                Panel(
                    content,
                    title=question.panel_title,
                    title_align="left",
                    border_style="monk.border",
                    box=box.ROUNDED,
                )
            )

            # Get selection
            max_index = len(question.choices) - 1
            default_index = 0
            for i, choice in enumerate(question.choices):
                if choice.value == question.default:
                    default_index = i
                    break

            while True:
                try:
                    prompt = f"Select [0-{max_index}] (default {default_index}): "
                    answer = await self._input_handler.prompt(prompt)
                    if not answer.strip():
                        return question.choices[default_index].value
                    selection = int(answer.strip())
                    if 0 <= selection < len(question.choices):
                        return question.choices[selection].value
                    self._console.print("[error]Invalid selection. Try again.[/]")
                except ValueError:
                    self._console.print("[error]Please enter a number.[/]")
                except (EOFError, KeyboardInterrupt):
                    # Return default on interrupt
                    return question.choices[default_index].value
        else:
            # Text input
            while True:
                try:
                    prompt = f"Enter path (default: {question.default}): " if question.default else "Enter path: "
                    answer = await self._input_handler.prompt(prompt)
                    answer = answer.strip()

                    if not answer:
                        return question.default

                    # Validate path
                    path = Path(answer)
                    if not path.is_absolute():
                        path = Path.cwd() / path

                    if path.exists() and path.is_dir():
                        return str(path)
                    elif question.allow_custom:
                        return str(path)
                    else:
                        self._console.print(
                            "[warning]Path does not exist or is not a directory.[/]"
                        )
                        self._console.print("[dim]Using current directory.[/]")
                        return str(path)
                except (EOFError, KeyboardInterrupt):
                    return question.default

    async def run(
        self,
        settings: Settings,
    ) -> Dict[str, Any]:
        """Run the setup wizard and return configuration choices.

        Args:
            settings: Current settings object to use for model discovery

        Returns:
            Dictionary with 'provider', 'model', and 'workspace' keys

        """
        self._choices = {}

        # Print wizard header
        self._console.print()
        header = Panel(
            Text("Session Configuration", style="tech.cyan"),
            title="╔══ SETUP WIZARD ══╗",
            title_align="center",
            border_style="monk.border",
            box=box.DOUBLE,
        )
        self._console.print(header)
        self._console.print()

        # Question 1: Provider selection
        provider_question = WizardQuestion(
            question="What is the Source?",
            choices=self._get_provider_choices(),
            default=settings.llm_provider,
            panel_title="Select Provider",
        )
        selected_provider = await self._ask_question(
            provider_question,
            question_number=1,
            total_questions=3,
        )
        self._choices["provider"] = selected_provider

        # Reload models if provider changed
        if selected_provider != settings.llm_provider:
            self._console.print(f"[dim]Loading {selected_provider} models...[/]")
            # Clear alias so it doesn't override wizard selection during reload
            settings.active_model_alias = ""
            try:
                await settings.reload_models_for_provider(selected_provider)
            except Exception as e:
                self._console.print(f"[warning]Failed to load models: {e}[/]")

        # Question 2: Model selection
        model_question = WizardQuestion(
            question="The Mind of?",
            choices=self._get_model_choices(settings),
            default=settings.active_model_name,
            panel_title="Select Model",
        )
        self._choices["model"] = await self._ask_question(
            model_question,
            question_number=2,
            total_questions=3,
        )

        # Question 3: Workspace selection (Desktop directories)
        workspace_choices = self._get_workspace_choices()
        workspace_default = str(settings.workspace) if settings.workspace else str(Path.cwd())

        # Find default index in choices
        workspace_default_index = 0
        for i, choice in enumerate(workspace_choices):
            if choice.value == workspace_default:
                workspace_default_index = i
                break

        workspace_question = WizardQuestion(
            question="Your Path of choice?",
            choices=workspace_choices,
            default=workspace_choices[workspace_default_index].value
            if workspace_default_index < len(workspace_choices)
            else workspace_choices[0].value,
            panel_title="Select Workspace",
        )
        workspace_result = await self._ask_question(
            workspace_question,
            question_number=3,
            total_questions=3,
        )

        # Handle "Other..." selection
        if workspace_result == "__custom__":
            custom_question = WizardQuestion(
                question="Enter custom path:",
                choices=None,  # Text input
                default=workspace_default,
                allow_custom=True,
            )
            self._choices["workspace"] = await self._ask_question(
                custom_question,
                question_number=3,
                total_questions=3,
            )
        else:
            self._choices["workspace"] = workspace_result

        # Print confirmation
        self._console.print()
        await typewriter_print(
            "Configuration complete.",
            console=self._console,
            config=self._typewriter_config,
            style="success",
        )
        await asyncio.sleep(0.3)

        # Show selected configuration
        self._console.print()
        config_lines = [
            f"  [tech.cyan]Provider:[/] {self._choices['provider']}",
            f"  [tech.cyan]Model:[/]    {self._choices['model']}",
            f"  [tech.cyan]Workspace:[/] {self._choices['workspace']}",
        ]
        self._console.print(
            Panel(
                Text.from_markup("\n".join(config_lines)),
                title="Choices Saved",
                border_style="monk.border",
                box=box.ROUNDED,
            )
        )

        await asyncio.sleep(0.5)

        # Clear screen for boot animation
        self._console.clear()

        return self._choices

    def apply_choices(self, settings: Settings, choices: Dict[str, Any]) -> None:
        """Apply wizard choices to settings object.

        Args:
            settings: Settings object to modify
            choices: Dictionary from run() method

        """
        if "provider" in choices:
            settings.llm_provider = choices["provider"]

        if "model" in choices:
            # Clear the alias so it doesn't override our selection
            settings.active_model_alias = ""
            settings._set_active_model(choices["model"])

        if "workspace" in choices:
            workspace_path = Path(choices["workspace"])
            if workspace_path.exists():
                settings.workspace = workspace_path