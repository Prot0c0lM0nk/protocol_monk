# Getting Started with Protocol Monk Core

Welcome to Protocol Monk - a terminal-based AI coding assistant with a unique Orthodox-Matrix aesthetic.

## Quick Start

### 1. Install Dependencies

**Using Conda (Recommended):**
```bash
conda env create -f environment.yml
conda activate protocol-monk
```

**Using pip:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example configuration:
```bash
cp .env.example .env
```

Edit `.env` to set your preferences:
```bash
# Use local Ollama (free):
PROTOCOL_MODEL=qwen3:4b

# OR use Anthropic Claude (requires API key):
# PROTOCOL_MODEL=claude-sonnet-4-5-20250929
# ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Run Protocol Monk

```bash
python main.py
```

You'll see the Matrix-Orthodox greeting:

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ☦  P R O T O C O L   M O N K  ☦                           ║
║                                                              ║
║   "What if I told you... the code was never broken?"         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

## Basic Usage

### Natural Language Requests

Simply describe what you need:

```
☦ > Create a Python script that prints fibonacci numbers

☦ > Show me test.py

☦ > Replace lines 5-10 in test.py with an optimized version
```

### Available Commands

- `/help` - Show help and available tools
- `/status` - View current model, token usage, and state
- `/model <name>` - Switch to a different model
- `/clear` - Clear conversation history
- `/quit` - Exit with blessing

### Available Tools

Protocol Monk has these core tools:

1. **create_file** - Create new files
2. **show_file** - Read and display files (with line numbers)
3. **replace_lines** - Edit files by line number (recommended for code changes)
4. **append_to_file** - Add content to end of file
5. **shell_execute** - Run shell commands (with safety validation)
6. **finish** - Signal task completion

## Examples

### Example 1: Create a Simple Python Script

```
☦ > Create a Python script called hello.py that prints "Hello, Protocol"
```

The agent will:
1. Explain what it's going to do
2. Show you the tool call (create_file)
3. Ask for confirmation
4. Create the file
5. Confirm completion

### Example 2: Edit a File

```
☦ > Show me hello.py

☦ > Replace lines 1-2 with a function that returns the greeting
```

The agent will:
1. Display the file with line numbers
2. Generate the new function code
3. Show the replace_lines tool call
4. Ask for confirmation
5. Update the file

### Example 3: Run Tests

```
☦ > Run pytest on the tests directory
```

The agent will:
1. Show the shell_execute tool call
2. Ask for confirmation
3. Execute the command
4. Display results

## Model Options

### Local Models (Free via Ollama)

```bash
# Fast and efficient
PROTOCOL_MODEL=qwen3:4b

# Larger, more capable
PROTOCOL_MODEL=qwen3:8b

# Specialized for coding
PROTOCOL_MODEL=deepseek-coder:7b
```

### Cloud Models (Paid via Anthropic)

```bash
# Best for coding tasks
PROTOCOL_MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Faster, cheaper
PROTOCOL_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## Troubleshooting

### "Anthropic model selected but ANTHROPIC_API_KEY not set"

Set your API key in `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-your-actual-key
```

### "Ollama connection failed"

Make sure Ollama is running:
```bash
ollama serve
```

### "Path outside working directory"

Protocol Monk restricts file operations to `PROTOCOL_WORKING_DIR` for security.
Set it in `.env` to your project directory.

### Token Usage High

The agent automatically prunes conversation when approaching limits.
You can also use `/clear` to start fresh.

## Tips for Best Results

1. **Show files first** - Use `show_file` before editing so the agent sees line numbers
2. **Use line-based editing** - `replace_lines` is more reliable than describing changes
3. **Be specific** - "Replace lines 10-15" works better than "fix the bug"
4. **Confirm carefully** - Review tool calls before approving
5. **Use /status** - Monitor token usage to avoid context limits

## What's Next?

- Read [README.md](README.md) for architecture details
- Explore the code in `agent/` and `tools/`
- Try different models to find what works best for you
- Customize the system prompt in `agent/context.py`

---

**☦ May your code compile without warning ☦**
