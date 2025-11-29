#!/usr/bin/env python3
"""
Clipboard Cleaner - Remove Apple's hidden Unicode characters that break code.
Provides bidirectional cleaning for both incoming and outgoing clipboard content.
"""

import subprocess
import re
import unicodedata
import logging
from typing import Optional
import asyncio

# No exception imports needed
from config.static import settings

logger = logging.getLogger(__name__)
_clipboard_lock = asyncio.Lock()


def clean_text(text: str) -> str:
    """Remove hidden Unicode characters that break code."""
    if not text:
        return text

    # Step 1: Normalize Unicode to decomposed form, then recompose
    try:
        text = unicodedata.normalize("NFKC", text)
    except Exception as e:
        # HEALTHCHECK FIX: Catches silent Unicode normalization failures
        logger.warning(
            f"Unicode normalization failed: {e}. Proceeding with un-normalized text.",
            exc_info=True,
        )

    # Step 2: Remove invisible/control characters except essential ones
    # Keep: \t (tab), \n (newline), \r (carriage return), space (32), printable ASCII (33-126)
    cleaned = "".join(
        char
        for char in text
        if (
            ord(char) == 9  # Tab
            or ord(char) == 10  # Newline
            or ord(char) == 13  # Carriage return
            or ord(char) == 32  # Space
            or (33 <= ord(char) <= 126)  # Printable ASCII
            or (
                ord(char) > 126 and unicodedata.category(char)[0] not in ["C", "Z"]
            )  # Allow valid non-ASCII but not control/separator
        )
    )

    # Step 3: Fix common Apple clipboard issues
    replacements = {
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
        cleaned = cleaned.replace(bad_char, replacement)

    # Step 4: Normalize whitespace
    cleaned = re.sub(r"\r\n", "\n", cleaned)  # Windows line endings
    cleaned = re.sub(r"\r", "\n", cleaned)  # Mac line endings


def _unsafe_read_clipboard() -> str:
    """Reads from the system clipboard without locking."""
    try:
        result = subprocess.run(
            settings.security.clipboard_paste_cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=True,  # Will raise CalledProcessError on failure
            timeout=2,
        )
        return result.stdout
    except subprocess.TimeoutExpired as e:
        logger.error("Clipboard read timed out.", exc_info=True)
        raise IOError("Clipboard paste command timed out.") from e
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Clipboard read failed with code {e.returncode}: {e.stderr}", exc_info=True
        )
        raise IOError(f"Clipboard paste failed: {e.stderr}") from e
    except FileNotFoundError as e:
        logger.error(
            f"Clipboard command not found: {settings.security.clipboard_paste_cmd}",
            exc_info=True,
        )
        raise IOError(
            f"Clipboard command not found: {settings.security.clipboard_paste_cmd}"
        ) from e
    except Exception as e:
        logger.error(f"Unexpected clipboard read error: {e}", exc_info=True)
        raise IOError(f"Unexpected clipboard read error: {e}") from e


def _unsafe_write_clipboard(text: str):
    """Writes to the system clipboard without locking."""
    try:
        process = subprocess.Popen(
            settings.security.clipboard_copy_cmd,
            shell=True,
            stdin=subprocess.PIPE,
            text=True,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(input=text, timeout=2)

        if process.returncode != 0:
            logger.error(
                f"Clipboard write failed with code {process.returncode}: {stderr}"
            )
            raise IOError(f"Clipboard copy failed: {stderr}")
    except subprocess.TimeoutExpired as e:
        logger.error("Clipboard write timed out.", exc_info=True)
        process.kill()  # Ensure process is cleaned up
        raise IOError("Clipboard copy command timed out.") from e
    except FileNotFoundError as e:
        logger.error(
            f"Clipboard command not found: {settings.security.clipboard_copy_cmd}",
            exc_info=True,
        )
        raise IOError(
            f"Clipboard command not found: {settings.security.clipboard_copy_cmd}"
        ) from e
    except Exception as e:
        logger.error(f"Unexpected clipboard write error: {e}", exc_info=True)
        raise IOError(f"Unexpected clipboard write error: {e}") from e


async def clean_clipboard_in() -> str:
    """Get clipboard content and clean it."""
    try:
        async with _clipboard_lock:
            original = await asyncio.to_thread(_unsafe_read_clipboard)
        cleaned = await asyncio.to_thread(clean_text, original)

        if original != cleaned:
            hidden_chars = len(original) - len(cleaned)
            logger.info(f"🧹 Cleaned {hidden_chars} hidden characters from clipboard")

        return cleaned
    except (IOError, Exception) as e:
        # HEALTHCHECK FIX: Catches silent subprocess failures
        logger.error(f"Error cleaning clipboard: {str(e)}", exc_info=True)
        return f"Error cleaning clipboard: {str(e)}"


async def clean_clipboard_out(text: str) -> bool:
    """Clean text and put it on clipboard."""
    try:
        cleaned = await asyncio.to_thread(clean_text, text)
        async with _clipboard_lock:
            await asyncio.to_thread(_unsafe_write_clipboard, cleaned)

        if text != cleaned:
            hidden_chars = len(text) - len(cleaned)
            logger.info(f"🧹 Cleaned {hidden_chars} hidden characters before copying")
        return True
    except (IOError, Exception) as e:
        logger.error(f"Error copying to clipboard: {str(e)}", exc_info=True)
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
        except (IOError, Exception) as e:
            return f"Error: {str(e)}"


if __name__ == "__main__":
    # Command-line usage
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        print(clean_clipboard_round_trip())
    else:
        print("Clipboard Cleaner Utility")
        print("Usage:")
        print("  python clipboard_cleaner.py clean    # Clean current clipboard")
        print("  from utils.clipboard_cleaner import clean_text  # Use in code")
