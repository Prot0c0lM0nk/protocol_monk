#!/usr/bin/env python3
"""
Test runner for Textual UI
Basic smoke test to verify the structure works
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.textual.app import TextualUI


def main():
    """Run the Textual UI"""
    print("Starting Textual UI for Protocol Monk...")
    print("Press Ctrl+C to quit\n")

    app = TextualUI()
    app.run()


if __name__ == "__main__":
    main()