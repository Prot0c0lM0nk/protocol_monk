# Protocol Monk ✠

A terminal-based AI coding assistant with streaming mixed-mode responses (text + tool execution).

## Overview

Protocol Monk is an AI assistant that combines natural language interaction with precise code editing capabilities. It solves a key limitation in current AI coding tools by supporting simultaneous chat and tool execution through a streaming mixed-mode response system.

## ✨ Key Features

- **Streaming Mixed-Mode Responses**: Seamlessly blends conversational text with executable tool calls
- **Line-Based File Editing**: Precise code modifications using line numbers (more reliable than string matching)
- **Robust JSON Parsing**: Multiple fallback strategies for handling model outputs
- **Local-First Architecture**: Runs entirely locally using Ollama models
- **Async Architecture**: Fully asynchronous design for optimal performance
- **Orthodox-Themed UI**: Unique terminal interface with prayer rope progress indicators

## 🚀 Installation

### Prerequisites
- Python 3.9+
- [Ollama](https://ollama.ai/) installed and running

### Quick Start

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

## ⚙️ Configuration

Create a `.env` file in the project root (optional):

```bash
# Set your preferred Ollama model (default: qwen3:4b)
# Uncomment and modify the line below to set your preferred model
# PROTOCOL_MODEL="your-preferred-model"

# Optional: Custom Ollama URL (if not using default)
# Uncomment and modify the line below if you need a custom Ollama URL
# PROTOCOL_OLLAMA_URL="http://localhost:11434/api/chat"

# Optional: Set default working directory
# Uncomment and modify the line below to set a default working directory
# PROTOCOL_WORKING_DIR="$HOME/your_project"
```

## 🛠️ Usage

### Basic Commands
- Create files and directories
- Edit specific lines of code
- Execute shell commands
- Run Python scripts

### Examples
```
User: Create a Python script that prints 'Hello, World!'

User: Show me the contents of main.py

User: Replace lines 5-10 in app.py with a better implementation

User: Run pytest on the test directory
```

### Slash Commands
- `/help` - Show available commands
- `/model <name>` - Switch AI model
- `/status` - Show token usage and current model

## 🤝 AI Collaboration

Protocol Monk is designed to work with AI models as collaborative partners. The system is built to leverage AI capabilities for code generation, analysis, and refactoring tasks.

### AI Model Integration
- Seamless integration with Ollama models
- Support for multiple AI backends
- Customizable prompting strategies

---

Solo Developed with ☦︎ by Nicholas Pitzarella
