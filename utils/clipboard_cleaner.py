#!/usr/bin/env python3
"""
Clipboard Cleaner - Remove Apple's hidden Unicode characters that break code.
Provides bidirectional cleaning for both incoming and outgoing clipboard content.
"""

import shlex
import unicodedata

import asyncio
import logging
import re
import subprocess
from typing import Dict

from config.static import settings

logger = logging.getLogger(__name__)
_clipboard_lock = asyncio.Lock()


def clean_text(text: str) -> str:
    """Remove hidden Unicode characters that break code."""
    if not text:
        return text

    text = _normalize_unicode(text)
    text = _filter_invisible_chars(text)
    text = _apply_replacements(text)
    text = _normalize_newlines(text)

    return text


def _normalize_unicode(text: str) -> str:
    """Normalize Unicode to decomposed form, then recompose."""
    try:
        return unicodedata.normalize("NFKC", text)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Unicode normalization failed: %s. Proceeding with un-normalized text.",
            e,
            exc_info=True,
        )
        return text


def _filter_invisible_chars(text: str) -> str:
    """Remove invisible/control characters except essential ones."""
    # Keep: \t (9), \n (10), \r (13), space (32), printable ASCII (33-126)
    allowed_control_codes = {9, 10, 13, 32}

    return "".join(
        char
        for char in text
        if (
            ord(char) in allowed_control_codes
            or (33 <= ord(char) <= 126)  # Printable ASCII
            # Allow valid non-ASCII but not control/separator
            or (ord(char) > 126 and unicodedata.category(char)[0] not in ["C", "Z"])
        )
    )


def _apply_replacements(text: str) -> str:
    """Fix common Apple clipboard issues."""
    replacements: Dict[str, str] = {
        "\u2018": "'",  # Left single quotation mark
        "\u2019": "'",  # Right single quotation mark
        "\u201c": '"',  # Left double quotation mark
        "\u201d": '"',  # Right double quotation mark
        "\u2013": "-",  # En dash
        "\u2014": "--",  # Em dash
        "\u00a0": " ",  # Non-breaking space
        "\u200b": "",  # Zero-width space
        "\u200c": "",  # Zero-width non-joiner
        "\u200d": "",  # Zero-width joiner
        "\ufeff": "",  # Byte order mark
    }

    for bad_char, replacement in replacements.items():
        text = text.replace(bad_char, replacement)
    return text


def _normalize_newlines(text: str) -> str:
    """Normalize whitespace and line endings."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)
    return text


def _get_command_args(command_str: str) -> list:
    """Safely parse command string into list for subprocess."""
    return shlex.split(command_str)


def _unsafe_read_clipboard() -> str:
    """Reads from the system clipboard without locking."""
    cmd = settings.security.clipboard_paste_cmd
    try:
        # SECURITY FIX: Use shell=False with parsed arguments
        result = subprocess.run(
            _get_command_args(cmd),
            shell=False,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        return result.stdout
    except subprocess.TimeoutExpired as e:
        logger.error("Clipboard read timed out.", exc_info=True)
        raise IOError("Clipboard paste command timed out.") from e
    except subprocess.CalledProcessError as e:
        logger.error(
            "Clipboard read failed with code %s: %s",
            e.returncode,
            e.stderr,
            exc_info=True,
        )
        raise IOError(f"Clipboard paste failed: {e.stderr}") from e
    except FileNotFoundError as e:
        logger.error("Clipboard command not found: %s", cmd, exc_info=True)
        raise IOError(f"Clipboard command not found: {cmd}") from e
    except Exception as e:
        logger.error("Unexpected clipboard read error: %s", e, exc_info=True)
        raise IOError(f"Unexpected clipboard read error: {e}") from e


def _unsafe_write_clipboard(text: str):
    """Writes to the system clipboard without locking."""
    cmd = settings.security.clipboard_copy_cmd
    try:
        # SECURITY FIX: Use 'with' context manager and shell=False
        with subprocess.Popen(
            _get_command_args(cmd),
            shell=False,
            stdin=subprocess.PIPE,
            text=True,
            stderr=subprocess.PIPE,
        ) as process:
            _, stderr = process.communicate(input=text, timeout=2)

            if process.returncode != 0:
                logger.error(
                    "Clipboard write failed with code %s: %s",
                    process.returncode,
                    stderr,
                )
                raise IOError(f"Clipboard copy failed: {stderr}")

    except subprocess.TimeoutExpired as e:
        logger.error("Clipboard write timed out.", exc_info=True)
        # Process is cleaned up by context manager mostly, but good to be explicit if stuck
        raise IOError("Clipboard copy command timed out.") from e
    except FileNotFoundError as e:
        logger.error("Clipboard command not found: %s", cmd, exc_info=True)
        raise IOError(f"Clipboard command not found: {cmd}") from e
    except Exception as e:
        logger.error("Unexpected clipboard write error: %s", e, exc_info=True)
        raise IOError(f"Unexpected clipboard write error: {e}") from e


async def clean_clipboard_in() -> str:
    """Get clipboard content and clean it."""
    try:
        async with _clipboard_lock:
            original = await asyncio.to_thread(_unsafe_read_clipboard)
        cleaned = await asyncio.to_thread(clean_text, original)

        if original != cleaned:
            hidden_chars = len(original) - len(cleaned)
            logger.info("🧹 Cleaned %d hidden characters from clipboard", hidden_chars)

        return cleaned
    except (IOError, Exception) as e:  # pylint: disable=broad-exception-caught
        logger.error("Error cleaning clipboard: %s", str(e), exc_info=True)
        return f"Error cleaning clipboard: {str(e)}"


async def clean_clipboard_out(text: str) -> bool:
    """Clean text and put it on clipboard."""
    try:
        cleaned = await asyncio.to_thread(clean_text, text)
        async with _clipboard_lock:
            await asyncio.to_thread(_unsafe_write_clipboard, cleaned)

        if text != cleaned:
            hidden_chars = len(text) - len(cleaned)
            logger.info("🧹 Cleaned %d hidden characters before copying", hidden_chars)
        return True
    except (IOError, Exception) as e:  # pylint: disable=broad-exception-caught
        logger.error("Error copying to clipboard: %s", str(e), exc_info=True)
        return False


async def clean_clipboard_round_trip() -> str:
    """Get clipboard, clean it, and put it back atomically."""
    async with _clipboard_lock:
        try:
            original = await asyncio.to_thread(_unsafe_read_clipboard)
            cleaned = await asyncio.to_thread(clean_text, original)

            if original == cleaned:
                return "✅ Clipboard already clean."

            await asyncio.to_thread(_unsafe_write_clipboard, cleaned)
            return "✅ Clipboard cleaned and updated"
        except (IOError, Exception) as e:  # pylint: disable=broad-exception-caught
            return f"Error: {str(e)}"


if __name__ == "__main__":
    import sys

    # Quick CLI for testing
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        print(asyncio.run(clean_clipboard_round_trip()))
    else:
        print("Clipboard Cleaner Utility")
        print("Usage:")
        print("  python clipboard_cleaner.py clean    # Clean current clipboard")
        print("  from utils.clipboard_cleaner import clean_text  # Use in code")
