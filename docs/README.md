# Protocol Monk ✠

**⚠️ DEMO VERSION - FOR EVALUATION ONLY**

A terminal-based AI agent with reliable task execution and comprehensive error handling.

---

## Overview
Protocol Monk is a sophisticated terminal-based AI agent designed for reliable task execution through natural language interaction. **This is a demonstration version** provided for evaluation purposes only. The system implements a TAOR (Think-Act-Observe-Reflect) cognitive loop with comprehensive error handling that prevents crashes and ensures graceful degradation.

**⚠️ Important Demo Notice:**
This version is provided as-is for evaluation. Features may be incomplete, context management may not work reliably in all scenarios, and this software should not be used for critical work.

---

## Key Features
- **Reliable Operation**: Comprehensive exception handling prevents crashes
- **Multi-Provider Support**: Runtime switching between Ollama and OpenRouter
- **Secure Tool Execution**: Path validation and dangerous pattern detection
- **Flexible UI**: Multiple rendering backends (plain, rich)
- **Context Management**: Token-aware conversation history with pruning
- **TAOR Loop**: Think-Act-Observe-Reflect cognitive cycle
- **Line-Based File Editing**: Precise code modifications using line numbers
- **Robust JSON Parsing**: Multiple fallback strategies for handling model outputs
- **Async Architecture**: Fully asynchronous design for optimal performance

---

## Installation

**IMPORTANT: This is a DEMO version for evaluation only.**

### From PyPI (Demo Version)
```bash
pip install protocol-monk
monk
```

**Demo Limitations:**
- Evaluation purposes only
- No redistribution or modification allowed
- Context management may not work reliably in all scenarios
- Session history is not preserved
- Features are incomplete and may contain bugs

### From Source
```bash
# Clone the repository
git clone <repository-url>
cd protocol-monk

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Protocol Monk
python main.py
```

### Development Installation
```bash
pip install -e .[dev]
```

---

## Prerequisites
- Python 3.8+
- Ollama (for local models) OR OpenRouter API key

---

## Configuration
*(Section previously empty)*

---

## Usage

### First Run
The agent will guide you through initial setup:
1. Select working directory
2. Choose AI provider and model
3. Configure optional settings

### Basic Commands
- Create files and directories
- Edit specific lines of files
- Execute shell commands
- Run Python scripts
- Perform git operations

### Examples
```
User: Create a Python script that prints 'Hello, World!'

User: Show me the contents of main.py

User: Replace lines 5-10 in app.py with a better implementation

User: Run pytest on the test directory

User: Commit the current changes with a descriptive message
```

### Slash Commands
- `/help` - Show available commands
- `/model <name>` - Switch AI model
- `/clear` - Clear conversation context
- `/status` - Show current status and token usage
- `/quit` - Exit the agent

---

## Architecture
```
agent/          # Core orchestration and TAOR loop
tools/          # Secure tool execution system
ui/             # User interface abstraction
exceptions/     # Comprehensive error handling
config/         # Configuration management
utils/          # Shared utilities
```

---

## Security
- Path validation prevents access to sensitive files
- Dangerous pattern detection blocks harmful operations
- Sandboxed tool execution with configurable policies
- Input validation for all user inputs

---

## AI Collaboration
Protocol Monk is designed to work with AI models as collaborative partners. The system supports multiple AI backends and provides reliable tool execution for iterative development workflows.

### AI Model Integration
- Seamless integration with Ollama models
- OpenRouter support for cloud-based models
- Runtime model switching
- Customizable prompting strategies

---

## Development
```bash
# Format code
black .

# Lint code
pylint .

# Type check
mypy .

# Run tests
pytest
```

---

## License
see LICENSE file for details.

---

Developed with ☦︎ by Nicholas Pitzarella

