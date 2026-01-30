import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor

class PlainInputHandler:
    """
    Handles reading from stdin without blocking the main asyncio event loop.
    """
    def __init__(self):
        # We keep a dedicated executor for input to ensure we don't starve other pools
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="StdinReader")

    async def get_input(self, prompt: str = "") -> str:
        """
        Asynchronously prompt the user and wait for a line of text.
        """
        # Print prompt without newline immediately
        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()

        loop = asyncio.get_running_loop()
        # run_in_executor(None, ...) usually uses the default loop executor.
        # Passing our own executor is safer for specific IO tasks.
        line = await loop.run_in_executor(self._executor, sys.stdin.readline)
        
        return line.strip()

    async def confirm(self, prompt: str) -> bool:
        """
        Simple y/n confirmation.
        """
        while True:
            response = await self.get_input(f"{prompt} [y/n]: ")
            clean = response.lower()
            if clean in ('y', 'yes'):
                return True
            if clean in ('n', 'no'):
                return False
            sys.stdout.write("Please enter 'y' or 'n'.\n")