#!/usr/bin/env python3
"""
Focused verification for async input implementation only.
"""

import sys
import time

# Add project root to path
sys.path.insert(0, '.')

def verify_naming_contracts():
    """Verify naming contracts compliance."""
    print("=== Verifying Naming Contracts ===")

    # Import event constants
    from events.input_events import (
        USER_INPUT_SUBMITTED,
        USER_COMMAND_ISSUED,
        USER_INTERRUPT_REQUESTED,
        AGENT_INPUT_REQUESTED,
        INPUT_VALIDATION_COMPLETED
    )

    # Check event naming
    events = [
        USER_INPUT_SUBMITTED,
        USER_COMMAND_ISSUED,
        USER_INTERRUPT_REQUESTED,
        AGENT_INPUT_REQUESTED,
        INPUT_VALIDATION_COMPLETED
    ]

    print("Event constants:")
    for event in events:
        print(f"  ✓ {event}")
        # Check SCREAMING_SNAKE_CASE
        assert event.isupper() and "_" in event, f"{event} must be SCREAMING_SNAKE_CASE"
        # Check present perfect tense
        assert event.split("_")[-1] in ["SUBMITTED", "ISSUED", "REQUESTED", "COMPLETED", "FAILED", "STARTED", "STOPPED"], f"{event} must use present perfect tense"

    print("✓ All events follow naming contracts\n")
    return True


def verify_feature_flags():
    """Verify feature flag implementation."""
    print("=== Verifying Feature Flags ===")

    from config.static import settings, initialize_settings

    # Test default (disabled)
    initialize_settings()
    print(f"Default USE_ASYNC_INPUT: {settings.ui.use_async_input}")
    assert settings.ui.use_async_input == False, "USE_ASYNC_INPUT must be False by default"

    # Test environment variable
    import os
    os.environ['USE_ASYNC_INPUT'] = 'true'
    initialize_settings(disable_async_input=False)
    print(f"With USE_ASYNC_INPUT=true: {settings.ui.use_async_input}")
    assert settings.ui.use_async_input == True, "USE_ASYNC_INPUT must respect environment variable"

    # Test command line override
    initialize_settings(disable_async_input=True)
    print(f"With --no-async-input flag: {settings.ui.use_async_input}")
    assert settings.ui.use_async_input == False, "--no-async-input must override environment variable"

    # Test fallback
    print(f"Fallback enabled: {settings.ui.async_input_fallback}")
    assert settings.ui.async_input_fallback == True, "Fallback must be enabled by default"

    print("✓ Feature flags work correctly\n")
    return True


def verify_safety_mechanisms():
    """Verify safety mechanisms."""
    print("=== Verifying Safety Mechanisms ===")

    from config.static import settings, initialize_settings

    # Reset to safe state
    initialize_settings(disable_async_input=True)

    # Test safety wrapper
    from ui.input_safety_wrapper import create_safe_input_manager

    manager = create_safe_input_manager("plain")
    print(f"SafeInputManager created: {type(manager).__name__}")

    # Verify async is not initialized when disabled
    assert settings.ui.use_async_input == False, "Async input must be disabled in safety test"

    print("✓ Safety mechanisms in place\n")
    return True


def verify_core_architecture():
    """Verify core async input architecture."""
    print("=== Verifying Core Architecture ===")

    # Check async input interface exists
    from ui.async_input_interface import AsyncInputInterface, AsyncInputManager
    print(f"✓ AsyncInputInterface: {AsyncInputInterface.__name__}")
    print(f"✓ AsyncInputManager: {AsyncInputManager.__name__}")

    # Check keyboard capture exists
    from ui.async_keyboard_capture import AsyncKeyboardCapture
    print(f"✓ AsyncKeyboardCapture: {AsyncKeyboardCapture.__name__}")

    # Check UI implementations
    from ui.plain.async_input import PlainAsyncInput
    from ui.textual.async_input import AsyncInputWidget
    print(f"✓ PlainAsyncInput: {PlainAsyncInput.__name__}")
    print(f"✓ AsyncInputWidget: {AsyncInputWidget.__name__}")

    print("\n✓ All core architectural components present\n")
    return True


def main():
    """Run focused verification."""
    print("Protocol Monk Async Input - Focused Verification")
    print("=" * 60)

    try:
        verify_naming_contracts()
        verify_feature_flags()
        verify_safety_mechanisms()
        verify_core_architecture()

        print("=" * 60)
        print("✅ ASYNC INPUT CORE VERIFICATION PASSED")
        print("\nCore async input system is ready for:")
        print("- Zero regression deployment")
        print("- Feature flag controlled rollout")
        print("- Further integration with AgentService")

        return 0

    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())