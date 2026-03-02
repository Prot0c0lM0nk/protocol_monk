"""Interactive Setup Wizard for Protocol Monk.

Implements an animated setup wizard with typewriter questions.
Configures provider, model, and workspace for each session.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Sequence

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
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
    display: Dict[str, str] = field(default_factory=dict)


@dataclass
class WizardQuestion:
    """A single question in the setup wizard."""

    question: str
    choices: Sequence[WizardChoice] | None = None  # None = text input
    default: str = ""
    allow_custom: bool = False  # For text input, allow custom values
    panel_title: str = "Select"  # Title for the selection panel
    table_columns: Sequence[str] | None = None  # Optional explicit table columns
    page_size: int = 10  # Pagination size when choices are long


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
                description="Use configured Ollama-compatible endpoint",
                display={
                    "Provider": "Ollama",
                    "Notes": "Configured Ollama-compatible endpoint",
                },
            ),
            WizardChoice(
                label="OpenRouter",
                value="openrouter",
                description="Use configured OpenRouter-compatible endpoint",
                display={
                    "Provider": "OpenRouter",
                    "Notes": "Configured OpenRouter-compatible endpoint",
                },
            ),
        ]

    @staticmethod
    def _format_context_window(value: Any) -> str:
        """Format context window value for display."""
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "?"

    @staticmethod
    def _extract_capabilities(config: Dict[str, Any]) -> List[str]:
        """Extract capability labels with fallback from boolean support flags."""
        raw = config.get("capabilities")
        capabilities: List[str] = []
        if isinstance(raw, list):
            capabilities = [str(item).strip().lower() for item in raw if str(item).strip()]
        elif isinstance(raw, str) and raw.strip():
            capabilities = [part.strip().lower() for part in raw.split(",") if part.strip()]

        if not capabilities:
            if config.get("supports_tools"):
                capabilities.append("tools")
            if config.get("supports_thinking"):
                capabilities.append("thinking")

        # Deduplicate while preserving order
        deduped: List[str] = []
        seen: set[str] = set()
        for cap in capabilities:
            if cap in seen:
                continue
            seen.add(cap)
            deduped.append(cap)
        return deduped

    def _build_model_choice(self, name: str, config: Dict[str, Any]) -> WizardChoice:
        """Create a model choice with structured display metadata."""
        family = str(config.get("family", "unknown"))
        context_text = self._format_context_window(config.get("context_window"))
        capabilities = self._extract_capabilities(config)
        capabilities_text = ", ".join(capabilities) if capabilities else "-"

        description = f"{family} | {context_text} ctx"
        if capabilities:
            description = f"{description} | {capabilities_text}"

        return WizardChoice(
            label=name,
            value=name,
            description=description,
            display={
                "Model": name,
                "Family": family,
                "Context": context_text,
                "Capabilities": capabilities_text,
            },
        )

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
                    display={
                        "Model": "Default Model",
                        "Family": "unknown",
                        "Context": "?",
                        "Capabilities": "-",
                    },
                ),
            ]

        choices = []
        for name, config in models.items():
            # Skip models that don't support tools (required for function calling)
            if not config.get("supports_tools", False):
                continue

            choices.append(self._build_model_choice(name, config))

        if not choices:
            default_model = models_config.get("default_model") or next(iter(models.keys()), "default")
            fallback_config = models.get(default_model, {})
            choices.append(self._build_model_choice(default_model, fallback_config))

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
        added_paths: set[str] = set()

        # Add current workspace if it exists and is a directory
        if current_workspace:
            current_path = Path(current_workspace)
            if current_path.exists() and current_path.is_dir():
                current_path_text = str(current_path)
                choices.append(
                    WizardChoice(
                        label=current_path.name or current_path_text,
                        value=current_path_text,
                        description=current_path_text,
                        display={
                            "Workspace": current_path.name or current_path_text,
                            "Path": current_path_text,
                            "Current": "Yes",
                        },
                    )
                )
                added_paths.add(current_path_text)

        # Add Desktop directories
        if desktop.exists() and desktop.is_dir():
            try:
                for item in sorted(desktop.iterdir(), key=lambda x: x.name.lower()):
                    if item.is_dir() and not item.name.startswith('.'):
                        item_path_text = str(item)
                        if item_path_text in added_paths:
                            continue
                        choices.append(
                            WizardChoice(
                                label=item.name,
                                value=item_path_text,
                                description=item_path_text,
                                display={
                                    "Workspace": item.name,
                                    "Path": item_path_text,
                                    "Current": "",
                                },
                            )
                        )
            except PermissionError:
                pass  # Fall through to default choices

        # Add "Other..." option for custom path
        choices.append(
            WizardChoice(
                label="Other...",
                value="__custom__",
                description="Enter a custom path",
                display={
                    "Workspace": "Other...",
                    "Path": "Enter a custom path",
                    "Current": "",
                },
            )
        )

        return choices

    @staticmethod
    def _choice_column_value(choice: WizardChoice, column_name: str) -> str:
        """Resolve a table column value for a choice."""
        if choice.display and column_name in choice.display:
            return choice.display[column_name]

        lowered = column_name.lower()
        if lowered in {"option", "provider", "model", "workspace"}:
            return choice.label
        if lowered in {"notes", "details", "description"}:
            return choice.description
        if lowered == "path":
            return choice.value
        if lowered == "current":
            return ""
        return ""

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
            # Get selection
            columns = list(question.table_columns or ("Option", "Details"))
            page_size = max(1, int(question.page_size))
            max_index = len(question.choices) - 1
            default_index = 0
            for i, choice in enumerate(question.choices):
                if choice.value == question.default:
                    default_index = i
                    break
            total_pages = (len(question.choices) - 1) // page_size + 1
            current_page = default_index // page_size

            while True:
                start_idx = current_page * page_size
                end_idx = min(start_idx + page_size, len(question.choices))

                table = Table(
                    box=box.SIMPLE_HEAD,
                    show_lines=False,
                    expand=True,
                    header_style="tech.cyan",
                )
                table.add_column("#", justify="right", style="monk.text", no_wrap=True)
                for column_name in columns:
                    table.add_column(column_name, style="monk.text", overflow="fold")

                for idx in range(start_idx, end_idx):
                    choice = question.choices[idx]
                    index_marker = f"{idx} *" if idx == default_index else str(idx)
                    row_values = [
                        self._choice_column_value(choice, column_name)
                        for column_name in columns
                    ]
                    table.add_row(index_marker, *row_values)

                footer_lines = [
                    f"[dim]Rows {start_idx}-{end_idx - 1} of 0-{max_index}.[/]",
                ]
                if total_pages > 1:
                    footer_lines.append(
                        f"[dim]Page {current_page + 1}/{total_pages}. Enter 'n'/'next' or 'p'/'prev' to navigate.[/]"
                    )
                footer_lines.append(
                    f"[dim]Press Enter for default ({default_index}).[/]"
                )
                footer = Text.from_markup("\n".join(footer_lines))

                content = Group(table, footer)
                panel_title = question.panel_title
                if total_pages > 1:
                    panel_title = f"{panel_title} ({current_page + 1}/{total_pages})"
                self._console.print(
                    Panel(
                        content,
                        title=panel_title,
                        title_align="left",
                        border_style="monk.border",
                        box=box.ROUNDED,
                    )
                )

                try:
                    if total_pages > 1:
                        prompt = (
                            f"Select [0-{max_index}] (default {default_index}, n/p pages): "
                        )
                    else:
                        prompt = f"Select [0-{max_index}] (default {default_index}): "
                    answer = await self._input_handler.prompt(prompt)
                    answer_clean = answer.strip().lower()
                    if not answer_clean:
                        return question.choices[default_index].value
                    if answer_clean in {"n", "next"}:
                        if current_page < total_pages - 1:
                            current_page += 1
                        else:
                            self._console.print("[warning]Already on the last page.[/]")
                        continue
                    if answer_clean in {"p", "prev"}:
                        if current_page > 0:
                            current_page -= 1
                        else:
                            self._console.print("[warning]Already on the first page.[/]")
                        continue

                    selection = int(answer_clean)
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
            table_columns=("Provider", "Notes"),
            page_size=8,
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
            table_columns=("Model", "Family", "Context", "Capabilities"),
            page_size=10,
        )
        self._choices["model"] = await self._ask_question(
            model_question,
            question_number=2,
            total_questions=3,
        )

        # Question 3: Workspace selection (Desktop directories)
        workspace_default = str(settings.workspace) if settings.workspace else str(Path.cwd())
        workspace_choices = self._get_workspace_choices(current_workspace=workspace_default)

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
            table_columns=("Workspace", "Path", "Current"),
            page_size=10,
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
