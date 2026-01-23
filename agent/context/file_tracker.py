from typing import Dict, Set


class FileTracker:
    """
    Tracks which files are currently loaded in the context.
    Prevents the agent from re-reading the same file multiple times.

    --- ARCHITECTURE NOTE: THREAD SAFETY ---
    CURRENT STATE (Asyncio):
    - This class is currently SAFE because it is used in a single-threaded
      asyncio event loop and methods contain no `await` points.
    - Operations like dictionary assignment and deletion are atomic within
      the main thread.

    FUTURE WARNING (Multi-threading):
    - If this application is ever refactored to use standard threading
      (e.g., `concurrent.futures.ThreadPoolExecutor` accessing this shared state),
      THIS CLASS WILL BECOME UNSAFE.
    - FIX: Add `threading.Lock()` or `asyncio.Lock()` around `self._loaded_files`
      mutations if concurrent access is introduced.
    ----------------------------------------
    """

    def __init__(self):
        # Maps file_path -> message_id that contains it
        self._loaded_files: Dict[str, str] = {}

    def is_loaded(self, file_path: str) -> bool:
        return file_path in self._loaded_files

    def mark_loaded(self, file_path: str, message_id: str) -> None:
        self._loaded_files[file_path] = message_id

    def remove_file(self, file_path: str) -> None:
        if file_path in self._loaded_files:
            del self._loaded_files[file_path]

    def sync_with_history(self, active_message_ids: Set[str]) -> None:
        """
        Garbage collection: Remove files that belong to pruned messages.
        """
        # Create a list of keys to remove to avoid runtime modification errors
        to_remove = []
        for path, msg_id in self._loaded_files.items():
            if msg_id not in active_message_ids:
                to_remove.append(path)

        for path in to_remove:
            del self._loaded_files[path]
