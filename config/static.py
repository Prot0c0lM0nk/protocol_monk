#!/usr/bin/env python3
"""
Static Configuration for Protocol Monk
=====================================

This configuration system is optimized for Ollama models with seamless
transition between local and cloud versions of the same models.

Key Features:
- Automatic model detection for local/cloud variants
- Context window management based on model capabilities
- Ollama-specific optimizations
"""

import json
import os
import sys
from dotenv import load_dotenv
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from exceptions import ConfigFileError, ModelConfigError

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# SENSITIVE STRING WRAPPER
# =============================================================================


class SensitiveStr:
    """
    Wrapper for sensitive strings to prevent accidental logging.

    When printed or converted to string, shows "[REDACTED]" instead of actual value.
    Use get_secret_value() to access the real value when needed.
    """

    def __init__(self, value: str):
        self._value = value

    def __str__(self):
        return "[REDACTED]" if self._value else ""

    def __repr__(self):
        return f"SensitiveStr('[REDACTED]')"

    def get_secret_value(self) -> str:
        """Get the actual secret value (use sparingly)."""
        return self._value


# =============================================================================
# MODEL MANAGEMENT
# =============================================================================


class ModelManager:
    """Manages model configuration and capabilities."""

    def __init__(self):
        # Default model (Ollama)
        self.default_model = os.getenv("PROTOCOL_MODEL", "qwen3-vl:4b-instruct-q4_K_M")

        # Model map file
        self.model_map_file = os.getenv("PROTOCOL_MODEL_MAP_FILE", "ollama_map.json")

        # Load model information
        self.model_info = self._load_model_map()

        # Get current model info
        self.current_model_info = self._get_model_info(self.default_model)

        # Context window (auto-detected from model, but can be overridden)
        self.context_window = int(
            os.getenv(
                "PROTOCOL_CONTEXT_WINDOW",
                str(self.current_model_info.get("context_window", 16384)),
            )
        )

        # Pruning thresholds
        self.pruning_threshold = int(
            os.getenv("PROTOCOL_PRUNING_THRESHOLD", str(int(self.context_window * 0.8)))
        )

        self.target_tokens = int(
            os.getenv("PROTOCOL_TARGET_TOKENS", str(int(self.context_window * 0.6)))
        )

        # Request timeout (seconds)
        self.request_timeout = int(os.getenv("PROTOCOL_TIMEOUT", "420"))

    def update_model(self, model_name: str):
        """Update the default model and context window based on the new model."""
        self.default_model = model_name
        self.current_model_info = self._get_model_info(model_name)
        # Update context window based on new model
        self.context_window = self.current_model_info.get("context_window", 16384)
        # Update pruning thresholds based on new context window
        self.pruning_threshold = int(self.context_window * 0.8)
        self.target_tokens = int(self.context_window * 0.6)

    def _load_model_map(self) -> Dict[str, Any]:
        """Load model mapping information."""
        project_root = Path(__file__).parent.parent.resolve()
        model_map_path = project_root / self.model_map_file

        try:
            if model_map_path.exists():
                with open(model_map_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("models", {})
            else:
                print(f"⚠️  Model map file not found: {model_map_path}", file=sys.stderr)
                return {}
        except json.JSONDecodeError as e:
            raise ModelConfigError(
                f"Invalid JSON format in model map file {model_map_path}: {e}",
                config_file=model_map_path,
                original_error=e,
            ) from e
        except (OSError, IOError) as e:
            raise ModelConfigError(
                f"Failed to read model map file {model_map_path}: {e}",
                config_file=model_map_path,
                original_error=e,
            ) from e

    def _get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get information about a specific model."""
        # Try exact match first
        if model_name in self.model_info:
            return self.model_info[model_name]

        # Try to find a matching model (for local/cloud variants)
        for name, info in self.model_info.items():
            # Check if this is a variant of the requested model
            if model_name.replace("-cloud", "").replace("-local", "") == name.replace(
                "-cloud", ""
            ).replace("-local", ""):
                return info

        # Return default info
        return self.model_info.get(
            "default",
            {"hf_path": "unknown", "context_window": 16384, "provider": "generic"},
        )

    def is_cloud_model(self, model_name: str = None) -> bool:
        """Check if a model is a cloud variant."""
        model_name = model_name or self.default_model
        info = self._get_model_info(model_name)
        return info.get("provider") == "cloud"

    def is_local_model(self, model_name: str = None) -> bool:
        """Check if a model is a local variant."""
        model_name = model_name or self.default_model
        info = self._get_model_info(model_name)
        return info.get("provider") == "local" or info.get("provider") == "generic"

    def get_model_hf_path(self, model_name: str = None) -> str:
        """Get the HuggingFace path for a model."""
        model_name = model_name or self.default_model
        info = self._get_model_info(model_name)
        return info.get("hf_path", "unknown")

    def get_model_context_window(self, model_name: str = None) -> int:
        """Get the context window for a model."""
        model_name = model_name or self.default_model
        info = self._get_model_info(model_name)
        return info.get("context_window", 32000)


# =============================================================================
# API CONFIGURATION
# =============================================================================


class ApiConfig:
    """API-related configuration settings."""

    def __init__(self):
        # Ollama API endpoint
        self.ollama_url = os.getenv(
            "PROTOCOL_OLLAMA_URL", "http://localhost:11434/api/chat"
        )

        # Provider configuration
        self.provider_chain = os.getenv(
            "PROTOCOL_PROVIDER_CHAIN", "ollama,openrouter"
        ).split(",")

        self.enable_provider_failover = (
            os.getenv("PROTOCOL_ENABLE_FAILOVER", "true").lower() == "true"
        )

        self.provider_timeout = int(os.getenv("PROTOCOL_PROVIDER_TIMEOUT", "420"))

        # Provider-specific settings
        # Provider-specific settings
        self.providers = {
            "ollama": {
                "timeout": int(os.getenv("PROTOCOL_OLLAMA_TIMEOUT", "420")),
                "max_retries": int(os.getenv("PROTOCOL_OLLAMA_RETRIES", "3")),
                "retry_delay": float(os.getenv("PROTOCOL_OLLAMA_RETRY_DELAY", "1.0")),
                "api_key": os.getenv("OLLAMA_API_KEY"),
            },
            "openrouter": {
                "timeout": int(os.getenv("PROTOCOL_OPENROUTER_TIMEOUT", "420")),
                "max_retries": int(os.getenv("PROTOCOL_OPENROUTER_RETRIES", "3")),
                "retry_delay": float(
                    os.getenv("PROTOCOL_OPENROUTER_RETRY_DELAY", "1.0")
                ),
                "api_key": os.getenv("OPENROUTER_API_KEY"),
            },
        }


# =============================================================================
# FILESYSTEM CONFIGURATION
# =============================================================================


class FileSystemConfig:
    """File system-related configuration settings."""

    def __init__(self):
        # Get the root directory of the project
        self.project_root = Path(__file__).parent.parent.resolve()

        # Working directory
        self.working_dir = Path(
            os.getenv("PROTOCOL_WORKING_DIR", self.project_root / "workspace")
        )

        # Create working directory if it doesn't exist
        self.working_dir.mkdir(parents=True, exist_ok=True)

        # History file
        self.history_file = self.working_dir / ".protocol_history.txt"

        # System prompt file
        self.system_prompt_filename = os.getenv(
            "PROTOCOL_SYSTEM_PROMPT_FILE", "system_prompt.txt"
        )
        self.system_prompt_file = self.project_root / self.system_prompt_filename


# =============================================================================
# MODEL OPTIONS
# =============================================================================


class ModelOptionsConfig:
    """Model options configuration."""

    def __init__(self, filesystem_config: FileSystemConfig):
        # Model options file
        self.model_options_filename = os.getenv(
            "PROTOCOL_MODEL_OPTIONS_FILE", "model_options.json"
        )
        self.model_options_file = (
            filesystem_config.project_root / self.model_options_filename
        )

        # Load model options
        self.tool_options, self.chat_options = self._load_model_options()

    def _load_model_options(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Load model options from the JSON file."""
        default_tool_options = {
            "temperature": 0.0,
            "num_ctx": 16384,
            "keep_alive": "5m",
        }
        default_chat_options = {
            "temperature": 0.7,
            "num_ctx": 16384,
            "keep_alive": "5m",
        }

        try:
            if self.model_options_file.exists():
                with open(self.model_options_file, "r", encoding="utf-8") as f:
                    options = json.load(f)
                    tool_options = options.get(
                        "TOOL_MODEL_OPTIONS", default_tool_options
                    )
                    chat_options = options.get(
                        "CHAT_MODEL_OPTIONS", default_chat_options
                    )

                    # Ensure num_ctx is set based on a reasonable default (will be updated later)
                    tool_options["num_ctx"] = tool_options.get("num_ctx", 16384)
                    chat_options["num_ctx"] = chat_options.get("num_ctx", 16384)

                    return tool_options, chat_options
            else:
                print(
                    f"⚠️  Config file not found: {self.model_options_file}. Using default model options.",
                    file=sys.stderr,
                )
                return default_tool_options, default_chat_options
        except json.JSONDecodeError as e:
            raise ConfigFileError(
                f"Invalid JSON format in model options file {self.model_options_file}: {e}",
                file_path=self.model_options_file,
                operation="load",
            ) from e
        except (OSError, IOError) as e:
            raise ConfigFileError(
                f"Failed to read model options file {self.model_options_file}: {e}",
                file_path=self.model_options_file,
                operation="load",
            ) from e
        except (TypeError, ValueError) as e:
            raise ConfigFileError(
                f"Invalid model options data structure in {self.model_options_file}: {e}",
                file_path=self.model_options_file,
                operation="load",
            ) from e


# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================


class SecurityConfig:
    """Security-related configuration settings."""

    def __init__(self):
        # Dangerous commands that should never be executed
        self.dangerous_commands = [
            "rm -rf",
            "rm -r",
            "rmdir",
            "mkfs",
            "dd if=",
            "sudo",
            "su -",
            "chmod 777",
            "passwd",
            "reboot",
            "shutdown",
            "halt",
            "> /dev/",
            "> /etc/",
            "> /usr/",
            "curl",
            "wget",
            "nc",
            "netcat",
        ]

        # Whitelist for safe command chains
        self.safe_command_chains = [
            r"^ls -l.+$",
            r"^git status$",
            r"^git diff.+$",
            r"^find . -name \".+\" | xargs grep \".+\"",
        ]

        # File paths that should never be accessed
        self.dangerous_paths = [
            "/etc/",
            "/usr/",
            "/var/",
            "/root/",
            "/boot/",
            "/dev/",
            "/proc/",
            "/sys/",
            ".ssh/",
            ".bash",
            ".profile",
        ]

        # Shell execution timeout (seconds)
        self.shell_timeout = int(os.getenv("PROTOCOL_SHELL_TIMEOUT", "30"))

        # Platform-specific clipboard commands
        self.clipboard_paste_cmd = os.getenv("PROTOCOL_PASTE_CMD", "pbpaste")
        self.clipboard_copy_cmd = os.getenv("PROTOCOL_COPY_CMD", "pbcopy")

    def validate_command(self, command: str) -> Tuple[bool, str]:
        """Validate that a shell command is safe to execute."""
        command_lower = command.lower()

        for pattern in self.dangerous_commands:
            if pattern in command_lower:
                return False, f"Dangerous command pattern detected: {pattern}"

        return True, ""

    def validate_path(self, filepath: str, working_dir: Path) -> Tuple[bool, str]:
        """Validate that a file path is safe to access."""
        # Check for dangerous patterns
        for pattern in self.dangerous_paths:
            if pattern in filepath:
                return False, f"Dangerous path pattern detected: {pattern}"

        # Ensure path is within working directory
        try:
            full_path = Path(filepath).resolve()
            working_path = working_dir.resolve()

            # Check if path is under working directory
            try:
                full_path.relative_to(working_path)
            except ValueError:
                return False, f"Path outside working directory: {filepath}"
        except Exception as e:
            return False, f"Invalid path: {e}"

        return True, ""


# =============================================================================
# DEBUG CONFIGURATION
# =============================================================================


class DebugConfig:
    """Debug-related configuration settings."""

    def __init__(self, filesystem_config: FileSystemConfig):
        # Enable debug logging to file
        self.debug_execution_logging = (
            os.getenv("PROTOCOL_DEBUG_LOGGING", "true").lower() == "true"
        )

        # Print debug info to terminal
        self.debug_terminal = (
            os.getenv("PROTOCOL_DEBUG_TERMINAL", "true").lower() == "true"
        )

        # Simple input mode
        self.simple_input = (
            os.getenv("PROTOCOL_SIMPLE_INPUT", "false").lower() == "true"
        )

        # Log file path
        self.debug_log_file = filesystem_config.working_dir / "debug.log"

        # Enhanced logger filename templates
        self.enhanced_log_detailed_tpl = os.getenv(
            "PROTOCOL_LOG_DETAILED", "detailed_{session_id}.jsonl"
        )
        self.enhanced_log_summary_tpl = os.getenv(
            "PROTOCOL_LOG_SUMMARY", "summary_{session_id}.log"
        )
        self.enhanced_log_tokens_tpl = os.getenv(
            "PROTOCOL_LOG_TOKENS", "tokens_{session_id}.jsonl"
        )
        self.enhanced_log_raw_context_tpl = os.getenv(
            "PROTOCOL_LOG_RAW_CONTEXT", "raw_context_{session_id}.jsonl"
        )


# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================


class EnvironmentConfig:
    """Environment-related configuration settings."""

    def __init__(self):
        self.preferred_env = os.getenv("PROTOCOL_PREFERRED_ENV", None)
        self.venv_path = os.getenv("PROTOCOL_VENV_PATH", None)
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")


# =============================================================================
# UI CONFIGURATION
# =============================================================================


class UIConfig:
    """UI-related configuration settings."""

    def __init__(self, disable_async_input: bool = False):
        # Async input feature flag - defaults to False for safety
        # Command-line flag takes precedence over environment variable
        if disable_async_input:
            self.use_async_input = False
        else:
            self.use_async_input = os.getenv("USE_ASYNC_INPUT", "true").lower() == "true"
            self.async_input_fallback = os.getenv("ASYNC_INPUT_FALLBACK", "true").lower() == "true"
            self.input_latency_target_ms = int(os.getenv("INPUT_LATENCY_TARGET_MS", "5"))
            self.platform_optimizations = {
                "linux": os.getenv("LINUX_INPUT_OPTIMIZATION", "true").lower() == "true",
                "darwin": os.getenv("MACOS_INPUT_OPTIMIZATION", "true").lower() == "true",
                "win32": os.getenv("WINDOWS_INPUT_OPTIMIZATION", "true").lower() == "true",
            }


# =============================================================================
# MAIN CONFIGURATION CLASS
# =============================================================================


class ProtocolConfig:
    """Main configuration class that holds all configuration sections."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, disable_async_input: bool = False):
        # Always reinitialize UI config to allow flag changes
        # Other configs can remain cached for performance
        if self._initialized:
            # Only reinitialize UI config
            self.ui = UIConfig(disable_async_input)
            return

        # Initialize configuration sections in dependency order
        self.model = ModelManager()
        self.api = ApiConfig()
        self.filesystem = FileSystemConfig()
        self.model_options = ModelOptionsConfig(self.filesystem)
        self.security = SecurityConfig()
        self.debug = DebugConfig(self.filesystem)
        self.environment = EnvironmentConfig()
        self.ui = UIConfig(disable_async_input)

        # Update model options with context window
        # Ensure num_ctx doesn't exceed the model's context window
        self.model_options.tool_options["num_ctx"] = min(
            self.model_options.tool_options.get("num_ctx", 16384),
            self.model.context_window,
        )
        self.model_options.chat_options["num_ctx"] = min(
            self.model_options.chat_options.get("num_ctx", 16384),
            self.model.context_window,
        )

        self._initialized = True

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        # Check working directory is writable
        pid = os.getpid()
        test_file_path = self.filesystem.working_dir / f".protocol_test_write_{pid}"

        try:
            test_file_path.touch()
        except (OSError, IOError) as e:
            errors.append(f"Working directory not writable: {e}")
        except PermissionError as e:
            errors.append(f"Permission denied creating files in working directory: {e}")
        finally:
            if test_file_path.exists():
                try:
                    test_file_path.unlink()
                except (OSError, IOError) as e:
                    # Non-critical error, just log it
                    print(
                        f"Warning: Could not remove test file {test_file_path}: {e}",
                        file=sys.stderr,
                    )

        # Check context window is reasonable
        if self.model.context_window < 1024:
            errors.append(
                f"Context window too small: {self.model.context_window} (minimum 1024)"
            )

        return errors


# Create global configuration instance
# Global settings instance - will be initialized with bootstrap parameters
def initialize_settings(disable_async_input: bool = False):
    """Initialize global settings with bootstrap parameters."""
    global settings
    settings = ProtocolConfig(disable_async_input)

# Initialize with default values for backward compatibility
settings = ProtocolConfig()
# Validation will be called explicitly in main.py after initialization
