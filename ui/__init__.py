"""UI package for MonkCode Agent."""

# Don't import at package level to avoid circular imports and __main__ conflicts
# Import explicitly when needed:
#   from ui.animations import play_startup_sequence
#   from ui.prayer_rope import thinking_spinner

__all__ = [
    # Animations
    "play_startup_sequence",
    "display_logos_intro",
    "monk_challenge",
    "play_cinematic_intro_sequence",
    "play_complete_intro_sequence",
    "display_monks_illumination",
    "wait_for_enter",
    "display_protocol_message",
    "display_welcome_panel",
    # Matrix effects
    "run_animation",
    "run_enhanced_matrix_intro",
    "run_sanctified_transition",
    "Matrix",
    # Prayer rope spinners
    "PrayerRope",
    "ThinkingSpinner",
    "GreekLetterSpinner",
    "prayer_rope_progress",
    "thinking_spinner",
    "greek_letter_spinner",
]
