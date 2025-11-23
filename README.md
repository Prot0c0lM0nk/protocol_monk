# Protocol Monk ✠

A terminal-based AI coding assistant with streaming mixed-mode responses (text + tool execution).

## Overview

Protocol Monk is designed to solve a specific problem in the agentic AI landscape: **most open-source coding assistants can either chat OR use tools, but not both simultaneously**. Protocol Monk implements streaming mixed-mode responses, allowing the AI to explain its reasoning while executing file operations, shell commands, and other tools.

### Key Technical Features

- **Streaming Mixed-Mode Parser**: Handles interleaved text and JSON tool calls in a single response stream
- **Line-Based File Editing**: Precise file modifications using line numbers (more reliable than string matching)
- **Robust JSON Parsing**: Multiple fallback strategies for handling malformed model outputs
- **Orthodox-Themed UI**: Unique branding with prayer rope progress indicators and Matrix-inspired visuals
- **Provider Flexibility**: Works with Ollama (local/free) or Anthropic Claude (cloud/paid)
- **Async Architecture**: Fully asynchronous design for better performance and responsiveness

## Architecture

Protocol Monk uses a clean, modular architecture with a unified configuration system:

```
protocol_core/
├── agent/
│   ├── __init__.py
│   ├── context.py          # Conversation context management with token pruning
│   ├── core.py             # Main agent loop with streaming response handler
│   ├── exceptions.py       # Custom exception classes
│   ├── model_client.py     # Async HTTP client for LLM providers
│   └── tool_executor.py    # Tool execution with user confirmation
├── config/
│   ├── __init__.py
│   ├── session.py          # Runtime session configuration (directory selection, environment)
│   └── static.py           # Static application configuration (models, security, etc.)
├── tools/
│   ├── __init__.py
### Core Components

**Agent Core** (`agent/core.py`)
- Main agent loop with streaming response handler
- Manages conversation flow and tool execution
- Fully asynchronous implementation

**Context Manager** (`agent/context.py`)
- Maintains conversation history with token counting
- Implements smart pruning when approaching context limits
- Preserves important messages while dropping low-priority content
- Asynchronous context management

**Tool Registry** (`tools/registry.py`)
- Auto-discovery and management of tools
- Dependency injection for environment configuration
- Dynamic tool loading and initialization

**Model Client** (`agent/model_client.py`)
- Async HTTP client for LLM providers
- Supports streaming responses with proper error handling
- Provider-agnostic interface for Ollama and other models

**Configuration System** (`config/static.py` and `config/session.py`)
- Unified three-pillar configuration architecture
- Static configuration for application-wide settings
- Session configuration for runtime environment settings
│   ├── __init__.py
│   ├── base.py             # Abstract UI interface
│   ├── plain.py            # Plain text terminal UI
│   ├── animations.py       # Loading animations
│   ├── custom_matrix.py    # Matrix-style visual effects
│   └── prayer_rope.py      # Orthodox-themed progress indicators
├── utils/
│   ├── __init__.py
│   ├── clipboard_cleaner.py # Unicode character cleanup for clipboard operations
│   ├── debug_logger.py     # Basic debug logging
│   ├── enhanced_logger.py  # Comprehensive session logging
│   ├── json_parser.py      # Robust JSON extraction from mixed text/code responses
│   ├── sensitive_str.py    # Secure string handling for API keys
│   └── token_estimation.py # Token counting and estimation
├── main.py                 # CLI entry point with command history
├── system_prompt.txt       # System prompt template with tool definitions
├── model_map.json          # Model capability mapping
├── model_options.json      # Model-specific options
├── requirements.txt        # Python dependencies
├── environment.yml         # Conda environment specification
└── README.md              # Project documentation
```

### Core Components

## Configuration

Protocol Monk uses a unified three-pillar configuration system:

1. **Static Configuration** (`config/static.py`) - Load-once application settings
2. **Session Configuration** (`config/session.py`) - Runtime environment settings
3. **Environment Variables** - Override settings at runtime

Create a `.env` file or export variables:

```bash
# Model Selection (Ollama local models)
export PROTOCOL_MODEL="qwen3:4b"

# OR use Anthropic Claude (requires API key)
export PROTOCOL_MODEL="claude-sonnet-4-5-20250929"
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Working Directory (automatically selected on first run)
# export PROTOCOL_WORKING_DIR="$HOME/Desktop/my_project"

# Optional: Ollama URL (if not default)
export PROTOCOL_OLLAMA_URL="http://localhost:11434/api/chat"

# Python Environment (automatically detected)
# export PROTOCOL_PREFERRED_ENV="my_conda_env"
# export PROTOCOL_VENV_PATH=".venv"
```
## Installation

### Prerequisites

- Python 3.9+
- Ollama (for local models) OR Anthropic API key (for Claude)

### Setup with Conda (Recommended)

```bash
# Create conda environment
conda env create -f environment.yml
conda activate protocol-monk

# Run the agent (will prompt for directory selection on first run)
python main.py
```

### Setup with pip

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the agent (will prompt for directory selection on first run)
python main.py
```
```bash
## Technical Highlights

### Unified Configuration System

Protocol Monk implements a clean three-pillar configuration architecture:

1. **Static Configuration** (`config/static.py`) - All load-once application settings
2. **Session Configuration** (`config/session.py`) - Runtime environment and project settings
3. **Dependency Injection** - Tools receive environment settings without global imports

This eliminates circular dependencies and makes the system more maintainable.

### Dynamic Project Directory Selection

On first run, Protocol Monk presents a desktop directory selector that:
- Shows all directories on the user's desktop
- Automatically detects Python projects and their environments
- Saves configuration for subsequent runs
- Supports both conda and virtual environments

### Streaming Mixed-Mode Response Handling

The core innovation is the ability to parse streaming responses that contain both conversational text and JSON tool calls:

```python
# Example streaming response from model:
"Let me help you with that. I'll create the file first.
{
    \"action\": \"create_file\",
    \"parameters\": {\"filepath\": \"test.py\", \"content\": \"print('hello')\"}
}
Now the file is created!"

# Parser extracts:
# - Text: "Let me help you with that. I'll create the file first."
# - Tool: create_file(filepath="test.py", content="print('hello')")
# - Text: "Now the file is created!"
```

### Line-Based File Editing

Unlike string-matching approaches (which fail with whitespace/formatting changes), Protocol Monk uses line numbers:

```python
replace_lines(
    filepath="app.py",
    line_start=15,
    line_end=20,
    new_content="def improved_function():\n    return True"
)
```

This approach is more reliable and matches how developers think about code locations.

### Robust JSON Parsing

The parser implements multiple fallback strategies:

1. **Standard JSON parsing** - Try json.loads() first
2. **Regex extraction** - Extract JSON blocks from mixed text
3. **Manual field extraction** - Parse known fields with regex
4. **Emergency inference** - Infer intent from natural language (disabled by default)

This multi-layered approach achieves high success rates even with models that struggle with structured output.
## Usage

### Basic Commands

```
User: Create a Python script that prints hello world

User: Show me the contents of main.py

User: Replace lines 5-10 in main.py with a better implementation

User: Run pytest on the test directory
```

### Slash Commands

- `/help` - Show available commands
- `/model <name>` - Switch AI model
- `/status` - Show token usage and current model
- `/clear` - Clear conversation history
- `/quit` - Exit with blessing

### Available Tools

#### File Operations
- **create_file** - Create a new file with content
- **show_file** - Read and display a file
- **replace_lines** - Edit specific line ranges (preferred method)
- **append_to_file** - Add content to end of file

#### Shell Operations
- **shell_execute** - Run shell commands (with safety validation)
- **run_python** - Execute Python code in a temporary script

#### Control Flow
- **finish** - Signal task completion

## Design Decisions

### Why Unified Configuration?

The three-pillar configuration system eliminates circular dependencies and makes the codebase more maintainable:
- **Static config** is loaded once and never changes
- **Session config** is runtime-specific and project-aware
- **Dependency injection** removes global state coupling

### Why Dynamic Directory Selection?

Hard-coding working directories limits flexibility. The desktop selector provides:
- Zero-configuration first-run experience
- Project-aware environment detection
- Persistent session management
- User-friendly directory browsing

### Why Line-Based Editing?

String-based find-replace fails when:
- Code formatting changes
- Multiple identical code blocks exist
- Whitespace is inconsistent

Line-based editing mirrors how developers navigate code and is less ambiguous.

### Why Mixed-Mode Streaming?

Pure JSON mode (no text) creates a robotic experience. Pure chat mode (no tools) can't modify files reliably. Mixed-mode provides:
- Natural explanations of what the AI is doing
- Reliable tool execution for file operations
- Better user experience than either extreme

### Why Multiple Parsers?

Different LLMs have different strengths:
- Claude: Excellent at structured JSON
- Qwen/DeepSeek: Good reasoning, inconsistent formatting
- Local models: Fast but struggle with complex schemas

Multiple fallback strategies allow Protocol Monk to work with various model qualities.
### Control Flow
## Project Status

Protocol Monk Core is a mature, production-ready agentic framework. Key features include:
- ✅ Unified three-pillar configuration system
- ✅ Dynamic project directory selection with environment detection
- ✅ Core agent loop with streaming mixed-mode responses
- ✅ Comprehensive file and shell operation tools
- ✅ Robust JSON parsing with multiple fallback strategies
- ✅ Multi-provider support (Ollama + Anthropic)
- ✅ Fully asynchronous architecture
- ✅ Orthodox-themed terminal UI with rich visual feedback
- ✅ Comprehensive logging and debugging capabilities

The framework is ready for real-world usage and can be extended with additional tools and UI implementations.
## License

This project is currently in development and not yet licensed for public distribution.

## Contributing

Contributions welcome! Areas of interest:
- Additional tool implementations
- Parser robustness improvements
- Model-specific optimizations
- UI/UX enhancements
- New environment detection strategies

## Credits

Developed by Nicholas Pitzarella
Orthodox-themed UI concept inspired by Byzantine iconography and modern cyberpunk aesthetics.

### Line-Based File Editing

Unlike string-matching approaches (which fail with whitespace/formatting changes), Protocol Monk uses line numbers:

```python
replace_lines(
    filepath="app.py",
    line_start=15,
    line_end=20,
    new_content="def improved_function():\n    return True"
)
```

This approach is more reliable and matches how developers think about code locations.

### Robust JSON Parsing

The parser implements multiple fallback strategies:

1. **Standard JSON parsing** - Try json.loads() first
2. **Regex extraction** - Extract JSON blocks from mixed text
3. **Manual field extraction** - Parse known fields with regex
4. **Emergency inference** - Infer intent from natural language (disabled by default)

This multi-layered approach achieves ~60% success rate even with models that struggle with structured output.

## Design Decisions

### Why Line-Based Editing?

String-based find-replace fails when:
- Code formatting changes
- Multiple identical code blocks exist
- Whitespace is inconsistent

Line-based editing mirrors how developers navigate code and is less ambiguous.

### Why Mixed-Mode Streaming?

Pure JSON mode (no text) creates a robotic experience. Pure chat mode (no tools) can't modify files reliably. Mixed-mode provides:
- Natural explanations of what the AI is doing
- Reliable tool execution for file operations
- Better user experience than either extreme

### Why Multiple Parsers?

Different LLMs have different strengths:
- Claude: Excellent at structured JSON
- Qwen/DeepSeek: Good reasoning, inconsistent formatting
- Local models: Fast but struggle with complex schemas

Multiple fallback strategies allow Protocol Monk to work with various model qualities.

## Project Status

Protocol Monk Core is the open-source foundation of a larger agentic framework. This version includes:
- ✅ Core agent loop with streaming
- ✅ Essential file and shell tools
- ✅ Robust JSON parsing
- ✅ Multi-provider support (Ollama + Anthropic)
- ✅ Fully asynchronous architecture

Advanced features (knowledge graphs, pattern learning, advanced guidance systems) are available in the enterprise version.

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Areas of interest:
- Additional tool implementations
- Parser robustness improvements
- Model-specific optimizations
- UI/UX enhancements

## Credits

Developed by Nicholas Pitzarella
Orthodox-themed UI concept inspired by Byzantine iconography and modern cyberpunk aesthetics.
