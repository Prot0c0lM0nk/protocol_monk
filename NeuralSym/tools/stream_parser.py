import re
import logging
from pathlib import Path
from typing import List


class StreamOutputParser:
    def __init__(self, working_dir: Path = None):
        self.scratch_dir = working_dir / "scratch" if working_dir else Path("./scratch")
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

    def parse_and_save(self, text: str) -> List[str]:
        # Define Regex: r"\[FILE:\s*(.*?)\](.*?)\[/FILE\]" (DOTALL flag)
        pattern = re.compile(r"\[FILE:\s*(.*?)\](.*?)\[/FILE\]", re.DOTALL)
        matches = pattern.findall(text)

        results = []

        # For each match:
        for filename, content in matches:
            # Clean filename (remove whitespace/path traversal)
            clean_filename = filename.strip()
            # Basic protection against path traversal
            clean_filename = re.sub(r'[\\/:*?"<>|]', "_", clean_filename)

            # Write content to scratch_dir / filename
            file_path = self.scratch_dir / clean_filename
            with open(file_path, "w") as f:
                f.write(content)

            # Log the write
            logging.info(f"Wrote file: {file_path}")

            # Add filename to results list
            results.append(clean_filename)

        # Return list of written filenames
        return results
