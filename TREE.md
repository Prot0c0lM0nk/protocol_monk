tree -I "*.pyc"
.
├── __init__.py
├── __pycache__
├── agent
│   ├── __pycache__
│   ├── context
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── coordinator.py
│   │   ├── file_tracker.py
│   │   ├── logic.py
│   │   └── store.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── execution.py
│   │   ├── service.py
│   │   └── state_machine.py
│   ├── loops.py
│   └── structs.py
├── config
│   ├── __init__.py
│   ├── __pycache__
│   ├── models.json
│   ├── openrouter_models.json
│   ├── settings.py
│   └── startup.py
├── exceptions
│   ├── __init__.py
│   ├── __pycache__
│   ├── base.py
│   ├── bus.py
│   ├── config.py
│   ├── context.py
│   ├── provider.py
│   └── tools.py
├── main.py
├── protocol
│   ├── __init__.py
│   ├── __pycache__
│   ├── bus.py
│   └── events.py
├── providers
│   ├── __pycache__
│   ├── base.py
│   ├── factory.py
│   ├── ollama.py
│   └── openrouter.py
├── scripts
│   ├── __init__.py
│   ├── __pycache__
│   ├── analyze_session.py
│   ├── fetch_model_config.py
│   └── setup_wizard.py
├── system_prompt.txt
├── tools
│   ├── __init__.py
│   ├── __pycache__
│   ├── base.py
│   ├── defaults.py
│   ├── file_operations
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── append_to_file_tool.py
│   │   ├── auto_stage_large_content.py
│   │   ├── create_file_tool.py
│   │   ├── delete_lines_tool.py
│   │   ├── insert_in_file_tool.py
│   │   ├── read_file_tool.py
│   │   ├── replace_lines_tool.py
│   │   └── scratch_coordination.py
│   ├── path_validator.py
│   ├── registry.py
│   └── shell_operations
│       ├── __pycache__
│       ├── execute_command_tool.py
│       ├── git_operation_tool.py
│       └── run_python_tool.py
├── ui
│   ├── __init__.py
│   ├── __pycache__
│   ├── cli.py
│   └── textual
│       ├── __init__.py
│       ├── __pycache__
│       ├── app.py
│       ├── bridge.py
│       ├── messages.py
│       ├── mock_agent.py
│       ├── mock_main.py
│       ├── models
│       │   ├── __init__.py
│       │   ├── __pycache__
│       │   └── phase_state.py
│       ├── screens
│       │   ├── __init__.py
│       │   ├── __pycache__
│       │   ├── main_chat.py
│       │   └── modals
│       │       ├── __init__.py
│       │       ├── __pycache__
│       │       └── tool_confirm.py
│       ├── styles
│       │   ├── chat.tcss
│       │   ├── components.tcss
│       │   └── main.tcss
│       └── widgets
│           ├── __init__.py
│           ├── __pycache__
│           ├── chat_area.py
│           ├── input_bar.py
│           └── status_bar.py
└── utils
    ├── __init__.py
    ├── __pycache__
    ├── exceptions.py
    ├── logger.py
    ├── model_discovery.py
    ├── openrouter_model_map.py
    ├── scratch.py
    ├── session_transcript.py
    └── token_estimation.py

39 directories, 83 files
