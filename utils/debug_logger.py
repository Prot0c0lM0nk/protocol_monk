#!/usr/bin/env python3
"""
Debug logging utility for MonkCode.

Writes debug output to both stderr and a log file that can be tailed in a separate terminal.
Usage:
    from utils.debug_logger import debug_log

    debug_log("System prompt", content, separator="=")
"""

import threading
from datetime import datetime
from queue import Empty, Queue

import sys
from pathlib import Path

from utils.exceptions import ConfigurationError


class DebugLogger:
    """Singleton debug logger that writes to both stderr and file using a queue-based worker thread"""

    _instance = None
    _instance_lock = threading.Lock()
    _file_handle = None

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the debug log file and start the worker thread"""
        self._log_queue = Queue()
        self._stop_event = threading.Event()

        # The default state is "disabled"
        self.is_file_logging_enabled = False
        self._file_handle = None

        # Start the worker thread
        self._worker_thread = threading.Thread(target=self._log_worker, daemon=True)
        self._worker_thread.start()

    def configure_file_logging(self, enable_logging: bool, log_file_path: str):
        """
        High-level code calls this *after* config is loaded
        to enable file logging.
        """
        if not enable_logging:
            self.is_file_logging_enabled = False
            return

        try:
            self._file_handle = open(log_file_path, "w", encoding="utf-8")
            self.is_file_logging_enabled = True
            self._write_line("--- Log Session Started ---")
        except Exception as e:
            # This is a fatal startup error, similar to config.
            print(
                f"⚠️ [DebugLogger] CRITICAL: Failed to open log file: {e}",
                file=sys.stderr,
            )
            raise ConfigurationError(
                message=f"Failed to open debug log file: {log_file_path}", root_cause=e
            )

    def _log_worker(self):
        """Worker thread that processes log messages from the queue and writes to file"""
        try:
            while not self._stop_event.is_set():
                try:
                    # Wait for a message with a timeout
                    message = self._log_queue.get(timeout=0.1)
                    # Write to file if file handle exists
                    if self._file_handle:
                        try:
                            self._file_handle.write(message + "\n")
                            self._file_handle.flush()
                        except Exception as e:
                            print(
                                f"[CRITICAL DEBUG_LOGGER ERROR] Failed to write to log: {e}",
                                file=sys.stderr,
                            )
                    self._log_queue.task_done()
                except Empty:
                    # Timeout occurred, continue checking stop event
                    continue

            # Flush any remaining messages in the queue
            while not self._log_queue.empty():
                try:
                    message = self._log_queue.get_nowait()
                    if self._file_handle:
                        try:
                            self._file_handle.write(message + "\n")
                            self._file_handle.flush()
                        except Exception as e:
                            print(
                                f"[CRITICAL DEBUG_LOGGER ERROR] Failed to flush log on exit: {e}",
                                file=sys.stderr,
                            )
                    self._log_queue.task_done()
                except Empty:
                    break
        except Exception:
            pass  # Don't break execution if worker fails

    def _write_line(self, text: str):
        """Write a line to stderr and/or queue based on config"""
        if not self.is_file_logging_enabled:
            return

        # Always add to queue if file logging is enabled
        if self.is_file_logging_enabled:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._log_queue.put(f"[{timestamp}] {text}")

    def _write_separator(self, char="=", length=80):
        """Write a separator line"""
        self._write_line(char * length)

    def log(self, title: str, content: str = None, separator: str = "="):
        """
        Log a debug message with optional content.

        Args:
            title: Title/header for this debug entry
            content: Optional detailed content to log
            separator: Character to use for separator lines ('=', '-', '*')
        """
        if not self.is_file_logging_enabled:
            return

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        self._write_line("")
        self._write_separator(separator)
        self._write_line(f"[{timestamp}] {title}")
        self._write_separator(separator)

        if content:
            self._write_line(content)
            self._write_separator(separator)

    def log_context(self, messages: list):
        """Log the full context being sent to the model"""
        if not self.is_file_logging_enabled:
            return

        self.log("CONTEXT WINDOW", separator="=")

        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            self._write_line(f"\n--- Message {i}: {role.upper()} ---")
            self._write_line(f"Length: {len(content)} chars")

            # Show full content for system messages (prompts), truncate user/assistant
            if role == "system":
                self._write_line(f"\n{content}")
            else:
                if len(content) > 500:
                    self._write_line(
                        f"\n{content[:250]}\n...[truncated]...\n{content[-250:]}"
                    )
                else:
                    self._write_line(f"\n{content}")

        self._write_separator("=")

    def log_response(self, response: str, tool_calls: list = None):
        """Log the model's response"""
        if not self.is_file_logging_enabled:
            return

        self.log("MODEL RESPONSE", separator="=")
        self._write_line(f"Response length: {len(response)} chars")
        self._write_line(f"\n{response}")

        if tool_calls:
            self._write_line(f"\n\nTool calls: {len(tool_calls)}")
            for i, call in enumerate(tool_calls):
                self._write_line(f"\nTool {i+1}:")
                import json

                self._write_line(json.dumps(call, indent=2))

        self._write_separator("=")

    def close(self):
        """Close the debug log file by stopping the worker thread"""
        if hasattr(self, "_stop_event"):
            self._stop_event.set()
            if hasattr(self, "_worker_thread"):
                self._worker_thread.join(timeout=5)  # Wait up to 5 seconds

        # Close file handle in main thread if still open
        if self._file_handle:
            try:
                self._write_separator()
                self._write_line(
                    f"Debug session ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                self._write_separator()
                self._file_handle.close()
            except Exception as e:
                print(
                    f"[CRITICAL DEBUG_LOGGER ERROR] Failed to close log handle: {e}",
                    file=sys.stderr,
                )
            finally:
                self._file_handle = None

    def __del__(self):
        """Cleanup on deletion"""
        self.close()


# Global singleton instance
_logger = DebugLogger()


# Convenience functions
def debug_log(title: str, content: str = None, separator: str = "="):
    """Log a debug message"""
    _logger.log(title, content, separator)


def debug_log_context(messages: list):
    """Log the context window"""
    _logger.log_context(messages)


def debug_log_response(response: str, tool_calls: list = None):
    """Log the model response"""
    _logger.log_response(response, tool_calls)


def close_debug_log():
    """Close the debug log"""
    _logger.close()
