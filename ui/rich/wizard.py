"""Interactive Setup Wizard and Glitch Clear Effect for Protocol Monk.

Implements an animated setup wizard with typewriter questions and
Matrix-style glitch clear screen effect.
"""

from __future__ import annotations

import asyncio
import random
import sys
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


# Matrix-style character set for glitch effect
GLITCH_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%&*<>[]{}|/\\~░▒▓█"


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


class SetupWizard:
    """Interactive setup wizard with typewriter animation.

    Configures the session with 3 questions:
    1. Provider selection (Ollama/OpenRouter)
    2. Model selection (from discovery)
    3. Workspace path input

    After wizard completes, performs a glitch clear effect.
    """

    def __init__(
        self,
        *,
        console: Console | None = None,
        input_handler: RichInputHandler | None = None,
        typewriter_config: TypewriterConfig | None = None,
        glitch_chars: str = GLITCH_CHARS,
    ) -> None:
        self._console = console or default_console
        self._input_handler = input_handler or RichInputHandler()
        self._typewriter_config = typewriter_config or TYPEWRITER_PRESETS["dramatic"]
        self._glitch_chars = glitch_chars
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
        """Get available model choices from settings."""
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
        for i, (name, config) in enumerate(models.items()):
            if i >= 20:  # Limit to 20 models for usability
                break

            # Build description with family and context window
            family = config.get("family", "unknown")
            ctx = config.get("context_window", "?")
            supports_tools = "tools" if config.get("supports_tools") else ""
            supports_thinking = "thinking" if config.get("supports_thinking") else ""
            features = ", ".join(filter(None, [supports_tools, supports_thinking]))

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

            # Build choices panel
            lines = []
            for i, choice in enumerate(question.choices):
                marker = "→" if i == 0 else " "
                lines.append(f"{marker} [{i}] {choice.label}")
                if choice.description:
                    lines.append(f"      [dim]{choice.description}[/]")

            content = Text("\n".join(lines), style="monk.text")
            self._console.print(
                Panel(
                    content,
                    title="Select Provider",
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

    async def _glitch_clear(
        self,
        *,
        rows: int | None = None,
        density: float = 0.15,
        iterations: int = 3,
        delay: float = 0.05,
        final_delay: float = 0.15,
    ) -> None:
        """Perform Matrix-style glitch clear effect.

        Fills the screen with random characters, then progressively
        clears them to create a "digital rain" wipe effect.

        Args:
            rows: Number of rows to fill (default: terminal height)
            density: Fraction of cells to fill per iteration (0.0-1.0)
            iterations: Number of fill iterations before clearing
            delay: Delay between iterations
            final_delay: Delay before final clear

        """
        try:
            import shutil

            terminal_width = shutil.get_terminal_size().columns
            terminal_height = shutil.get_terminal_size().lines
        except Exception:
            terminal_width = 80
            terminal_height = 24

        if rows is None:
            rows = terminal_height

        # Step 1: Fill screen with random characters progressively
        for iteration in range(iterations):
            fill_ratio = (iteration + 1) / iterations
            chars_per_row = int(terminal_width * density * fill_ratio)

            for row in range(rows):
                # Randomly scatter characters across the row
                positions = random.sample(
                    range(terminal_width),
                    min(chars_per_row, terminal_width),
                )
                line_chars = []
                for pos in range(terminal_width):
                    if pos in positions:
                        char = random.choice(self._glitch_chars)
                        # Use different styles for visual interest
                        style = random.choice(["dim", "monk.text", "tech.cyan"])
                        line_chars.append(f"[{style}]{char}[/{style}]")
                    else:
                        line_chars.append(" ")

                if line_chars:
                    # Move to the specific row and print
                    self._console.print("\r\033[K", end="")  # Clear current line
                    self._console.print("".join(line_chars), end="")

            await asyncio.sleep(delay)

        # Step 2: Progressive clear - characters "fall away"
        for clear_pass in range(3):
            rows_to_clear = int(rows * (clear_pass + 1) / 3)

            for row in range(rows):
                if row < rows_to_clear:
                    # Clear this row with more white space
                    clear_amount = random.randint(0, terminal_width // 3)
                    remaining = terminal_width - clear_amount

                    if remaining > 0 and random.random() < 0.5:
                        # Fade from left or right
                        if random.random() < 0.5:
                            # Clear from left
                            line = " " * clear_amount
                            remaining_chars = [
                                random.choice(self._glitch_chars)
                                for _ in range(min(remaining, 20))
                            ]
                            line += " ".join(remaining_chars[:remaining])
                        else:
                            # Clear from right
                            remaining_chars = [
                                random.choice(self._glitch_chars)
                                for _ in range(min(remaining, 20))
                            ]
                            line = " ".join(remaining_chars[:remaining])
                            line += " " * clear_amount
                        self._console.print(f"\r{line}\033[K", end="")
                    else:
                        self._console.print("\r\033[K", end="")  # Clear line

            await asyncio.sleep(delay)

        # Step 3: Final clear - screen goes dark
        await asyncio.sleep(final_delay)
        self._console.print("\033[2J\033[H", end="")  # Clear screen and move to home
        self._console.print()

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
        )
        self._choices["provider"] = await self._ask_question(
            provider_question,
            question_number=1,
            total_questions=3,
        )

        # Question 2: Model selection
        model_question = WizardQuestion(
            question="The Mind of?",
            choices=self._get_model_choices(settings),
            default=settings.active_model_name,
        )
        self._choices["model"] = await self._ask_question(
            model_question,
            question_number=2,
            total_questions=3,
        )

        # Question 3: Workspace path
        workspace_default = str(settings.workspace) if settings.workspace else str(Path.cwd())
        workspace_question = WizardQuestion(
            question="Your Path of choice?",
            choices=None,  # Text input
            default=workspace_default,
            allow_custom=True,
        )
        self._choices["workspace"] = await self._ask_question(
            workspace_question,
            question_number=3,
            total_questions=3,
        )

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
                Text("\n".join(config_lines), style="monk.text"),
                title="[monk.border]Choices Saved[/]",
                border_style="monk.border",
                box=box.ROUNDED,
            )
        )

        await asyncio.sleep(0.5)

        # Perform glitch clear effect
        await self._glitch_clear()

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
            settings._set_active_model(choices["model"])

        if "workspace" in choices:
            workspace_path = Path(choices["workspace"])
            if workspace_path.exists():
                settings.workspace = workspace_path